"""
speech/voice_commands.py
──────────────────────────
Section 13 — Voice Command System

Maps spoken responder commands to system actions.
Uses keyword spotting (no ML required — fully offline).

Supported commands:
  "show critical incidents"     → filter queue to CRITICAL
  "show all incidents"          → remove filter
  "mark incident 003 resolved"  → resolve INC-003
  "assign team alpha to 003"    → assign TEAM-ALPHA to INC-003
  "request more oxygen"         → flag oxygen shortage
  "activate panic mode"         → enable PANIC_MODE
  "deactivate panic mode"       → disable PANIC_MODE
  "situation report"            → generate sitrep

Command processing pipeline:
  Audio → Whisper transcription → intent classifier → action executor
"""

import re
from typing import Dict, Optional, Callable, List

# ────────────────────────────────────────────────────────────
# Intent definitions
# ────────────────────────────────────────────────────────────

INTENT_SHOW_CRITICAL     = "show_critical"
INTENT_SHOW_ALL          = "show_all"
INTENT_MARK_RESOLVED     = "mark_resolved"
INTENT_ASSIGN_TEAM       = "assign_team"
INTENT_REQUEST_RESOURCE  = "request_resource"
INTENT_PANIC_ON          = "panic_on"
INTENT_PANIC_OFF         = "panic_off"
INTENT_SITREP            = "sitrep"
INTENT_UNKNOWN           = "unknown"

# Intent patterns: (intent_name, list_of_trigger_phrases)
INTENT_PATTERNS = [
    (INTENT_SHOW_CRITICAL,    ["show critical", "display critical", "critical only", "only critical"]),
    (INTENT_SHOW_ALL,         ["show all", "display all", "all incidents", "full view"]),
    (INTENT_PANIC_ON,         ["activate panic", "panic mode on", "enable panic", "panic on"]),
    (INTENT_PANIC_OFF,        ["deactivate panic", "panic mode off", "disable panic", "panic off"]),
    (INTENT_SITREP,           ["situation report", "sitrep", "status report", "current status"]),
    (INTENT_REQUEST_RESOURCE, ["request", "need more", "out of", "low on", "send more"]),
    (INTENT_MARK_RESOLVED,    ["mark", "resolve", "resolved", "close incident", "done"]),
    (INTENT_ASSIGN_TEAM,      ["assign", "send team", "dispatch team", "deploy"]),
]


def classify_intent(text: str) -> Dict:
    """
    Classify spoken command into an intent + extract entities.

    Args:
        text: Transcribed voice command

    Returns:
        Dict with intent, entities, and confidence
    """
    text_lower = text.lower().strip()

    for intent, patterns in INTENT_PATTERNS:
        for pattern in patterns:
            if pattern in text_lower:
                entities = _extract_entities(intent, text_lower)
                return {
                    "intent":     intent,
                    "entities":   entities,
                    "raw_text":   text,
                    "confidence": 0.9 if pattern == text_lower else 0.75,
                }

    return {
        "intent":     INTENT_UNKNOWN,
        "entities":   {},
        "raw_text":   text,
        "confidence": 0.0,
    }


def _extract_entities(intent: str, text: str) -> Dict:
    """Extract relevant entities (incident_id, team_id, resource) from text."""
    entities = {}

    # Extract incident ID patterns: "incident 003", "INC-003", "003"
    inc_match = re.search(r"incident\s+([a-z0-9\-]+)|inc[-\s]?([0-9]+)", text, re.IGNORECASE)
    if inc_match:
        raw = inc_match.group(1) or inc_match.group(2)
        entities["incident_id"] = f"INC-{raw.upper().lstrip('INC-').lstrip('0') or '0'}" \
            if not raw.upper().startswith("INC-") else raw.upper()

    # Extract team ID: "team alpha", "team bravo", etc.
    team_match = re.search(
        r"team\s+(alpha|bravo|charlie|delta|echo|[a-z]+)",
        text, re.IGNORECASE
    )
    if team_match:
        entities["team_id"] = f"TEAM-{team_match.group(1).upper()}"

    # Extract resource name for resource requests
    if intent == INTENT_REQUEST_RESOURCE:
        resource_keywords = [
            "oxygen", "bandage", "stretcher", "defibrillator",
            "splint", "tourniquet", "cold pack", "burn gel",
            "painkiller", "water", "blanket",
        ]
        for kw in resource_keywords:
            if kw in text:
                entities["resource"] = kw
                break

    return entities


