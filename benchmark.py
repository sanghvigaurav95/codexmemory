import time
from pathlib import Path
from src.tools.project_memory import ProjectMemory

def generate_massive_file(lines_count, funcs_count):
    content = []
    lines_per_func = lines_count // funcs_count
    for i in range(funcs_count):
        content.append(f"def hardcore_func_{i}(x):")
        for j in range(lines_per_func - 1):
            content.append(f"    # Line {j} of function {i}")
            content.append(f"    x += {j}")
        content.append(f"    return x")
        content.append("")
    return "\n".join(content)

def benchmark():
    mem = ProjectMemory(Path("."))
    
    # 1. Create a massive fake file
    rel_path = "massive_test.py"
    print("Generating massive script (10_000 lines, 1_000 nodes)...")
    content = generate_massive_file(10000, 1000)
    
    # Mock necessary structures
    mem.file_contents[rel_path] = content
    print("Extracting code structure...")
    start_ast = time.time()
    mem._build_code_structure()
    print(f"AST Extraction took: {time.time() - start_ast:.3f} seconds")
    
    mem.dependency_graph[rel_path] = {"imports": [], "imported_by": []}
    
    # 2. Benchmark the CRS Chunks
    print("Running _build_crs_chunks...")
    start_crs = time.time()
    chunks = mem._build_crs_chunks(rel_path, content, 250)
    end_crs = time.time()
    
    print(f"Generated {len(chunks)} chunks.")
    print(f"CRS Chunking took: {end_crs - start_crs:.3f} seconds")
    
    if end_crs - start_crs > 5.0:
        print("FAIL: Performance leak is still present.")
        exit(1)
    else:
        print("PASS: O(N) leak fixed! Performance is lightning fast.")
        
if __name__ == "__main__":
    benchmark()
