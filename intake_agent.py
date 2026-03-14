"""
agents/intake_agent.py
──────────────────────
Intake Agent: Parses raw transcription into structured emergency context.

Uses lightweight rule-based NLP with keyword matching.
Loads a KTAS emergency triage cases DataFrame for case-based matching.
No external LLM required — runs fully offline on CPU.

Input:  raw transcription string
Output: structured EmergencyContext dict
"""

import os
import re
from typing import Dict, List, Optional

import pandas as pd


# ── Load KTAS triage cases DataFrame ──
_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data.csv")
try:
    CASES_DF = pd.read_csv(_DATA_PATH, sep=";", encoding="latin-1")
    CASES_DF.columns = CASES_DF.columns.str.strip()
    # Clean up text columns
    for col in ["Chief_complain", "Diagnosis in ED"]:
        if col in CASES_DF.columns:
            CASES_DF[col] = CASES_DF[col].astype(str).str.strip().str.lower()
    print(f"[Intake Agent] Loaded {len(CASES_DF)} cases from data.csv")
except Exception as e:
    CASES_DF = pd.DataFrame()
    print(f"[Intake Agent] ⚠️ Could not load data.csv: {e}")


# ── Keyword dictionaries for entity extraction ──

# ── Written-out number words → digit mapping ──
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

def _words_to_num(text: str) -> str:
    """Replace written-out age words with digits, e.g. 'five year old' → '5 year old'."""
    for word, digit in _NUM_WORDS.items():
        text = re.sub(rf"\b{word}\b", str(digit), text, flags=re.IGNORECASE)
    return text


# ══════════════════════════════════════════════════════════════════════
# REGEX PATTERNS — each entry is (pattern, confidence_score, label_hint)
# Higher confidence = richer / more specific description.
# All patterns use a single capturing group that returns the full label.
# ══════════════════════════════════════════════════════════════════════
_VICTIM_PATTERN_TABLE = [

    # ── Explicit digit age + gender/role (most specific) ──────────────
    (r"(\d+[- ](?:year|yr)s?[- ]old\s+(?:baby|infant|newborn))",           95,  None),
    (r"(\d+[- ](?:year|yr)s?[- ]old\s+(?:boy|girl|child|kid|toddler))",    93,  None),
    (r"(\d+[- ](?:year|yr)s?[- ]old\s+(?:man|male|gentleman|father|grandfather|grandpa))",  90,  None),
    (r"(\d+[- ](?:year|yr)s?[- ]old\s+(?:woman|female|lady|mother|grandmother|grandma))",   90,  None),
    (r"(\d+[- ](?:year|yr)s?[- ]old\s+(?:person|patient|victim|individual|student|worker))", 88, None),
    (r"(\d+[- ](?:month|mo)s?[- ]old\s+(?:baby|infant|child|girl|boy))",    96,  None),
    (r"(\d+[- ]weeks?[- ]old\s+(?:baby|infant|newborn))",                   96,  None),

    # ── Digit age with role reversed ("boy of 5") ──────────────────────
    (r"((?:baby|infant|newborn|boy|girl|child|kid|toddler)\s+(?:of|aged?)\s+\d+\s*(?:years?|yrs?|months?|mos?))", 92, None),

    # ── Age adjective + gender combinations ────────────────────────────
    (r"((?:very\s+)?(?:newborn|premature)\s+(?:baby|infant))",               98, None),
    (r"((?:very\s+)?young\s+(?:baby|infant|toddler))",                       95, None),
    (r"((?:very\s+)?(?:young|little|small|tiny)\s+(?:girl|boy|child|kid))",  92, None),
    (r"((?:teenage?|adolescent)\s+(?:girl|boy|female|male|student))",        90, None),
    (r"((?:teenage?|adolescent)\s+(?:person|patient|victim))",               88, None),
    (r"((?:middle[- ]aged?|middle\s+age)\s+(?:man|woman|male|female))",     86, None),
    (r"((?:elderly|aged?|senior|old)\s+(?:man|gentleman|grandfather|grandpa))", 88, None),
    (r"((?:elderly|aged?|senior|old)\s+(?:woman|lady|grandmother|grandma))", 88, None),
    (r"((?:elderly|aged?|senior|old)\s+(?:person|patient|couple))",         86, None),

    # ── Standalone gender + role ────────────────────────────────────────
    (r"(pregnant\s+(?:woman|female|lady|patient|mother|teenager|teen))",     92, None),
    (r"(expectant\s+(?:mother|mom|woman))",                                  92, None),
    (r"(nursing\s+(?:mother|mom|baby))",                                     88, None),

    # ── Relationship hints (my son, her daughter, the driver …) ─────────
    (r"(?:my|his|her|their|the)\s+(son|daughter|child|baby|grandson|granddaughter)", 91, None),
    (r"(?:my|his|her|their|the)\s+(father|mother|dad|mom|grandfather|grandmother|grandpa|grandma)", 91, None),
    (r"(?:my|his|her|our|the)\s+(husband|wife|brother|sister|partner|spouse)", 87, None),

    # ── Occupation / role hints ─────────────────────────────────────────
    (r"(construction\s+worker|factory\s+worker|farm\s+worker|mine\s+worker)", 82, None),
    (r"(bus\s+driver|truck\s+driver|taxi\s+driver|motorcycle\s+rider|cyclist|pedestrian)", 82, None),
    (r"(student|schoolchild|schoolgirl|schoolboy|teacher|nurse|firefighter|soldier|officer)", 80, None),
    (r"(hiker|climber|swimmer|athlete|runner|player)",                        78, None),

    # ── Mass-casualty with explicit count ──────────────────────────────
    (r"(\d+\s+(?:people|persons|victims|individuals|passengers|workers|students|patients|children|adults|civilians))", 85, None),
    (r"((?:multiple|several|many|dozens?\s+of|hundreds?\s+of|few)\s+(?:people|persons|victims|individuals|passengers|workers|students|children|civilians))", 83, None),
    (r"(a\s+(?:family|couple|group(?:\s+of\s+\w+)?|crowd|class|team|bus(?:load)?(?:\s+of\s+(?:people|passengers|students))?))", 80, None),
]

