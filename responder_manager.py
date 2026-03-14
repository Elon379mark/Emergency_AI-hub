"""
command/responder_manager.py
──────────────────────────────
Section 3 — Responder Assignment System

Manages responder teams and auto-assigns them to incidents.

Assignment Algorithm:
  Score = (priority_weight * 0.6) + (proximity_weight * 0.3) + (availability * 0.1)
  Assign highest-scoring available team to each pending incident.

Data Structures:
  responders.json  — persistent team registry
  assignments.json — incident ↔ team assignment log
"""

import os
import sys
import json
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

if sys.platform != "win32":
    import fcntl
    _USE_FCNTL = True
else:
    _USE_FCNTL = False

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESPONDERS_PATH   = os.path.join(_BASE, "data", "responders.json")
ASSIGNMENTS_PATH  = os.path.join(_BASE, "data", "assignments.json")

# ── Team status values ──
STATUS_AVAILABLE = "available"
STATUS_BUSY      = "busy"
STATUS_OFFLINE   = "offline"

# ── Team type priorities for incident types ──
TEAM_SPECIALISATION = {
    "rescue":  ["fracture", "trapped", "spinal", "flood", "earthquake"],
    "medical": ["cardiac_arrest", "bleeding", "burn", "choking", "breathing"],
    "hazmat":  ["chemical", "toxic", "poisoning", "fire"],
    "general": [],   # handles any incident
}

# ── Priority score weights ──
W_PRIORITY    = 0.60
W_PROXIMITY   = 0.30
W_AVAIL_BONUS = 0.10


# ────────────────────────────────────────────────────────────
# I/O helpers
# ────────────────────────────────────────────────────────────

def _read_json(path: str) -> List:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except:
        return []


def _write_json(path: str, data: List) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if _USE_FCNTL:
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
                json.dump(data, f, indent=2, default=str)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        else:
            json.dump(data, f, indent=2, default=str)


