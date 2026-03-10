import os
os.environ["OMP_NUM_THREADS"] = "1"
import re
import ast
from pathlib import Path
import tiktoken
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import pickle
import logging
import threading
from synaptic_router import SynapticGrid

try:
    from tree_sitter import Language, Parser
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_typescript
    import tree_sitter_java
    import tree_sitter_cpp
    import tree_sitter_go
    import tree_sitter_rust
    import tree_sitter_ruby
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CodexMemory.ProjectMemory")

enc = tiktoken.get_encoding("cl100k_base")
model = SentenceTransformer('all-MiniLM-L6-v2')

# Supported file extensions for indexing (all major coding languages + configs)
SUPPORTED_EXTENSIONS = {
    # Python
    '.py', '.pyi', '.pyx',
    # JavaScript / TypeScript / Node.js
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    # Web
    '.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
    # C / C++ / C#
    '.c', '.h', '.cpp', '.hpp', '.cc', '.cs',
    # Java / Kotlin
    '.java', '.kt', '.kts',
    # Go / Rust / Swift
    '.go', '.rs', '.swift',
    # Ruby / PHP / Perl
    '.rb', '.php', '.pl', '.pm',
    # Shell / Scripts
    '.sh', '.bash', '.zsh', '.bat', '.cmd', '.ps1',
    # Config / Data
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.env', '.xml',
    # Documentation / Text
    '.md', '.txt', '.rst', '.csv',
    # Build / Package
    '.gradle', '.cmake', '.makefile', '.dockerfile',
    # SQL
    '.sql',
    # Lua / R / Dart
    '.lua', '.r', '.dart',
    # GraphQL / Proto
    '.graphql', '.gql', '.proto',
}
# Directories to always exclude from scanning
EXCLUDED_DIRS = {'.venv', 'venv', 'node_modules', 'artifacts', '.codexmemory', '__pycache__', '.git', '.agents', '.vscode'}