# ── Fallback keyword → label mapping (most specific first, broad adult LAST) ──
_VICTIM_FALLBACK = [
    # Neonates / very young
    (["newborn", "neonate", "premature baby", "preemie"],        "newborn baby"),
    (["infant", "baby"],                                          "infant"),
    (["toddler"],                                                 "toddler"),
    # Children / teens
    (["schoolgirl", "schoolboy", "schoolchild"],                  "school-age child"),
    (["girl"],                                                    "girl"),
    (["boy"],                                                     "boy"),
    (["child", "kid"],                                            "child"),
    (["teenager", "teen", "adolescent"],                          "teenager"),
    # Elderly
    (["grandmother", "grandma", "grandma"],                       "elderly woman"),
    (["grandfather", "grandpa"],                                   "elderly man"),
    (["elderly", "old woman", "old man", "senior citizen",
      "senior", "aged"],                                          "elderly person"),
    # Special categories
    (["pregnant", "pregnancy", "expectant mother",
      "expecting", "with child"],                                 "pregnant woman"),
    (["disabled", "wheelchair", "differently abled",
      "special needs"],                                           "person with disability"),
    (["unconscious person", "unresponsive person"],               "unconscious person"),
    # Mass casualty
    (["multiple", "several", "many", "crowd", "mass casualty",
      "casualties", "victims", "passengers", "people", "workers",
      "students", "civilians"],                                   "multiple victims"),
    # Relationships (singular falls through to here)
    (["daughter", "granddaughter"],                               "girl"),
    (["son", "grandson"],                                         "boy"),
    (["mother", "mom"],                                           "adult female"),
    (["father", "dad"],                                           "adult male"),
    (["wife", "sister"],                                          "adult female"),
    (["husband", "brother"],                                      "adult male"),
    # Broad adult catch-alls — ALWAYS LAST
    (["woman", "lady", "female"],                                 "adult female"),
    (["man", "gentleman", "male"],                                "adult male"),
    (["adult", "person", "individual", "worker",
      "patient", "victim", "someone", "bystander"],              "adult"),
]


def _infer_gender_from_pronouns(text: str) -> str:
    """
    Best-effort gender inference from third-person pronouns if no
    victim descriptor was found elsewhere.
    Returns 'female', 'male', or '' if ambiguous.
    """
    text_lower = text.lower()
    female_hits = len(re.findall(r"\b(she|her|hers|herself)\b", text_lower))
    male_hits   = len(re.findall(r"\b(he|him|his|himself)\b",  text_lower))
    if female_hits > male_hits:
        return "female"
    if male_hits > female_hits:
        return "male"
    return ""


def _apply_num_words(text: str) -> str:
    """Pre-process: replace written-out numbers so regex age-patterns fire."""
    return _words_to_num(text)


