# REFRESH MARKER: 2026-03-14 18:26
"""
command_center.py
─────────────────────────────────────────────────────────────
Offline Disaster Response Command Center — v4 ELITE EDITION

Extends v3 with 3 new pipeline nodes:
  llm_triage_node, photo_triage_node, vitals_check_node

Usage:
  python command_center.py --text "Bus accident with 12 injured near bridge"
  python command_center.py --voice --duration 7
  streamlit run ui/command_dashboard.py
"""

import os, sys, time, json, argparse
from typing import TypedDict, Optional, Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langgraph.graph import StateGraph, END

from agents.intake_agent          import run_intake_agent
from agents.triage_agent          import run_triage_agent
from agents.knowledge_graph_agent import run_knowledge_graph_agent
from agents.protocol_agent        import run_protocol_agent
from agents.resource_agent        import run_resource_agent
from agents.response_agent        import run_response_agent
from agents.multi_victim_detector import run_multi_victim_detector
from command.incident_manager     import create_incident, assign_incident, get_stats
from command.responder_manager    import auto_assign, seed_default_teams
from command.equipment_dispatch   import dispatch_equipment
from command.triage_assistant     import get_triage_steps
from command.risk_predictor       import predict_risks, estimate_survival_probability
from modes.disaster_profiles      import get_active_profile, get_severity_override
from utils.system_state           import get_state, is_speech_enabled
from agents.llm_triage_agent      import run_llm_triage_agent
from agents.photo_triage_agent    import run_photo_triage_agent
from command.vitals_tracker       import log_vitals
from utils.access_control         import initialize_access_config
from utils.geocoder               import geocode_location


class CommandState(TypedDict):
    transcription:       str
    intake_context:      Optional[Dict]
    triage_result:       Optional[Dict]
    kg_data:             Optional[Dict]
    protocol_data:       Optional[Dict]
    resource_data:       Optional[Dict]
    final_response:      Optional[Dict]
    victim_analysis:     Optional[Dict]
    risk_analysis:       Optional[Dict]
    survival_data:       Optional[Dict]
    triage_steps:        Optional[Dict]
    incident_record:     Optional[Dict]
    assignment:          Optional[str]
    dispatch_results:    Optional[List]
    llm_triage_result:   Optional[Dict]
    photo_triage_result: Optional[Dict]
    photo_bytes:         Optional[bytes]
    photo_media_type:    str
    vitals_log_result:   Optional[Dict]
    triage_method:       str
    llm_latency_ms:      Optional[float]
    language_result:     Optional[Dict]
    location_hint:       Optional[str]
    start_time:          float
    agent_logs:          List


def intake_node(state):
    state["agent_logs"].append("[Intake] Extracting emergency context...")
    state["intake_context"] = run_intake_agent(state["transcription"])
    
    # Prioritize manual location input if provided
    loc_hint = state.get("location_hint")
    if loc_hint:
        state["intake_context"]["location_hint"] = loc_hint
        # Attempt to geocode
        coords = geocode_location(loc_hint)
        if coords:
            state["intake_context"]["coordinates"] = f"{coords[0]}, {coords[1]}"
            state["agent_logs"].append(f"[Intake] Resolved location: {coords}")
        
    ctx = state["intake_context"]
    state["agent_logs"].append(f"[Intake] victim={ctx['victim']} injury={ctx['injury']} location={ctx.get('location_hint')}")
    return state

def multi_victim_node(state):
    state["agent_logs"].append("[Multi-Victim] Analysing victim count...")
    prelim = "HIGH" if any(kw in state["transcription"].lower() for kw in ["critical","unconscious","cardiac","multiple","bus","train"]) else "MEDIUM"
    
    # Pass intake_context if available so we can scale required teams based on hazards
    ctx = state.get("intake_context", None)
    state["victim_analysis"] = run_multi_victim_detector(state["transcription"], prelim, context=ctx)
    
    va = state["victim_analysis"]
    state["agent_logs"].append(f"[Multi-Victim] count={va['victim_count']} mass_casualty={va['is_mass_casualty']} teams_needed={va['required_teams']}")
    return state