class ProjectMemory:
    """
    100x Production-Grade Vectorized Project Memory.
    
    Capabilities:
    - Semantic chunking with MiniLM embeddings + FAISS index
    - Full file content storage for instant retrieval (no filesystem I/O needed)
    - Import/dependency graph for cross-file relationship understanding
    - Code structure index (classes, functions, signatures) per file
    
    Artifacts produced:
    - project_index.faiss    → FAISS vector index for semantic search
    - project_metadata.pkl   → Chunk-level metadata (paths, tokens, content)
    - project_files.pkl      → Full file contents keyed by relative path
    - project_deps.pkl       → Import/dependency graph per file
    - project_structure.pkl  → Code structure (classes, functions) per file
    """
    def __init__(self, root_dir=None):
        if root_dir is None:
            # 100x Dynamic Workspace Resolution:
            # 1. Check environment variable (set by IDE or install script)
            root_dir = os.environ.get('CODEX_PROJECT_ROOT', None)
            if root_dir is None:
                # 2. Smart walk-up: find the closest ancestor with a project root marker
                root_dir = self._detect_project_root(Path.cwd())
        self.root_dir = Path(root_dir).resolve()
        self.index = None
        self.metadata = []
        self.file_contents = {}      # path → full file content string (deleted before save)
        self.dependency_graph = {}   # path → {imports: [], imported_by: []}
        self.code_structure = {}     # path → {classes: [], functions: [], summary: str}
        self.lock = threading.RLock()  # Reentrant: safe for CRR wrapper + direct calls
        self.sparse_index = None  # Live shared IncrementalBM25 — mutated by update_file, read by CRR search
        
        # Synaptic Grid Integration — stored in hidden .codexmemory folder
        self.grid = SynapticGrid(str(self.root_dir))
        
        self._ts_parsers = {}        # ext → cached Parser instance (Fix #3)
        if HAS_TREE_SITTER:
            self._ts_parsers = {
                '.py': Parser(Language(tree_sitter_python.language())),
                '.pyi': Parser(Language(tree_sitter_python.language())),
                '.js': Parser(Language(tree_sitter_javascript.language())),
                '.jsx': Parser(Language(tree_sitter_javascript.language())),
                '.ts': Parser(Language(tree_sitter_typescript.language_typescript())),
                '.tsx': Parser(Language(tree_sitter_typescript.language_tsx())),
                '.java': Parser(Language(tree_sitter_java.language())),
                '.c': Parser(Language(tree_sitter_cpp.language())),
                '.cpp': Parser(Language(tree_sitter_cpp.language())),
                '.h': Parser(Language(tree_sitter_cpp.language())),
                '.hpp': Parser(Language(tree_sitter_cpp.language())),
                '.go': Parser(Language(tree_sitter_go.language())),
                '.rs': Parser(Language(tree_sitter_rust.language())),
                '.rb': Parser(Language(tree_sitter_ruby.language())),
            }

    @staticmethod
    def _detect_project_root(start_path: Path) -> Path:
        """
        100x Smart Project Root Detection.
        Walks up from start_path to find the closest ancestor containing
        a project root marker (.git, requirements.txt, package.json, etc).
        Falls back to start_path if no marker is found.
        """
        ROOT_MARKERS = {
            '.git', 'requirements.txt', 'package.json', 'setup.py',
            'pyproject.toml', 'Cargo.toml', 'go.mod', 'Gemfile',
            'pom.xml', 'build.gradle',
        }
        current = start_path.resolve()
        while current != current.parent:  # Stop at filesystem root
            if any((current / marker).exists() for marker in ROOT_MARKERS):
                return current
            current = current.parent
        # Last resort: return the original path
        return start_path

    def build(self):
        """
        Codex Holographic Slicing (CHS) — 100x Production Build.
        1. Scan project files => Full contents
        2. Extract Code Structure (Classes, Functions)
        3. Extract Dependency Graph
        4. CHS Semantic Chunking with Holograms
        5. Embeddings (MiniLM)
        6. FAISS Vector Save
        """
        with self.lock:
            docs = []
            self.metadata = []
            self.file_contents = {}
            self.dependency_graph = {}
            self.code_structure = {}

        import sys
        print("=" * 60, file=sys.stderr)
        print("  100x CodexMemory — CHS Holographic Build", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # --- Phase 1: Load Full Contents ---
        print("    Phase 1: Scanning project files...", file=sys.stderr)
        all_files = []
        for root, dirs, files in os.walk(self.root_dir, followlinks=False):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not (Path(root) / d).is_symlink()]
            root_path = Path(root)
            for file_name in files:
                file_path = root_path / file_name
                if file_path.is_symlink():
                    continue
                if file_path.is_file() and file_path.suffix in SUPPORTED_EXTENSIONS:
                    all_files.append(file_path)

        print(f"    Found {len(all_files)} indexable files.", file=sys.stderr)
        for file in all_files:
            try:
                content = file.read_bytes().decode('utf-8', errors='replace')  # Binary decode preserves \r\n for exact byte offsets
                relative_path = str(file.relative_to(self.root_dir))
                self.file_contents[relative_path] = content
            except Exception as e:
                print(f"    ⚠ Skipped {file.name}: {e}", file=sys.stderr)

        # --- Phase 2: Extract Code Structure ---
        # We MUST do this BEFORE chunking so CHS can use the spatial map
        print("    Phase 2: Extracting Code Structure for Spatial Mapping...", file=sys.stderr)
        self._build_code_structure()
        total_symbols = sum(
            len(v.get('classes', [])) + len(v.get('functions', []))
            for v in self.code_structure.values()
        )
        print(f"    Extracted {total_symbols} symbols from {len(self.code_structure)} source files", file=sys.stderr)

        # --- Phase 3: Dependencies ---
        print("    Phase 3: Building Dependency Graph...", file=sys.stderr)
        self._build_dependency_graph()
        dep_edges = sum(len(v.get('imports', [])) for v in self.dependency_graph.values())
        print(f"    Mapped {dep_edges} import relationships across {len(self.dependency_graph)} files", file=sys.stderr)

        # --- Phase 4: CRS Chunking ---
        print("    Phase 4: Executing Codex Resonance Slicing (CRS)...", file=sys.stderr)
        CHUNK_SIZE = 250
        
        crs_chunk_count = 0
        fallback_chunk_count = 0

        for rel_path, content in self.file_contents.items():
            tokens = enc.encode(content)
            if len(tokens) < 50:
                continue

            # Universal CRS Chunker
            chunks = self._build_crs_chunks(rel_path, content, CHUNK_SIZE)
            
            # If CRS yielded nothing (e.g. dense minified single-line file)
            if not chunks:
                chunks = self._fixed_window_chunk_with_offsets(tokens, content, CHUNK_SIZE, 50)
                fallback_chunk_count += len(chunks)
            else:
                crs_chunk_count += len(chunks)

            for chunk_id, chunk_data in enumerate(chunks):
                chunk_text = chunk_data.get("header", "") + chunk_data["text"]
                estimated_tokens = max(1, len(chunk_text) // 4)
                docs.append(chunk_text)
                
                node_id = self.grid.write_node(
                    parent_id=0,
                    rel_path=rel_path,
                    node_type=chunk_data.get("type", "global"),
                    byte_start=chunk_data.get("byte_start", 0),
                    byte_end=chunk_data.get("byte_end", 0),
                    vector_id=len(docs) - 1
                )

                self.metadata.append({
                    "path": rel_path,
                    "chunk_id": chunk_id,
                    "tokens": estimated_tokens,
                    "node_id": node_id,
                    "header": chunk_data.get("header", "")
                })

        if not docs:
            print("    ❌ No files found to index!", file=sys.stderr)
            return

        total_tokens = sum(m['tokens'] for m in self.metadata)
        print(f"    CRS Generated {crs_chunk_count} Resonance Splices | {fallback_chunk_count} fallback chunks", file=sys.stderr)
        print(f"    Total tokens prepared for LLM: {total_tokens:,}", file=sys.stderr)

        # --- Phase 5: Generate embeddings ---
        print("    Phase 5: Generating MiniLM Semantic Vectors...", file=sys.stderr)
        
        batch_size = 128
        all_embeddings = []
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            batch_emb = model.encode(batch, show_progress_bar=True if len(docs) > 1000 and i == 0 else False)
            all_embeddings.append(batch_emb)
            
        embeddings = np.vstack(all_embeddings) if all_embeddings else np.array([])
        d = embeddings.shape[1] if len(embeddings) > 0 else 384
        
        self.index = faiss.IndexFlatL2(d)
        if len(embeddings) > 0:
            self.index.add(embeddings.astype("float32"))

        # --- Phase 6: Save all artifacts ---
        print("    Phase 6: Saving CRS Artifacts...", file=sys.stderr)
        artifacts_dir = self.root_dir / ".codexmemory"
        os.makedirs(artifacts_dir, exist_ok=True)

        faiss.write_index(self.index, str(artifacts_dir / "project_index.faiss"))
        with open(artifacts_dir / "project_metadata.pkl", "wb") as f:
            pickle.dump(self.metadata, f)
            
        # Initialize IncrementalBM25
        import re
        from project_search import IncrementalBM25
        def _code_tokenize(text: str) -> list[str]:
            if not text: return []
            tokens = []
            raw_words = re.findall(r'[a-zA-Z0-9]+', text)
            for word in raw_words:
                tokens.append(word.lower())
                if '_' in word:
                    tokens.extend([sw.lower() for sw in word.split('_') if sw])
                camel_splits = re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', word)).split()
                if len(camel_splits) > 1:
                    tokens.extend([cs.lower() for cs in camel_splits if cs])
            return list(dict.fromkeys(tokens))
            
        sparse_index = IncrementalBM25()
        tokenized_corpus = [_code_tokenize(doc) for doc in docs]
        if tokenized_corpus:
            sparse_index.add_documents(tokenized_corpus)
            
        bm25_path = artifacts_dir / "project_bm25.pkl"
        with open(bm25_path, "wb") as f:
            pickle.dump(sparse_index, f)
            
        with open(artifacts_dir / "project_deps.pkl", "wb") as f:
            pickle.dump(self.dependency_graph, f)
        with open(artifacts_dir / "project_structure.pkl", "wb") as f:
            pickle.dump(self.code_structure, f)

        self.grid._save_registry()
        self.file_contents = {} # RAM bloated string cache dropped

        for artifact_name in ["project_index.faiss", "project_metadata.pkl", 
                              "project_deps.pkl", "project_structure.pkl"]:
            size_kb = os.path.getsize(artifacts_dir / artifact_name) / 1024
            print(f"      → {artifact_name}: {size_kb:.1f} KB", file=sys.stderr)

        print(f"    ✅ CRS Production build complete: {len(docs)} chunks from {len(self.file_contents)} files indexed", file=sys.stderr)

    def update_file(self, rel_path: str):
        """
        Surgically updates the AST and FAISS vectors for a single file.
        Provides robust locking for async thread safety.
        """
        with self.lock:
            try:
                full_path = self.root_dir / rel_path
                
                # Evict stale mmap for this file so the LRU cache doesn't serve old data
                from synaptic_router import HolographicCanvas
                HolographicCanvas.invalidate_cache(full_path)
                
                # Zero-shifting Vector Mapping: 
                # Instead of rebuilding the whole index or shifting indices, mark old vectors as deleted
                for m in self.metadata:
                    if m.get('path') == rel_path:
                        m['deleted'] = True
                        
                if not full_path.exists():
                    return
                content = full_path.read_bytes().decode('utf-8', errors='replace')  # Binary decode preserves \r\n for exact byte offsets
                
                ext = full_path.suffix
                if HAS_TREE_SITTER and self._get_ts_parser(ext):
                    self.code_structure[rel_path] = self._extract_ts_structure(content, ext)
                elif ext in {'.py', '.pyi', '.pyx'}:
                    self.code_structure[rel_path] = self._extract_python_structure(content, rel_path)
                elif ext in self._BRACED_STRUCTURE_EXTS:
                    self.code_structure[rel_path] = self._extract_braced_structure(content)
                elif ext in self._RUBY_EXTS:
                    self.code_structure[rel_path] = self._extract_ruby_structure(content)
                    
                tokens = enc.encode(content)
                if len(tokens) >= 50:
                    self.file_contents[rel_path] = content
                    
                    # --- 100x Live Delta Graph Update ---
                    # 1. Temporarily rebuild routing tables for resolution
                    project_files = {}
                    project_modules = {}
                    for m in self.metadata:
                        p = m.get('path')
                        if not p or m.get('deleted'): continue
                        stem = Path(p).stem
                        project_files[stem] = p
                        project_files[Path(p).name] = p
                        no_ext = p.rsplit('.', 1)[0] if '.' in p else p
                        project_files[no_ext] = p
                        project_files[no_ext.replace('\\', '/')] = p
                        if p.endswith('.py'):
                            module_path = p.replace(os.sep, '.').replace('/', '.').removesuffix('.py')
                            project_modules[module_path] = p
                            parts = module_path.split('.')
                            for i in range(len(parts)):
                                partial = '.'.join(parts[i:])
                                if partial not in project_modules:
                                    project_modules[partial] = p
                    
                    # Also include the current file being updated
                    p = rel_path
                    stem = Path(p).stem
                    project_files[stem] = p
                    project_files[Path(p).name] = p
                    no_ext = p.rsplit('.', 1)[0] if '.' in p else p
                    project_files[no_ext] = p
                    project_files[no_ext.replace('\\', '/')] = p
                    if p.endswith('.py'):
                        module_path = p.replace(os.sep, '.').replace('/', '.').removesuffix('.py')
                        project_modules[module_path] = p
                        parts = module_path.split('.')
                        for i in range(len(parts)):
                            partial = '.'.join(parts[i:])
                            if partial not in project_modules:
                                project_modules[partial] = p

                    # 2. Extract new imports
                    new_imports = self._extract_imports(rel_path, content, project_files, project_modules)

                    # 3. Clean old dependencies
                    old_deps = self.dependency_graph.get(rel_path, {}).get("imports", [])
                    for old_import in old_deps:
                        if old_import in self.dependency_graph:
                            if rel_path in self.dependency_graph[old_import]["imported_by"]:
                                self.dependency_graph[old_import]["imported_by"].remove(rel_path)

                    # 4. Update the graph for this file
                    self.dependency_graph[rel_path] = {
                        "imports": new_imports,
                        "imported_by": self.dependency_graph.get(rel_path, {}).get("imported_by", [])
                    }

                    # 5. Connect new dependencies
                    for new_import in new_imports:
                        if new_import not in self.dependency_graph:
                            self.dependency_graph[new_import] = {"imports": [], "imported_by": []}
                        if rel_path not in self.dependency_graph[new_import]["imported_by"]:
                            self.dependency_graph[new_import]["imported_by"].append(rel_path)

                    chunks = self._build_crs_chunks(rel_path, content, 250)
                    if not chunks:
                        chunks = self._fixed_window_chunk_with_offsets(tokens, content, 250, 50)
                else:
                    chunks = []
                
                docs = []
                for chunk_id, chunk_data in enumerate(chunks):
                    chunk_text = chunk_data.get("header", "") + chunk_data["text"]
                    estimated_tokens = max(1, len(chunk_text) // 4)
                    docs.append(chunk_text)
                    
                    vector_id = self.index.ntotal + len(docs) - 1 if self.index else 0
                    
                    node_id = self.grid.write_node(
                        parent_id=0,
                        rel_path=rel_path,
                        node_type=chunk_data.get("type", "global"),
                        byte_start=chunk_data.get("byte_start", 0),
                        byte_end=chunk_data.get("byte_end", 0),
                        vector_id=vector_id
                    )

                    self.metadata.append({
                        "path": rel_path,
                        "chunk_id": chunk_id,
                        "tokens": estimated_tokens,
                        "node_id": node_id,
                        "header": chunk_data.get("header", "")
                    })
                    
                if docs and self.index:
                    batch_size = 128
                    all_embeddings = []
                    for i in range(0, len(docs), batch_size):
                        batch = docs[i : i + batch_size]
                        batch_emb = model.encode(batch, show_progress_bar=False)
                        all_embeddings.append(batch_emb)
                    embeddings = np.vstack(all_embeddings)
                    self.index.add(embeddings.astype("float32"))
                    
                if rel_path in self.file_contents:
                    del self.file_contents[rel_path]
                    
                # 100x Live BM25 Sync — mutate the shared RAM instance directly
                if self.sparse_index is not None and hasattr(self.sparse_index, 'remove_document'):
                    import re
                    def _code_tokenize(text: str) -> list[str]:
                        if not text: return []
                        tokens = []
                        raw_words = re.findall(r'[a-zA-Z0-9]+', text)
                        for word in raw_words:
                            tokens.append(word.lower())
                            if '_' in word:
                                tokens.extend([sw.lower() for sw in word.split('_') if sw])
                            camel_splits = re.sub('([A-Z][a-z]+)', r' \\1', re.sub('([A-Z]+)', r' \\1', word)).split()
                            if len(camel_splits) > 1:
                                tokens.extend([cs.lower() for cs in camel_splits if cs])
                        return list(dict.fromkeys(tokens))
                        
                    # Phase 1: Remove old vectors from BM25 (mark emptied, not deleted, to keep alignment)
                    for i, m in enumerate(self.metadata):
                        if m.get('path') == rel_path and m.get('deleted'):
                            self.sparse_index.remove_document(i)
                            
                    # Phase 2: Add new vectors to BM25
                    new_docs = [_code_tokenize(chunk_text) for chunk_text in docs]
                    if new_docs:
                        self.sparse_index.add_documents(new_docs)
                
                import sys
                print(f"    [ProjectMemory] Surgically updated FAISS & Grid for {rel_path}.", file=sys.stderr)
                
                # --- FAISS / BM25 Garbage Collection Threshold Check ---
                deleted_count = sum(1 for m in self.metadata if m.get('deleted'))
                if deleted_count > 50 or (len(self.metadata) > 0 and deleted_count / len(self.metadata) > 0.2):
                    self._compact_memory()
                
            except Exception as e:
                import sys
                print(f"    [ProjectMemory] Error updating {rel_path}: {e}", file=sys.stderr)

    def _compact_memory(self):
        """
        Garbage collector for dead vectors. Rebuilds FAISS, Metadata, and BM25 
        to strip out deleted chunks, preventing infinite disk/RAM bloat.
        """
        import sys
        print("\n    [ProjectMemory] 🧹 Triggering Garbage Collection (Compacting Index)...", file=sys.stderr)
        
        old_len = len(self.metadata)
        alive_metadata = []
        alive_indices = []
        
        for i, m in enumerate(self.metadata):
            if not m.get('deleted'):
                alive_metadata.append(m)
                alive_indices.append(i)
                
        if len(alive_metadata) == old_len:
            return # Nothing to compact
            
        import faiss
        import numpy as np
        
        # 1. Compact FAISS Vector Index
        if self.index:
            d = self.index.d
            new_index = faiss.IndexFlatL2(d)
            vectors_to_keep = []
            for i in alive_indices:
                try:
                    vec = self.index.reconstruct(i)
                    vectors_to_keep.append(vec)
                except Exception:
                    pass
            if vectors_to_keep:
                new_index.add(np.array(vectors_to_keep).astype("float32"))
            self.index = new_index
            
        self.metadata = alive_metadata
        
        artifacts_dir = self.root_dir / ".codexmemory"
        
        # 2. Compact BM25 Array Alignments
        bm25_path = artifacts_dir / "project_bm25.pkl"
        if bm25_path.exists():
            try:
                import pickle
                with open(bm25_path, "rb") as f:
                    sparse_index = pickle.load(f)
                if hasattr(sparse_index, 'doc_freqs'):
                    # Strip out dead docs from the parallel lists
                    sparse_index.doc_freqs = [sparse_index.doc_freqs[i] for i in alive_indices]
                    sparse_index.doc_len = [sparse_index.doc_len[i] for i in alive_indices]
                    with open(bm25_path, "wb") as f:
                        pickle.dump(sparse_index, f)
            except Exception as e:
                print(f"    [ProjectMemory] Error compacting BM25: {e}", file=sys.stderr)
                
        # 3. Compact the SynapticGrid binary file (purge zombie nodes from disk)
        if hasattr(self, 'grid') and self.grid:
            active_node_ids = [m['node_id'] for m in self.metadata if 'node_id' in m]
            if active_node_ids:
                id_map = self.grid.compact(active_node_ids)
                # Reconcile metadata node_ids with the new sequential IDs
                for m in self.metadata:
                    old_id = m.get('node_id')
                    if old_id is not None and old_id in id_map:
                        m['node_id'] = id_map[old_id]
                        
        # 4. Flush Artifacts to Disk
        if self.index:
            faiss.write_index(self.index, str(artifacts_dir / "project_index.faiss"))
        with open(artifacts_dir / "project_metadata.pkl", "wb") as f:
            import pickle
            pickle.dump(self.metadata, f)
            
        print(f"    [ProjectMemory] 🧹 GC Complete: Purged {old_len - len(self.metadata)} dead vectors.", file=sys.stderr)

    def flush_to_disk(self):
        """
        100x I/O Batch Flusher.
        Called by the NervousSystem after a batch of files has been processed in RAM.
        Prevents the SSD from thrashing during mass-edits (like git branch switches).
        """
        with self.lock:
            try:
                import sys
                artifacts_dir = self.root_dir / ".codexmemory"
                os.makedirs(artifacts_dir, exist_ok=True)

                # 1. Flush FAISS Vectors
                if self.index:
                    faiss.write_index(self.index, str(artifacts_dir / "project_index.faiss"))
                
                # 2. Flush Python Metadata & Graph State
                with open(artifacts_dir / "project_metadata.pkl", "wb") as f:
                    import pickle
                    pickle.dump(self.metadata, f)
                with open(artifacts_dir / "project_structure.pkl", "wb") as f:
                    import pickle
                    pickle.dump(self.code_structure, f)
                with open(artifacts_dir / "project_deps.pkl", "wb") as f:
                    import pickle
                    pickle.dump(self.dependency_graph, f)
                    
                # 3. Flush Sparse BM25 State
                if self.sparse_index is not None:
                    bm25_path = artifacts_dir / "project_bm25.pkl"
                    with open(bm25_path, "wb") as f:
                        import pickle
                        pickle.dump(self.sparse_index, f)
                        
                # 4. Flush Synaptic Grid Registry
                if hasattr(self, 'grid') and self.grid:
                    self.grid._save_registry()

                print("[ProjectMemory] 💾 I/O Flush Complete: RAM state safely committed to disk.", file=sys.stderr)
            except Exception as e:
                import sys
                print(f"[ProjectMemory] ❌ Critical Error during I/O Flush: {e}", file=sys.stderr)

    def close(self):
        """Gracefully shutdown mmap grid to prevent file descriptor leaks."""
        if hasattr(self, 'grid') and self.grid:
            self.grid.close()
            
    def __del__(self):
        if hasattr(self, 'lock'):
            self.close()

    def _fixed_window_chunk_with_offsets(self, tokens: list, content: str, chunk_size: int, overlap: int) -> list[dict]:
        chunks = []
        i = 0
        token_count = len(tokens)
        step = max(1, chunk_size - overlap)
        content_bytes_len = len(content.encode('utf-8'))

        while i < token_count:
            chunk_tokens = tokens[i : i + chunk_size]
            chunk_text = enc.decode(chunk_tokens)
            chunks.append({
                "header": "",
                "text": chunk_text,
                "byte_start": 0,
                "byte_end": content_bytes_len,
                "type": "fallback"
            })
            i += step

        return chunks

    def _fixed_window_chunk(self, tokens: list, chunk_size: int, overlap: int) -> list[str]:
        """
        Fixed-window chunking with configurable overlap.
        Used for non-Python files where no AST structure is available.
        
        Args:
            tokens: Pre-tokenized content (from tiktoken)
            chunk_size: Max tokens per chunk (250 for MiniLM)
            overlap: Number of overlapping tokens between adjacent chunks
        
        Returns:
            List of chunk text strings
        """
        chunks = []
        i = 0
        token_count = len(tokens)
        step = max(1, chunk_size - overlap)  # Ensure we always move forward

        while i < token_count:
            chunk_tokens = tokens[i : i + chunk_size]
            chunk_text = enc.decode(chunk_tokens)
            chunks.append(chunk_text)
            i += step

        return chunks

    def _build_crs_chunks(self, rel_path: str, content: str, max_tokens: int) -> list[dict]:
        """
        Codex Resonance Slicing (CRS) Core.
        Extracts exact structural anchors and inlines cross-file dependency signatures.
        """
        chunks = []
        lines = content.split('\n')
        
        line_offsets = []
        curr = 0
        for line in lines:
            line_offsets.append(curr)
            curr += len(line.encode('utf-8')) + 1 # +1 for \n

        def get_byte_range(start_line_idx, end_line_idx):
            start_byte = line_offsets[start_line_idx]
            if end_line_idx < len(lines):
                end_byte = line_offsets[end_line_idx] + len(lines[end_line_idx].encode('utf-8'))
            else:
                end_byte = curr
            return start_byte, end_byte

        # 1. Reference code structure to determine spatial scope (Anchors)
        struct = self.code_structure.get(rel_path, {})
        classes = struct.get('classes', [])
        functions = struct.get('functions', [])

        # Build a linear timeline of nodes based on their line numbers
        nodes = []
        for cls in classes:
            nodes.append({"type": "class", "name": cls['name'], "start": cls['line'], "end": cls['end_line'], "calls": cls.get('calls', [])})
            for method in cls.get('methods', []):
                nodes.append({"type": "method", "name": f"{cls['name']}.{method['name']}", "start": method['line'], "end": method['end_line'], "calls": method.get('calls', [])})
                
        for func in functions:
            nodes.append({"type": "function", "name": func['name'], "start": func['line'], "end": func['end_line'], "calls": func.get('calls', [])})

        # Helper to generate Holographic Splices
        def build_and_push_splice(scope_name: str, scope_type: str, block_lines: list, calls: set, byte_start: int, byte_end: int):
            if not block_lines:
                return
            
            # Build CRS Header
            header_lines = [f"#[CRS-Anchor: {Path(rel_path).name}::{scope_name}]"]
            
            # Resonance Threading: Resolve called functions
            resolved_deps = []
            injected_context = []
            
            if calls:
                # Fix #1: Only search same file + actually imported files
                valid_import_paths = self.dependency_graph.get(rel_path, {}).get("imports", [])
                search_scope = {rel_path} | set(valid_import_paths)
                
                for c_name in calls:
                    found = False
                    for f_path in search_scope:
                        f_struct = self.code_structure.get(f_path, {})
                        for glob_func in f_struct.get('functions', []):
                            if glob_func['name'] == c_name:
                                resolved_deps.append(f"{Path(f_path).name}::{c_name}")
                                args = glob_func.get('args', '')
                                sig = f"def {c_name}({args}):"
                                doc = glob_func.get('docstring', '')
                                inj = f"# [Injected Context from {Path(f_path).name}]\n# {sig}"
                                if doc:
                                    inj += f"\n# \"\"\"{doc.split(chr(10))[0]}...\"\"\"" # truncated doc
                                injected_context.append(inj)
                                found = True
                                break
                        # Also check methods inside classes
                        if not found:
                            for cls in f_struct.get('classes', []):
                                for method in cls.get('methods', []):
                                    if method['name'] == c_name:
                                        resolved_deps.append(f"{Path(f_path).name}::{cls['name']}.{c_name}")
                                        args = method.get('args', '')
                                        sig = f"def {c_name}({args}):"
                                        doc = method.get('docstring', '')
                                        inj = f"# [Injected Context from {Path(f_path).name}::{cls['name']}]\n# {sig}"
                                        if doc:
                                            inj += f"\n# \"\"\"{doc.split(chr(10))[0]}...\"\"\"" # truncated doc
                                        injected_context.append(inj)
                                        found = True
                                        break
                                if found:
                                    break
                        if found:
                            break
            
            if resolved_deps:
                header_lines.append(f"#[CRS-Resonance-Dependencies: {', '.join(resolved_deps)}]")
            
            header_text = '\n'.join(header_lines) + '\n\n'
            
            if injected_context:
                header_text += '\n\n'.join(injected_context) + '\n\n'
                
            block_text = '\n'.join(block_lines)
            splice_tokens = enc.encode(header_text + block_text)
            
            if len(splice_tokens) <= max_tokens:
                chunks.append({
                    "header": header_text,
                    "text": block_text,
                    "byte_start": byte_start,
                    "byte_end": byte_end,
                    "type": scope_type
                })
            else:
                # Dynamic Token Budget: prevent header from stealing all the embedding capacity
                header_tokens = len(enc.encode(header_text))
                remaining_tokens = max(50, max_tokens - header_tokens)
                
                # If the header is hogging > 80% of the budget, aggressively truncate it
                if remaining_tokens < 50:
                    header_text = header_lines[0] + '\n\n'  # Keep only the CRS-Anchor line
                    header_tokens = len(enc.encode(header_text))
                    remaining_tokens = max(50, max_tokens - header_tokens)
                
                block_tokenized = enc.encode(block_text)
                sub_chunks = self._fixed_window_chunk(block_tokenized, remaining_tokens, overlap=50)
                for sc in sub_chunks:
                    chunks.append({
                        "header": header_text,
                        "text": sc,
                        "byte_start": byte_start,
                        "byte_end": byte_end,
                        "type": scope_type
                    })

        # 2. Extract AST logic segments precisely without double-counting overlapping lines
        # Precompute the deepest node for each line to eliminate O(N^2) complexity leak
        line_to_node = [None] * len(lines)
        # Sort by length descending, so smaller nodes overwrite larger ones, leaving the "deepest" node
        sorted_nodes = sorted(nodes, key=lambda n: n['end'] - n['start'], reverse=True)
        for n in sorted_nodes:
            start_idx = max(0, n['start'] - 1)
            end_idx = min(len(lines) - 1, n['end'] - 1)
            for i in range(start_idx, end_idx + 1):
                line_to_node[i] = n

        current_idx = 0
        while current_idx < len(lines):
            node = line_to_node[current_idx]
            start_idx = current_idx
            
            block_lines = []
            while current_idx < len(lines) and line_to_node[current_idx] == node:
                block_lines.append(lines[current_idx])
                current_idx += 1
                
            block_text = '\n'.join(block_lines).strip()
            if block_text:
                scope_name = node['name'] if node else "Global"
                scope_type = node['type'] if node else "global"
                calls = set(node['calls']) if node and 'calls' in node else set()
                byte_start, byte_end = get_byte_range(start_idx, current_idx - 1)
                build_and_push_splice(scope_name, scope_type, block_lines, calls, byte_start, byte_end)

        return chunks

    def _extract_imports(self, rel_path: str, content: str, project_files: dict, project_modules: dict) -> list[str]:
        """
        Extracts imports from a single file's string content.
        Fully isolated from self.file_contents to support live delta updates.
        """
        ext = Path(rel_path).suffix
        imports = []

        def _resolve_import(import_str: str, current_path: str) -> str | None:
            """Try to resolve an import string to a project file path."""
            import_str = import_str.strip().strip("'").strip('"').strip()
            clean = import_str.lstrip('./').lstrip('../')
            for candidate in [clean, clean.replace('.', '/'), clean.replace('.', '\\')]:
                if candidate in project_files and project_files[candidate] != current_path:
                    return project_files[candidate]
            stem = Path(clean).stem if '/' in clean or '\\' in clean else clean
            if stem in project_files and project_files[stem] != current_path:
                return project_files[stem]
            return None

        # --- Python ---
        if ext in {'.py', '.pyi', '.pyx'}:
            try:
                tree = ast.parse(content, filename=rel_path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            resolved = project_modules.get(alias.name)
                            if resolved and resolved != rel_path:
                                imports.append(resolved)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            resolved = project_modules.get(node.module)
                            if resolved and resolved != rel_path:
                                imports.append(resolved)
            except SyntaxError:
                for line in content.split('\n'):
                    line = line.strip()
                    match = re.match(r'^(?:from\s+(\S+)\s+import|import\s+(\S+))', line)
                    if match:
                        module_name = match.group(1) or match.group(2)
                        resolved = project_modules.get(module_name)
                        if resolved and resolved != rel_path:
                            imports.append(resolved)

        # --- JS/TS/JSX/TSX ---
        elif ext in {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'}:
            for line in content.split('\n'):
                line = line.strip()
                match = re.match(r"^import\s+.*?from\s+['\"]([^'\"]+)['\"].*$", line)
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)
                    continue
                match = re.search(r"require\(['\"]([^'\"]+)['\"]\)", line)
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)

        # --- Java ---
        elif ext == '.java':
            for line in content.split('\n'):
                match = re.match(r'^import\s+(?:static\s+)?([\w.]+);', line.strip())
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)

        # --- Go ---
        elif ext == '.go':
            for line in content.split('\n'):
                match = re.match(r'^\s*"([^"]+)"', line.strip())
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)

        # --- Rust ---
        elif ext == '.rs':
            for line in content.split('\n'):
                match = re.match(r'^\s*(?:use|mod)\s+([\w:]+)', line.strip())
                if match:
                    resolved = _resolve_import(match.group(1).replace('::', '.'), rel_path)
                    if resolved:
                        imports.append(resolved)

        # --- Ruby ---
        elif ext == '.rb':
            for line in content.split('\n'):
                match = re.match(r"^\s*require(?:_relative)?\s+['\"]([^'\"]+)['\"].*$", line.strip())
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)

        # --- C/C++ ---
        elif ext in {'.c', '.h', '.cpp', '.hpp', '.cc', '.cs'}:
            for line in content.split('\n'):
                match = re.match(r'^\s*#include\s+["<]([^"<>]+)[">]', line.strip())
                if match:
                    resolved = _resolve_import(match.group(1), rel_path)
                    if resolved:
                        imports.append(resolved)

        return list(dict.fromkeys(imports))
    def _build_dependency_graph(self):
        """
        Parses ALL source files for import statements and builds a bidirectional
        dependency graph: who imports whom, and who is imported by whom.
        Fix #2: Now supports Python, JS/TS, Java, Go, Rust, Ruby, C/C++.
        """
        # First pass: collect all project file paths for resolution
        # Maps filename stems and relative paths to their canonical rel_path
        project_files = {}  # basename → rel_path
        project_modules = {}  # dotted module path → rel_path (Python-specific)
        
        for rel_path in self.file_contents:
            ext = Path(rel_path).suffix
            stem = Path(rel_path).stem
            
            # Store by filename (without extension) for cross-language resolution
            project_files[stem] = rel_path
            project_files[Path(rel_path).name] = rel_path
            # Store by relative path (for JS/TS relative imports like './utils')
            # Strip extension for fuzzy matching
            no_ext = rel_path.rsplit('.', 1)[0] if '.' in rel_path else rel_path
            project_files[no_ext] = rel_path
            project_files[no_ext.replace('\\', '/')] = rel_path
            
            if rel_path.endswith('.py'):
                # Python dotted module resolution
                module_path = rel_path.replace(os.sep, '.').replace('/', '.').removesuffix('.py')
                project_modules[module_path] = rel_path
                parts = module_path.split('.')
                for i in range(len(parts)):
                    partial = '.'.join(parts[i:])
                    if partial not in project_modules:
                        project_modules[partial] = rel_path

        # Second pass: parse imports from each file using the isolated extractor
        for rel_path, content in self.file_contents.items():
            imports = self._extract_imports(rel_path, content, project_files, project_modules)
            self.dependency_graph[rel_path] = {
                "imports": imports,
                "imported_by": []
            }

        # Reverse pass: populate imported_by
        for file_path, deps in self.dependency_graph.items():
            for imported_file in deps["imports"]:
                if imported_file in self.dependency_graph:
                    if file_path not in self.dependency_graph[imported_file]["imported_by"]:
                        self.dependency_graph[imported_file]["imported_by"].append(file_path)

    # File extensions that support regex-based structure extraction
    _BRACED_STRUCTURE_EXTS = {
        '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
        '.c', '.h', '.cpp', '.hpp', '.cc', '.cs',
        '.java', '.kt', '.kts',
        '.go', '.rs', '.swift', '.dart',
        '.php', '.lua',
    }
    _RUBY_EXTS = {'.rb'}

    def _get_ts_parser(self, ext: str):
        """Fix #3: Returns a cached Parser instance — zero re-instantiation overhead."""
        return self._ts_parsers.get(ext)

    def _extract_ts_structure(self, content: str, ext: str) -> dict:
        """Universal AST-based structure extraction using Tree-sitter."""
        structure = {"classes": [], "functions": [], "summary": ""}
        parser = self._get_ts_parser(ext)
        if not parser:
            return structure
            
        tree = parser.parse(content.encode('utf-8'))
        root = tree.root_node
        
        # Generic node identifiers across languages
        CLASS_TYPES = {'class_definition', 'class_declaration', 'struct_item', 'class'}
        FUNC_TYPES = {'function_definition', 'function_declaration', 'method_definition', 'arrow_function', 'function_item', 'method', 'method_declaration'}
        CALL_TYPES = {'call', 'call_expression', 'method_invocation'}
        
        def _get_name(node):
            """Finds the identifier child node containing the name."""
            for child in node.children:
                if child.type == 'identifier' or child.type == 'name':
                    return content[child.start_byte:child.end_byte]
            return "Anonymous"
            
        def _extract_calls(node):
            """Recursively extract all call expressions."""
            calls = []
            if node.type in CALL_TYPES:
                # C-style calls usually have the function name down the first child path
                if len(node.children) > 0 and node.children[0].type in ['identifier', 'identifier_reference', 'member_expression']:
                    calls.append(content[node.children[0].start_byte:node.children[0].end_byte].split('.')[-1])
            for child in node.children:
                calls.extend(_extract_calls(child))
            return list(set(calls))
            
        # Recursive walk to find classes and functions
        def _walk(node, current_class=None):
            if node.type in CLASS_TYPES:
                cls_info = {
                    "name": _get_name(node),
                    "line": node.start_point.row + 1,
                    "end_line": node.end_point.row + 1,
                    "docstring": "",
                    "methods": [],
                    "calls": _extract_calls(node)
                }
                structure["classes"].append(cls_info)
                for child in node.children:
                    _walk(child, cls_info)
            elif node.type in FUNC_TYPES:
                # Fix #4: Extract args from the function's parameter list
                func_text = content[node.start_byte:node.end_byte]
                args_match = re.search(r'\(([^)]*)\)', func_text)
                extracted_args = args_match.group(1).strip() if args_match else ""
                func_info = {
                    "name": _get_name(node),
                    "line": node.start_point.row + 1,
                    "end_line": node.end_point.row + 1,
                    "args": extracted_args,
                    "is_async": 'async' in content[max(0, node.start_byte - 10):node.start_byte],
                    "docstring": "",
                    "calls": _extract_calls(node)
                }
                if current_class:
                    current_class["methods"].append(func_info)
                else:
                    structure["functions"].append(func_info)
                for child in node.children:
                    _walk(child, current_class)
            else:
                for child in node.children:
                    _walk(child, current_class)

        _walk(root)
        structure["summary"] = self._build_summary(structure)
        return structure

    def _build_code_structure(self):
        """
        Extracts classes, functions, and their signatures from ALL source files.
        - Tree-sitter: Full AST parsing for major languages (most accurate)
        - Python: built-in AST parsing
        - JS/TS/C-style: regex-based structural extraction
        - Ruby: regex-based with def/class/module detection
        """
        for rel_path, content in self.file_contents.items():
            ext = Path(rel_path).suffix  # Fix #5: Use Path.suffix instead of manual rsplit

            if HAS_TREE_SITTER and self._get_ts_parser(ext):
                self.code_structure[rel_path] = self._extract_ts_structure(content, ext)
            elif ext in {'.py', '.pyi', '.pyx'}:
                self.code_structure[rel_path] = self._extract_python_structure(content, rel_path)
            elif ext in self._BRACED_STRUCTURE_EXTS:
                self.code_structure[rel_path] = self._extract_braced_structure(content)
            elif ext in self._RUBY_EXTS:
                self.code_structure[rel_path] = self._extract_ruby_structure(content)

    def _extract_python_structure(self, content: str, rel_path: str) -> dict:
        """AST-based structure extraction for Python — most accurate."""
        structure = {"classes": [], "functions": [], "summary": ""}
        try:
            tree = ast.parse(content, filename=rel_path)
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno),
                        "docstring": ast.get_docstring(node) or "",
                        "methods": []
                    }
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            calls = []
                            for child in ast.walk(item):
                                if isinstance(child, ast.Call):
                                    if isinstance(child.func, ast.Name):
                                        calls.append(child.func.id)
                                    elif isinstance(child.func, ast.Attribute):
                                        calls.append(child.func.attr)
                            method_info = {
                                "name": item.name,
                                "line": item.lineno,
                                "end_line": getattr(item, 'end_lineno', item.lineno),
                                "args": self._extract_args(item),
                                "is_async": isinstance(item, ast.AsyncFunctionDef),
                                "docstring": ast.get_docstring(item) or "",
                                "calls": list(set(calls))
                            }
                            class_info["methods"].append(method_info)
                    structure["classes"].append(class_info)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    calls = []
                    for child in ast.walk(node):
                        if isinstance(child, ast.Call):
                            if isinstance(child.func, ast.Name):
                                calls.append(child.func.id)
                            elif isinstance(child.func, ast.Attribute):
                                calls.append(child.func.attr)
                    func_info = {
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, 'end_lineno', node.lineno),
                        "args": self._extract_args(node),
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "docstring": ast.get_docstring(node) or "",
                        "calls": list(set(calls))
                    }
                    structure["functions"].append(func_info)
            structure["summary"] = self._build_summary(structure)
        except SyntaxError:
            structure["summary"] = "Could not parse (SyntaxError)"
        return structure

    def _extract_braced_structure(self, content: str) -> dict:
        """
        Regex-based structure extraction for JS/TS/C/C++/Java/Go/Rust/Swift/etc.
        Detects function definitions, class definitions, and method signatures.
        """
        structure = {"classes": [], "functions": [], "summary": ""}
        lines = content.split('\n')

        # Regex patterns for classes and functions
        class_re = re.compile(
            r'^\s*(?:export\s+)?(?:abstract\s+)?(?:public\s+)?'
            r'(?:class|interface|struct|enum)\s+(\w+)',
            re.MULTILINE
        )
        func_re = re.compile(
            r'^\s*(?:export\s+)?(?:public|private|protected|static|async|'  # modifiers
            r'pub(?:\(crate\))?\s+|)'
            r'(?:(?:async\s+)?function\*?\s+(\w+)'              # JS/TS function
            r'|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?'  # arrow function
            r'(?:\([^)]*\)|\w+)\s*=>'
            r'|fn\s+(\w+)'                                     # Rust fn
            r'|func\s+(\w+)'                                   # Go func
            r'|(?:void|int|float|double|char|bool|string|auto|'
            r'String|Promise|Future|Task)\s+(\w+)\s*\()',       # C-style return type
            re.MULTILINE
        )

        # Find classes
        for match in class_re.finditer(content):
            name = match.group(1)
            line_num = content[:match.start()].count('\n') + 1
            # Find end using brace counting
            end_line = self._find_brace_end(lines, line_num - 1)
            structure["classes"].append({
                "name": name,
                "line": line_num,
                "end_line": end_line + 1,
                "docstring": "",
                "methods": []
            })

        # Find top-level functions
        for match in func_re.finditer(content):
            # Extract the first non-None group (different regex groups for different patterns)
            name = next((g for g in match.groups() if g is not None), None)
            if not name:
                continue
            line_num = content[:match.start()].count('\n') + 1
            end_line = self._find_brace_end(lines, line_num - 1)
            is_async = 'async' in match.group(0)
            # Extract args if present
            args_match = re.search(r'\(([^)]*)\)', match.group(0))
            args = args_match.group(1).strip() if args_match else ""
            structure["functions"].append({
                "name": name,
                "line": line_num,
                "end_line": end_line + 1,
                "args": args,
                "is_async": is_async,
                "docstring": ""
            })

        structure["summary"] = self._build_summary(structure)
        return structure

    def _extract_ruby_structure(self, content: str) -> dict:
        """Regex-based structure extraction for Ruby files."""
        structure = {"classes": [], "functions": [], "summary": ""}
        lines = content.split('\n')

        block_start_re = re.compile(
            r'^\s*(?:def|class|module|do|if|unless|while|until|for|begin|case)\b'
        )
        block_end_re = re.compile(r'^\s*end\b')
        class_re = re.compile(r'^\s*(?:class|module)\s+(\w+)')
        func_re = re.compile(r'^\s*def\s+(\w+[?!]?)(?:\(([^)]*)\))?')

        for line_num, line in enumerate(lines):
            # Classes/modules
            cls_match = class_re.match(line)
            if cls_match:
                end_line = self._find_ruby_end(lines, line_num, block_start_re, block_end_re)
                structure["classes"].append({
                    "name": cls_match.group(1),
                    "line": line_num + 1,
                    "end_line": end_line + 1,
                    "docstring": "",
                    "methods": []
                })
            # Functions (top-level def)
            func_match = func_re.match(line)
            if func_match and not cls_match:
                end_line = self._find_ruby_end(lines, line_num, block_start_re, block_end_re)
                structure["functions"].append({
                    "name": func_match.group(1),
                    "line": line_num + 1,
                    "end_line": end_line + 1,
                    "args": func_match.group(2) or "",
                    "is_async": False,
                    "docstring": ""
                })

        structure["summary"] = self._build_summary(structure)
        return structure

    def _find_brace_end(self, lines: list, start_idx: int) -> int:
        """
        Find the closing brace line for a block starting at start_idx.
        Uses a lightweight state machine to ignore braces inside strings, 
        comments, regex literals, and template literals.
        """
        depth = 0
        found_open = False
        in_single_str = False
        in_double_str = False
        in_template = False      # JS/TS backtick template literals
        in_line_comment = False
        in_block_comment = False
        
        for j in range(start_idx, len(lines)):
            line = lines[j]
            in_line_comment = False  # Reset per line
            i = 0
            while i < len(line):
                ch = line[i]
                prev = line[i - 1] if i > 0 else ''
                
                # --- Block comment state ---
                if in_block_comment:
                    if ch == '/' and prev == '*':
                        in_block_comment = False
                    i += 1
                    continue
                
                # --- String states ---
                if in_single_str:
                    if ch == "'" and prev != '\\':
                        in_single_str = False
                    i += 1
                    continue
                if in_double_str:
                    if ch == '"' and prev != '\\':
                        in_double_str = False
                    i += 1
                    continue
                if in_template:
                    if ch == '`' and prev != '\\':
                        in_template = False
                    i += 1
                    continue
                
                # --- Line comment ---
                if in_line_comment:
                    i += 1
                    continue
                
                # --- Detect state transitions from code state ---
                if ch == '/' and i + 1 < len(line):
                    next_ch = line[i + 1]
                    if next_ch == '/':
                        in_line_comment = True
                        i += 2
                        continue
                    elif next_ch == '*':
                        in_block_comment = True
                        i += 2
                        continue
                
                if ch == "'":
                    in_single_str = True
                    i += 1
                    continue
                if ch == '"':
                    in_double_str = True
                    i += 1
                    continue
                if ch == '`':
                    in_template = True
                    i += 1
                    continue
                
                # --- Only count braces in code state ---
                if ch == '{':
                    depth += 1
                    found_open = True
                elif ch == '}':
                    depth -= 1
                
                i += 1
            
            if found_open and depth <= 0:
                return j
        return start_idx  # No braces found, return start

    def _find_ruby_end(self, lines: list, start_idx: int, start_re, end_re) -> int:
        """Find the matching 'end' for a Ruby block starting at start_idx."""
        depth = 0
        for j in range(start_idx, len(lines)):
            if start_re.match(lines[j]):
                depth += 1
            if end_re.match(lines[j]):
                depth -= 1
            if depth <= 0:
                return j
        return start_idx

    def _build_summary(self, structure: dict) -> str:
        """Build a one-line summary of a code structure."""
        class_names = [c["name"] for c in structure["classes"]]
        func_names = [f["name"] for f in structure["functions"]]
        parts = []
        if class_names:
            parts.append(f"Classes: {', '.join(class_names)}")
        if func_names:
            parts.append(f"Functions: {', '.join(func_names)}")
        return " | ".join(parts) if parts else "No top-level classes or functions"

    def _extract_args(self, func_node) -> str:
        """Extracts a human-readable argument list from an AST function node."""
        args = []
        for arg in func_node.args.args:
            name = arg.arg
            if name == 'self':
                continue
            annotation = ""
            if arg.annotation:
                try:
                    annotation = f": {ast.unparse(arg.annotation)}"
                except Exception:
                    pass
            args.append(f"{name}{annotation}")
        return ", ".join(args) if args else ""

    def search(self, query, k=5):
        """Dense semantic search using MiniLM embeddings."""
        with self.lock:
            if self.index is None:
                self.load()
            q_emb = model.encode([query])
            D, I = self.index.search(np.array(q_emb).astype("float32"), k)
            return [self.metadata[i] for i in I[0]]

    def load(self):
        """Load pre-built FAISS index and chunk metadata from artifacts/."""
        artifacts_dir = self.root_dir / ".codexmemory"
        self.index = faiss.read_index(str(artifacts_dir / "project_index.faiss"))
        with open(artifacts_dir / "project_metadata.pkl", "rb") as f:
            self.metadata = pickle.load(f)

    def load_full(self):
        """
        Load ALL artifacts into memory: FAISS index, metadata, full file contents,
        dependency graph, and code structure. Used by MCP tools for maximum retrieval.
        
        100x Auto-Build: If no .codexmemory index exists yet (new project or fresh install),
        automatically triggers a full build() first, then loads the result.
        """
        artifacts_dir = self.root_dir / ".codexmemory"
        index_path = artifacts_dir / "project_index.faiss"

        # 100x Auto-Build: Detect if this is a brand new project with no index
        if not index_path.exists():
            import sys
            print(f"[CodexMemory] No index found at {artifacts_dir}. Auto-building for: {self.root_dir}", file=sys.stderr)
            self.build()
            # After build, the artifacts should now exist
            if not index_path.exists():
                print(f"[CodexMemory] WARNING: Build completed but no index was generated (empty project?).", file=sys.stderr)
                return

        # Core index
        self.index = faiss.read_index(str(artifacts_dir / "project_index.faiss"))
        with open(artifacts_dir / "project_metadata.pkl", "rb") as f:
            self.metadata = pickle.load(f)

        # Full file contents
        files_pkl = artifacts_dir / "project_files.pkl"
        if files_pkl.exists():
            with open(files_pkl, "rb") as f:
                self.file_contents = pickle.load(f)

        # Dependency graph
        deps_pkl = artifacts_dir / "project_deps.pkl"
        if deps_pkl.exists():
            with open(deps_pkl, "rb") as f:
                self.dependency_graph = pickle.load(f)

        # Code structure
        struct_pkl = artifacts_dir / "project_structure.pkl"
        if struct_pkl.exists():
            with open(struct_pkl, "rb") as f:
                self.code_structure = pickle.load(f)


if __name__ == "__main__":
    print("=" * 50)
    print("CodexMemory — 100x Production Build")
    print("=" * 50)
    mem = ProjectMemory()
    mem.build()

    print("\n    Test query: 'target user profile conversation'")
    try:
        results = mem.search("target user profile conversation", k=3)
        for i, r in enumerate(results, 1):
            print(f"    {i}. {r['path']} (chunk #{r['chunk_id']}, {r['tokens']:,} tokens)")
    except Exception as e:
        print(f"    Could not perform test query: {e}")
