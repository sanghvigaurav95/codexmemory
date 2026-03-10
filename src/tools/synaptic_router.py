import os
import mmap
import struct
import json
import hashlib
import time
from pathlib import Path
from queue import Queue
from threading import Thread
import threading

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

# ============================================================================
# PILLAR 1: The Synaptic Grid (Zero-String Binary State)
# ============================================================================
class SynapticGrid:
    """
    100x Memory Mapped AST Pointer Grid.
    Instead of storing strings, we store 32-byte C-struct pointers to exact logic blocks.
    
    Layout (32 bytes per AST Node):
    - node_id    (uint32) : 4 bytes
    - parent_id  (uint32) : 4 bytes
    - file_idx   (uint32) : 4 bytes (Maps to a registry of file paths, supports 4.2B files)
    - type_hash  (uint16) : 2 bytes (Hash of 'function', 'class', etc.)
    - byte_start (uint32) : 4 bytes (Start offset in the actual source file)
    - byte_end   (uint32) : 4 bytes (End offset in the actual source file)
    - vector_id  (int64)  : 8 bytes (FAISS index ID)
    - padding    (pad)    : 2 bytes (Alignment)
    
    Total: 1,000,000 nodes = ~32 MB of RAM. (Beats 4GB of raw text).
    """
    STRUCT_FMT = '!IIIHIIq2x'
    SLOT_SIZE = struct.calcsize(STRUCT_FMT) # Should be 32 bytes
    
    def __init__(self, workspace_dir: str, max_nodes: int = 500000):
        self.workspace_dir = Path(workspace_dir)
        self.artifacts_dir = self.workspace_dir / ".codexmemory"
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        
        self.grid_path = self.artifacts_dir / "synaptic_grid.dat"
        self.registry_path = self.artifacts_dir / "file_registry.json"
        
        self.max_nodes = max_nodes
        self.total_size = self.SLOT_SIZE * self.max_nodes
        
        self.file_registry = {} # file_idx -> rel_path
        self.path_to_idx = {}   # rel_path -> file_idx
        self.next_file_idx = 0
        self.next_node_id = 0
        
        self._init_mmap()
        self._load_registry()

    def _init_mmap(self):
        """Pre-allocates the binary grid if it doesn't exist, then maps it."""
        if not self.grid_path.exists():
            with open(self.grid_path, "wb") as f:
                f.write(b'\x00' * self.total_size)
                
        self.f = open(self.grid_path, "r+b")
        self.mm = mmap.mmap(self.f.fileno(), 0)

    def _load_registry(self):
        if self.registry_path.exists():
            with open(self.registry_path, 'r') as f:
                data = json.load(f)
                self.file_registry = {int(k): v for k, v in data.get("files", {}).items()}
                self.path_to_idx = {v: int(k) for k, v in self.file_registry.items()}
                self.next_file_idx = data.get("next_file_idx", 0)
                self.next_node_id = data.get("next_node_id", 0)

    def _save_registry(self):
        try:
            with open(self.registry_path, 'w') as f:
                json.dump({
                    "files": self.file_registry,
                    "next_file_idx": self.next_file_idx,
                    "next_node_id": self.next_node_id
                }, f)
        except Exception:
            pass  # Silently ignore during interpreter shutdown

    def register_file(self, rel_path: str) -> int:
        """Assigns a highly efficient uint32 ID to a file path (supports 4.2B files)."""
        if rel_path not in self.path_to_idx:
            idx = self.next_file_idx
            self.file_registry[idx] = rel_path
            self.path_to_idx[rel_path] = idx
            self.next_file_idx += 1
            self._save_registry()
        return self.path_to_idx[rel_path]

    def write_node(self, parent_id: int, rel_path: str, node_type: str, byte_start: int, byte_end: int, vector_id: int) -> int:
        """Packs AST metadata directly into the binary memory map. Auto-expands if full."""
        if self.next_node_id >= self.max_nodes:
            self.mm.close()
            with open(self.grid_path, "ab") as f:
                f.write(b'\x00' * self.total_size) # Double the capacity
            self.max_nodes *= 2
            self.total_size *= 2
            self.f.seek(0)
            self.mm = mmap.mmap(self.f.fileno(), 0)
            import sys
            print(f"[Grid] Auto-expanded capacity to {self.max_nodes} nodes.", file=sys.stderr)

        node_id = self.next_node_id
        file_idx = self.register_file(rel_path)
        type_hash = hash(node_type) % 65535  # Simple 16-bit hash for node type
        
        packed = struct.pack(self.STRUCT_FMT, node_id, parent_id, file_idx, type_hash, byte_start, byte_end, vector_id)
        
        offset = node_id * self.SLOT_SIZE
        self.mm.seek(offset)
        self.mm.write(packed)
        
        self.next_node_id += 1
        return node_id

    def read_node(self, node_id: int) -> dict:
        """Unpacks the C-struct back into Python logic instantly."""
        offset = node_id * self.SLOT_SIZE
        self.mm.seek(offset)
        packed = self.mm.read(self.SLOT_SIZE)
        
        unpacked = struct.unpack(self.STRUCT_FMT, packed)
        return {
            "node_id": unpacked[0],
            "parent_id": unpacked[1],
            "file_path": self.file_registry.get(unpacked[2], "UNKNOWN"),
            "byte_start": unpacked[4],
            "byte_end": unpacked[5],
            "vector_id": unpacked[6]
        }

    def close(self):
        try:
            self._save_registry()
            self.mm.close()
            self.f.close()
        except Exception:
            pass  # Silently ignore during interpreter shutdown

    def compact(self, active_node_ids: list) -> dict:
        """
        Defragments synaptic_grid.dat by rewriting only active nodes sequentially.
        Purges all zombie nodes (dead, unreachable 32-byte structs) from disk.
        
        Args:
            active_node_ids: List of node_ids that are still alive in ProjectMemory.
            
        Returns:
            dict: Mapping of old_node_id -> new_node_id for upstream reconciliation.
        """
        import sys
        if not active_node_ids:
            print("[Grid] 🧹 Compact skipped: no active nodes.", file=sys.stderr)
            return {}

        old_count = self.next_node_id

        # 1. Read raw packed bytes for each active node from the current mmap
        active_packed = []
        for old_id in sorted(active_node_ids):
            if old_id >= old_count:
                continue  # Safety: skip out-of-range IDs
            offset = old_id * self.SLOT_SIZE
            self.mm.seek(offset)
            packed = self.mm.read(self.SLOT_SIZE)
            active_packed.append((old_id, packed))

        # 2. Close the old mmap and file handle
        self.mm.close()
        self.f.close()

        # 3. Create a new temp .dat file with minimum capacity
        tmp_path = self.grid_path.with_suffix('.tmp')
        new_count = len(active_packed)
        new_max = max(new_count * 2, 500000)  # Keep minimum capacity
        new_total_size = self.SLOT_SIZE * new_max

        with open(tmp_path, "wb") as f:
            f.write(b'\x00' * new_total_size)

        # 4. Write compacted nodes with new sequential IDs
        id_map = {}  # old_node_id -> new_node_id
        f_new = open(tmp_path, "r+b")
        mm_new = mmap.mmap(f_new.fileno(), 0)

        for new_id, (old_id, packed) in enumerate(active_packed):
            id_map[old_id] = new_id
            # Unpack the raw struct, replace only node_id, repack (preserves type_hash, file_idx, etc.)
            unpacked = list(struct.unpack(self.STRUCT_FMT, packed))
            unpacked[0] = new_id  # Assign new sequential node_id
            repacked = struct.pack(self.STRUCT_FMT, *unpacked)

            offset = new_id * self.SLOT_SIZE
            mm_new.seek(offset)
            mm_new.write(repacked)

        mm_new.close()
        f_new.close()

        # 5. Atomic file swap: old -> .old, tmp -> .dat, delete .old
        old_path = self.grid_path.with_suffix('.old')
        try:
            if old_path.exists():
                old_path.unlink()
            self.grid_path.rename(old_path)
            tmp_path.rename(self.grid_path)
            old_path.unlink()
        except OSError:
            # Fallback for Windows file locking edge cases
            if self.grid_path.exists():
                self.grid_path.unlink()
            tmp_path.rename(self.grid_path)

        # 6. Reopen the compacted file and update internal state
        self.max_nodes = new_max
        self.total_size = new_total_size
        self.next_node_id = new_count
        self.f = open(self.grid_path, "r+b")
        self.mm = mmap.mmap(self.f.fileno(), 0)
        self._save_registry()

        print(f"[Grid] 🧹 Compacted: {new_count}/{old_count} active nodes preserved. "
              f"Purged {old_count - new_count} zombie nodes.", file=sys.stderr)

        return id_map


