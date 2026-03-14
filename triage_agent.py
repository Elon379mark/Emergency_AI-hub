"""
agents/triage_agent.py
──────────────────────
Triage Agent: Classifies emergency severity using hybrid rule-based reasoning.

Severity levels:
  CRITICAL → immediate life threat
  HIGH     → serious, act quickly
  MEDIUM   → concerning but stable
  LOW      → minor, routine care

Uses:
1. Rule-based keyword matching (primary)
2. Weighted scoring for edge cases
3. Modifier logic (environment/victim adjustments)
"""

from typing import Dict, Tuple

# ── Priority ordering (shared across modules) ──
PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}

# ── Severity rule definitions ──
# Each rule: (keywords_list, severity, base_confidence)

SEVERITY_RULES = {
    "CRITICAL": {
        "keywords": [
            # Cardiac / respiratory
            "cardiac arrest", "heart attack", "not breathing", "unconscious",
            "no pulse", "collapsed", "choking", "unresponsive",
            # Bleeding
            "severe bleeding", "hemorrhage", "heavy bleeding", "blood spurting",
            "internal bleeding",
            # Trauma
            "spinal injury", "neck injury", "head injury", "skull fracture",
            "crush injury", "crush syndrome", "amputation", "impalement",
            # Burns
            "electrical burn", "third degree burn", "third-degree burn",
            "chemical burn", "extensive burn",
            # Other immediate life threats
            "drowning", "overdose", "anaphylaxis", "anaphylactic",
            "seizure", "stroke", "eclampsia", "pre-eclampsia",
            # ── Obstetric emergencies ──
            "obstetric emergency", "miscarriage", "placental abruption",
            "ectopic pregnancy", "placenta previa", "premature labour",
            "premature labor", "cord prolapse", "uterine rupture",
            "postpartum hemorrhage", "antepartum hemorrhage",
            "pregnancy complication", "fetal distress",
        ],
        "base_confidence": 0.95,
    },
    "HIGH": {
        "keywords": [
            "fracture", "broken bone", "broken leg", "broken arm", "dislocation",
            "deep wound", "laceration", "bleeding", "blood", "burn",
            "difficulty breathing", "chest pain", "severe pain", "abdominal pain",
            "severe abdominal", "trapped", "flood", "fire", "earthquake",
            "high fever", "altered consciousness", "severe allergic",
            "snake bite", "animal bite", "electrocution", "eye injury",
        ],
        "base_confidence": 0.85,
    },
    "MEDIUM": {
        "keywords": [
            "sprain", "twisted", "bruise", "moderate pain", "nausea",
            "vomiting", "fever", "allergic reaction", "mild burn",
            "dehydration", "dizzy", "faint", "headache",
        ],
        "base_confidence": 0.75,
    },
    "LOW": {
        "keywords": [
            "minor cut", "small cut", "scratch", "bruise", "abrasion",
            "blister", "splinter", "insect bite", "minor headache",
            "cold", "cough", "sore throat", "low_severity_injury_token"
        ],
        "base_confidence": 0.70,
    },
}


# Victim modifiers: some victim types increase severity.
# Keys are SUBSTRINGS searched in the victim label (works with rich labels too).
VICTIM_SEVERITY_MODIFIER = {
    "elderly":   0.05,
    "senior":    0.05,
    "child":     0.06,
    "girl":      0.06,
    "boy":       0.06,
    "infant":    0.08,
    "baby":      0.08,
    "newborn":   0.09,
    "toddler":   0.07,
    "teenager":  0.04,
    "teen":      0.04,
    "pregnant":  0.07,
    "multiple":  0.10,   # mass casualty bump
    "victims":   0.10,
    "people":    0.08,
}

# Situation modifiers: disaster situations increase severity
SITUATION_SEVERITY_MODIFIER = {
    "flood": 0.05,
    "fire": 0.08,
    "earthquake": 0.07,
    "trapped": 0.05,
}

# Severity ordering for comparison
SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}