def extract_victim(text: str) -> str:
    """
    Extract a rich, human-readable victim description from transcription.

    Multi-stage pipeline:
      1. Pre-process: convert word-numbers → digits (e.g. 'five-year-old').
      2. Score every pattern in _VICTIM_PATTERN_TABLE; keep highest-confidence match.
      3. Post-process: join captured groups into clean label, title-case.
      4. Fall back to keyword-→-label table (_VICTIM_FALLBACK), most-specific first.
      5. Last resort: pronoun-based gender inference ('adult male' / 'adult female').
      6. Default: 'Unknown person'.
    """
    processed = _apply_num_words(text)
    text_lower = processed.lower()

    # ── Stage 1 & 2: regex scoring ────────────────────────────────────────────
    best_label      = ""
    best_confidence = 0

    for pattern, confidence, _hint in _VICTIM_PATTERN_TABLE:
        m = re.search(pattern, text_lower, re.IGNORECASE)
        if m and confidence > best_confidence:
            parts = [g.strip() for g in m.groups() if g]
            candidate = " ".join(parts).strip()
            # Reject empty or suspiciously short labels
            if len(candidate) >= 2:
                best_label      = candidate
                best_confidence = confidence

    if best_label:
        # ── Stage 3: post-process ─────────────────────────────────────────────
        # Normalise spacing/hyphens; title-case
        label = re.sub(r"\s{2,}", " ", best_label).strip()
        # Restore "year-old" hyphen style
        label = re.sub(r"(\d+)\s+year\s+old", r"\1-year-old", label, flags=re.IGNORECASE)
        label = re.sub(r"(\d+)\s+month\s+old", r"\1-month-old", label, flags=re.IGNORECASE)
        label = re.sub(r"(\d+)\s+week\s+old",  r"\1-week-old",  label, flags=re.IGNORECASE)
        return label.capitalize()

    # ── Stage 4: keyword fallback ─────────────────────────────────────────────
    for keywords, label in _VICTIM_FALLBACK:
        if any(re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text_lower) for kw in keywords):
            return label.capitalize()

    # ── Stage 5: pronoun inference ────────────────────────────────────────────
    gender = _infer_gender_from_pronouns(text)
    if gender == "female":
        return "Adult female"
    if gender == "male":
        return "Adult male"

    return "Unknown person"

INJURY_KEYWORDS = {
    # ── Specific low-severity phrases (evaluated first) ──
    "minor cut":              ["minor cut", "small cut", "tiny cut", "superficial cut",
                               "paper cut", "scratch", "abrasion", "scrape", "graze",
                               "minor wound", "small wound", "small bleeding", "minor bleeding"],
    # Ordered: severe/specific first
    "cardiac arrest":         ["cardiac arrest", "heart attack", "no pulse", "not breathing",
                               "unresponsive", "unconscious", "collapsed"],
    "severe bleeding":        ["severe bleeding", "hemorrhage", "heavy bleeding", "blood spurting"],
    "head injury":            ["head injury", "head trauma", "concussion", "skull fracture",
                               "head wound", "traumatic brain"],
    "spinal injury":          ["spinal", "spine injury", "back injury", "neck injury", "paralysis"],
    "fracture":               ["fracture", "broken bone", "broken leg", "broken arm",
                               "broken wrist", "broken collar", "snap"],
    "burn":                   ["burn", "burning", "scalded", "fire injury", "thermal injury",
                               "chemical burn"],
    "choking":                ["choking", "can't breathe", "cannot breathe", "airway blocked",
                               "airway obstruction", "throat"],
    "breathing difficulty":   ["difficulty breathing", "shortness of breath", "asthma attack",
                               "respiratory distress", "breathing problem"],
    "bleeding":               ["bleeding", "blood", "laceration", "wound", "stab",
                               "slash", "gash"],
    "hypothermia":            ["hypothermia", "freezing", "cold exposure", "frostbite"],
    "poisoning":              ["poisoning", "overdose", "swallowed", "ingested", "toxic",
                               "drug overdose", "chemical ingestion"],
    "fall injury":            ["fell", "fallen", "fall", "falling", "tripped", "slipped",
                               "tumbled", "dropped from"],
    "drowning":               ["drowning", "drowned", "submerged", "underwater"],
    "allergic reaction":      ["allergic reaction", "allergy", "anaphylaxis", "anaphylactic",
                               "hives", "swelling", "bee sting"],
    "pain":                   ["severe pain", "chest pain", "abdominal pain", "intense pain",
                               "acute pain"],
    "cut":                    ["cut", "cuts"],
}


