"""
main.py
────────
Offline Emergency Intelligence Hub — Main Orchestrator

This file wires together all agents using LangGraph for orchestration.
Supports two modes:
  1. Voice mode  — capture microphone audio → transcribe → pipeline
  2. Text mode   — pass text directly (for demo/testing)

Usage:
  # Text mode (no microphone needed)
  python main.py --text "Elderly man with leg fracture trapped in flooded building"

  # Voice mode (5 second recording)
  python main.py --voice --duration 5

  # Launch Streamlit dashboard
  streamlit run ui/dashboard.py
"""

import os
import sys
import time
import json
import argparse
from typing import TypedDict, Optional, Any, Dict

# ── LangGraph imports ──
from langgraph.graph import StateGraph, END

# ── Agent imports ──
from agents.intake_agent import run_intake_agent
from agents.triage_agent import run_triage_agent
from agents.knowledge_graph_agent import run_knowledge_graph_agent
from agents.protocol_agent import run_protocol_agent
from agents.resource_agent import run_resource_agent
from agents.response_agent import run_response_agent

# ── Logging / history ──
from data.incident_logger import log_incident, log_agent_run


# ────────────────────────────────────────────────────────────
# LangGraph State Schema
# ────────────────────────────────────────────────────────────

class EmergencyState(TypedDict):
    """
    Shared state passed between all agents in the graph.
    Each agent reads from and writes to this state.
    """
    # Input
    transcription: str

    # Agent outputs (populated as pipeline runs)
    intake_context: Optional[Dict]
    triage_result: Optional[Dict]
    kg_data: Optional[Dict]
    protocol_data: Optional[Dict]
    resource_data: Optional[Dict]
    final_response: Optional[Dict]

    # Metadata
    start_time: float
    agent_logs: list


# ────────────────────────────────────────────────────────────
# Agent Node Functions (LangGraph nodes)
# ────────────────────────────────────────────────────────────

def intake_node(state: EmergencyState) -> EmergencyState:
    """Node 1: Extract structured context from transcription."""
    log = "[Intake Agent] Extracting emergency context..."
    state["agent_logs"].append(log)
    print(log)

    state["intake_context"] = run_intake_agent(state["transcription"])
    state["agent_logs"].append(
        f"[Intake Agent] Victim: {state['intake_context']['victim']}, "
        f"Injury: {state['intake_context']['injury']}, "
        f"Location: {state['intake_context'].get('location_hint', 'unknown')}"
    )
    return state


def triage_node(state: EmergencyState) -> EmergencyState:
    """Node 2: Classify emergency severity."""
    log = "[Triage Agent] Classifying severity..."
    state["agent_logs"].append(log)
    print(log)

    state["triage_result"] = run_triage_agent(state["intake_context"])
    state["agent_logs"].append(
        f"[Triage Agent] Severity: {state['triage_result']['severity']} "
        f"(confidence: {state['triage_result']['confidence']} — "
        f"{state['triage_result'].get('confidence_label', '')})"
    )
    return state


def knowledge_graph_node(state: EmergencyState) -> EmergencyState:
    """Node 3: Query knowledge graph for treatments and resources."""
    log = "[Knowledge Graph Agent] Querying injury-treatment relationships..."
    state["agent_logs"].append(log)
    print(log)

    state["kg_data"] = run_knowledge_graph_agent(
        state["intake_context"],
        state["triage_result"]
    )
    state["agent_logs"].append(
        f"[Knowledge Graph Agent] Found {len(state['kg_data']['required_resources'])} resources, "
        f"{len(state['kg_data']['recommended_treatments'])} treatments"
    )
    return state


def protocol_node(state: EmergencyState) -> EmergencyState:
    """Node 4: Retrieve protocol instructions via offline RAG."""
    log = "[Protocol Agent] Retrieving treatment protocols (offline RAG)..."
    state["agent_logs"].append(log)
    print(log)

    state["protocol_data"] = run_protocol_agent(
        state["intake_context"],
        state["kg_data"]
    )
    state["agent_logs"].append(
        f"[Protocol Agent] Retrieved protocol (relevance: "
        f"{state['protocol_data'].get('top_relevance', 0):.2f})"
    )
    return state


