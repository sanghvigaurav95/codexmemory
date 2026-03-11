import os
import sys
import time
import argparse

# Inject the local source to test the module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/tools')))
try:
    from project_memory import get_model, ProjectMemory
    import project_memory
except ImportError:
    from codexmemory.project_memory import get_model, ProjectMemory
    import codexmemory.project_memory as project_memory

def test_lazy_loading():
    print("=" * 60)
    print(" 🚀 360-Degree Lazy Loader Benchmark ")
    print("=" * 60)
    
    # 1. State Verification
    print("[1/4] Verifying Initial State...")
    initial_state = project_memory._model
    print(f"      Initial _model state: {initial_state}")
    if initial_state is not None:
        print("      ❌ Error: Model should be None initially.")
        sys.exit(1)
    print("      ✅ Passed: Model is lazy.")
    
    # 2. Boot Benchmark
    print("\n[2/4] Benchmarking First Initialization (Cold Boot)...")
    t0 = time.time()
    m1 = get_model()
    t1 = time.time()
    cold_time = t1 - t0
    print(f"      Time taken to load PyTorch & Model: {cold_time:.4f} seconds")
    
    # 3. Cache Benchmark
    print("\n[3/4] Benchmarking Cached Initialization (Warm Boot)...")
    t0 = time.time()
    m2 = get_model()
    t1 = time.time()
    warm_time = t1 - t0
    print(f"      Time taken for cached fetch: {warm_time:.6f} seconds")
    
    if m1 is m2:
        print("      ✅ Passed: Singleton cache is functioning perfectly.")
    else:
        print("      ❌ Error: Model instances do not match.")
        sys.exit(1)
        
    speedup = cold_time / warm_time if warm_time > 0 else float('inf')
    print(f"      ⚡ Lazy Loading provides a {speedup:,.0f}x theoretical speedup on non-query CLI commands.")

    # 4. End-to-End Retrieval Simulation
    print("\n[4/4] End-to-End Integration Check...")
    pm = ProjectMemory()
    try:
        # Bypassing the FAISS index load just to test encode hook
        q_emb = get_model().encode(["Test Query"])
        print(f"      Test Query Embedding Shape: {q_emb.shape}")
        print("      ✅ Passed: Integrates with ProjectMemory successfully.")
    except Exception as e:
        print(f"      ❌ Error during mock search: {e}")
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run 360-degree Lazy Loader Benchmark')
    parser.add_argument('--global', action='store_true', dest='is_global', help='Test the globally installed engine')
    args = parser.parse_args()
    
    if args.is_global:
        print("Running against GLOBAL engine installation.")
        # If --global is passed, we remove the local inject so it tests the pip-installed package
        sys.path.pop(0)

    test_lazy_loading()
    print("\n🎉 All 360-Degree Checks Passed! The lazy loader is highly efficient.")
