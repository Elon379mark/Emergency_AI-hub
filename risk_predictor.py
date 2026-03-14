"""
command/risk_predictor.py
───────────────────────────
Section 10 — Risk Prediction
Section 11 — Survival Probability Estimation

Risk Prediction:
  Rule-based + knowledge-graph approach.
  Each injury/situation combination maps to potential escalation risks.
  Example: burn + factory → toxic gas risk → send hazmat

Survival Probability:
  Time-decay model based on medical literature.
  P(survival) = P_base * exp(-lambda * response_delay_minutes)
  Where lambda is the injury-specific decay constant.
"""

import os
import sys
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ────────────────────────────────────────────────────────────
# Section 10 — Risk Prediction Rules
# ────────────────────────────────────────────────────────────

# Rule format: (injury_keywords, situation_keywords) → risk_info
ESCALATION_RULES = [
    {
        "trigger_injuries":   ["burn", "poisoning"],
        "trigger_situations": ["factory", "chemical", "industrial", "workplace"],
        "risk":               "Toxic gas / chemical exposure",
        "action":             "Send hazmat team. Evacuate 200m radius. Do not enter without breathing apparatus.",
        "severity_boost":     True,
    },
    {
        "trigger_injuries":   ["breathing", "choking", "smoke"],
        "trigger_situations": ["fire", "smoke"],
        "risk":               "Carbon monoxide / smoke inhalation risk",
        "action":             "Move all victims upwind. Apply oxygen masks immediately.",
        "severity_boost":     True,
    },
    {
        "trigger_injuries":   ["fracture", "spinal", "head_injury"],
        "trigger_situations": ["earthquake", "collapse", "rubble"],
        "risk":               "Secondary collapse / crush syndrome",
        "action":             "Establish safe perimeter. Monitor for rhabdomyolysis in prolonged entrapment.",
        "severity_boost":     False,
    },
    {
        "trigger_injuries":   ["flooding", "hypothermia"],
        "trigger_situations": ["flood", "water"],
        "risk":               "Secondary drowning / hypothermia cascade",
        "action":             "Warm all rescued victims immediately. Monitor 24 hours for secondary drowning.",
        "severity_boost":     False,
    },
    {
        "trigger_injuries":   ["bleeding", "cardiac_arrest"],
        "trigger_situations": ["accident", "crash"],
        "risk":               "Hemorrhagic shock escalation",
        "action":             "Establish large-bore IV access. Monitor for systolic BP < 90.",
        "severity_boost":     True,
    },
    {
        "trigger_injuries":   ["cardiac_arrest", "fracture"],
        "trigger_situations": [],
        "trigger_victims":    ["elderly", "pregnant", "infant", "baby", "multiple"],
        "risk":               "High vulnerability population / Mass casualty— rapid deterioration likely",
        "action":             "Prioritise immediate transport over field treatment.",
        "severity_boost":     True,
    },
]


def predict_risks(context: Dict) -> List[Dict]:
    """
    Identify all applicable escalation risks for a given context.

    Args:
        context: Intake agent output (injury, situation, victim, environment)

    Returns:
        List of risk dicts with risk description and recommended action
    """
    injury    = context.get("injury",    "").lower()
    situation = context.get("situation", "").lower()
    victim    = context.get("victim",    "").lower()
    raw_text  = context.get("raw_text",  "").lower()

    risks = []
    for rule in ESCALATION_RULES:
        # Check injury trigger
        injury_match = any(kw in injury or kw in raw_text
                           for kw in rule["trigger_injuries"])

        # Check situation trigger (empty means always applies if injury matches)
        sit_triggers = rule.get("trigger_situations", [])
        situation_match = (not sit_triggers) or any(
            kw in situation or kw in raw_text for kw in sit_triggers
        )

        # Check victim trigger (optional field)
        victim_triggers = rule.get("trigger_victims", [])
        victim_match = (not victim_triggers) or any(kw in victim for kw in victim_triggers)

        if injury_match and situation_match and victim_match:
            risks.append({
                "risk":           rule["risk"],
                "action":         rule["action"],
                "severity_boost": rule["severity_boost"],
            })

    if risks:
        print(f"[Risk Predictor] {len(risks)} escalation risk(s) detected")

    return risks


