"""
command/triage_assistant.py
─────────────────────────────
Section 9 — Offline Triage Assistant

Provides step-by-step treatment instructions with built-in timers.
Instructions are retrieved from the RAG system (FAISS + protocol text).

For each treatment step:
  • Description of action
  • Timer in seconds (if applicable)
  • Recheck instruction

Falls back to a hardcoded step library if RAG is unavailable.
"""

import os
import sys
import time
from typing import Dict, List, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

# ── Hardcoded step library (guaranteed offline fallback) ──
STEP_LIBRARY = {
    "bleeding": [
        {"step": 1, "action": "Apply direct firm pressure to the wound using a clean cloth",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Elevate the injured limb above heart level if possible",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Apply tourniquet 5–7 cm above wound if bleeding is severe",
         "timer_seconds": None, "recheck": "Note exact tourniquet application time"},
        {"step": 4, "action": "Maintain pressure continuously — do NOT remove cloth",
         "timer_seconds": 120, "recheck": "Recheck bleeding every 2 minutes"},
        {"step": 5, "action": "Monitor for signs of shock: pale skin, rapid pulse, confusion",
         "timer_seconds": 300, "recheck": "Recheck vitals every 5 minutes"},
    ],
    "cardiac_arrest": [
        {"step": 1, "action": "Check scene safety and confirm victim is unresponsive",
         "timer_seconds": 10, "recheck": None},
        {"step": 2, "action": "Call for AED and emergency services immediately",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Begin chest compressions: 30 compressions, hard and fast",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Give 2 rescue breaths after every 30 compressions",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "Continue CPR at 100–120 compressions per minute",
         "timer_seconds": 120, "recheck": "Check for pulse every 2 minutes"},
        {"step": 6, "action": "Apply AED pads when available and follow voice prompts",
         "timer_seconds": None, "recheck": None},
    ],
    "fracture": [
        {"step": 1, "action": "Do NOT attempt to straighten the limb",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Immobilise the fracture with a splint — pad well",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Apply cold pack wrapped in cloth to reduce swelling",
         "timer_seconds": 600, "recheck": "Remove cold pack after 10 minutes"},
        {"step": 4, "action": "Check circulation: pulse, sensation, movement below fracture",
         "timer_seconds": 120, "recheck": "Recheck circulation every 2 minutes"},
        {"step": 5, "action": "Elevate limb if no spinal injury suspected",
         "timer_seconds": None, "recheck": None},
    ],
    "burn": [
        {"step": 1, "action": "Cool burn immediately with cool running water",
         "timer_seconds": 1200, "recheck": "Continue cooling for 20 minutes minimum"},
        {"step": 2, "action": "Remove jewellery and clothing around burn (not if stuck)",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Cover loosely with clean non-stick dressing",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Do NOT use ice, butter, or toothpaste on burns",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "Monitor for infection signs: increasing redness, swelling",
         "timer_seconds": 600, "recheck": "Recheck dressing every 10 minutes"},
    ],
    "choking": [
        {"step": 1, "action": "Ask victim: 'Are you choking?' — if they cannot speak, act immediately",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Give 5 firm back blows between shoulder blades with heel of hand",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Give 5 abdominal thrusts (Heimlich): fist above navel, thrust inward and upward",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Alternate 5 back blows and 5 abdominal thrusts until cleared",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "If victim loses consciousness, begin CPR and look in mouth before each breath",
         "timer_seconds": None, "recheck": None},
    ],
    "hypothermia": [
        {"step": 1, "action": "Move victim to warm, dry location — prevent further heat loss",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Remove wet clothing carefully — handle gently to avoid triggering arrhythmia",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Cover with blankets — apply heat packs to neck, armpits, groin",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Give warm sweet beverages if conscious and able to swallow",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "Monitor core temperature and pulse every 5 minutes",
         "timer_seconds": 300, "recheck": "Recheck temperature every 5 minutes"},
    ],
    "spinal": [
        {"step": 1, "action": "Do NOT move the victim unless in immediate danger",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Stabilise the head and neck in neutral alignment",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Apply cervical collar if available",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Log-roll technique ONLY if movement is required (3+ persons)",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "Monitor breathing — be prepared to give rescue breaths",
         "timer_seconds": 120, "recheck": "Recheck breathing every 2 minutes"},
    ],
    "default": [
        {"step": 1, "action": "Ensure scene safety before approaching the victim",
         "timer_seconds": None, "recheck": None},
        {"step": 2, "action": "Assess: Airway — Breathing — Circulation (ABC)",
         "timer_seconds": None, "recheck": None},
        {"step": 3, "action": "Keep victim still, warm, and calm",
         "timer_seconds": None, "recheck": None},
        {"step": 4, "action": "Call for additional medical support if available",
         "timer_seconds": None, "recheck": None},
        {"step": 5, "action": "Continue monitoring and document all actions",
         "timer_seconds": 300, "recheck": "Reassess ABC every 5 minutes"},
    ],
}