# ────────────────────────────────────────────────────────────
# Distance computation (Haversine formula)
# ────────────────────────────────────────────────────────────

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute great-circle distance between two GPS coordinates.
    Returns distance in metres.

    Formula: d = 2R * arcsin(sqrt(sin²(Δlat/2) + cos(lat1)*cos(lat2)*sin²(Δlon/2)))
    R = 6371000 metres
    """
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_travel_time_minutes(distance_metres: float, speed_kmh: float = 30.0) -> float:
    """Estimate travel time in minutes given distance and average speed."""
    return (distance_metres / 1000.0) / speed_kmh * 60.0


# ────────────────────────────────────────────────────────────
# Responder team management
# ────────────────────────────────────────────────────────────

def seed_default_teams() -> None:
    """
    Seed a default set of responder teams if no data exists.
    Called on first run.
    """
    if os.path.exists(RESPONDERS_PATH):
        return

    default_teams = [
        {
            "team_id":      "TEAM-ALPHA",
            "name":         "Alpha Rescue Unit",
            "type":         "rescue",
            "members":      4,
            "status":       STATUS_AVAILABLE,
            "lat":          0.0,
            "lon":          0.0,
            "current_incident": None,
            "skills":       ["fracture", "trapped", "flood"],
            "created_at":   datetime.now().isoformat(timespec="seconds"),
        },
        {
            "team_id":      "TEAM-BRAVO",
            "name":         "Bravo Medical Unit",
            "type":         "medical",
            "members":      3,
            "status":       STATUS_AVAILABLE,
            "lat":          0.0,
            "lon":          0.005,
            "current_incident": None,
            "skills":       ["cardiac_arrest", "bleeding", "burn"],
            "created_at":   datetime.now().isoformat(timespec="seconds"),
        },
        {
            "team_id":      "TEAM-CHARLIE",
            "name":         "Charlie General Response",
            "type":         "general",
            "members":      5,
            "status":       STATUS_AVAILABLE,
            "lat":          0.003,
            "lon":          0.0,
            "current_incident": None,
            "skills":       [],
            "created_at":   datetime.now().isoformat(timespec="seconds"),
        },
        {
            "team_id":      "TEAM-DELTA",
            "name":         "Delta Hazmat Unit",
            "type":         "hazmat",
            "members":      4,
            "status":       STATUS_AVAILABLE,
            "lat":          0.005,
            "lon":          0.005,
            "current_incident": None,
            "skills":       ["chemical", "toxic", "fire"],
            "created_at":   datetime.now().isoformat(timespec="seconds"),
        },
    ]
    _write_json(RESPONDERS_PATH, default_teams)
    print("[Responder Manager] Seeded 4 default teams ✓")


def get_all_teams() -> List[Dict]:
    seed_default_teams()
    return _read_json(RESPONDERS_PATH)


def get_available_teams() -> List[Dict]:
    return [t for t in get_all_teams() if t.get("status") == STATUS_AVAILABLE]


def update_team_status(team_id: str, status: str, incident_id: Optional[str] = None) -> bool:
    teams = get_all_teams()
    for t in teams:
        if t["team_id"] == team_id:
            t["status"]           = status
            t["current_incident"] = incident_id
            _write_json(RESPONDERS_PATH, teams)
            return True
    return False


def update_team_location(team_id: str, lat: float, lon: float) -> bool:
    teams = get_all_teams()
    for t in teams:
        if t["team_id"] == team_id:
            t["lat"] = lat
            t["lon"] = lon
            _write_json(RESPONDERS_PATH, teams)
            return True
    return False


# ────────────────────────────────────────────────────────────
# Assignment algorithm
# ────────────────────────────────────────────────────────────

def _specialisation_bonus(team: Dict, incident: Dict) -> float:
    """
    Return 0.0–1.0 bonus if team skills match incident injury/situation.
    """
    injury    = incident.get("injury", "").lower()
    situation = incident.get("situation", "").lower()
    skills    = [s.lower() for s in team.get("skills", [])]

    if not skills:  # general team handles anything
        return 0.5

    combined = injury + " " + situation
    for skill in skills:
        if skill in combined:
            return 1.0
    return 0.2


def score_team_for_incident(team: Dict, incident: Dict, max_distance: float = 50_000.0) -> float:
    """
    Compute assignment score for a team–incident pair.

    Score = W_PRIORITY * priority_norm
          + W_PROXIMITY * (1 - normalised_distance)
          + W_AVAIL_BONUS * specialisation_bonus

    Args:
        team:         Team dict
        incident:     Incident dict
        max_distance: Normalisation cap in metres (default 50 km)

    Returns:
        Score in [0, 1]
    """
    # Priority contribution
    from command.incident_manager import PRIORITY_ORDER
    severity = incident.get("severity", "LOW")
    priority_norm = PRIORITY_ORDER.get(severity, 1) / 4.0   # normalise to [0,1]

    # Proximity contribution (use stored lat/lon if available, else 0 distance)
    inc_lat = incident.get("lat", team["lat"])
    inc_lon = incident.get("lon", team["lon"])
    distance = haversine_distance(team["lat"], team["lon"], inc_lat, inc_lon)
    proximity_norm = max(0.0, 1.0 - distance / max_distance)

    # Specialisation bonus
    spec_bonus = _specialisation_bonus(team, incident)

    score = W_PRIORITY * priority_norm + W_PROXIMITY * proximity_norm + W_AVAIL_BONUS * spec_bonus
    return round(score, 4)


def auto_assign(incident: Dict, required_teams: int = 1) -> Optional[str]:
    """
    Auto-assign the best available team(s) to an incident.

    Algorithm:
      1. Filter available teams
      2. Score each team against the incident
      3. Assign highest-scoring team(s) up to required_teams capability
      4. Update team status to busy

    Returns:
        Assigned team_id(s) joined by comma or None if no teams available
    """
    available = get_available_teams()
    if not available:
        print("[Responder Manager] ⚠️  No available teams for assignment")
        return None

    # Score all available teams
    scored = [(t, score_team_for_incident(t, incident)) for t in available]
    scored.sort(key=lambda x: x[1], reverse=True)
    
    assigned_team_ids = []
    assignments = _read_json(ASSIGNMENTS_PATH)
    incident_id = incident["incident_id"]

    teams_to_assign = min(required_teams, len(scored))
    
    for i in range(teams_to_assign):
        best_team, best_score = scored[i]
        team_id = best_team["team_id"]

        # Update team status
        update_team_status(team_id, STATUS_BUSY, incident_id)
        assigned_team_ids.append(team_id)

        # Log assignment
    assignments = _read_json(ASSIGNMENTS_PATH)
    assignments.append({
        "assignment_id":  f"ASGN-{len(assignments)+1:04d}",
        "incident_id":    incident_id,
        "team_id":        team_id,
        "score":          best_score,
        "timestamp":      datetime.now().isoformat(timespec="seconds"),
        "travel_time_est": estimate_travel_time_minutes(
            haversine_distance(
                best_team["lat"], best_team["lon"],
                incident.get("lat", best_team["lat"]),
                incident.get("lon", best_team["lon"])
            )
        ),
    })
    _write_json(ASSIGNMENTS_PATH, assignments)

    joined_teams = ", ".join(assigned_team_ids)
    print(f"[Responder Manager] {joined_teams} → {incident_id}")
    return joined_teams


def release_team(team_id: str) -> bool:
    """Release a team back to available status when incident is resolved."""
    return update_team_status(team_id, STATUS_AVAILABLE, None)