# ============================================================================
# PILLAR 2: The Holographic Canvas (Zero-Copy Read)
# ============================================================================
class HolographicCanvas:
    """
    Never load the whole string into RAM. 
    Memory map the target source file, slice out the bytes requested by the Grid, and drop it.
    
    Uses an LRU cache of open memory maps (max 25 files) to prevent the syscall 
    death loop of opening/closing mmap handles on every single chunk read.
    Thread-safe: RLock prevents eviction of an mmap during an active slice read.
    """
    _mmap_cache = {}       # str(full_path) -> (file_handle, mmap_object)
    _access_order = []     # LRU tracking list
    _MAX_CACHE_SIZE = 25
    _lock = threading.RLock()

    @classmethod
    def _get_mmap(cls, full_path: Path):
        """Returns a cached mmap for the given file, creating one if needed. Caller must hold _lock."""
        key = str(full_path)
        
        if key in cls._mmap_cache:
            # Move to end of access order (most recently used)
            if key in cls._access_order:
                cls._access_order.remove(key)
            cls._access_order.append(key)
            return cls._mmap_cache[key][1]
        
        # Evict oldest entry if cache is full
        while len(cls._mmap_cache) >= cls._MAX_CACHE_SIZE:
            oldest_key = cls._access_order.pop(0)
            if oldest_key in cls._mmap_cache:
                old_fh, old_mm = cls._mmap_cache.pop(oldest_key)
                try:
                    old_mm.close()
                    old_fh.close()
                except Exception:
                    pass
        
        # Open and cache new mmap
        fh = open(full_path, "rb")
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        cls._mmap_cache[key] = (fh, mm)
        cls._access_order.append(key)
        return mm

    @classmethod
    def invalidate_cache(cls, full_path: Path = None):
        """Evicts a specific file (or all files) from the mmap cache."""
        with cls._lock:
            if full_path:
                key = str(full_path)
                if key in cls._mmap_cache:
                    fh, mm = cls._mmap_cache.pop(key)
                    try:
                        mm.close()
                        fh.close()
                    except Exception:
                        pass
                    if key in cls._access_order:
                        cls._access_order.remove(key)
            else:
                for fh, mm in cls._mmap_cache.values():
                    try:
                        mm.close()
                        fh.close()
                    except Exception:
                        pass
                cls._mmap_cache.clear()
                cls._access_order.clear()

    @staticmethod
    def extract_splice(workspace_dir: Path, file_path: str, byte_start: int, byte_end: int) -> str:
        full_path = workspace_dir / file_path
        if not full_path.exists():
            return ""
            
        size = full_path.stat().st_size
        if size == 0:
            return ""
            
        byte_start = min(byte_start, size)
        byte_end = min(byte_end, size)
        if byte_start == byte_end:
            return ""
            
        if size > 1024 * 50: # If larger than 50KB, use LRU-cached mmap slicing
            try:
                # Hold the lock across get+slice so the map can't be evicted mid-read
                with HolographicCanvas._lock:
                    mm = HolographicCanvas._get_mmap(full_path)
                    code_bytes = mm[byte_start:byte_end]
            except (ValueError, mmap.error):
                # File was modified externally, invalidate and retry with standard read
                HolographicCanvas.invalidate_cache(full_path)
                with open(full_path, "rb") as f:
                    f.seek(byte_start)
                    code_bytes = f.read(byte_end - byte_start)
        else:
            with open(full_path, "rb") as f:
                f.seek(byte_start)
                code_bytes = f.read(byte_end - byte_start)
                
        return code_bytes.decode('utf-8', errors='replace')


