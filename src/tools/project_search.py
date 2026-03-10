import os
os.environ["OMP_NUM_THREADS"] = "1"
import re
import math
from typing import List, Dict, Any, Union
import numpy as np

import threading

class IncrementalBM25:
    """An incrementally updatable BM25 implementation."""
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_freqs = [] # list of dicts mapping term to freq in that doc
        self.idf = {}
        self.doc_len = []
        self._sum_doc_len = 0
        self.nd = {} # Term -> number of documents containing term
        self.lock = threading.RLock()

    def __getstate__(self):
        state = self.__dict__.copy()
        # Remove the unpicklable RLock
        if 'lock' in state:
            del state['lock']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # Restore the RLock
        self.lock = threading.RLock()

    def _calc_idf(self, nd):
        idf_sum = 0
        negative_idfs = []
        for word, freq in nd.items():
            # Clamp to prevent math domain error when corpus_size matches freq perfectly and +0.5 is misaligned during deletions
            val1 = max(0.5, self.corpus_size - freq + 0.5)
            val2 = max(0.5, freq + 0.5)
            idf = math.log(val1) - math.log(val2)
            self.idf[word] = idf
            idf_sum += idf
            if idf < 0:
                negative_idfs.append(word)
        
        self.average_idf = idf_sum / len(self.idf) if self.idf else 0
        eps = 0.25 * self.average_idf
        for word in negative_idfs:
            self.idf[word] = eps

    def add_documents(self, corpus: List[List[str]]):
        with self.lock:
            for document in corpus:
                frequencies = {}
                for word in document:
                    frequencies[word] = frequencies.get(word, 0) + 1
                self.doc_freqs.append(frequencies)
                
                for word in frequencies.keys():
                    self.nd[word] = self.nd.get(word, 0) + 1
                    
                length = len(document)
                self.doc_len.append(length)
                self._sum_doc_len += length
                self.corpus_size += 1
                
            if self.corpus_size > 0:
                self.avgdl = self._sum_doc_len / self.corpus_size
            self._calc_idf(self.nd)

    def remove_document(self, doc_index: int):
        with self.lock:
            if doc_index >= len(self.doc_freqs):
                return
                
            frequencies = self.doc_freqs[doc_index]
            for word in frequencies.keys():
                self.nd[word] -= 1
                if self.nd[word] == 0:
                    del self.nd[word]
                    if word in self.idf:
                        del self.idf[word]
                        
            length = self.doc_len[doc_index]
            self._sum_doc_len -= length
            self.corpus_size -= 1
            
            # We don't delete from the lists to keep indices aligned, we just empty them
            self.doc_freqs[doc_index] = {}
            self.doc_len[doc_index] = 0
            
            if self.corpus_size > 0:
                self.avgdl = self._sum_doc_len / self.corpus_size
            else:
                self.avgdl = 0.0
            self._calc_idf(self.nd)

    def get_scores(self, query: List[str]) -> np.ndarray:
        with self.lock:
            scores = np.zeros(len(self.doc_freqs))
            if self.corpus_size == 0:
                return scores
                
            for q in query:
                q_freq = np.array([doc.get(q, 0) for doc in self.doc_freqs])
                if q not in self.idf:
                    continue
                
                idf = self.idf[q]
                doc_len = np.array(self.doc_len)
                
                # Avoid division by zero for deleted docs where avgdl might be 0
                if self.avgdl == 0:
                    denominator = q_freq + self.k1
                else:
                    denominator = q_freq + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                    
                numerator = idf * q_freq * (self.k1 + 1)
                valid_indices = denominator > 0
                scores[valid_indices] += numerator[valid_indices] / denominator[valid_indices]
                
            return scores

# Import your core memory engine
from project_memory import ProjectMemory

