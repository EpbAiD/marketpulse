#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
graph.py
LangGraph Pipeline Orchestrator
=============================================================
Defines the complete RFP pipeline as a LangGraph StateGraph
with conditional routing and human-in-the-loop checkpoints.
=============================================================
"""

from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.state import PipelineState
from orchestrator.nodes import (
    cleanup_node,
    fetch_node,
    engineer_node,
    select_node,
    cluster_node,
    classify_node,
    forecast_node,
)
from orchestrator.human_nodes import (
    review_fetch_node,
    review_engineer_node,
    review_select_node,
    review_cluster_node,
    review_classify_node,
    review_forecast_node,
)
from orchestrator.inference_nodes import (
    inference_node,
    alerts_node,
    validation_node,
    monitoring_node,
)


# ============================================================
# CONDITIONAL ROUTING FUNCTIONS
# ============================================================

def should_continue_after_fetch(state: PipelineState) -> Literal["abort", "review_fetch"]:
    """Route after fetch: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("fetch_status", {}).get("success", False) and not state.get("skip_fetch", False):
        return "abort"
    return "review_fetch"


def should_continue_after_fetch_review(state: PipelineState) -> Literal["abort", "engineer"]:
    """Route after fetch review: abort if not approved, otherwise engineer."""
    if state.get("abort_pipeline", False) or not state.get("fetch_approved", False):
        return "abort"
    return "engineer"


def should_continue_after_engineer(state: PipelineState) -> Literal["abort", "review_engineer"]:
    """Route after engineer: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("engineer_status", {}).get("success", False) and not state.get("skip_engineer", False):
        return "abort"
    return "review_engineer"


def should_continue_after_engineer_review(state: PipelineState) -> Literal["abort", "select"]:
    """Route after engineer review: abort if not approved, otherwise select."""
    if state.get("abort_pipeline", False) or not state.get("engineer_approved", False):
        return "abort"
    return "select"


def should_continue_after_select(state: PipelineState) -> Literal["abort", "review_select"]:
    """Route after select: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("select_status", {}).get("success", False) and not state.get("skip_select", False):
        return "abort"
    return "review_select"


def should_continue_after_select_review(state: PipelineState) -> Literal["abort", "parallel_agents"]:
    """Route after select review: abort if not approved, otherwise run parallel agents."""
    if state.get("abort_pipeline", False) or not state.get("select_approved", False):
        return "abort"
    return "parallel_agents"


def route_parallel_agents(state: PipelineState) -> list[str]:
    """
    Determine which agents to run in parallel after feature selection.
    Returns a list of node names to execute concurrently.
    """
    agents = []

    # Add cluster if not skipped
    if not state.get("skip_cluster", False):
        agents.append("cluster")

    # Add classify if not skipped (depends on cluster)
    if not state.get("skip_classify", False) and not state.get("skip_cluster", False):
        agents.append("classify")

    # Add forecast if not skipped
    if not state.get("skip_forecast", False):
        agents.append("forecast")

    return agents if agents else ["end"]


def should_continue_after_cluster(state: PipelineState) -> Literal["abort", "review_cluster"]:
    """Route after cluster: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("cluster_status", {}).get("success", False) and not state.get("skip_cluster", False):
        return "abort"
    return "review_cluster"


def should_continue_after_cluster_review(state: PipelineState) -> Literal["abort", "classify", "end"]:
    """Route after cluster review: retry, classify, or abort."""
    if state.get("abort_pipeline", False) or not state.get("cluster_approved", False):
        return "abort"

    # Check if we should retry clustering with different params
    if state.get("retry_stage") == "cluster":
        state["retry_stage"] = None  # Clear retry flag
        return "cluster"

    # Proceed to classification if not skipped
    if not state.get("skip_classify", False):
        return "classify"

    return "end"


def should_continue_after_classify(state: PipelineState) -> Literal["abort", "review_classify"]:
    """Route after classify: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("classify_status", {}).get("success", False) and not state.get("skip_classify", False):
        return "abort"
    return "review_classify"


def should_continue_after_classify_review(state: PipelineState) -> Literal["abort", "end"]:
    """Route after classify review: end or abort."""
    if state.get("abort_pipeline", False) or not state.get("classify_approved", False):
        return "abort"
    return "end"


def should_continue_after_forecast(state: PipelineState) -> Literal["abort", "review_forecast"]:
    """Route after forecast: abort if failed, otherwise review."""
    if state.get("abort_pipeline", False):
        return "abort"
    if not state.get("forecast_status", {}).get("success", False) and not state.get("skip_forecast", False):
        return "abort"
    return "review_forecast"


