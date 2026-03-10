import sys
sys.path.insert(0, "d:\\codexmemory\\src\\tools")

from project_memory import ProjectMemory

def test_brace_counting():
    mem = ProjectMemory.__new__(ProjectMemory)  # Bypass __init__ for unit testing
    
    # Test 1: Braces inside double-quoted strings should NOT be counted
    lines1 = [
        'function test() {',
        '  const payload = "{ malicious }";',
        '  return payload;',
        '}'
    ]
    result = mem._find_brace_end(lines1, 0)
    assert result == 3, f"Test 1 FAILED: Expected line 3, got {result}"
    print("Test 1 PASSED: Braces inside double-quoted strings ignored.")
    
    # Test 2: Braces inside single-quoted strings
    lines2 = [
        'function test() {',
        "  const x = '{ trap }';",
        '  return x;',
        '}'
    ]
    result = mem._find_brace_end(lines2, 0)
    assert result == 3, f"Test 2 FAILED: Expected line 3, got {result}"
    print("Test 2 PASSED: Braces inside single-quoted strings ignored.")
    
    # Test 3: Braces inside line comments
    lines3 = [
        'function test() {',
        '  // don\'t forget the closing }',
        '  return 42;',
        '}'
    ]
    result = mem._find_brace_end(lines3, 0)
    assert result == 3, f"Test 3 FAILED: Expected line 3, got {result}"
    print("Test 3 PASSED: Braces inside line comments ignored.")
    
    # Test 4: Braces inside block comments
    lines4 = [
        'function test() {',
        '  /* this { comment has braces } */',
        '  return 42;',
        '}'
    ]
    result = mem._find_brace_end(lines4, 0)
    assert result == 3, f"Test 4 FAILED: Expected line 3, got {result}"
    print("Test 4 PASSED: Braces inside block comments ignored.")
    
    # Test 5: Braces inside template literals (backtick)
    lines5 = [
        'function test() {',
        '  const tpl = `{ template brace }`;',
        '  return tpl;',
        '}'
    ]
    result = mem._find_brace_end(lines5, 0)
    assert result == 3, f"Test 5 FAILED: Expected line 3, got {result}"
    print("Test 5 PASSED: Braces inside template literals ignored.")
    
    # Test 6: Multi-line block comment with braces
    lines6 = [
        'function test() {',
        '  /*',
        '   { this is a trap',
        '   } still in comment',
        '  */',
        '  return 1;',
        '}'
    ]
    result = mem._find_brace_end(lines6, 0)
    assert result == 6, f"Test 6 FAILED: Expected line 6, got {result}"
    print("Test 6 PASSED: Multi-line block comment braces ignored.")
    
    # Test 7: Nested real braces (should count normally)
    lines7 = [
        'function outer() {',
        '  if (true) {',
        '    return 1;',
        '  }',
        '}'
    ]
    result = mem._find_brace_end(lines7, 0)
    assert result == 4, f"Test 7 FAILED: Expected line 4, got {result}"
    print("Test 7 PASSED: Nested real braces counted correctly.")
    
    print("\nAll 7 tests PASSED. State machine is working correctly.")

if __name__ == "__main__":
    test_brace_counting()
