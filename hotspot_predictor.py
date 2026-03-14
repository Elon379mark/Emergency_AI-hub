"""
command/hotspot_predictor.py
─────────────────────────────
Hotspot Prediction Engine — Disaster Command Center v4 ELITE

Analyzes historical incident data to predict high-risk locations.
Uses frequency × recency weighting to score hotspots.

Returns top 5 hotspots with risk scores, predicted injury types,
and peak hour ranges. Dashboard shows heatmap and hotspot list.
"""

import os
import sys
import json
import time
import math
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCIDENTS_FILE = os.path.join(BASE_DIR, "data", "incident_table.json")


def _load_incidents() -> List[Dict]:
    """Load all incidents from disk."""
    try:
        if os.path.exists(INCIDENTS_FILE):
            with open(INCIDENTS_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _parse_hour(timestamp_str: str) -> Optional[int]:
    """Extract hour (0-23) from ISO timestamp string."""
    try:
        time_part = timestamp_str.split("T")[1] if "T" in timestamp_str else timestamp_str
        hour = int(time_part.split(":")[0])
        return hour
    except Exception:
        return None


def _parse_day_of_week(timestamp_str: str) -> Optional[str]:
    """Extract day of week abbreviation from ISO timestamp."""
    try:
        import datetime
        date_part = timestamp_str.split("T")[0]
        dt = datetime.datetime.strptime(date_part, "%Y-%m-%d")
        return dt.strftime("%a")  # Mon, Tue, etc.
    except Exception:
        return None


def _recency_weight(timestamp_str: str, decay_days: float = 30.0) -> float:
    """
    Compute recency weight using exponential decay.
    Recent incidents have weight ~1.0, older incidents approach 0.

    Args:
        timestamp_str: ISO format timestamp
        decay_days: Half-life in days (default 30 days)

    Returns:
        Weight between 0 and 1
    """
    try:
        import datetime
        date_part = timestamp_str.split("T")[0]
        incident_date = datetime.datetime.strptime(date_part, "%Y-%m-%d")
        now = datetime.datetime.now()
        days_ago = (now - incident_date).days
        # Exponential decay
        return math.exp(-days_ago / decay_days)
    except Exception:
        return 0.5  # Default weight for unparseable timestamps


def _normalize_location(location: str) -> str:
    """Normalize location string for aggregation."""
    if not location:
        return "Unknown"
    # Lowercase, strip, truncate to first meaningful segment
    loc = location.strip().lower()
    # Remove common prefixes
    for prefix in ["near ", "at ", "in ", "by "]:
        if loc.startswith(prefix):
            loc = loc[len(prefix):]
    return loc[:50]


def analyze_hotspots(top_n: int = 5) -> List[Dict]:
    """
    Analyze incident history to identify geographic hotspots.

    Uses frequency × recency weighting:
        risk_score = Σ (severity_weight × recency_weight) per location

    Args:
        top_n: Number of top hotspots to return

    Returns:
        List of hotspot dicts, sorted by risk_score descending
    """
    incidents = _load_incidents()

    if not incidents:
        return _get_demo_hotspots()

    # ── Aggregate by location ──
    location_data: Dict[str, Dict] = defaultdict(lambda: {
        "raw_location": "",
        "incidents": [],
        "injuries": [],
        "severities": [],
        "hours": [],
        "days": [],
        "risk_score": 0.0,
        "frequency": 0,
    })

    severity_weights = {"CRITICAL": 4.0, "HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.0}

    for inc in incidents:
        raw_loc = inc.get("location", inc.get("location_hint", "Unknown"))
        norm_loc = _normalize_location(str(raw_loc))
        sev = inc.get("severity", "MEDIUM")
        ts = inc.get("created_at", "")

        entry = location_data[norm_loc]
        entry["raw_location"] = raw_loc
        entry["incidents"].append(inc.get("incident_id", "?"))
        entry["injuries"].append(inc.get("injury", "unknown"))
        entry["severities"].append(sev)
        entry["frequency"] += 1

        # Hour and day tracking for heatmap
        hour = _parse_hour(ts)
        day = _parse_day_of_week(ts)
        if hour is not None:
            entry["hours"].append(hour)
        if day is not None:
            entry["days"].append(day)

        # Weighted score
        sw = severity_weights.get(sev, 2.0)
        rw = _recency_weight(ts)
        entry["risk_score"] += sw * rw

    # ── Build hotspot list ──
    hotspots = []
    for norm_loc, data in location_data.items():
        if data["frequency"] == 0:
            continue

        # Most common injury
        injury_counts: Dict[str, int] = defaultdict(int)
        for inj in data["injuries"]:
            injury_counts[str(inj).lower()] += 1
        predicted_injury = max(injury_counts, key=lambda k: injury_counts[k]) if injury_counts else "unknown"

        # Peak hour range
        hours = data["hours"]
        if hours:
            avg_hour = sum(hours) / len(hours)
            peak_start = int(avg_hour - 1) % 24
            peak_end = int(avg_hour + 1) % 24
            peak_hour_range = f"{peak_start:02d}:00 – {peak_end:02d}:00"
        else:
            peak_hour_range = "Unknown"

        # Dominant severity
        sev_counts: Dict[str, int] = defaultdict(int)
        for s in data["severities"]:
            sev_counts[s] += 1
        dominant_sev = max(sev_counts, key=lambda k: sev_counts[k]) if sev_counts else "MEDIUM"

        hotspots.append({
            "hotspot_location": str(data["raw_location"])[:60],
            "normalized_location": norm_loc,
            "risk_score": round(data["risk_score"], 2),
            "frequency": data["frequency"],
            "predicted_injury": predicted_injury,
            "dominant_severity": dominant_sev,
            "peak_hour_range": peak_hour_range,
            "incident_ids": data["incidents"][:5],
            "days_active": list(set(data["days"])),
        })

    hotspots.sort(key=lambda h: h["risk_score"], reverse=True)
    return hotspots[:top_n]


def build_hour_day_heatmap() -> Dict:
    """
    Build hour × day heatmap of incident frequency.

    Returns:
        Dict with:
            days: list of 7 day labels
            hours: list of 24 hour labels
            matrix: 7×24 grid of incident counts
    """
    incidents = _load_incidents()

    days_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hours_order = list(range(24))

    # Initialize 7×24 matrix
    matrix = {day: {h: 0 for h in hours_order} for day in days_order}

    for inc in incidents:
        ts = inc.get("created_at", "")
        hour = _parse_hour(ts)
        day = _parse_day_of_week(ts)
        if hour is not None and day in matrix:
            matrix[day][hour] += 1

    # Convert to 2D list for Streamlit/plotting
    grid = []
    for day in days_order:
        row = [matrix[day][h] for h in hours_order]
        grid.append(row)

    return {
        "days": days_order,
        "hours": [f"{h:02d}:00" for h in hours_order],
        "matrix": grid,
        "total_incidents": len(incidents),
    }


def get_hotspot_risk_level(risk_score: float) -> str:
    """Classify risk score into human-readable level."""
    if risk_score >= 12:
        return "EXTREME"
    elif risk_score >= 8:
        return "HIGH"
    elif risk_score >= 4:
        return "MEDIUM"
    else:
        return "LOW"


def _get_demo_hotspots() -> List[Dict]:
    """Return demo hotspots when no incident data exists."""
    return [
        {
            "hotspot_location": "Main Bridge Junction",
            "normalized_location": "main bridge junction",
            "risk_score": 15.4,
            "frequency": 6,
            "predicted_injury": "trauma",
            "dominant_severity": "HIGH",
            "peak_hour_range": "08:00 – 10:00",
            "incident_ids": [],
            "days_active": ["Mon", "Fri"],
        },
        {
            "hotspot_location": "Central Market Area",
            "normalized_location": "central market area",
            "risk_score": 11.2,
            "frequency": 4,
            "predicted_injury": "crush injury",
            "dominant_severity": "CRITICAL",
            "peak_hour_range": "12:00 – 14:00",
            "incident_ids": [],
            "days_active": ["Sat", "Sun"],
        },
        {
            "hotspot_location": "Industrial Zone North",
            "normalized_location": "industrial zone north",
            "risk_score": 8.7,
            "frequency": 3,
            "predicted_injury": "chemical burn",
            "dominant_severity": "HIGH",
            "peak_hour_range": "06:00 – 08:00",
            "incident_ids": [],
            "days_active": ["Mon", "Tue", "Wed"],
        },
    ]


def get_hotspot_summary() -> Dict:
    """Dashboard-ready summary of current hotspot analysis."""
    hotspots = analyze_hotspots(top_n=5)
    heatmap = build_hour_day_heatmap()

    return {
        "top_hotspots": hotspots,
        "heatmap": heatmap,
        "highest_risk_location": hotspots[0]["hotspot_location"] if hotspots else "N/A",
        "highest_risk_score": hotspots[0]["risk_score"] if hotspots else 0,
        "total_locations_analyzed": len(analyze_hotspots(top_n=100)),
    }