SITUATION_KEYWORDS = {
    "flood": ["flood", "flooding", "flooded", "water rising", "submerged"],
    "fire": ["fire", "smoke", "burning building", "flames", "blaze"],
    "earthquake": ["earthquake", "quake", "collapsed building", "debris", "rubble"],
    "accident": ["accident", "crash", "collision", "vehicle", "car crash"],
    "workplace": ["workplace", "factory", "construction", "industrial", "site accident"],
    "home": ["home", "house", "residential", "domestic"],
    "outdoor": ["outdoor", "hiking", "wilderness", "remote", "field"],
}

ENVIRONMENT_KEYWORDS = {
    "trapped_indoors": ["trapped", "trapped indoors", "can't get out", "stuck inside"],
    "outdoors": ["outdoor", "outside", "open area", "field", "park"],
    "vehicle": ["vehicle", "car", "truck", "inside a vehicle"],
    "water": ["water", "lake", "river", "swimming pool", "flood water"],
    "high_altitude": ["roof", "window", "floor", "high up", "elevated"],
}

# ── Location hint patterns (ordered most → least specific) ──
LOCATION_PATTERNS = [
    r"\b(school building|school|university|college|hospital|clinic|pharmacy)\b",
    r"\b(fire station|police station|train station|bus station|metro station)\b",
    r"\b(shopping mall|supermarket|market|store|shop|warehouse)\b",
    r"\b(office building|office|factory|plant|industrial site|construction site)\b",
    r"\b(apartment|flat|house|home|residence|building|complex)\b",
    r"\b(bridge|tunnel|highway|road|street|avenue|lane|alley)\b",
    r"\b(park|garden|playground|field|farm|forest|jungle|beach|river|lake)\b",
    r"\b(basement|ground floor|rooftop|roof|stairwell|corridor|hallway)\b",
    r"(?:near|at|in|inside|outside|behind|beside|next to|close to)\s+([\w\s]{3,30}?)(?=\s+(?:during|while|when|and|but|,)|$)",
]


def extract_location_hint(text: str) -> str:
    """
    Extract a location hint from transcription text.
    Tries structural patterns first, then keyword lookup.

    Args:
        text: Raw transcription string

    Returns:
        Location hint string, or "unknown location"
    """
    text_lower = text.lower()
    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            # Use group(1) if capturing group exists, else group(0)
            hint = match.group(1) if match.lastindex else match.group(0)
            hint = hint.strip().strip(",.")
            if hint and len(hint) > 2:
                return hint
    return "unknown location"




def extract_injury(text: str) -> str:
    """
    Extract primary injury description from transcription.

    Returns the matched keyword phrase (not the raw dict key) so the UI
    shows meaningful text like 'fall injury' instead of 'cardiac_arrest'.
    """
    text_lower = text.lower()
    best_match_len = 0
    best_label = None
    best_matched_keyword = None

    for injury_label, keywords in INJURY_KEYWORDS.items():
        for kw in keywords:
            if len(kw) > best_match_len and re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text_lower):
                best_match_len = len(kw)
                best_label = injury_label
                best_matched_keyword = kw

    if best_label and best_matched_keyword:
        if len(best_matched_keyword) > len(best_label):
            return best_matched_keyword.capitalize()
        return best_label.capitalize()

    # Fallback: extract medically-relevant verb or phrase from raw text
    medical_pattern = re.search(
        r"(pain|injured|hurt|wound|trauma|emergency|crisis|sick|ill|bleed|broke|broken|fell|fall)[\w\s]{0,30}",
        text_lower
    )
    if medical_pattern:
        return medical_pattern.group(0).strip()[:60].capitalize()
    return "Unspecified injury"


def extract_situation(text: str) -> str:
    """Extract situation/disaster type from transcription."""
    text_lower = text.lower()
    for situation, keywords in SITUATION_KEYWORDS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text_lower) for kw in keywords):
            return situation
    return "emergency situation"


def extract_environment(text: str) -> str:
    """Extract environmental context from transcription."""
    text_lower = text.lower()
    for env, keywords in ENVIRONMENT_KEYWORDS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text_lower) for kw in keywords):
            return env.replace("_", " ")
    return "unknown environment"


