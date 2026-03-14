"""
command/incident_manager.py
────────────────────────────
Section 1 — Incident Queue Management

Manages all incoming emergency requests with:
  • Unique incident ID assignment
  • Priority-sorted queue (CRITICAL > HIGH > MEDIUM > LOW)
  • Status tracking (pending / assigned / resolved)
  • Team assignment tracking
  • Thread-safe append-safe JSON persistence
"""

import os
import sys
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Cross-platform file locking
if sys.platform != "win32":
    import fcntl
    _USE_FCNTL = True
else:
    _USE_FCNTL = False

# ── Paths ──
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCIDENT_TABLE_PATH = os.path.join(_BASE, "data", "incident_table.json")

# ── Priority ordering ──
PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}

# ── Status values ──
STATUS_PENDING  = "pending"
STATUS_ASSIGNED = "assigned"
STATUS_RESOLVED = "resolved"


# ────────────────────────────────────────────────────────────
# I/O helpers
# ────────────────────────────────────────────────────────────

def _read_table() -> List[Dict]:
    if not os.path.exists(INCIDENT_TABLE_PATH):
        return []
    try:
        with open(INCIDENT_TABLE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError):
        return []


def _write_table(data: List[Dict]) -> None:
    os.makedirs(os.path.dirname(INCIDENT_TABLE_PATH), exist_ok=True)
    with open(INCIDENT_TABLE_PATH, "w", encoding="utf-8") as f:
        if _USE_FCNTL:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(data, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        else:
            json.dump(data, f, indent=2, default=str)


# ────────────────────────────────────────────────────────────
# Core incident operations
# ────────────────────────────────────────────────────────────

def create_incident(
    context: Dict,
    triage: Dict,
    resource_data: Dict,
    **kwargs
) -> Dict:
    """
    Create a new incident record and append to the incident table.

    Args:
        context:        Intake agent output
        triage:         Triage agent output
        resource_data:  Resource agent output
        **kwargs:       Additional fields like victim_analysis, survival_data, etc.

    Returns:
        New incident dict
    """
    incident_id = "INC-" + str(uuid.uuid4())[:6].upper()
    victim_analysis = kwargs.get("victim_analysis")
    survival_data   = kwargs.get("survival_data")

    incident = {
        "incident_id":    incident_id,
        "timestamp":      datetime.now().isoformat(timespec="seconds"),
        "victim":         context.get("victim", "unknown"),
        "victim_count":   (victim_analysis or {}).get("victim_count", 1),
        "injury":         context.get("injury", "unspecified"),
        "situation":      context.get("situation", "unknown"),
        "location":       context.get("location_hint", "unknown location"),
        "environment":    context.get("environment", "unknown"),
        "severity":       triage.get("severity", "UNKNOWN"),
        "confidence":     triage.get("confidence", 0.0),
        "triage":         triage,
        "survival_data":  survival_data or {},
        "status":         STATUS_PENDING,
        "assigned_team":  None,
        "resources_needed": resource_data.get("critical_missing", []),
        "priority_score": _compute_priority_score(triage, victim_analysis),
        "coordinates":    context.get("coordinates"),
        "raw_text":       context.get("raw_text", ""),
        "cluster_id":     None,
        "resolved_at":    None,
    }

    table = _read_table()
    table.append(incident)
    _write_table(table)

    print(f"[Incident Manager] Created {incident_id} | {incident['severity']} | {incident['location']}")
    return incident


def _compute_priority_score(triage: Dict, victim_analysis: Optional[Dict]) -> float:
    """
    Compute a numeric priority score for queue sorting.

    Score = severity_base + confidence_boost + victim_count_boost

    Higher score = higher queue priority.
    """
    base = PRIORITY_ORDER.get(triage.get("severity", "LOW"), 1) * 25.0
    confidence_boost = triage.get("confidence", 0.5) * 10.0
    victim_count = (victim_analysis or {}).get("victim_count", 1)
    count_boost = min(victim_count * 0.5, 15.0)   # capped at 15
    return round(base + confidence_boost + count_boost, 2)


def get_sorted_queue(
    status_filter: Optional[List[str]] = None
) -> List[Dict]:
    """
    Return incidents sorted by priority_score descending.

    Args:
        status_filter: Only include incidents with these statuses (None = all)

    Returns:
        Sorted list of incident dicts
    """
    table = _read_table()
    if status_filter:
        table = [i for i in table if i.get("status") in status_filter]
    return sorted(table, key=lambda x: x.get("priority_score", 0), reverse=True)


def get_pending_queue() -> List[Dict]:
    """Return pending incidents sorted by priority."""
    return get_sorted_queue(status_filter=[STATUS_PENDING])


def assign_incident(incident_id: str, team_id: str) -> bool:
    """
    Assign a team to an incident and set status to 'assigned'.

    Returns True if successful.
    """
    table = _read_table()
    for inc in table:
        if inc["incident_id"] == incident_id:
            inc["status"]       = STATUS_ASSIGNED
            inc["assigned_team"] = team_id
            _write_table(table)
            print(f"[Incident Manager] {incident_id} assigned to {team_id}")
            return True
    return False


def resolve_incident(incident_id: str) -> bool:
    """Mark an incident as resolved."""
    table = _read_table()
    for inc in table:
        if inc["incident_id"] == incident_id:
            inc["status"]      = STATUS_RESOLVED
            inc["resolved_at"] = datetime.now().isoformat(timespec="seconds")
            _write_table(table)
            print(f"[Incident Manager] {incident_id} resolved ✓")
            return True
    return False


def get_incident(incident_id: str) -> Optional[Dict]:
    """Look up a single incident by ID."""
    for inc in _read_table():
        if inc["incident_id"] == incident_id:
            return inc
    return None


def get_stats() -> Dict:
    """Return aggregate statistics for the situation report."""
    table = _read_table()
    stats = {
        "total":    len(table),
        "critical": sum(1 for i in table if i.get("severity") == "CRITICAL"),
        "high":     sum(1 for i in table if i.get("severity") == "HIGH"),
        "medium":   sum(1 for i in table if i.get("severity") == "MEDIUM"),
        "low":      sum(1 for i in table if i.get("severity") == "LOW"),
        "pending":  sum(1 for i in table if i.get("status") == STATUS_PENDING),
        "assigned": sum(1 for i in table if i.get("status") == STATUS_ASSIGNED),
        "resolved": sum(1 for i in table if i.get("status") == STATUS_RESOLVED),
    }
    return stats
