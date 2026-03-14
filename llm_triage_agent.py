"""
agents/llm_triage_agent.py
──────────────────────────
LLM-Powered Triage Agent — Disaster Command Center v4 ELITE

Replaces keyword-based triage with Claude API intelligence.
Falls back to rule-based triage on timeout or API failure.

Features:
• POST to https://api.anthropic.com/v1/messages
• Model: claude-sonnet-4-20250514
• Retry logic (2 retries with exponential backoff)
• Timeout fallback to rule-based triage
• Cache last 10 calls in data/llm_cache.json
• Latency logging in logs/llm_calls.json
"""

import os
import sys
import json
import time
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from collections import deque
from dotenv import load_dotenv

# ── Load environment variables ──
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Constants ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "data", "llm_cache.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "llm_calls.json")
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
MAX_CACHE = 10
TIMEOUT_SECONDS = 8
MAX_RETRIES = 2

# ── Severity priority mapping (matches triage_agent.py) ──
PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

SEVERITY_COLORS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}


# ──────────────────────────────────────────────────────────────
# Cache helpers
# ──────────────────────────────────────────────────────────────

def _load_cache() -> Dict[str, Any]:
    """Load LLM response cache from disk."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"entries": [], "keys": []}


def _save_cache(cache: Dict[str, Any]) -> None:
    """Persist cache to disk, keeping only last MAX_CACHE entries."""
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _cache_key(transcription: str) -> str:
    """Generate deterministic cache key from transcription."""
    return hashlib.md5(transcription.strip().lower().encode()).hexdigest()


def _get_cached(transcription: str) -> Optional[Dict]:
    """Return cached triage result if available."""
    key = _cache_key(transcription)
    cache = _load_cache()
    for entry in cache.get("entries", []):
        if entry.get("key") == key:
            return entry.get("result")
    return None


def _store_cached(transcription: str, result: Dict) -> None:
    """Store result in cache, evicting oldest if over MAX_CACHE."""
    key = _cache_key(transcription)
    cache = _load_cache()
    entries = cache.get("entries", [])

    # Remove existing entry with same key
    entries = [e for e in entries if e.get("key") != key]

    entries.append({
        "key": key,
        "transcription_preview": transcription[:80],
        "result": result,
        "cached_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    # Keep only last MAX_CACHE
    if len(entries) > MAX_CACHE:
        entries = entries[-MAX_CACHE:]

    cache["entries"] = entries
    _save_cache(cache)


# ──────────────────────────────────────────────────────────────
# Log helpers
# ──────────────────────────────────────────────────────────────

def _log_call(transcription: str, latency_ms: float, method: str,
              success: bool, error: str = "") -> None:
    """Append call metadata to logs/llm_calls.json."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        logs = []
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
        logs.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "transcription_preview": transcription[:60],
            "latency_ms": round(latency_ms, 1),
            "method": method,
            "success": success,
            "error": error,
        })
        # Keep last 200 log entries
        if len(logs) > 200:
            logs = logs[-200:]
        with open(LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# Rule-based fallback triage
# ──────────────────────────────────────────────────────────────

def _rule_based_triage(intake_context: Dict) -> Dict:
    """
    Keyword-based triage fallback when LLM is unavailable.
    Returns same schema as LLM triage.
    """
    injury = str(intake_context.get("injury", "")).lower()
    victim = str(intake_context.get("victim", "")).lower()
    transcription = str(intake_context.get("transcription", "")).lower()
    text = f"{injury} {victim} {transcription}"

    critical_kw = ["cardiac arrest", "not breathing", "unconscious", "severe bleeding",
                   "head trauma", "spinal", "anaphylaxis", "stroke", "drowning",
                   "crush injury", "multiple trauma"]
    high_kw = ["chest pain", "difficulty breathing", "heavy bleeding", "fracture",
               "burn", "loss of consciousness", "seizure", "overdose", "stab", "gunshot"]
    low_kw = ["minor cut", "bruise", "sprain", "mild", "stable", "conscious",
              "talking", "walking"]

    if any(kw in text for kw in critical_kw):
        severity = "CRITICAL"
        reasoning = "Critical keywords detected (cardiac/trauma/airway)"
        immediate = ["Establish airway", "CPR if pulseless", "Call ALS immediately"]
        color_code = "RED"
    elif any(kw in text for kw in high_kw):
        severity = "HIGH"
        reasoning = "High-priority keywords (chest/bleeding/breathing)"
        immediate = ["Control bleeding", "Monitor vitals", "Prepare transport"]
        color_code = "ORANGE"
    elif any(kw in text for kw in low_kw):
        severity = "LOW"
        reasoning = "Minor injury keywords detected"
        immediate = ["Clean and dress wound", "Monitor for changes"]
        color_code = "GREEN"
    else:
        severity = "MEDIUM"
        reasoning = "No definitive keywords — defaulting to MEDIUM"
        immediate = ["Assess ABCs", "Monitor vitals every 5 minutes"]
        color_code = "YELLOW"

    return {
        "severity": severity,
        "color_code": color_code,
        "confidence": 0.65,
        "reasoning": reasoning,
        "immediate_actions": immediate,
        "transport_priority": "IMMEDIATE" if severity in ("CRITICAL", "HIGH") else "DELAYED",
        "triage_category": color_code,
        "triage_method": "rule_based",
        "model_used": None,
    }


# ──────────────────────────────────────────────────────────────
# LLM triage via Claude API
# ──────────────────────────────────────────────────────────────

def _build_prompt(transcription: str, intake_context: Dict) -> str:
    """Build structured triage prompt for Claude."""
    victim = intake_context.get("victim", "unknown")
    injury = intake_context.get("injury", "unknown")
    location = intake_context.get("location_hint", "unknown")

    return f"""You are a senior emergency medical triage officer in a disaster response center.
Analyze the following emergency report and provide a structured triage assessment.

EMERGENCY REPORT:
Transcription: {transcription}
Victim: {victim}
Reported Injury: {injury}
Location: {location}

Respond ONLY with a valid JSON object in this exact format:
{{
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "color_code": "RED|ORANGE|YELLOW|GREEN",
  "confidence": 0.0-1.0,
  "reasoning": "brief clinical reasoning",
  "immediate_actions": ["action1", "action2", "action3"],
  "transport_priority": "IMMEDIATE|URGENT|DELAYED|EXPECTANT",
  "triage_category": "RED|ORANGE|YELLOW|GREEN",
  "secondary_injuries_suspected": ["list or empty"],
  "special_considerations": "any flags (pediatric, elderly, hazmat, etc.)"
}}

Severity definitions:
- CRITICAL (RED): Life-threatening, immediate intervention required
- HIGH (ORANGE): Serious, can wait 30-60 min
- MEDIUM (YELLOW): Non-life-threatening, can wait 1-2 hours
- LOW (GREEN): Minor, ambulatory, treat last"""


def _call_claude_api(transcription: str, intake_context: Dict) -> Optional[Dict]:
    """
    Call Claude API with retry logic.
    Returns parsed JSON dict or None on failure.
    """
    prompt = _build_prompt(transcription, intake_context)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    last_error = ""
    for attempt in range(1, MAX_RETRIES + 2):  # attempts: 1, 2, 3
        try:
            req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                text = body["content"][0]["text"].strip()

                # Strip markdown fences if present
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]

                parsed = json.loads(text)
                parsed["triage_method"] = "llm"
                parsed["model_used"] = MODEL
                return parsed

        except urllib.error.URLError as e:
            last_error = f"URLError: {e.reason}"
        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e}"
        except Exception as e:
            last_error = str(e)

        if attempt <= MAX_RETRIES:
            time.sleep(0.5 * attempt)  # Exponential backoff

    return None  # All retries exhausted


