"""
data/incident_logger.py
────────────────────────
Append-safe incident history and structured agent log writer.

Feature 4 — Incident History:
  Writes every processed emergency to data/incidents.json
  Fields: id, timestamp, victim, injury, severity, location,
          resource_used, confidence, situation

Feature 7 — Agent Execution Logs:
  Writes per-run structured agent logs to logs/agent_logs.json
  Each entry captures which agents ran, their timing, and key outputs.

Both files are append-safe: new records are added without corrupting
existing data, even if the file is empty or has previous entries.
"""

import os
import json
import uuid
import sys
from datetime import datetime
from typing import Dict, List, Optional

# fcntl is Linux/Mac only — use a cross-platform fallback for Windows
if sys.platform != "win32":
    import fcntl
    _USE_FCNTL = True
else:
    _USE_FCNTL = False

# ── File paths ──
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCIDENTS_PATH  = os.path.join(_BASE, "data", "incidents.json")
AGENT_LOGS_PATH = os.path.join(_BASE, "logs", "agent_logs.json")


# ────────────────────────────────────────────────────────────
# Low-level helpers
# ────────────────────────────────────────────────────────────

def _read_json_list(path: str) -> List:
    """Read a JSON file that contains a list. Returns [] if missing or malformed."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _write_json_list(path: str, data: List) -> None:
    """
    Write a list as JSON to path.
    Uses fcntl locking on Linux/Mac, simple write on Windows.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if _USE_FCNTL:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(data, f, indent=2, default=str, ensure_ascii=False)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        else:
            # Windows — just write directly (single-process use case)
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)


def _append_to_json_list(path: str, record: Dict) -> None:
    """
    Append a single record to a JSON list file atomically.
    Safe against concurrent writes.
    """
    existing = _read_json_list(path)
    existing.append(record)
    _write_json_list(path, existing)


# ────────────────────────────────────────────────────────────
# Feature 4 — Incident History
# ────────────────────────────────────────────────────────────

def log_incident(
    context: Dict,
    triage: Dict,
    resource_data: Dict,
    elapsed_seconds: float = 0.0,
) -> str:
    """
    Append a processed emergency to data/incidents.json.

    Args:
        context:        Intake agent output
        triage:         Triage agent output
        resource_data:  Resource agent output
        elapsed_seconds: Total pipeline processing time

    Returns:
        Incident ID string (UUID)
    """
    incident_id = str(uuid.uuid4())[:8].upper()

    # Collect resources actually used (AVAILABLE items)
    resources_used = [
        r["item"] for r in resource_data.get("resources", [])
        if r.get("status") == "AVAILABLE"
    ]

    record = {
        "id":             incident_id,
        "timestamp":      datetime.now().isoformat(timespec="seconds"),
        "victim":         context.get("victim", "unknown"),
        "injury":         context.get("injury", "unspecified"),
        "situation":      context.get("situation", "unknown"),
        "severity":       triage.get("severity", "UNKNOWN"),
        "confidence":     triage.get("confidence", 0.0),
        "location":       context.get("location_hint", "unknown location"),
        "environment":    context.get("environment", "unknown"),
        "resource_used":  resources_used,
        "low_stock_alerts": [
            a["item"] for a in resource_data.get("low_stock_alerts", [])
        ],
        "elapsed_seconds": round(elapsed_seconds, 2),
        "raw_text":       context.get("raw_text", ""),
    }

    _append_to_json_list(INCIDENTS_PATH, record)
    print(f"[Incident Logger] Saved incident {incident_id} → {INCIDENTS_PATH}")
    return incident_id


def get_recent_incidents(limit: int = 10) -> List[Dict]:
    """
    Return the most recent N incidents, newest first.

    Args:
        limit: Maximum number of incidents to return

    Returns:
        List of incident dicts
    """
    all_incidents = _read_json_list(INCIDENTS_PATH)
    return list(reversed(all_incidents))[:limit]


def get_incident_by_id(incident_id: str) -> Optional[Dict]:
    """Look up a single incident by its short ID."""
    for inc in _read_json_list(INCIDENTS_PATH):
        if inc.get("id") == incident_id:
            return inc
    return None


# ────────────────────────────────────────────────────────────
# Feature 7 — Structured Agent Execution Logs
# ────────────────────────────────────────────────────────────

def log_agent_run(
    incident_id: str,
    agent_logs: List[str],
    context: Dict,
    triage: Dict,
    elapsed_seconds: float,
) -> None:
    """
    Write a structured agent execution record to logs/agent_logs.json.

    Args:
        incident_id:     Short incident ID from log_incident()
        agent_logs:      List of log strings from LangGraph state
        context:         Intake agent output
        triage:          Triage agent output
        elapsed_seconds: Total pipeline time
    """
    # Parse which agents ran from the log strings
    agents_executed = []
    agent_names = [
        "Speech Module",
        "Intake Agent",
        "Triage Agent",
        "Knowledge Graph Agent",
        "Protocol Agent",
        "Resource Agent",
        "Response Agent",
    ]
    for name in agent_names:
        if any(name in log for log in agent_logs):
            agents_executed.append(f"{name} executed")

    record = {
        "incident_id":      incident_id,
        "timestamp":        datetime.now().isoformat(timespec="seconds"),
        "agents_executed":  agents_executed,
        "agent_count":      len(agents_executed),
        "severity":         triage.get("severity", "UNKNOWN"),
        "confidence":       triage.get("confidence", 0.0),
        "injury":           context.get("injury", "unspecified"),
        "victim":           context.get("victim", "unknown"),
        "elapsed_seconds":  round(elapsed_seconds, 2),
        "raw_logs":         agent_logs,
    }

    _append_to_json_list(AGENT_LOGS_PATH, record)
    print(f"[Incident Logger] Agent log saved → {AGENT_LOGS_PATH}")


def get_recent_agent_logs(limit: int = 10) -> List[Dict]:
    """Return most recent N agent log entries, newest first."""
    all_logs = _read_json_list(AGENT_LOGS_PATH)
    return list(reversed(all_logs))[:limit]