def extract_keywords(text: str) -> List[str]:
    """Extract emergency-relevant keywords from text."""
    all_keywords = []
    text_lower = text.lower()

    # Collect all keyword strings from victim fallback, injury, and situation dicts
    victim_kw_lists  = [kws for kws, _label in _VICTIM_FALLBACK]
    injury_kw_lists  = list(INJURY_KEYWORDS.values())
    situation_kw_lists = list(SITUATION_KEYWORDS.values())

    all_kw_lists = victim_kw_lists + injury_kw_lists + situation_kw_lists
    for kw_list in all_kw_lists:
        for kw in kw_list:
            if kw not in all_keywords and re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", text_lower):
                all_keywords.append(kw)

    # Filter out substrings to avoid redundancy and false severity escalations
    filtered_keywords = []
    for kw in all_keywords:
        # Keep if no other LONGER matched keyword contains this one
        if not any(kw != other and kw in other for other in all_keywords):
            filtered_keywords.append(kw)

    return filtered_keywords[:10]  # Cap at 10 keywords



def match_from_cases(text: str, top_n: int = 3) -> List[Dict]:
    """
    Match transcription against the KTAS cases DataFrame.
    Finds cases with the most keyword overlap in Chief_complain and Diagnosis.

    Args:
        text: Raw transcription string
        top_n: Number of top matches to return

    Returns:
        List of matched case dicts with vitals, severity, and diagnosis
    """
    if CASES_DF.empty:
        return []

    text_lower = text.lower()
    words = set(re.findall(r'\b[a-z]{3,}\b', text_lower))

    if not words:
        return []

    # Score each case by keyword overlap with Chief_complain + Diagnosis
    scores = []
    for idx, row in CASES_DF.iterrows():
        complaint = str(row.get("Chief_complain", ""))
        diagnosis = str(row.get("Diagnosis in ED", ""))
        case_text = f"{complaint} {diagnosis}"
        case_words = set(re.findall(r'\b[a-z]{3,}\b', case_text))
        overlap = len(words & case_words)
        if overlap > 0:
            scores.append((idx, overlap))

    if not scores:
        return []

    # Sort by overlap descending and take top_n
    scores.sort(key=lambda x: x[1], reverse=True)
    top_indices = [s[0] for s in scores[:top_n]]

    # Build result dicts
    results = []
    ktas_map = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "MINIMAL"}
    for idx in top_indices:
        row = CASES_DF.iloc[idx]
        severity_code = row.get("KTAS_expert", row.get("KTAS_RN", None))
        try:
            severity_code = int(float(severity_code))
        except (ValueError, TypeError):
            severity_code = None

        case = {
            "chief_complaint":  str(row.get("Chief_complain", "")),
            "diagnosis":        str(row.get("Diagnosis in ED", "")),
            "severity_ktas":    severity_code,
            "severity_label":   ktas_map.get(severity_code, "UNKNOWN"),
            "age":              row.get("Age", None),
            "sex":              row.get("Sex", None),
            "injury_flag":      row.get("Injury", None),
            "vitals": {
                "sbp":          row.get("SBP", None),
                "dbp":          row.get("DBP", None),
                "heart_rate":   row.get("HR", None),
                "resp_rate":    row.get("RR", None),
                "body_temp":    row.get("BT", None),
                "saturation":   row.get("Saturation", None),
            },
            "pain_score":       row.get("NRS_pain", None),
            "mental_status":    row.get("Mental", None),
            "disposition":      row.get("Disposition", None),
            "match_score":      scores[top_indices.index(idx)][1],
        }
        results.append(case)

    return results


def run_intake_agent(transcription: str) -> Dict:
    """
    Main intake agent function.
    Parses raw transcription into structured emergency context.
    Also matches against the KTAS cases DataFrame for enriched context.

    Args:
        transcription: Raw text from speech recognition

    Returns:
        Structured dict with victim, injury, situation, environment, keywords,
        and matched_cases from the DataFrame.
    """
    print("[Intake Agent] Parsing emergency context from transcription...")

    context = {
        "raw_text": transcription,
        "victim": extract_victim(transcription),
        "injury": extract_injury(transcription),
        "situation": extract_situation(transcription),
        "environment": extract_environment(transcription),
        "location_hint": extract_location_hint(transcription),
        "keywords": extract_keywords(transcription),
        "matched_cases": match_from_cases(transcription),
    }

    # If we found matching cases, enrich the context with the top match
    if context["matched_cases"]:
        top = context["matched_cases"][0]
        context["suggested_severity"] = top["severity_label"]
        context["suggested_diagnosis"] = top["diagnosis"]
        context["reference_vitals"] = top["vitals"]
        print(f"[Intake Agent] Top case match: {top['chief_complaint']} -> "
              f"{top['severity_label']} (score: {top['match_score']})")

    print(f"[Intake Agent] Extracted context: victim={context['victim']}, "
          f"injury={context['injury']}, situation={context['situation']}")
    return context