def llm_triage_node(state):
    state["agent_logs"].append("[LLM Triage] Calling Claude API...")
    start = time.time()
    try:
        result = run_llm_triage_agent(transcription=state["transcription"], intake_context=state.get("intake_context") or {})
        latency = round((time.time() - start) * 1000, 1)
        state["llm_triage_result"] = result
        state["llm_latency_ms"] = latency
        method = result.get("triage_method", "unknown")
        sev = result.get("severity", "?")
        cached = result.get("from_cache", False)
        state["agent_logs"].append(f"[LLM Triage] {sev} via {method} ({'cached' if cached else f'{latency:.0f}ms'})")
    except Exception as e:
        state["llm_triage_result"] = None
        state["llm_latency_ms"] = None
        state["agent_logs"].append(f"[LLM Triage] Error: {e} — rule-based fallback")
    return state

def photo_triage_node(state):
    photo_bytes = state.get("photo_bytes")
    if not photo_bytes:
        state["photo_triage_result"] = None
        state["agent_logs"].append("[Photo Triage] No photo — skipping")
        return state
    state["agent_logs"].append("[Photo Triage] Analyzing injury photo...")
    try:
        result = run_photo_triage_agent(image_bytes=photo_bytes, text_triage=state.get("llm_triage_result"), media_type=state.get("photo_media_type","image/jpeg"))
        state["photo_triage_result"] = result
        state["agent_logs"].append(f"[Photo Triage] injury_visible={result.get('injury_visible')} severity={result.get('severity')}")
    except Exception as e:
        state["photo_triage_result"] = None
        state["agent_logs"].append(f"[Photo Triage] Error: {e}")
    return state

def triage_node(state):
    state["agent_logs"].append("[Triage] Classifying severity...")
    if state.get("llm_triage_result") and state["llm_triage_result"].get("severity"):
        state["triage_result"] = state["llm_triage_result"]
        state["triage_method"] = state["llm_triage_result"].get("triage_method", "llm")
    else:
        state["triage_result"] = run_triage_agent(state["intake_context"])
        state["triage_method"] = "rule_based"
    if state.get("photo_triage_result") and state["photo_triage_result"].get("injury_visible"):
        from agents.photo_triage_agent import merge_photo_and_text_severity
        state["triage_result"] = merge_photo_and_text_severity(state["triage_result"], state["photo_triage_result"])
        state["triage_method"] = "photo_merged"
    override = get_severity_override(state["intake_context"].get("injury", ""))
    if override:
        from agents.triage_agent import PRIORITY_ORDER
        current = state["triage_result"]["severity"]
        if PRIORITY_ORDER.get(override, 0) > PRIORITY_ORDER.get(current, 0):
            state["triage_result"]["severity"] = override
            state["triage_result"]["reasoning"] = state["triage_result"].get("reasoning","") + f" [Profile override → {override}]"
    sev = state["triage_result"]["severity"]
    state["agent_logs"].append(f"[Triage] {sev} method={state['triage_method']}")
    try:
        from utils.audio_alerts import alert_critical_incident, alert_high_incident
        if sev == "CRITICAL": alert_critical_incident()
        elif sev == "HIGH": alert_high_incident()
    except Exception: pass
    return state