def compute_severity_score(text: str) -> Tuple[str, float]:
    """
    Score all severity levels against text and return highest match.

    Args:
        text: Lowercase emergency description

    Returns:
        Tuple of (severity_label, confidence_score)
    """
    best_severity = "LOW"
    best_confidence = 0.50

    # Mask minor phrases so their individual words (e.g. "bleeding" in "small bleeding") 
    # do not falsely trigger higher severity rules.
    masked_text = text
    minor_phrases = [
        "minor cut", "small cut", "tiny cut", "superficial cut", "paper cut",
        "minor wound", "small wound", "small bleeding", "minor bleeding"
    ]
    for phrase in minor_phrases:
        if phrase in masked_text:
            masked_text = masked_text.replace(phrase, "low_severity_injury_token")

    for severity, rule in SEVERITY_RULES.items():
        matched_keywords = [kw for kw in rule["keywords"] if kw in masked_text]
        if matched_keywords:
            # Confidence boosted by number of matched keywords
            confidence = rule["base_confidence"] + (len(matched_keywords) - 1) * 0.02
            confidence = min(confidence, 0.99)

            if SEVERITY_ORDER[severity] > SEVERITY_ORDER[best_severity]:
                best_severity = severity
                best_confidence = confidence
            elif (
                SEVERITY_ORDER[severity] == SEVERITY_ORDER[best_severity]
                and confidence > best_confidence
            ):
                best_confidence = confidence

    return best_severity, best_confidence


def apply_modifiers(
    severity: str,
    confidence: float,
    victim: str,
    situation: str,
    raw_text: str = "",
) -> Tuple[str, float]:
    """
    Apply victim and situation modifiers to severity assessment.
    Modifiers can increase confidence or escalate severity.

    Args:
        severity:  Current severity label
        confidence: Current confidence score
        victim:    Victim type string
        situation: Situation type string
        raw_text:  Full raw report text for combination rule checks

    Returns:
        Possibly modified (severity, confidence) tuple
    """
    victim_lower    = victim.lower()
    situation_lower = situation.lower()

    # ── Special combination rules (override base severity) ────────────────
    # Pregnant + any danger sign = always at least CRITICAL
    _danger_signs = (
        "bleed", "hemorrhage", "pain", "unconscious", "collapse",
        "not breathing", "seizure", "eclampsia", "fetal", "labour",
        "labor", "cord", "placenta", "rupture", "miscarriage", "ectopic",
    )
    if "pregnant" in victim_lower or "pregnancy" in victim_lower:
        combined_lower = (raw_text + " " + victim_lower).lower()
        if any(ds in combined_lower for ds in _danger_signs):
            print(f"[Triage Agent] Obstetric emergency detected — escalating to CRITICAL")
            return "CRITICAL", 0.97

    # Apply victim modifier — use substring search so rich labels work too
    for keyword, boost in VICTIM_SEVERITY_MODIFIER.items():
        if keyword in victim_lower:
            confidence = min(confidence + boost, 0.99)

            # Escalate MEDIUM → HIGH for vulnerable victims
            _vulnerable = (
                "elderly", "senior", "child", "girl", "boy",
                "infant", "baby", "newborn", "toddler", "pregnant",
            )
            if severity == "MEDIUM" and keyword in _vulnerable:
                severity = "HIGH"
                print(f"[Triage Agent] Escalated to HIGH due to vulnerable victim: {victim}")
            break

    # Apply situation modifier
    for keyword, boost in SITUATION_SEVERITY_MODIFIER.items():
        if keyword in situation_lower:
            confidence = min(confidence + boost, 0.99)
            break

    return severity, confidence


def run_triage_agent(context: Dict) -> Dict:
    """
    Main triage agent function.
    Classifies emergency severity from extracted context.

    Args:
        context: Output from intake agent (victim, injury, situation, environment)

    Returns:
        Dict with severity level, confidence, and reasoning
    """
    print("[Triage Agent] Classifying emergency severity...")

    # Build combined text for matching
    combined_text = " ".join([
        context.get("raw_text", ""),
        context.get("injury", ""),
        context.get("situation", ""),
        context.get("environment", ""),
        " ".join(context.get("keywords", [])),
    ]).lower()

    # Compute base severity from rules
    severity, confidence = compute_severity_score(combined_text)

    # Apply modifiers
    severity, confidence = apply_modifiers(
        severity,
        confidence,
        context.get("victim", ""),
        context.get("situation", ""),
        raw_text=context.get("raw_text", ""),
    )

    # Round confidence to 2 decimal places
    confidence = round(confidence, 2)

    # Human-readable confidence label
    if confidence >= 0.90:
        confidence_label = "High confidence"
    elif confidence >= 0.75:
        confidence_label = "Moderate confidence"
    else:
        confidence_label = "Low confidence"

    triage_result = {
        "severity": severity,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "reasoning": f"Matched keywords in: injury='{context.get('injury')}', "
                     f"situation='{context.get('situation')}', victim='{context.get('victim')}'"
    }

    print(f"[Triage Agent] Severity: {severity} (confidence: {confidence})")
    return triage_result
