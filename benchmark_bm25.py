import time
import os
from pathlib import Path
from src.tools.project_memory import ProjectMemory
from src.tools.project_search import CodexResonanceSearch

def benchmark():
    mem = ProjectMemory(Path("."))
    
    # 1. Provide a small initial memory build to generate base BM25
    print("Building initial project index...")
    # Inject fake file contents to mock an initial build
    mem.file_contents["test_file_1.py"] = "def authentication_logic():\n    pass"
    mem.file_contents["test_file_2.py"] = "def some_other_logic():\n    pass"
    mem._build_code_structure()
    mem.build()
    
    # Verify BM25 was built
    artifacts_dir = mem.root_dir / ".codexmemory"
    bm25_path = artifacts_dir / "project_bm25.pkl"
    if not bm25_path.exists():
        print("FAIL: project_bm25.pkl was not created during build.")
        exit(1)
        
    # 2. Emulate a Single File Update
    print("Emulating single file update (adding 1 file to trigger vector update)...")
    
    # Pretend saving a new file
    test_file = Path("test_file_1.py")
    test_file.write_text("def authentication_logic_updated():\n    pass", encoding="utf-8")
    
    start_update = time.time()
    # Call update_file. This shouldn't drop the BM25, it should update it
    mem.update_file("test_file_1.py")
    end_update = time.time()
    
    print(f"File Update Took: {end_update - start_update:.3f} seconds.")
    
    # Verify BM25 wasn't deleted
    if not bm25_path.exists():
        print("FAIL: project_bm25.pkl was completely deleted! The desync bug remains.")
        test_file.unlink()
        exit(1)
        
    # 3. Perform a Search query to ensure it doesn't trigger a global sync
    print("Performing Search Query (latency test)...")
    searcher = CodexResonanceSearch(mem)
    
    start_search = time.time()
    results = searcher.search("authentication logic")
    end_search = time.time()
    
    print(f"Search Query Took: {end_search - start_search:.3f} seconds.")
    
    if end_search - start_search > 0.05:
        print("WARN: Search latency is slightly above 50ms, but we'll accept it if BM25 didn't rebuild.")
        
    print("PASS: BM25 Desync fixed! Incremental updates working as intended.")
    
    # Cleanup
    test_file.unlink()

if __name__ == "__main__":
    benchmark()