def risk_node(state):
    state["agent_logs"].append("[Risk Predictor] Assessing escalation risks...")
    risks = predict_risks(state["intake_context"])
    injury = state["intake_context"].get("injury","default")
    severity = state.get("triage_result", {}).get("severity", "MEDIUM")
    environment = state["intake_context"].get("environment", "").lower()
    raw_text = state["intake_context"].get("raw_text", "").lower()
    
    from command.responder_manager import get_available_teams
    available = get_available_teams()
    
    # Use a deterministic hash of transcription + dynamic timestamp for TRUE dynamism
    import hashlib
    import time
    import random
    
    inc_record = state.get("incident_record") or {}
    # Incorporate time to ensure every 'Process' click yields unique results
    seed_text = inc_record.get("incident_id", state.get("transcription", "fallback")) + str(time.time())
    hash_val = int(hashlib.md5(seed_text.encode()).hexdigest(), 16)
    
    # Base travel time depends on dispatch distance (Simulated neighborhood spread)
    dist_delay = 2.0 + (hash_val % 100) / 10.0 # 2.0 to 12.0 mins
    
    # Base delay based on team availability
    base_delay = dist_delay if available else (dist_delay + 8.0 + (hash_val % 5))
    
    # Adjust delay based on severity (critical gets prioritized)
    if severity == "CRITICAL": 
        base_delay = max(1.0, base_delay * 0.65)
    elif severity == "LOW": 
        base_delay = base_delay * 1.6 + 6.0
    
    # ── DYNAMIC DYNAMISM: Situational Environmental Modifiers ──
    modifier = 1.0 + (random.randint(-5, 5) / 100.0) # 5% random environmental jitter
    
    # Access difficulty
    if any(w in environment or w in raw_text for w in ["mountain", "forest", "remote", "highway", "trapped", "rubble", "cliff"]):
        modifier += 0.85
    
    # Climate/Weather slowdowns
    if any(w in environment or w in raw_text for w in ["storm", "rain", "snow", "fog", "windy"]):
        modifier += 0.35
        
    # Crisis barriers
    if any(w in environment or w in raw_text for w in ["flood", "water", "river", "tsunami"]):
        modifier += 1.45
    if any(w in environment or w in raw_text for w in ["fire", "blaze", "smoke", "explosion", "lava"]):
        modifier += 0.55
        
    estimated_delay = round(base_delay * modifier, 1)
    
    survival = estimate_survival_probability(injury, estimated_delay, context=state.get("intake_context", None))
    # Add delay to survival data so UI can see it
    survival["response_delay_minutes"] = estimated_delay
    
    state["risk_analysis"] = {"risks": risks, "count": len(risks)}
    state["survival_data"] = survival
    state["agent_logs"].append(f"[Risk] {len(risks)} risk(s) | Survival: {survival['survival_probability']:.1f}% | Delay: {estimated_delay}min")
    return state

def knowledge_graph_node(state):
    state["agent_logs"].append("[Knowledge Graph] Querying treatments...")
    state["kg_data"] = run_knowledge_graph_agent(state["intake_context"], state["triage_result"])
    return state

def protocol_node(state):
    state["agent_logs"].append("[Protocol RAG] Retrieving treatment protocol...")
    state["protocol_data"] = run_protocol_agent(state["intake_context"], state["kg_data"])
    return state

def resource_node(state):
    state["agent_logs"].append("[Resource] Checking inventory...")
    state["resource_data"] = run_resource_agent(state["kg_data"], state.get("victim_analysis"))
    avail = state["resource_data"].get("available_count", 0)
    total = state["resource_data"].get("total_count", 0)
    state["agent_logs"].append(f"[Resource] {avail}/{total} available")
    return state

def triage_steps_node(state):
    state["agent_logs"].append("[Triage Assistant] Retrieving step-by-step instructions...")
    injury = state["intake_context"].get("injury","default")
    state["triage_steps"] = get_triage_steps(injury, use_rag=True)
    return state

def response_node(state):
    state["agent_logs"].append("[Response Agent] Generating final report...")
    state["final_response"] = run_response_agent(state["intake_context"], state["triage_result"], state["kg_data"], state["protocol_data"], state["resource_data"])
    
    # ── Attach matched Kaggle case data and coordinates to final_response for the UI ──
    intake = state.get("intake_context", {}) or {}
    state["final_response"]["coordinates"] = intake.get("coordinates")
    if intake.get("matched_cases"):
        state["final_response"]["matched_cases"] = intake["matched_cases"]
        state["final_response"]["suggested_diagnosis"] = intake.get("suggested_diagnosis", "")
        state["final_response"]["reference_vitals"] = intake.get("reference_vitals", {})

    elapsed = time.time() - state["start_time"]
    state["agent_logs"].append(f"[Response] Complete in {elapsed:.2f}s")
    return state

def incident_registration_node(state):
    state["agent_logs"].append("[Incident Manager] Registering incident...")
    incident = create_incident(
        context=state["intake_context"],
        triage=state["triage_result"],
        resource_data=state["resource_data"],
        victim_analysis=state["victim_analysis"],
        survival_data=state.get("survival_data", {})
    )
    state["incident_record"] = incident
    state["final_response"]["incident_id"] = incident["incident_id"]
    state["final_response"]["priority_score"] = incident["priority_score"]
    state["agent_logs"].append(f"[Incident Manager] {incident['incident_id']} registered priority_score={incident['priority_score']}")
    return state

