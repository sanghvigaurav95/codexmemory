import time
import threading
from pathlib import Path
from src.tools.project_memory import ProjectMemory
from src.tools.project_search import CodexResonanceSearch

def generate_fake_python(lines):
    return "\n".join([f"def search_func_{i}():\n    return 'neural matching'\n" for i in range(lines)])

def background_mutator(mem, iterations):
    test_file = Path("test_race.py")
    for i in range(iterations):
        test_file.write_text(generate_fake_python(10 + i % 5), encoding="utf-8")
        mem.update_file("test_race.py")
        time.sleep(0.01) # Small sleep to yield to main thread

def benchmark():
    mem = ProjectMemory(Path("."))
    
    # 1. Provide initial memory build
    print("Building initial project index...")
    mem.file_contents["test_race.py"] = generate_fake_python(10)
    mem._build_code_structure()
    mem.build()
    
    searcher = CodexResonanceSearch(mem)
    
    # 2. Start intense background mutations
    print("Spawning background Delta Watcher thread...")
    mutator_thread = threading.Thread(target=background_mutator, args=(mem, 200))
    mutator_thread.start()
    
    # 3. Bombard the search endpoint simultaneously
    print("Bombarding search endpoint with concurrent queries...")
    successful_searches = 0
    start_time = time.time()
    
    for i in range(200):
        try:
            results = searcher.search("neural matching")
            successful_searches += 1
        except IndexError as e:
            import traceback
            print(f"\nFAIL: Caught IndexError (Race Condition) on query {i}!")
            traceback.print_exc()
            exit(1)
        except Exception as e:
            import traceback
            print(f"\nFAIL: Caught Exception (Race Condition) on query {i}! {e}")
            traceback.print_exc()
            exit(1)
            
        time.sleep(0.01)
        
    mutator_thread.join()
    
    print(f"Executed {successful_searches} stable concurrent searches during live mutations.")
    print("PASS: Thread-Unsafe Reads fixed! Lock mechanisms working as intended.")
    
    Path("test_race.py").unlink()

if __name__ == "__main__":
    benchmark()