def get_triage_steps(injury: str, use_rag: bool = True) -> Dict:
    """
    Retrieve step-by-step triage instructions for a given injury.

    Strategy:
      1. Try RAG retrieval if use_rag=True
      2. Fall back to hardcoded step library

    Args:
        injury:   Injury type string (from intake agent)
        use_rag:  Whether to attempt RAG retrieval

    Returns:
        Triage dict with steps, each having action, timer, recheck
    """
    injury_lower = injury.lower().replace(" ", "_")

    # ── Try RAG retrieval ──
    rag_steps = None
    if use_rag:
        try:
            from agents.protocol_agent import run_protocol_agent
            context = {"injury": injury, "situation": "emergency", "keywords": [injury]}
            kg_data = {"required_resources": [], "recommended_treatments": []}
            protocol = run_protocol_agent(context, kg_data)
            protocol_text = protocol.get("protocol_text", "")
            if protocol_text and len(protocol_text) > 50:
                rag_steps = _parse_rag_steps(protocol_text, injury)
        except Exception as e:
            print(f"[Triage Assistant] RAG unavailable: {e}")

    if rag_steps:
        steps = rag_steps
    else:
        # Fallback to step library
        steps = STEP_LIBRARY.get(injury_lower, STEP_LIBRARY["default"])

    return {
        "injury":        injury,
        "total_steps":   len(steps),
        "steps":         steps,
        "source":        "rag" if rag_steps else "library",
    }


def _parse_rag_steps(protocol_text: str, injury: str) -> Optional[List[Dict]]:
    """
    Parse numbered steps from RAG protocol text.
    Returns list of step dicts or None if parsing fails.
    """
    import re
    lines = protocol_text.split("\n")
    steps = []
    step_num = 0
    for line in lines:
        line = line.strip()
        # Match lines starting with number: "1.", "Step 1:", "1)"
        m = re.match(r"^(?:step\s*)?(\d+)[.):\s]+(.+)", line, re.IGNORECASE)
        if m:
            step_num += 1
            action = m.group(2).strip()
            # Detect timers mentioned in step text
            timer = None
            recheck = None
            time_m = re.search(r"(\d+)\s*minute", action, re.IGNORECASE)
            time_s = re.search(r"(\d+)\s*second", action, re.IGNORECASE)
            if time_m:
                timer = int(time_m.group(1)) * 60
                recheck = f"Recheck after {time_m.group(1)} minutes"
            elif time_s:
                timer = int(time_s.group(1))

            steps.append({
                "step":          step_num,
                "action":        action,
                "timer_seconds": timer,
                "recheck":       recheck,
            })

    return steps if len(steps) >= 3 else None


def format_steps_for_display(triage_data: Dict) -> str:
    """Format triage steps as a readable string for CLI output."""
    lines = [f"\n🩺 TRIAGE PROTOCOL: {triage_data['injury'].upper()}",
             f"   Source: {triage_data['source']}",
             "─" * 50]
    for s in triage_data["steps"]:
        timer_str = f"  ⏱  {s['timer_seconds']}s" if s.get("timer_seconds") else ""
        recheck_str = f"\n   🔁 {s['recheck']}" if s.get("recheck") else ""
        lines.append(f"  Step {s['step']}: {s['action']}{timer_str}{recheck_str}")
    return "\n".join(lines)