class CodexResonanceSearch:
    """
    100x Production Retrieval Engine (CRR).
    
    Architecture:
    - Sub-Lexical Tokenization (Understands camelCase and snake_case natively).
    - Chunk-Level Reciprocal Rank Fusion (RRF).
    - Zero-Disk I/O (Operates entirely on RAM-cached artifacts).
    - Returns full Holographic Splices (Code + Dependencies) instead of file paths.
    """
    def __init__(self, memory: ProjectMemory = None):
        # Attach to the singleton memory instance to prevent reloading FAISS
        self.dense = memory if memory is not None else ProjectMemory()
        self.sparse = None
        self._preload()

    def _code_tokenize(self, text: str) -> List[str]:
        """
        Advanced Sub-Lexical Tokenization for Code.
        
        Why this is 100x:
        If code has 'calculateTradeMargin', and the user searches 'trade margin', 
        standard BM25 fails. This tokenizer splits 'calculateTradeMargin' into:
        ['calculatetrademargin', 'calculate', 'trade', 'margin']
        """
        if not text:
            return []
            
        tokens = []
        # 1. Extract raw words (ignore punctuation/symbols)
        raw_words = re.findall(r'[a-zA-Z0-9]+', text)
        
        for word in raw_words:
            # Add the full lowercase word
            tokens.append(word.lower())
            
            # 2. Split snake_case
            if '_' in word:
                sub_words = word.split('_')
                tokens.extend([sw.lower() for sw in sub_words if sw])
                
            # 3. Split camelCase and PascalCase
            # Uses regex lookahead to split on uppercase letters
            camel_splits = re.sub('([A-Z][a-z]+)', r' \1', re.sub('([A-Z]+)', r' \1', word)).split()
            if len(camel_splits) > 1:
                tokens.extend([cs.lower() for cs in camel_splits if cs])
                
        # Deduplicate while preserving order for performance
        return list(dict.fromkeys(tokens))

    def _preload(self):
        """
        RAM Cache Initialization.
        Loads the vector index, metadata, and fits the Code-Aware BM25 corpus.
        """
        # Ensure memory is fully loaded into RAM (uses the hidden .codexmemory folder internally)
        if self.dense.index is None:
            self.dense.load_full()

        import pickle
        import sys
        bm25_path = self.dense.root_dir / ".codexmemory" / "project_bm25.pkl"
        
        # Load from lightweight cache to prevent thousands of disk I/O reads on boot
        if os.path.exists(bm25_path):
            with open(bm25_path, "rb") as f:
                self.sparse = pickle.load(f)
            print("    [CRR] Loaded precise sub-lexical BM25 index from cache.", file=sys.stderr)
            return
            
        # Extract text directly from mapped Grid and Canvas
        from synaptic_router import HolographicCanvas
        docs_text = []
        with self.dense.lock:
            for meta in self.dense.metadata:
                if meta.get('deleted'):
                    docs_text.append("") # Blank string prevents BM25 keyword hits but maintains array index alignment
                    continue
                    
                header = meta.get('header', '')
                node_id = meta.get('node_id')
                if node_id is not None:
                    node = self.dense.grid.read_node(node_id)
                    code_bytes = HolographicCanvas.extract_splice(self.dense.root_dir, node['file_path'], node['byte_start'], node['byte_end'])
                    docs_text.append(header + code_bytes)
                else:
                    docs_text.append(header) # fallback
                
        # Fit BM25 using the advanced code tokenizer
        import sys
        print("    [CRR] Compiling sub-lexical sparse index...", file=sys.stderr)
        tokenized_corpus = [self._code_tokenize(doc) for doc in docs_text]
        self.sparse = IncrementalBM25()
        self.sparse.add_documents(tokenized_corpus)
        
        # Save cache
        with open(bm25_path, "wb") as f:
            pickle.dump(self.sparse, f)
            
        print("    [CRR] Search engine ready.", file=sys.stderr)

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Codex Resonance Retrieval (CRR) Core Function.
        
        Executes a dense (MiniLM) and sparse (BM25) search, fuses them at the 
        exact CHUNK level using RRF, and returns the highest value Holographic Splices.
        """
        # 100x Reactive State Sync: Re-compile precise tokens if Delta Watcher mutated the FAISS
        bm25_path = self.dense.root_dir / ".codexmemory" / "project_bm25.pkl"
        if not bm25_path.exists():
            import sys
            print("\n    [CRR] ⚡ Live Delta Shift detected! Re-syncing Semantic and BM25 Corpus...", file=sys.stderr)
            self._preload()
            
        # Over-sample to ensure we have enough chunks to fuse properly
        search_depth = k * 4
        
        dense_ranks = {}
        with self.dense.lock:
            # ---------------------------------------------------------
            # 1. Dense Search (Semantic Intent via FAISS + MiniLM)
            # ---------------------------------------------------------
            dense_results = self.dense.search(query, search_depth)
            
            # Map the dense rank back to the global chunk index in self.dense.metadata
            for rank, meta_dict in enumerate(dense_results):
                try:
                    # Find exactly where this chunk lives in the global array
                    global_idx = self.dense.metadata.index(meta_dict)
                    dense_ranks[global_idx] = rank
                except ValueError:
                    continue

            # ---------------------------------------------------------
            # 2. Sparse Search (Exact Keyword via BM25Okapi)
            # ---------------------------------------------------------
            q_tokens = self._code_tokenize(query)
            bm25_scores = self.sparse.get_scores(q_tokens)
            
            # Get the indices of the top N BM25 scores, sorted highest to lowest
            bm25_top_indices = np.argsort(bm25_scores)[-search_depth:][::-1]

            # ---------------------------------------------------------
            # 3. Reciprocal Rank Fusion (RRF)
            # ---------------------------------------------------------
            fused_scores = {}
            RRF_K = 60  # Standard smoothing constant for RRF math
            
            # Apply Dense Ranks to the fusion score
            for global_idx, rank in dense_ranks.items():
                fused_scores[global_idx] = fused_scores.get(global_idx, 0.0) + (1.0 / (RRF_K + rank + 1))
                
            # Apply Sparse Ranks to the fusion score
            for rank, global_idx in enumerate(bm25_top_indices):
                # Verify max length so garbage collection shifts don't throw IndexError
                if global_idx < len(bm25_scores) and bm25_scores[global_idx] > 0:
                    fused_scores[global_idx] = fused_scores.get(global_idx, 0.0) + (1.0 / (RRF_K + rank + 1))
                
            # ---------------------------------------------------------
            # 4. Sort & Package the Holographic Payload
            # ---------------------------------------------------------
            # Sort by highest fused score first, grab the top K
            top_chunk_indices = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)[:k]
            
            results = []
            results = []
            for global_idx, score in top_chunk_indices:
                # bounds check to prevent IndexError during concurrent Garbage Collection shifts
                if global_idx >= len(self.dense.metadata) or global_idx < 0:
                    continue
                    
                meta = self.dense.metadata[global_idx]
                
                # Skip overwritten vectors
                if meta.get('deleted'):
                    continue
                    
                # Fetch the high-level file summary from the dependency graph/structure
                # This gives the LLM the "map" of the file the chunk came from
                path = meta['path']
                file_structure = self.dense.code_structure.get(path, {})
                file_summary = file_structure.get("summary", "")
                
                from synaptic_router import HolographicCanvas
                node_id = meta.get('node_id')
                if node_id is not None:
                    node = self.dense.grid.read_node(node_id)
                    code_bytes = HolographicCanvas.extract_splice(self.dense.root_dir, node['file_path'], node['byte_start'], node['byte_end'])
                    content = meta.get('header', '') + code_bytes
                else:
                    content = meta.get('header', '')

                results.append({
                    'path': path,
                    'chunk_id': meta.get('chunk_id', 0),
                    'tokens': meta.get('tokens', 0),
                    'fusion_score': float(score),
                    'file_summary': file_summary,
                    'content': content  # The actual CRS injected code block
                })
                
                if len(results) >= k:
                    break
                    
        return results

if __name__ == "__main__":
    import sys
    
    # Setup a realistic test query that tests both semantic and exact match
    test_query = sys.argv[1] if len(sys.argv) > 1 else "neural networks trading margin"
    
    print("=" * 60)
    print("  CodexMemory — 100x CRR Search Test")
    print("=" * 60)
    
    try:
        retriever = CodexResonanceSearch()
        results = retriever.search(test_query, k=3)
        
        print(f"\n🔍 **Query:** '{test_query}'")
        print(f"🎯 Found {len(results)} exact resonance splices.\n")
        
        for i, r in enumerate(results, 1):
            print(f"[{i}] FILE: {r['path']} (Chunk #{r['chunk_id']})")
            print(f"    SCORE: {r['fusion_score']:.4f} | TOKENS: {r['tokens']}")
            print(f"    CONTEXT: {r['file_summary']}")
            print("-" * 40)
            
            # Print a preview of the actual injected code the LLM will see
            content_preview = r['content'].strip()
            # Show first 5 lines of the chunk
            preview_lines = content_preview.split('\n')[:5]
            print('\n'.join(preview_lines))
            if len(content_preview.split('\n')) > 5:
                print("    ... [code continues] ...\n")
                
    except Exception as e:
        print(f"\n❌ Error running search. Ensure ProjectMemory has built the index first.")
        print(f"Details: {e}")