def resource_node(state: EmergencyState) -> EmergencyState:
    """Node 5: Check local inventory for required resources."""
    log = "[Resource Agent] Checking inventory..."
    state["agent_logs"].append(log)
    print(log)

    state["resource_data"] = run_resource_agent(state["kg_data"])
    avail = state["resource_data"].get("available_count", 0)
    total = state["resource_data"].get("total_count", 0)
    low_stock = state["resource_data"].get("low_stock_alerts", [])
    log_msg = f"[Resource Agent] {avail}/{total} items available in inventory"
    if low_stock:
        log_msg += f" | ⚠️ Low stock: {', '.join(a['item'] for a in low_stock)}"
    state["agent_logs"].append(log_msg)
    return state


def response_node(state: EmergencyState) -> EmergencyState:
    """Node 6: Generate final emergency response."""
    log = "[Response Agent] Generating final report..."
    state["agent_logs"].append(log)
    print(log)

    state["final_response"] = run_response_agent(
        state["intake_context"],
        state["triage_result"],
        state["kg_data"],
        state["protocol_data"],
        state["resource_data"],
    )

    elapsed = time.time() - state["start_time"]
    state["agent_logs"].append(
        f"[Response Agent] Complete in {elapsed:.2f}s | "
        f"Severity: {state['final_response']['severity_display']}"
    )

    # ── Feature 4: Log incident to history ──
    incident_id = log_incident(
        context=state["intake_context"],
        triage=state["triage_result"],
        resource_data=state["resource_data"],
        elapsed_seconds=elapsed,
    )
    state["final_response"]["incident_id"] = incident_id

    # ── Feature 7: Log structured agent execution ──
    log_agent_run(
        incident_id=incident_id,
        agent_logs=state["agent_logs"],
        context=state["intake_context"],
        triage=state["triage_result"],
        elapsed_seconds=elapsed,
    )

    return state


# ────────────────────────────────────────────────────────────
# Build LangGraph Pipeline
# ────────────────────────────────────────────────────────────

def build_emergency_pipeline() -> Any:
    """
    Construct the LangGraph multi-agent pipeline.

    Graph topology (linear):
    intake → triage → knowledge_graph → protocol → resource → response → END
    """
    builder = StateGraph(EmergencyState)

    # Add nodes
    builder.add_node("intake",          intake_node)
    builder.add_node("triage",          triage_node)
    builder.add_node("knowledge_graph", knowledge_graph_node)
    builder.add_node("protocol",        protocol_node)
    builder.add_node("resource",        resource_node)
    builder.add_node("response",        response_node)

    # Define edges (linear pipeline)
    builder.set_entry_point("intake")
    builder.add_edge("intake",          "triage")
    builder.add_edge("triage",          "knowledge_graph")
    builder.add_edge("knowledge_graph", "protocol")
    builder.add_edge("protocol",        "resource")
    builder.add_edge("resource",        "response")
    builder.add_edge("response",        END)

    return builder.compile()


# ────────────────────────────────────────────────────────────
# Main Processing Function
# ────────────────────────────────────────────────────────────

