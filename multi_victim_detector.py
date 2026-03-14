"""
agents/multi_victim_detector.py
────────────────────────────────
Section 2 — Multi-Victim Detection

Detects victim counts and mass-casualty indicators from emergency text.
Uses rule-based NLP: number word parsing + digit extraction + keyword triggers.

Example:
  Input:  "Bus accident near bridge with 12 injured people"
  Output: { "victim_count": 12, "is_mass_casualty": True,
            "required_teams": 4, "required_stretchers": 6 }
"""

import re
from typing import Dict, Optional

# ── Number word → integer map ──
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "dozens": 24, "scores": 40,
}

# ── Trigger patterns that imply multiple victims ──
MULTI_VICTIM_TRIGGERS = [
    "multiple", "several", "many", "group", "crowd", "mass",
    "victims", "people", "passengers", "workers", "students",
    "bus", "train", "vehicle", "collapse", "explosion", "blast",
]

# ── Mass casualty threshold ──
MASS_CASUALTY_THRESHOLD = 5

# ── Resource estimation ratios ──
# One team can handle N victims simultaneously
VICTIMS_PER_TEAM        = 3
# One stretcher needed per N victims (serious cases)
VICTIMS_PER_STRETCHER   = 2
# Bandages per victim
BANDAGES_PER_VICTIM     = 4
# Oxygen masks for 20% of victims in mass casualty
OXYGEN_MASK_RATIO       = 0.2


def extract_victim_count(text: str) -> Optional[int]:
    """
    Extract victim count from text using three strategies:
      1. Digit extraction: "12 people", "15 injured"
      2. Number word parsing: "twelve people", "five victims"
      3. Implicit multi-victim triggers: return estimate

    Args:
        text: Raw emergency text

    Returns:
        Integer victim count or None if single/unknown
    """
    text_lower = text.lower()

    # ── Strategy 1: Look for digits followed by victim words ──
    digit_pattern = re.compile(
        r"(\d+)\s*(?:people|persons?|victims?|injured|casualties|passengers?|"
        r"workers?|students?|survivors?|trapped|dead|wounded|hurt)"
    )
    m = digit_pattern.search(text_lower)
    if m:
        return int(m.group(1))

    # ── Strategy 2: Number word + victim word ──
    for word, value in sorted(NUMBER_WORDS.items(), key=lambda x: -x[1]):
        pattern = rf"\b{word}\b.{{0,20}}(?:people|persons?|victims?|injured|casualties)"
        if re.search(pattern, text_lower):
            return value

    # ── Strategy 3: Approximate from collective nouns ──
    collective_map = {
        "bus": 30, "train": 80, "vehicle": 5, "truck": 8,
        "crowd": 15, "group": 6, "several people": 5,
        "multiple victims": 6, "many people": 10,
    }
    for phrase, estimate in collective_map.items():
        if phrase in text_lower:
            return estimate

    # ── Strategy 4: Any multi-victim trigger → assume 2+ ──
    if any(kw in text_lower for kw in MULTI_VICTIM_TRIGGERS):
        # Return 2 as minimum multi-victim estimate
        return 2

    return 1  # Default: single victim


def estimate_resources(victim_count: int, severity: str, context: Optional[Dict] = None) -> Dict:
    """
    Estimate required resources based on victim count and severity.

    Formula:
      teams      = ceil(victims / VICTIMS_PER_TEAM)
      stretchers = ceil(victims / VICTIMS_PER_STRETCHER) for CRITICAL/HIGH
      bandages   = victims * BANDAGES_PER_VICTIM
      oxygen     = ceil(victims * OXYGEN_MASK_RATIO)

    Args:
        victim_count: Number of victims
        severity:     Triage severity level
        context:      Intake context to assess situational hazards

    Returns:
        Resource estimate dict
    """
    import math

    teams = math.ceil(victim_count / VICTIMS_PER_TEAM)
    
    if severity == "CRITICAL" and victim_count == 1:
        teams = max(2, teams) # CRITICAL cases often require an extra ALS/rescue team minimum
        
    if context:
        raw_text = context.get("raw_text", "").lower()
        situation = context.get("situation", "").lower()
        environment = context.get("environment", "").lower()
        
        # Heavy extrication / rescue requires extra manpower regardless of victim count
        if any(w in raw_text or w in environment for w in ["trapped", "rubble", "collapse", "earthquake", "mountain", "cliff", "crush"]):
            teams += 2
            
        # Fire, flood, or hazmat scenarios require specialized teams overlapping with medical
        if any(w in raw_text or w in situation for w in ["fire", "blaze", "smoke", "flood", "water", "river", "chemical", "toxic", "poison"]):
            teams += 1
            
        # If it's a mass low-severity event (e.g. 50 people with headaches), 
        # we don't necessarily need 17 teams. We can use a much lighter ratio.
        if severity == "LOW" and victim_count > 5:
            teams = math.ceil(victim_count / 15) # Optimized ratio for minor mass incidents
            
        # Unconscious/Critical patients require more hands per patient
        if any(w in raw_text for w in ["unconscious", "unresponsive", "stopped breathing", "no pulse"]):
            teams += 1 # Add a dedicated CPR/ALS monitoring team allocation modifier
            
    teams = max(1, teams)

    stretchers = 0
    if severity in ("CRITICAL", "HIGH"):
        stretchers = math.ceil(victim_count / VICTIMS_PER_STRETCHER)

    bandages = victim_count * BANDAGES_PER_VICTIM
    oxygen_masks = math.ceil(victim_count * OXYGEN_MASK_RATIO)

    return {
        "required_teams":       teams,
        "required_stretchers":  stretchers,
        "required_bandages":    bandages,
        "required_oxygen_masks": oxygen_masks,
        "required_first_aid_kits": max(1, math.ceil(victim_count / 5)),
    }


def run_multi_victim_detector(text: str, severity: str = "MEDIUM", context: Dict = None) -> Dict:
    """
    Main multi-victim detection function.

    Args:
        text:     Raw emergency transcription
        severity: Triage severity (for resource estimation)
        context:  Intake context containing situational hazards

    Returns:
        victim_analysis dict
    """
    victim_count = extract_victim_count(text)
    is_mass_casualty = victim_count >= MASS_CASUALTY_THRESHOLD
    resource_estimate = estimate_resources(victim_count, severity, context)

    result = {
        "victim_count":      victim_count,
        "is_mass_casualty":  is_mass_casualty,
        "triage_protocol":   "START triage" if is_mass_casualty else "Individual triage",
        **resource_estimate,
    }

    print(f"[Multi-Victim Detector] Count: {victim_count} | "
          f"Mass casualty: {is_mass_casualty} | "
          f"Teams needed: {resource_estimate['required_teams']}")
    return result