# ────────────────────────────────────────────────────────────
# Action executor
# ────────────────────────────────────────────────────────────

def execute_command(command_result: Dict) -> Dict:
    """
    Execute the action associated with a classified intent.

    Args:
        command_result: Output from classify_intent()

    Returns:
        Execution result dict with success flag and message
    """
    intent   = command_result.get("intent")
    entities = command_result.get("entities", {})

    if intent == INTENT_PANIC_ON:
        from utils.system_state import activate_panic_mode
        activate_panic_mode()
        return {"success": True, "message": "🔴 PANIC MODE ACTIVATED",
                "action": "state_change", "reload": True}

    elif intent == INTENT_PANIC_OFF:
        from utils.system_state import deactivate_panic_mode
        deactivate_panic_mode()
        return {"success": True, "message": "✅ Panic mode deactivated",
                "action": "state_change", "reload": True}

    elif intent == INTENT_SHOW_CRITICAL:
        return {"success": True, "message": "Showing CRITICAL incidents only",
                "action": "filter", "filter_severity": "CRITICAL", "reload": True}

    elif intent == INTENT_SHOW_ALL:
        return {"success": True, "message": "Showing all incidents",
                "action": "filter", "filter_severity": None, "reload": True}

    elif intent == INTENT_SITREP:
        from command.sitrep_generator import generate_sitrep
        sitrep = generate_sitrep()
        return {"success": True, "message": sitrep["summary"],
                "action": "sitrep", "data": sitrep}

    elif intent == INTENT_MARK_RESOLVED:
        incident_id = entities.get("incident_id")
        if incident_id:
            from command.incident_manager import resolve_incident
            success = resolve_incident(incident_id)
            return {
                "success": success,
                "message": f"{'✅ Resolved' if success else '❌ Not found'}: {incident_id}",
                "action": "resolve", "reload": True,
            }
        return {"success": False, "message": "No incident ID detected in command"}

    elif intent == INTENT_ASSIGN_TEAM:
        incident_id = entities.get("incident_id")
        team_id     = entities.get("team_id")
        if incident_id and team_id:
            from command.incident_manager import assign_incident, get_incident
            from command.responder_manager import update_team_status, STATUS_BUSY
            inc = get_incident(incident_id)
            if inc:
                assign_incident(incident_id, team_id)
                update_team_status(team_id, STATUS_BUSY, incident_id)
                return {
                    "success": True,
                    "message": f"✅ {team_id} assigned to {incident_id}",
                    "action": "assign", "reload": True,
                }
        return {"success": False, "message": "Could not extract incident ID and team ID from command"}

    elif intent == INTENT_REQUEST_RESOURCE:
        resource = entities.get("resource", "unspecified resource")
        return {
            "success": True,
            "message": f"⚠️  Resource request logged: {resource}",
            "action": "resource_request", "resource": resource,
        }

    return {"success": False, "message": "Command not understood", "action": "none"}


def process_voice_command(audio_duration: int = 4) -> Dict:
    """
    Full pipeline: record → transcribe → classify → execute.

    Args:
        audio_duration: Seconds to record

    Returns:
        Execution result dict
    """
    try:
        from speech.speech_to_text import record_and_transcribe
        print(f"[Voice Command] 🎤 Listening for {audio_duration}s...")
        text = record_and_transcribe(duration=audio_duration)
        print(f"[Voice Command] Heard: '{text}'")
    except Exception as e:
        return {"success": False, "message": f"Voice capture failed: {e}"}

    intent_result = classify_intent(text)
    print(f"[Voice Command] Intent: {intent_result['intent']} "
          f"(confidence: {intent_result['confidence']:.0%})")

    return execute_command(intent_result)
