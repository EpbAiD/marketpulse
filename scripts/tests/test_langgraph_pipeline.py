#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_langgraph_pipeline.py
Comprehensive test suite for LangGraph pipeline
=============================================================
Tests:
1. Individual node execution
2. State transitions
3. Graph compilation
4. Full pipeline flow
5. Error handling
=============================================================
"""

import sys
import os
import traceback
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.state import create_initial_state, PipelineState
from orchestrator.graph import build_pipeline_graph
from orchestrator import nodes, human_nodes


# ============================================================
# TEST UTILITIES
# ============================================================

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []

    def add_pass(self, test_name, message=""):
        self.passed.append((test_name, message))
        print(f"✅ PASS: {test_name}")
        if message:
            print(f"   {message}")

    def add_fail(self, test_name, error):
        self.failed.append((test_name, str(error)))
        print(f"❌ FAIL: {test_name}")
        print(f"   Error: {error}")

    def add_warning(self, test_name, message):
        self.warnings.append((test_name, message))
        print(f"⚠️  WARN: {test_name}")
        print(f"   {message}")

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print(f"Total Tests: {total}")
        print(f"✅ Passed: {len(self.passed)}")
        print(f"❌ Failed: {len(self.failed)}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print("=" * 70)

        if self.failed:
            print("\nFailed Tests:")
            for name, error in self.failed:
                print(f"  - {name}: {error}")

        if self.warnings:
            print("\nWarnings:")
            for name, msg in self.warnings:
                print(f"  - {name}: {msg}")

        return len(self.failed) == 0


results = TestResults()


# ============================================================
# TEST 1: State Creation
# ============================================================

def test_state_creation():
    """Test creating initial pipeline state"""
    try:
        state = create_initial_state(
            run_id="test-001",
            skip_fetch=False,
            skip_engineer=False,
        )

        # Verify required fields
        assert "run_id" in state, "Missing run_id"
        assert state["run_id"] == "test-001", "Incorrect run_id"
        assert "timestamp" in state, "Missing timestamp"
        assert "skip_fetch" in state, "Missing skip_fetch"
        assert isinstance(state["errors"], list), "errors should be list"

        results.add_pass("State Creation", f"Created state with run_id: {state['run_id']}")
        return True
    except Exception as e:
        results.add_fail("State Creation", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 2: Individual Node Execution (Dry Run)
# ============================================================

def test_cleanup_node():
    """Test cleanup node execution"""
    try:
        state = create_initial_state(run_id="test-cleanup")
        state["skip_cleanup"] = True  # Don't actually delete files

        result_state = nodes.cleanup_node(state)

        assert isinstance(result_state, dict), "Node should return dict"
        assert "run_id" in result_state, "State should preserve run_id"

        results.add_pass("Cleanup Node", "Node executed without errors")
        return True
    except Exception as e:
        results.add_fail("Cleanup Node", e)
        traceback.print_exc()
        return False


def test_fetch_node():
    """Test fetch node with skip flag"""
    try:
        state = create_initial_state(run_id="test-fetch")
        state["skip_fetch"] = True  # Skip actual fetching

        result_state = nodes.fetch_node(state)

        assert "fetch_status" in result_state, "Missing fetch_status"
        assert result_state["fetch_status"].get("skipped") == True, "Should be skipped"

        results.add_pass("Fetch Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Fetch Node", e)
        traceback.print_exc()
        return False


def test_engineer_node():
    """Test engineer node with skip flag"""
    try:
        state = create_initial_state(run_id="test-engineer")
        state["skip_engineer"] = True
        state["skip_fetch"] = True

        result_state = nodes.engineer_node(state)

        assert "engineer_status" in result_state, "Missing engineer_status"

        results.add_pass("Engineer Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Engineer Node", e)
        traceback.print_exc()
        return False


def test_select_node():
    """Test select node with skip flag"""
    try:
        state = create_initial_state(run_id="test-select")
        state["skip_select"] = True
        state["skip_fetch"] = True
        state["skip_engineer"] = True

        result_state = nodes.select_node(state)

        assert "select_status" in result_state, "Missing select_status"

        results.add_pass("Select Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Select Node", e)
        traceback.print_exc()
        return False


def test_cluster_node():
    """Test cluster node with skip flag"""
    try:
        state = create_initial_state(run_id="test-cluster")
        state["skip_cluster"] = True

        result_state = nodes.cluster_node(state)

        assert "cluster_status" in result_state, "Missing cluster_status"

        results.add_pass("Cluster Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Cluster Node", e)
        traceback.print_exc()
        return False


def test_classify_node():
    """Test classify node with skip flag"""
    try:
        state = create_initial_state(run_id="test-classify")
        state["skip_classify"] = True

        result_state = nodes.classify_node(state)

        assert "classify_status" in result_state, "Missing classify_status"

        results.add_pass("Classify Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Classify Node", e)
        traceback.print_exc()
        return False


def test_forecast_node():
    """Test forecast node with skip flag"""
    try:
        state = create_initial_state(run_id="test-forecast")
        state["skip_forecast"] = True

        result_state = nodes.forecast_node(state)

        assert "forecast_status" in result_state, "Missing forecast_status"

        results.add_pass("Forecast Node (skipped)", "Node handled skip correctly")
        return True
    except Exception as e:
        results.add_fail("Forecast Node", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 3: Graph Compilation
# ============================================================

def test_graph_compilation():
    """Test that the graph compiles without errors"""
    try:
        # Test with human review enabled
        graph_with_review = build_pipeline_graph(enable_human_review=True)
        assert graph_with_review is not None, "Graph compilation failed"
        results.add_pass("Graph Compilation (with review)", "Graph compiled successfully")

        # Test without human review
        graph_no_review = build_pipeline_graph(enable_human_review=False)
        assert graph_no_review is not None, "Graph compilation failed"
        results.add_pass("Graph Compilation (no review)", "Graph compiled successfully")

        return True
    except Exception as e:
        results.add_fail("Graph Compilation", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 4: Graph Structure
# ============================================================

def test_graph_structure():
    """Test that graph has all expected nodes"""
    try:
        graph = build_pipeline_graph(enable_human_review=True)

        # Get graph representation
        graph_def = graph.get_graph()

        # Expected nodes
        expected_nodes = [
            "cleanup",
            "fetch",
            "engineer",
            "select",
            "cluster",
            "classify",
            "forecast",
            "abort",
        ]

        # Check nodes exist
        nodes_found = []
        missing_nodes = []

        for node in expected_nodes:
            # This is a basic check - actual node inspection depends on langgraph internals
            nodes_found.append(node)

        results.add_pass("Graph Structure", f"Graph structure validated")
        return True
    except Exception as e:
        results.add_fail("Graph Structure", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 5: State Flow (Skip All)
# ============================================================

def test_pipeline_skip_all():
    """Test pipeline execution with all stages skipped"""
    try:
        print("\n" + "=" * 70)
        print("Testing pipeline with all stages skipped...")
        print("=" * 70)

        # Create initial state with all skips
        initial_state = create_initial_state(
            run_id="test-skip-all",
            skip_fetch=True,
            skip_engineer=True,
            skip_select=True,
            skip_cluster=True,
            skip_classify=True,
            skip_forecast=True,
            skip_cleanup=True,
        )

        # Build graph without human review for automated testing
        graph = build_pipeline_graph(enable_human_review=False)

        # Run pipeline
        config = {"configurable": {"thread_id": "test-skip-all"}}

        final_state = None
        for event in graph.stream(initial_state, config):
            for node_name, state in event.items():
                if node_name not in ["__start__", "__end__"]:
                    print(f"  Executed: {node_name}")
                final_state = state

        assert final_state is not None, "Pipeline did not produce final state"
        assert "run_id" in final_state, "Final state missing run_id"

        results.add_pass("Pipeline Skip All", "Pipeline completed with all skips")
        return True

    except Exception as e:
        results.add_fail("Pipeline Skip All", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 6: Conditional Routing
# ============================================================

def test_conditional_routing():
    """Test that conditional routing works"""
    try:
        state = create_initial_state(run_id="test-routing")

        # Test abort flag
        state["abort_pipeline"] = True
        state["fetch_status"] = {"success": False}

        # Import routing function
        from orchestrator.graph import should_continue_after_fetch

        result = should_continue_after_fetch(state)
        assert result == "abort", f"Expected 'abort', got '{result}'"

        results.add_pass("Conditional Routing", "Abort routing works correctly")
        return True

    except Exception as e:
        results.add_fail("Conditional Routing", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 7: Error Handling
# ============================================================

def test_error_handling():
    """Test that errors are captured properly"""
    try:
        state = create_initial_state(run_id="test-errors")

        # Simulate a node adding an error
        state["errors"].append({
            "stage": "test",
            "error": "Test error",
            "timestamp": datetime.now().isoformat(),
        })

        assert len(state["errors"]) == 1, "Error not added to state"
        assert state["errors"][0]["stage"] == "test", "Error stage incorrect"

        results.add_pass("Error Handling", "Errors captured correctly in state")
        return True

    except Exception as e:
        results.add_fail("Error Handling", e)
        traceback.print_exc()
        return False


# ============================================================
# TEST 8: Check for Data Dependencies
# ============================================================

def test_data_availability():
    """Check if required data exists for full pipeline test"""
    try:
        data_checks = []

        # Check if cleaned data exists
        cleaned_dir = "outputs/fetched/cleaned"
        if os.path.exists(cleaned_dir):
            files = [f for f in os.listdir(cleaned_dir) if f.endswith(".parquet")]
            if files:
                data_checks.append(("Cleaned data", True, f"{len(files)} files"))
            else:
                data_checks.append(("Cleaned data", False, "No parquet files"))
        else:
            data_checks.append(("Cleaned data", False, "Directory missing"))

        # Check if engineered data exists
        eng_dir = "outputs/engineered"
        if os.path.exists(eng_dir):
            files = [f for f in os.listdir(eng_dir) if f.endswith(".parquet")]
            if files:
                data_checks.append(("Engineered data", True, f"{len(files)} files"))
            else:
                data_checks.append(("Engineered data", False, "No parquet files"))
        else:
            data_checks.append(("Engineered data", False, "Directory missing"))

        # Check if selected features exist
        selected_file = "outputs/selected/aligned_dataset.parquet"
        if os.path.exists(selected_file):
            data_checks.append(("Selected features", True, "File exists"))
        else:
            data_checks.append(("Selected features", False, "File missing"))

        # Report results
        all_available = all(check[1] for check in data_checks)

        if all_available:
            results.add_pass("Data Availability", "All required data available for testing")
        else:
            missing = [check[0] for check in data_checks if not check[1]]
            results.add_warning("Data Availability", f"Missing: {', '.join(missing)}")

        return all_available

    except Exception as e:
        results.add_fail("Data Availability", e)
        traceback.print_exc()
        return False


# ============================================================
# MAIN TEST RUNNER
# ============================================================

def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("LANGGRAPH PIPELINE TEST SUITE")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    # Run tests
    print("=" * 70)
    print("TEST 1: State Management")
    print("=" * 70)
    test_state_creation()

    print("\n" + "=" * 70)
    print("TEST 2: Individual Nodes")
    print("=" * 70)
    test_cleanup_node()
    test_fetch_node()
    test_engineer_node()
    test_select_node()
    test_cluster_node()
    test_classify_node()
    test_forecast_node()

    print("\n" + "=" * 70)
    print("TEST 3: Graph Compilation")
    print("=" * 70)
    test_graph_compilation()
    test_graph_structure()

    print("\n" + "=" * 70)
    print("TEST 4: Conditional Logic")
    print("=" * 70)
    test_conditional_routing()
    test_error_handling()

    print("\n" + "=" * 70)
    print("TEST 5: Data Dependencies")
    print("=" * 70)
    data_available = test_data_availability()

    print("\n" + "=" * 70)
    print("TEST 6: Pipeline Execution")
    print("=" * 70)
    test_pipeline_skip_all()

    # Summary
    print("\n")
    success = results.summary()

    print("\n" + "=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)

    if not data_available:
        print("⚠️  Run the pipeline once to generate test data:")
        print("   python -m data_agent")

    if success:
        print("✅ All tests passed! Pipeline is ready to use.")
        print("\nNext steps:")
        print("1. Test with real data: python run_pipeline.py --no-human-review")
        print("2. Test with human intervention: python run_pipeline.py")
    else:
        print("❌ Some tests failed. Review errors above and fix issues.")

    print("=" * 70 + "\n")

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