# ============================================================================
# PILLAR 3: The Nervous System (Event-Driven Deltas)
# ============================================================================
class FileDeltaWatcher(FileSystemEventHandler if HAS_WATCHDOG else object):
    """
    Listens to the Operating System. 
    When a file changes, it calculates the hash. If different, it queues it for a surgical update.
    """
    def __init__(self, workspace_dir: str, update_queue: Queue):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.update_queue = update_queue
        self.file_hashes = {}
        
    def _hash_file(self, filepath: Path) -> str:
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                # Read in 64k chunks to avoid RAM spikes on massive files
                for chunk in iter(lambda: f.read(65536), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""

    def on_modified(self, event):
        if event.is_directory:
            return
            
        filepath = Path(event.src_path).resolve()
        # Ignore git, cache, and our own artifacts
        if any(ignored in filepath.parts for ignored in ['.git', '__pycache__', 'node_modules', 'artifacts', '.codexmemory']):
            return

        # Explicitly ignore non-code/text files to save memory and FAISS operations
        # We import here to avoid circular dependencies with ProjectMemory
        from project_memory import SUPPORTED_EXTENSIONS
        file_suffix = filepath.suffix.lower()
        
        # Give leeway to files with no extension (like Dockerfile, Makefile) but strictly block binaries if they slip through
        if file_suffix and file_suffix not in SUPPORTED_EXTENSIONS:
            return
            
        new_hash = self._hash_file(filepath)
        try:
            rel_path = str(filepath.relative_to(self.workspace_dir))
        except ValueError:
            return
        
        if self.file_hashes.get(rel_path) != new_hash:
            self.file_hashes[rel_path] = new_hash
            # Push delta to the queue for the FAISS updater thread
            self.update_queue.put({
                "action": "update",
                "file": rel_path,
                "timestamp": time.time()
            })

    def on_created(self, event):
        self.on_modified(event)

    def on_deleted(self, event):
        self.on_modified(event)

class NervousSystem:
    def __init__(self, workspace_dir: str, memory_engine=None):
        self.workspace_dir = workspace_dir
        self.memory_engine = memory_engine
        self.queue = Queue()
        self.watcher = FileDeltaWatcher(workspace_dir, self.queue)
        self.observer = None
        
        if HAS_WATCHDOG:
            self.observer = Observer()
            self.observer.schedule(self.watcher, workspace_dir, recursive=True)
            
        self.running = False
        self.worker_thread = Thread(target=self._process_deltas, daemon=True)

    def start(self):
        self.running = True
        if self.observer:
            self.observer.start()
        self.worker_thread.start()
        import sys
        print("[NervousSystem] OS File monitoring active. Listening for deltas...", file=sys.stderr)

    def stop(self):
        self.running = False
        if self.observer:
            self.observer.stop()
            self.observer.join()

    def _process_deltas(self):
        """
        Consumes the delta queue with a 2-second debounce to batch rapid saves.
        Calls ProjectMemory.update_file() to surgically manipulate the FAISS vectors.
        """
        import contextlib
        import io
        while self.running:
            try:
                event = self.queue.get(timeout=1.0)
                # Debounce: wait 2s to allow batch saves (e.g., search & replace across multiple files)
                time.sleep(2.0)
                events = [event]
                while not self.queue.empty():
                    try:
                        events.append(self.queue.get_nowait())
                    except:
                        break
                        
                unique_paths = list({e['file'] for e in events})
                for rel_path in unique_paths:
                    import sys
                    print(f"\n[⚡ Synaptic Delta Detected] Routing RAM update for: {rel_path}", file=sys.stderr)
                    if self.memory_engine:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.memory_engine.update_file(rel_path)
                
                # 100x I/O Flush: Dump all accumulated RAM mutations to disk exactly once per batch
                if self.memory_engine and unique_paths:
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.memory_engine.flush_to_disk()
                
                
            except Exception:
                pass # Queue empty, sleep naturally

if __name__ == "__main__":
    print("=" * 60)
    print("  CodexMemory — Synaptic Code Router (SCR) Engine Test")
    print("=" * 60)
    
    workspace = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Initialize Grid
    grid = SynapticGrid(workspace)
    print(f"[Grid] Memory Map initialized. Capacity: {grid.max_nodes} AST nodes.")
    
    # Simulate saving a parsed AST node into the grid
    mock_vector_id = 42
    node_id = grid.write_node(
        parent_id=0,
        rel_path="src/api/routes.py",
        node_type="function",
        byte_start=150,
        byte_end=450,
        vector_id=mock_vector_id
    )
    
    # Read it back in microseconds
    data = grid.read_node(node_id)
    print(f"[Grid] Node {node_id} retrieved instantly: {data}")
    
    # 2. Start Nervous System
    nervous_system = NervousSystem(workspace)
    nervous_system.start()
    
    try:
        print("[System] Running. Modify any file in this directory to see Delta Routing. (Ctrl+C to exit)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        nervous_system.stop()
        grid.close()
        print("\n[System] Graceful shutdown complete.")