# ──────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────

def run_llm_triage_agent(transcription: str, intake_context: Optional[Dict] = None) -> Dict:
    """
    Primary entry point for LLM-powered triage.

    Args:
        transcription: Raw emergency report text
        intake_context: Dict with victim, injury, location_hint keys

    Returns:
        Triage result dict with triage_method = "llm" | "rule_based"
    """
    if intake_context is None:
        intake_context = {"transcription": transcription}

    # ── Check cache first ──
    cached = _get_cached(transcription)
    if cached:
        cached["from_cache"] = True
        return cached

    start = time.time()

    # ── Try LLM ──
    result = _call_claude_api(transcription, intake_context)
    latency_ms = (time.time() - start) * 1000

    if result:
        result["from_cache"] = False
        _store_cached(transcription, result)
        _log_call(transcription, latency_ms, "llm", success=True)
        return result

    # ── Fallback to rule-based ──
    _log_call(transcription, latency_ms, "rule_based", success=False,
              error="LLM unavailable — used rule-based fallback")
    fallback = _rule_based_triage(intake_context)
    fallback["from_cache"] = False
    return fallback


def get_cache_stats() -> Dict:
    """Return cache statistics for dashboard display."""
    cache = _load_cache()
    entries = cache.get("entries", [])
    return {
        "cached_entries": len(entries),
        "max_cache": MAX_CACHE,
        "recent_keys": [e.get("transcription_preview", "")[:40] for e in entries[-3:]],
    }


def get_llm_log_summary() -> List[Dict]:
    """Return last 20 LLM call log entries."""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                logs = json.load(f)
            return logs[-20:]
    except Exception:
        pass
    return []
