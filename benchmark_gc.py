import time
import os
from pathlib import Path
from src.tools.project_memory import ProjectMemory

def generate_fake_python(lines):
    return "\n".join([f"def func_{i}():\n    pass\n" for i in range(lines)])

def benchmark():
    mem = ProjectMemory(Path("."))
    
    print("Building initial project index...")
    # Inject fake file contents to mock an initial build
    test_file_name = "test_gc_file.py"
    mem.file_contents[test_file_name] = generate_fake_python(10)
    mem._build_code_structure()
    mem.build()
    
    initial_metadata_len = len(mem.metadata)
    print(f"Initial metadata length: {initial_metadata_len}")
    
    # 2. Emulate 60 File Updates
    print("Emulating 60 file updates to trigger Garbage Collection (>50 deleted vectors)...")
    
    test_file = Path(test_file_name)
    test_file.write_text(generate_fake_python(10), encoding="utf-8")
    
    # Run 60 updates
    for i in range(60):
        # We simulate a tiny change so hash/content doesn't matter
        test_file.write_text(generate_fake_python(10 + i % 3), encoding="utf-8")
        mem.update_file(test_file_name)
    
    # Check if GC successfully preserved metadata length near original instead of 600+
    final_metadata_len = len(mem.metadata)
    print(f"Final metadata length after 60 updates: {final_metadata_len}")
    
    if final_metadata_len > initial_metadata_len * 5:
        print("FAIL: Garbage Collection did not trigger or failed to compact the arrays!")
        test_file.unlink()
        exit(1)
        
    print("PASS: FAISS GC Memory Leak Fixed! Index compacted successfully.")
    
    # Cleanup
    test_file.unlink()

if __name__ == "__main__":
    benchmark()