def process_emergency(transcription: str) -> Dict:
    """
    Run the full emergency AI pipeline on a transcription.

    Args:
        transcription: Emergency request text

    Returns:
        Final response dict with all agent outputs
    """
    print("\n" + "═" * 60)
    print("🚨  EMERGENCY AI HUB — PROCESSING REQUEST")
    print("═" * 60)
    print(f"Input: \"{transcription}\"\n")

    # Initialize state
    initial_state: EmergencyState = {
        "transcription": transcription,
        "intake_context": None,
        "triage_result": None,
        "kg_data": None,
        "protocol_data": None,
        "resource_data": None,
        "final_response": None,
        "start_time": time.time(),
        "agent_logs": [
            f"[Speech Module] Transcription received: \"{transcription[:80]}...\""
            if len(transcription) > 80 else
            f"[Speech Module] Transcription received: \"{transcription}\""
        ],
    }

    # Build and run pipeline
    pipeline = build_emergency_pipeline()
    final_state = pipeline.invoke(initial_state)

    # Print agent logs
    print("\n" + "─" * 60)
    print("📋  AGENT EXECUTION LOG")
    print("─" * 60)
    for log in final_state["agent_logs"]:
        print(f"  {log}")

    # Print final response summary
    response = final_state["final_response"]
    print("\n" + "═" * 60)
    print(f"🚨  EMERGENCY RESPONSE: {response['severity_display']}")
    print("═" * 60)
    print(f"  Victim:      {response['victim']}")
    print(f"  Injury:      {response['injury']}")
    print(f"  Situation:   {response['situation']}")
    print(f"\n  PROTOCOL STEPS:")
    for i, step in enumerate(response["protocol_steps"][:5], 1):
        print(f"    {i}. {step}")
    print(f"\n  RESOURCES:")
    for r in response["resources"]:
        print(f"    {r.get('display', r['item'])}")
    print("═" * 60 + "\n")

    return final_state


def voice_mode(duration: int = 5) -> Dict:
    """
    Run pipeline with live microphone input using sounddevice + faster-whisper.

    Workflow:
      1. Show countdown so operator knows when to speak
      2. Capture audio via sounddevice (blocking)
      3. Transcribe with faster-whisper (int8 quantized, CPU)
      4. Feed transcription into the LangGraph pipeline

    Args:
        duration: Recording duration in seconds (default 5)

    Returns:
        Final pipeline state
    """
    try:
        from speech.speech_to_text import record_and_transcribe, SOUNDDEVICE_AVAILABLE, WHISPER_AVAILABLE
    except ImportError as e:
        print(f"[Speech Module] ❌ Import error: {e}")
        print("[Speech Module] Install deps: pip install sounddevice faster-whisper")
        sys.exit(1)

    if not SOUNDDEVICE_AVAILABLE:
        print("[Speech Module] ❌ sounddevice not installed.")
        print("  Run: pip install sounddevice")
        sys.exit(1)

    if not WHISPER_AVAILABLE:
        print("[Speech Module] ❌ faster-whisper not installed.")
        print("  Run: pip install faster-whisper")
        sys.exit(1)

    print("\n" + "═" * 60)
    print("🎤  LIVE MICROPHONE MODE")
    print("═" * 60)
    print(f"  Recording duration : {duration} seconds")
    print(f"  Sample rate        : 16000 Hz (Whisper standard)")
    print(f"  Model              : Whisper tiny (int8, CPU)")
    print()

    # Countdown before recording
    for i in range(3, 0, -1):
        print(f"  Starting in {i}...", end="\r")
        time.sleep(1)
    print("  🔴 RECORDING NOW — Describe the emergency clearly...   ")

    transcription = record_and_transcribe(duration=duration)

    if not transcription.strip():
        print("[Speech Module] ⚠️  No speech detected. Please try again.")
        sys.exit(1)

    print(f"\n[Speech Module] ✅ Transcribed: \"{transcription}\"")
    return process_emergency(transcription)


# ────────────────────────────────────────────────────────────
# CLI Entry Point
# ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Offline Emergency Intelligence Hub"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--text", "-t",
        type=str,
        help="Process a text emergency request directly"
    )
    group.add_argument(
        "--voice", "-v",
        action="store_true",
        help="Capture voice input from microphone"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=5,
        help="Voice recording duration in seconds (default: 5)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Save JSON output to file"
    )

    args = parser.parse_args()

    if args.text:
        final_state = process_emergency(args.text)
    else:
        final_state = voice_mode(duration=args.duration)

    # Optionally save output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(final_state["final_response"], f, indent=2, default=str)
        print(f"\nOutput saved to: {args.output}")