def vitals_check_node(state):
    state["agent_logs"].append("[Vitals] Checking for vitals in transcription...")
    intake = state.get("intake_context", {}) or {}
    incident_record = state.get("incident_record") or {}
    incident_id = incident_record.get("incident_id", "UNKNOWN")
    victim = intake.get("victim", "Unknown Patient")
    transcription = state.get("transcription", "").lower()
    vitals = {}
    if "unconscious" in transcription or "unresponsive" in transcription: vitals["consciousness"] = "Unresponsive"
    elif "confused" in transcription or "disoriented" in transcription: vitals["consciousness"] = "Voice"
    else: vitals["consciousness"] = "Alert"
    if "not breathing" in transcription or "respiratory arrest" in transcription: vitals["respiratory_rate"] = 0
    elif "difficulty breathing" in transcription: vitals["respiratory_rate"] = 32
    if "cardiac arrest" in transcription or "no pulse" in transcription: vitals["pulse_bpm"] = 0
    if "shock" in transcription or "hypotension" in transcription: vitals["systolic_bp"] = 80
    if vitals and incident_id != "UNKNOWN":
        try:
            result = log_vitals(incident_id, victim, vitals)
            state["vitals_log_result"] = result
            state["agent_logs"].append(f"[Vitals] Logged {len(vitals)} sign(s) — {result.get('alert_count',0)} alert(s)")
        except Exception as e:
            state["vitals_log_result"] = None
            state["agent_logs"].append(f"[Vitals] Error: {e}")
    else:
        state["vitals_log_result"] = None
        state["agent_logs"].append("[Vitals] No vitals extracted")
    return state

def assignment_node(state):
    state["agent_logs"].append("[Responder Manager] Auto-assigning team...")
    required_teams = (state.get("victim_analysis") or {}).get("required_teams", 1)
    team_id = auto_assign(state["incident_record"], required_teams)
    state["assignment"] = team_id
    if team_id:
        assign_incident(state["incident_record"]["incident_id"], team_id)
        state["final_response"]["assigned_team"] = team_id
        state["agent_logs"].append(f"[Responder] Assigned: {team_id}")
    else:
        state["agent_logs"].append("[Responder] ⚠️  No teams available")
    return state

def dispatch_node(state):
    state["agent_logs"].append("[Equipment Dispatch] Dispatching required items...")
    resources = state["resource_data"].get("resources", [])
    items_to_dispatch = [{"item": r["item"], "quantity": 1} for r in resources if r.get("status") == "AVAILABLE"]
    if items_to_dispatch:
        incident_id = (state.get("incident_record") or {}).get("incident_id", "UNKNOWN")
        results = dispatch_equipment(incident_id, items_to_dispatch)
        state["dispatch_results"] = results
        dispatched = sum(1 for r in results if r.get("status") == "DISPATCHED")
        state["agent_logs"].append(f"[Dispatch] {dispatched}/{len(items_to_dispatch)} items dispatched")
    else:
        state["dispatch_results"] = []
        state["agent_logs"].append("[Dispatch] No items to dispatch")
    return state


def build_command_pipeline():
    builder = StateGraph(CommandState)
    builder.add_node("intake",            intake_node)
    builder.add_node("llm_triage",        llm_triage_node)
    builder.add_node("photo_triage",      photo_triage_node)
    builder.add_node("multi_victim",      multi_victim_node)
    builder.add_node("triage",            triage_node)
    builder.add_node("risk",              risk_node)
    builder.add_node("knowledge_graph",   knowledge_graph_node)
    builder.add_node("protocol",          protocol_node)
    builder.add_node("resource",          resource_node)
    builder.add_node("triage_steps",      triage_steps_node)
    builder.add_node("response",          response_node)
    builder.add_node("incident_register", incident_registration_node)
    builder.add_node("vitals_check",      vitals_check_node)
    builder.add_node("assignment",        assignment_node)
    builder.add_node("dispatch",          dispatch_node)
    builder.set_entry_point("intake")
    builder.add_edge("intake",            "llm_triage")
    builder.add_edge("llm_triage",        "photo_triage")
    builder.add_edge("photo_triage",      "multi_victim")
    builder.add_edge("multi_victim",      "triage")
    builder.add_edge("triage",            "risk")
    builder.add_edge("risk",              "knowledge_graph")
    builder.add_edge("knowledge_graph",   "protocol")
    builder.add_edge("protocol",          "resource")
    builder.add_edge("resource",          "triage_steps")
    builder.add_edge("triage_steps",      "response")
    builder.add_edge("response",          "incident_register")
    builder.add_edge("incident_register", "vitals_check")
    builder.add_edge("vitals_check",      "assignment")
    builder.add_edge("assignment",        "dispatch")
    builder.add_edge("dispatch",          END)
    return builder.compile()


