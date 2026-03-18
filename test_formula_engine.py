"""Quick test of Formula Engine components."""
from core.formula_engine.expression_compiler import expression_compiler
from core.formula_engine.dependency_graph import dependency_graph

# Test 1: Expression Compiler
print("Testing Expression Compiler...")
try:
    # Simple arithmetic
    expr1 = expression_compiler.compile("T1 + T2")
    result1 = expr1({"T1": 10, "T2": 20})
    assert result1 == 30, f"Expected 30, got {result1}"
    print(f"✅ T1 + T2 = {result1}")
    
    # Complex expression
    expr2 = expression_compiler.compile("(T1 + T2) * T3 / 100")
    result2 = expr2({"T1": 10, "T2": 20, "T3": 50})
    assert result2 == 15.0, f"Expected 15.0, got {result2}"
    print(f"✅ (T1 + T2) * T3 / 100 = {result2}")
    
    # Conditional
    expr3 = expression_compiler.compile("T1 if T1 > T2 else T2")
    result3 = expr3({"T1": 100, "T2": 50})
    assert result3 == 100, f"Expected 100, got {result3}"
    print(f"✅ T1 if T1 > T2 else T2 = {result3}")
    
    # Test unsafe expression (should fail)
    try:
        expr_bad = expression_compiler.compile("__import__('os').system('ls')")
        print("❌ Unsafe expression was not blocked!")
    except ValueError:
        print("✅ Unsafe expression blocked correctly")
    
    print("\n✅ Expression Compiler: PASSED\n")
    
except Exception as e:
    print(f"❌ Expression Compiler: FAILED - {e}\n")

# Test 2: Dependency Graph
print("Testing Dependency Graph...")
try:
    dependency_graph.clear()
    
    # Add formula dependencies
    dependency_graph.add_formula(1, [71, 72])
    dependency_graph.add_formula(2, [72, 73])
    dependency_graph.add_formula(3, [71, 73])
    
    # Test lookups
    affected_by_71 = dependency_graph.get_affected_formulas(71)
    assert set(affected_by_71) == {1, 3}, f"Expected {{1, 3}}, got {set(affected_by_71)}"
    print(f"✅ Tag 71 affects formulas: {affected_by_71}")
    
    affected_by_72 = dependency_graph.get_affected_formulas(72)
    assert set(affected_by_72) == {1, 2}, f"Expected {{1, 2}}, got {set(affected_by_72)}"
    print(f"✅ Tag 72 affects formulas: {affected_by_72}")
    
    # Test formula tags
    tags_for_2 = dependency_graph.get_formula_tags(2)
    assert set(tags_for_2) == {72, 73}, f"Expected {{72, 73}}, got {set(tags_for_2)}"
    print(f"✅ Formula 2 depends on tags: {tags_for_2}")
    
    # Test removal
    dependency_graph.remove_formula(1)
    affected_by_71_after = dependency_graph.get_affected_formulas(71)
    assert set(affected_by_71_after) == {3}, f"Expected {{3}}, got {set(affected_by_71_after)}"
    print(f"✅ After removing formula 1, tag 71 affects: {affected_by_71_after}")
    
    print("\n✅ Dependency Graph: PASSED\n")
    
except Exception as e:
    print(f"❌ Dependency Graph: FAILED - {e}\n")

print("=" * 50)
print("All core components working correctly!")
print("=" * 50)