def should_continue_after_forecast_review(state: PipelineState) -> Literal["abort", "end"]:
    """Route after forecast review: end or abort."""
    if state.get("abort_pipeline", False) or not state.get("forecast_approved", False):
        return "abort"
    return "end"


# ============================================================
# ABORT NODE
# ============================================================
def abort_node(state: PipelineState) -> PipelineState:
    """Handle pipeline abortion."""
    print("\n" + "=" * 70)
    print("⛔ PIPELINE ABORTED")
    print("=" * 70)

    # Show errors if any
    if state.get("errors"):
        print("\n❌ Errors encountered:")
        for error in state["errors"]:
            print(f"   • [{error['stage']}] {error['error']}")

    # Show which stage caused abort
    for stage in ["fetch", "engineer", "select", "cluster", "classify", "forecast"]:
        if not state.get(f"{stage}_approved", True):
            print(f"\n🚫 Pipeline aborted at: {stage} (not approved by user)")
            break

    print("\n" + "=" * 70)
    return state


# ============================================================
# BUILD GRAPH
# ============================================================
def build_pipeline_graph(enable_human_review: bool = True) -> StateGraph:
    """
    Construct the LangGraph StateGraph for the RFP pipeline.

    Args:
        enable_human_review: If True, includes human checkpoint nodes.
                            If False, runs fully automated.

    Returns:
        Compiled StateGraph ready for execution
    """
    # Initialize graph
    workflow = StateGraph(PipelineState)

    # Add all agent nodes
    workflow.add_node("cleanup", cleanup_node)
    workflow.add_node("fetch", fetch_node)
    workflow.add_node("engineer", engineer_node)
    workflow.add_node("select", select_node)
    workflow.add_node("cluster", cluster_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("forecast", forecast_node)
    workflow.add_node("abort", abort_node)

    # Add human review nodes if enabled
    if enable_human_review:
        workflow.add_node("review_fetch", review_fetch_node)
        workflow.add_node("review_engineer", review_engineer_node)
        workflow.add_node("review_select", review_select_node)
        workflow.add_node("review_cluster", review_cluster_node)
        workflow.add_node("review_classify", review_classify_node)
        workflow.add_node("review_forecast", review_forecast_node)

    # ========== DEFINE FLOW ==========

    # Start with cleanup
    workflow.set_entry_point("cleanup")
    workflow.add_edge("cleanup", "fetch")

    # Fetch → Review (or abort)
    workflow.add_conditional_edges(
        "fetch",
        should_continue_after_fetch,
        {
            "review_fetch": "review_fetch" if enable_human_review else "engineer",
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Fetch → Engineer (or abort)
        workflow.add_conditional_edges(
            "review_fetch",
            should_continue_after_fetch_review,
            {
                "engineer": "engineer",
                "abort": "abort",
            }
        )

    # Engineer → Review (or abort)
    workflow.add_conditional_edges(
        "engineer",
        should_continue_after_engineer,
        {
            "review_engineer": "review_engineer" if enable_human_review else "select",
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Engineer → Select (or abort)
        workflow.add_conditional_edges(
            "review_engineer",
            should_continue_after_engineer_review,
            {
                "select": "select",
                "abort": "abort",
            }
        )

    # Select → Review (or abort)
    workflow.add_conditional_edges(
        "select",
        should_continue_after_select,
        {
            "review_select": "review_select" if enable_human_review else "cluster",
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Select → Parallel Agents
        workflow.add_conditional_edges(
            "review_select",
            should_continue_after_select_review,
            {
                "parallel_agents": "cluster",  # Start with cluster
                "abort": "abort",
            }
        )

    # Cluster → Review (or abort)
    workflow.add_conditional_edges(
        "cluster",
        should_continue_after_cluster,
        {
            "review_cluster": "review_cluster" if enable_human_review else "classify",
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Cluster → Classify (or retry/abort)
        workflow.add_conditional_edges(
            "review_cluster",
            should_continue_after_cluster_review,
            {
                "cluster": "cluster",  # Retry if requested
                "classify": "classify",
                "abort": "abort",
                "end": END,
            }
        )

    # Classify → Review (or abort)
    workflow.add_conditional_edges(
        "classify",
        should_continue_after_classify,
        {
            "review_classify": "review_classify" if enable_human_review else "forecast",
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Classify → Forecast
        workflow.add_conditional_edges(
            "review_classify",
            should_continue_after_classify_review,
            {
                "end": "forecast",  # Continue to forecast
                "abort": "abort",
            }
        )

    # Forecast → Review (or abort)
    workflow.add_conditional_edges(
        "forecast",
        should_continue_after_forecast,
        {
            "review_forecast": "review_forecast" if enable_human_review else END,
            "abort": "abort",
        }
    )

    if enable_human_review:
        # Review Forecast → End
        workflow.add_conditional_edges(
            "review_forecast",
            should_continue_after_forecast_review,
            {
                "end": END,
                "abort": "abort",
            }
        )

    # Abort always goes to END
    workflow.add_edge("abort", END)

    # Compile graph with checkpointer for state persistence
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# BUILD COMPLETE GRAPH (Training + Inference + Monitoring)
# ============================================================
def build_complete_graph(workflow_type: str = "full", enable_human_review: bool = False):
    """
    Build unified LangGraph with all workflow types.

    Args:
        workflow_type: "training", "inference", or "full"
        enable_human_review: Enable human checkpoint nodes

    Returns:
        Compiled StateGraph
    """
    workflow = StateGraph(PipelineState)

    # ========== ADD ALL NODES ==========

    # Training nodes
    workflow.add_node("cleanup", cleanup_node)
    workflow.add_node("fetch", fetch_node)
    workflow.add_node("engineer", engineer_node)
    workflow.add_node("select", select_node)
    workflow.add_node("cluster", cluster_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("forecast", forecast_node)

    # Inference/monitoring nodes
    workflow.add_node("inference", inference_node)
    workflow.add_node("alerts", alerts_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("monitoring", monitoring_node)

    # Abort node
    workflow.add_node("abort", abort_node)

    # ========== DEFINE WORKFLOW ==========

    # Entry point: cleanup
    workflow.set_entry_point("cleanup")

    # Route after cleanup based on workflow type
    def route_after_cleanup(state):
        wf_type = state.get("workflow_type", "full")
        # All workflows start with data fetch to ensure latest data
        return "fetch"

    workflow.add_conditional_edges(
        "cleanup",
        route_after_cleanup,
        {"fetch": "fetch"}
    )

    # ========== TRAINING WORKFLOW ==========
    # fetch → engineer → select → cluster → classify → forecast

    # Route after fetch based on workflow type
    def route_after_fetch(state):
        wf_type = state.get("workflow_type", "full")
        if wf_type == "inference":
            # Inference workflow: skip training, go straight to inference
            return "inference"
        else:
            # Training/full workflow: continue with engineering
            return "engineer"

    workflow.add_conditional_edges(
        "fetch",
        route_after_fetch,
        {"engineer": "engineer", "inference": "inference"}
    )

    workflow.add_edge("engineer", "select")
    workflow.add_edge("select", "cluster")
    workflow.add_edge("cluster", "classify")
    workflow.add_edge("classify", "forecast")

    # After training: route to inference or end
    def route_after_forecast(state):
        if state.get("workflow_type") == "full":
            return "inference"
        return "end"

    workflow.add_conditional_edges(
        "forecast",
        route_after_forecast,
        {"inference": "inference", "end": END}
    )

    # ========== INFERENCE WORKFLOW ==========
    # inference → alerts → validation → monitoring

    workflow.add_edge("inference", "alerts")
    workflow.add_edge("alerts", "validation")
    workflow.add_edge("validation", "monitoring")

    # After monitoring: check if retraining needed
    def route_after_monitoring(state):
        if state.get("needs_retraining", False) and state.get("workflow_type") == "full":
            # Retrain: go back to fetch (full training cycle)
            return "retrain"
        return "end"

    workflow.add_conditional_edges(
        "monitoring",
        route_after_monitoring,
        {"retrain": "fetch", "end": END}
    )

    # Abort always goes to END
    workflow.add_edge("abort", END)

    # Compile graph with checkpointer
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


# ============================================================
# GRAPH VISUALIZATION
# ============================================================
def visualize_graph(output_path: str = "outputs/pipeline_graph.png"):
    """
    Generate a visual representation of the pipeline graph.

    Args:
        output_path: Where to save the graph image
    """
    try:
        from data_agent.utils import ensure_dir
        import os

        graph = build_complete_graph(workflow_type="full", enable_human_review=False)

        # Get mermaid representation
        mermaid = graph.get_graph().draw_mermaid()

        # Save to file
        ensure_dir(os.path.dirname(output_path))
        with open(output_path.replace(".png", ".mmd"), "w") as f:
            f.write(mermaid)

        print(f"✅ Graph diagram saved to: {output_path.replace('.png', '.mmd')}")
        print("   (View at https://mermaid.live)")

    except Exception as e:
        print(f"⚠️  Could not generate graph visualization: {e}")