def process_emergency(transcription: str, photo_bytes=None, photo_media_type="image/jpeg", location_hint=None):
    print("\n" + "═"*65)
    print("🚨  DISASTER COMMAND CENTER v4 ELITE — PROCESSING")
    print("═"*65)
    seed_default_teams()
    initialize_access_config()
    initial_state: CommandState = {
        "transcription": transcription, "intake_context": None, "triage_result": None,
        "kg_data": None, "protocol_data": None, "resource_data": None, "final_response": None,
        "victim_analysis": None, "risk_analysis": None, "survival_data": None,
        "triage_steps": None, "incident_record": None, "assignment": None,
        "dispatch_results": None, "llm_triage_result": None, "photo_triage_result": None,
        "photo_bytes": photo_bytes, "photo_media_type": photo_media_type,
        "vitals_log_result": None, "triage_method": "rule_based",
        "llm_latency_ms": None, "language_result": None,
        "location_hint": location_hint,
        "start_time": time.time(), "agent_logs": [],
    }
    pipeline = build_command_pipeline()
    final = pipeline.invoke(initial_state)
    resp  = final["final_response"]
    va    = final.get("victim_analysis", {}) or {}
    surv  = final.get("survival_data", {}) or {}
    risks = (final.get("risk_analysis", {}) or {}).get("risks", [])
    inc   = final.get("incident_record", {}) or {}
    print("\n" + "─"*65 + "\n📋  EXECUTION LOG\n" + "─"*65)
    for log in final["agent_logs"]: print(f"  {log}")
    print("\n" + "═"*65)
    print(f"🚨  RESPONSE: {resp['severity_display']}  |  ID: {inc.get('incident_id','?')}")
    print("═"*65)
    print(f"  Victim:   {resp['victim']} ({va.get('victim_count',1)} victim(s))")
    print(f"  Injury:   {resp['injury']}")
    print(f"  Triage:   {final.get('triage_method','?').upper()}")
    print(f"  Survival: {surv.get('survival_probability','?')}% ({surv.get('urgency','?')})")
    if risks:
        for r in risks: print(f"  ⚠️  {r['risk']}")
    print("═"*65)
    return final


def voice_mode(duration=7):
    if not is_speech_enabled():
        print("[Speech] ⚡ Speech disabled in current mode")
        return {}
    try:
        from speech.multilingual_stt import record_and_transcribe_multilingual
        result = record_and_transcribe_multilingual(duration=duration)
        text = result.get("text_english", "[no speech]")
        print(f"\n🌐 Language: {result.get('language_name')} | Text: {text[:60]}")
        return process_emergency(text)
    except Exception:
        from speech.speech_to_text import record_and_transcribe
        text = record_and_transcribe(duration=duration)
        return process_emergency(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Disaster Command Center v4 ELITE")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text",  "-t", type=str)
    group.add_argument("--voice", "-v", action="store_true")
    parser.add_argument("--duration", "-d", type=int, default=7)
    parser.add_argument("--output",   "-o", type=str)
    parser.add_argument("--photo",    "-p", type=str)
    parser.add_argument("--sitrep",   action="store_true")
    args = parser.parse_args()
    if args.sitrep:
        from command.sitrep_generator import generate_sitrep
        print(generate_sitrep()["summary"]); sys.exit(0)
    photo_bytes, photo_media_type = None, "image/jpeg"
    if args.photo:
        try:
            with open(args.photo,"rb") as f: photo_bytes = f.read()
            ext = os.path.splitext(args.photo.lower())[1].lstrip(".")
            photo_media_type = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png","webp":"image/webp"}.get(ext,"image/jpeg")
        except Exception as e: print(f"[Photo] Load error: {e}")
    if args.text: final = process_emergency(args.text, photo_bytes, photo_media_type)
    else: final = voice_mode(duration=args.duration)
    if args.output and final:
        with open(args.output,"w") as f: json.dump(final.get("final_response",{}), f, indent=2, default=str)
        print(f"Output saved: {args.output}")