# ────────────────────────────────────────────────────────────
# Section 11 — Survival Probability Estimation
# ────────────────────────────────────────────────────────────

# Survival model parameters: (P_base, lambda_decay)
# Based on medical literature approximations
# P(t) = P_base * exp(-lambda * t)  where t = response delay in minutes
SURVIVAL_MODELS = {
    "cardiac_arrest": {
        "p_base":      0.90,
        "lambda":      0.10,   # drops ~10% per minute
        "golden_time": 4,      # minutes — golden window
        "description": "Survival drops rapidly. Every minute without CPR reduces survival by ~10%.",
    },
    "severe_bleeding": {
        "p_base":      0.85,
        "lambda":      0.05,
        "golden_time": 10,
        "description": "Major haemorrhage requires control within 10 minutes.",
    },
    "bleeding": {
        "p_base":      0.88,
        "lambda":      0.04,
        "golden_time": 15,
        "description": "Uncontrolled bleeding — apply tourniquet within 15 minutes.",
    },
    "minor_cut": {
        "p_base":      0.99,
        "lambda":      0.001,
        "golden_time": 120,
        "description": "Minor wound. Risk of mortality is negligible.",
    },
    "fracture": {
        "p_base":      0.95,
        "lambda":      0.005,
        "golden_time": 60,
        "description": "Fractures are rarely immediately fatal. Risk is shock and nerve damage.",
    },
    "burn": {
        "p_base":      0.80,
        "lambda":      0.02,
        "golden_time": 20,
        "description": "Major burns: survival linked to early cooling and fluid resuscitation.",
    },
    "spinal": {
        "p_base":      0.85,
        "lambda":      0.01,
        "golden_time": 30,
        "description": "Survival is high but permanent paralysis risk increases with movement delay.",
    },
    "choking": {
        "p_base":      0.90,
        "lambda":      0.15,
        "golden_time": 3,
        "description": "Complete airway obstruction is fatal within 3–5 minutes without intervention.",
    },
    "hypothermia": {
        "p_base":      0.75,
        "lambda":      0.008,
        "golden_time": 45,
        "description": "Severe hypothermia — warming must begin within 45 minutes.",
    },
    "default": {
        "p_base":      0.80,
        "lambda":      0.02,
        "golden_time": 30,
        "description": "General emergency — prompt response improves outcomes.",
    },
}


