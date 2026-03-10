import time
import os
import tempfile
from pathlib import Path

# Inject the tools path
import sys
sys.path.insert(0, "d:\\codexmemory\\src\\tools")

from synaptic_router import HolographicCanvas

def benchmark():
    # Create a large temp file (200KB) to trigger mmap path
    workspace = Path(tempfile.mkdtemp())
    test_file = workspace / "large_test.py"
    
    content = "\n".join([f"def function_{i}():\n    return {i} * 2\n" for i in range(5000)])
    test_file.write_text(content, encoding="utf-8")
    
    file_size = test_file.stat().st_size
    print(f"Test file size: {file_size / 1024:.1f} KB")
    
    # Define 5000 random splice reads
    import random
    slices = []
    for _ in range(5000):
        start = random.randint(0, max(0, file_size - 200))
        end = min(start + 150, file_size)
        slices.append((start, end))
    
    # --- Benchmark: Old pattern (open/mmap/close per call) ---
    import mmap
    start_time = time.perf_counter()
    for byte_start, byte_end in slices:
        with open(test_file, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            _ = mm[byte_start:byte_end]
            mm.close()
    old_time = time.perf_counter() - start_time
    print(f"OLD (open/mmap/close per call): {old_time:.4f}s for 5000 reads")
    
    # --- Benchmark: New LRU cached mmap ---
    HolographicCanvas.invalidate_cache()  # Clear any state
    start_time = time.perf_counter()
    for byte_start, byte_end in slices:
        HolographicCanvas.extract_splice(workspace, "large_test.py", byte_start, byte_end)
    new_time = time.perf_counter() - start_time
    print(f"NEW (LRU cached mmap):          {new_time:.4f}s for 5000 reads")
    
    speedup = old_time / new_time if new_time > 0 else float('inf')
    print(f"\nSpeedup: {speedup:.1f}x faster")
    
    if speedup > 1.5:
        print("PASS: mmap LRU cache is significantly faster than per-call open/close.")
    else:
        print("WARNING: Speedup is marginal. May need tuning.")
    
    # Cleanup
    HolographicCanvas.invalidate_cache()
    test_file.unlink()
    workspace.rmdir()

if __name__ == "__main__":
    benchmark()