def estimate_survival_probability(
    injury: str,
    response_delay_minutes: float,
    context: Dict = None
) -> Dict:
    """
    Estimate survival probability based on injury type and response delay.

    Model: P(t) = P_base * exp(-lambda * t)

    Args:
        injury:                  Injury type string
        response_delay_minutes:  Estimated time until help arrives
        context:                 Intake context containing situational hazards

    Returns:
        Dict with probability, urgency level, time benchmarks
    """
    injury_key = injury.lower().strip().replace(" ", "_").replace("-", "_")
    import re
    injury_key = re.sub(r'[^a-z0-9_]', '', injury_key) # Strip punctuation
    
    # Handle simple pluralization
    if injury_key.endswith("s") and len(injury_key) > 4:
        stem = injury_key[:-1]
    else:
        stem = injury_key

    # Early intercept for minor injuries
    minor_keywords = ["minor", "small", "tiny", "scratch", "superficial", "scrape", "abrasion", "graze", "paper_cut", "cut"]
    if any(m in injury_key for m in minor_keywords) and "severe" not in injury_key:
        model = SURVIVAL_MODELS["minor_cut"]
    else:
        # Match to closest model (longest match first for specificity)
        sorted_keys = sorted(SURVIVAL_MODELS.keys(), key=len, reverse=True)
        model = SURVIVAL_MODELS.get(injury_key)
        if model is None:
            for key in sorted_keys:
                if key != "default" and (key in injury_key or injury_key in key or key in stem or stem in key):
                    model = SURVIVAL_MODELS[key]
                    break

    if model is None:
        model = SURVIVAL_MODELS["default"]

    p_base = model["p_base"]
    lambda_decay = model["lambda"]
    
    # --- DYNAMIC DYNAMISM: Situational Intensity Modifiers ---
    if context:
        victim = context.get("victim", "").lower()
        raw_text = context.get("raw_text", "").lower()
        situation = context.get("situation", "").lower()
        
        # 1. Demographic Fragility
        # Senior/Infant populations deteriorate faster physiologically
        if any(v in victim or v in raw_text for v in ["elderly", "senior", "infant", "baby", "newborn", "pregnant", "child"]):
            p_base -= 0.08
            lambda_decay *= 1.35
            
        # 2. Situational Intensity (The "Adjective" factor)
        # Keywords that indicate higher than normal model decay
        intense_keywords = ["gushing", "spurting", "massive", "uncontrolled", "profuse", "rapid", "sudden", "deep"]
        if any(w in raw_text for w in intense_keywords):
            lambda_decay *= 1.4
            p_base -= 0.05
            
        # Keywords that indicate a managed or slow-moving situation
        stable_keywords = ["slow", "controlled", "stopped", "minor", "small", "moderate", "steady"]
        if any(w in raw_text for w in stable_keywords):
            lambda_decay *= 0.6
            p_base += 0.03

        # 3. Environmental Life-Threats
        # Conditions that lower the base chance of survival regardless of time
        critical_keywords = ["unconscious", "unresponsive", "submerged", "no pulse", "cyanosis", "shock", "crush", "impalement"]
        if any(w in raw_text or w in situation for w in critical_keywords):
            p_base -= 0.15
            lambda_decay *= 1.1

    # Ensure p_base stays within realistic medical bounds
    p_base = max(0.05, min(1.0, p_base))

    # Compute survival probability
    p_survival = p_base * math.exp(-lambda_decay * response_delay_minutes)
    p_survival = max(0.0, min(1.0, p_survival))
    p_pct      = round(p_survival * 100, 1)

    # Urgency classification
    if p_pct >= 75:
        urgency = "MANAGEABLE"
        urgency_color = "green"
    elif p_pct >= 50:
        urgency = "URGENT"
        urgency_color = "orange"
    elif p_pct >= 25:
        urgency = "CRITICAL — ACT NOW"
        urgency_color = "red"
    else:
        urgency = "CRITICAL — IMMEDIATE"
        urgency_color = "darkred"

    # Time benchmarks
    golden_time = model["golden_time"]
    benchmarks = []
    for t_min in [1, 2, 4, 5, 10, 15, 20, 30]:
        p = model["p_base"] * math.exp(-model["lambda"] * t_min)
        benchmarks.append({
            "minutes":     t_min,
            "survival_pct": round(max(0, p * 100), 1)
        })

    return {
        "injury":                 injury,
        "response_delay_minutes": response_delay_minutes,
        "survival_probability":   p_pct,
        "urgency":                urgency,
        "urgency_color":          urgency_color,
        "golden_time_minutes":    golden_time,
        "is_past_golden_time":    response_delay_minutes > golden_time,
        "description":            model["description"],
        "time_benchmarks":        benchmarks,
    }


def get_urgency_message(survival_data: Dict) -> str:
    """Return a short urgency message for display."""
    p = survival_data["survival_probability"]
    delay = survival_data["response_delay_minutes"]
    injury = survival_data["injury"]
    golden = survival_data["golden_time_minutes"]

    if delay <= golden:
        return f"⚡ Within golden time ({delay:.0f}m/{golden}m) — {p:.0f}% survival"
    else:
        return f"⚠️  Past golden time ({delay:.0f}m > {golden}m) — {p:.0f}% survival — URGENT"
