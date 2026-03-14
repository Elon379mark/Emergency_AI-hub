"""
utils/simulation_mode.py
─────────────────────────
Training Simulation Mode — Disaster Command Center v4 ELITE

Injects simulated disaster scenarios for responder training.
Tracks response time, teams deployed, and simulation score.

Includes 10 predefined scenarios covering major disaster types.
Loads additional scenarios from data/simulation_scenarios.json.
"""

import os
import sys
import json
import time
import uuid
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS_FILE = os.path.join(BASE_DIR, "data", "simulation_scenarios.json")
SIM_LOG_FILE = os.path.join(BASE_DIR, "data", "simulation_log.json")

# ── Builtin Scenarios ──
BUILTIN_SCENARIOS = [
    {
        "id": "SIM-001",
        "name": "Bus Accident — Mass Casualty",
        "description": "City bus overturns on highway, 15 casualties reported.",
        "transcription": "Bus overturned on highway 5 near Junction 12. Approximately 15 injured, 3 unconscious and not breathing. Heavy bleeding visible on multiple victims. Request immediate ALS and trauma teams.",
        "expected_severity": "CRITICAL",
        "expected_teams": 4,
        "disaster_type": "Trauma",
        "difficulty": "HARD",
        "time_limit_seconds": 120,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-002",
        "name": "Building Collapse — Earthquake",
        "description": "3-story building collapses after 6.2 magnitude earthquake.",
        "transcription": "Building collapse at Main Street 44 following earthquake. Unknown number of people trapped. Dust and debris everywhere. Multiple people screaming inside. Request search and rescue immediately.",
        "expected_severity": "CRITICAL",
        "expected_teams": 5,
        "disaster_type": "Earthquake",
        "difficulty": "HARD",
        "time_limit_seconds": 90,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-003",
        "name": "Chemical Spill — Industrial Zone",
        "description": "Chlorine gas leak at chemical plant, 8 workers exposed.",
        "transcription": "Chemical spill at factory north zone. Workers reporting burning eyes and difficulty breathing. Strong smell. 8 people affected, 2 collapsed. Possible chlorine leak. Need hazmat and medical teams urgently.",
        "expected_severity": "CRITICAL",
        "expected_teams": 3,
        "disaster_type": "Chemical",
        "difficulty": "HARD",
        "time_limit_seconds": 100,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-004",
        "name": "Flood Rescue — Residential",
        "description": "Flash flood traps 20 residents in single-story homes.",
        "transcription": "Flash flooding on Oak Street and Elm Avenue. Water rising fast, residents on rooftops. Elderly residents unable to swim. At least 20 people trapped. Need boat rescue teams and emergency shelter.",
        "expected_severity": "HIGH",
        "expected_teams": 3,
        "disaster_type": "Flood",
        "difficulty": "MEDIUM",
        "time_limit_seconds": 150,
        "scoring": {
            "correct_severity": 25,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 20,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-005",
        "name": "Cardiac Arrest — Public Space",
        "description": "Man collapses in shopping mall, bystanders performing CPR.",
        "transcription": "Adult male approximately 55 years collapsed in Central Mall food court. Not breathing. Bystander performing CPR. AED available on-site. No obvious trauma. Request ALS immediately.",
        "expected_severity": "CRITICAL",
        "expected_teams": 1,
        "disaster_type": "Medical",
        "difficulty": "EASY",
        "time_limit_seconds": 180,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-006",
        "name": "School Fire — Multiple Children",
        "description": "Fire breaks out in primary school, 30 children evacuating.",
        "transcription": "Fire at Sunshine Primary School, Block B. Teachers evacuating 30 children. Smoke visible from third floor. Two children unaccounted for. One teacher has burns on arms. Request fire and medical response.",
        "expected_severity": "HIGH",
        "expected_teams": 3,
        "disaster_type": "Fire",
        "difficulty": "MEDIUM",
        "time_limit_seconds": 120,
        "scoring": {
            "correct_severity": 25,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 20,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-007",
        "name": "Drowning — Beach",
        "description": "Multiple swimmers in distress during riptide event.",
        "transcription": "Multiple swimmers in difficulty at South Beach. Strong riptide. Three people spotted floating motionless. Lifeguard in water attempting rescue. One person unconscious on shore. Need water rescue and resuscitation team.",
        "expected_severity": "CRITICAL",
        "expected_teams": 2,
        "disaster_type": "Drowning",
        "difficulty": "MEDIUM",
        "time_limit_seconds": 120,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-008",
        "name": "Minor Traffic Accident",
        "description": "Two-car collision, no critical injuries.",
        "transcription": "Two vehicle collision at Green Road intersection. Both drivers conscious and alert. One passenger complaining of neck pain. Minor cuts and bruises. No entrapment. Vehicles blocking traffic.",
        "expected_severity": "MEDIUM",
        "expected_teams": 1,
        "disaster_type": "Trauma",
        "difficulty": "EASY",
        "time_limit_seconds": 240,
        "scoring": {
            "correct_severity": 25,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 20,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-009",
        "name": "Structural Fire — High-Rise",
        "description": "Fire on 8th floor of apartment building, residents trapped.",
        "transcription": "Fire reported on 8th floor of Tower Block A. Residents on floors 8 to 12 unable to exit due to smoke. Fire alarms active. Estimated 40 people in affected area. Elderly resident with mobility issues on floor 10. Request fire crews and medical standby.",
        "expected_severity": "CRITICAL",
        "expected_teams": 5,
        "disaster_type": "Fire",
        "difficulty": "HARD",
        "time_limit_seconds": 90,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
    {
        "id": "SIM-010",
        "name": "Landslide — Rural Community",
        "description": "Landslide buries three houses, 12 residents missing.",
        "transcription": "Landslide on northern hill road has buried three houses. 12 residents missing, 5 confirmed with injuries. Mud and debris blocking access road. Need excavation equipment, search and rescue dogs, and medical teams. Heavy rain continuing.",
        "expected_severity": "CRITICAL",
        "expected_teams": 4,
        "disaster_type": "Natural",
        "difficulty": "HARD",
        "time_limit_seconds": 100,
        "scoring": {
            "correct_severity": 30,
            "correct_team_count": 20,
            "speed_bonus_under_60s": 25,
            "speed_bonus_under_90s": 10,
        },
    },
]


def _load_scenarios() -> List[Dict]:
    """Load scenarios — builtin + file-based."""
    scenarios = list(BUILTIN_SCENARIOS)
    try:
        if os.path.exists(SCENARIOS_FILE):
            with open(SCENARIOS_FILE, "r") as f:
                extra = json.load(f)
            if isinstance(extra, list):
                scenarios.extend(extra)
    except Exception:
        pass
    return scenarios


def _load_sim_log() -> List[Dict]:
    """Load simulation session log."""
    try:
        if os.path.exists(SIM_LOG_FILE):
            with open(SIM_LOG_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_sim_log(log: List[Dict]) -> None:
    """Save simulation session log."""
    try:
        os.makedirs(os.path.dirname(SIM_LOG_FILE), exist_ok=True)
        with open(SIM_LOG_FILE, "w") as f:
            json.dump(log[-100:], f, indent=2)  # Keep last 100 sessions
    except Exception:
        pass


def get_all_scenarios() -> List[Dict]:
    """Return all available simulation scenarios."""
    return _load_scenarios()


def get_scenario(scenario_id: str) -> Optional[Dict]:
    """Retrieve a specific scenario by ID."""
    for s in _load_scenarios():
        if s.get("id") == scenario_id:
            return s
    return None


def start_simulation(scenario_id: str) -> Dict:
    """
    Start a simulation session for a given scenario.

    Args:
        scenario_id: Scenario ID (e.g., "SIM-001")

    Returns:
        Session dict with session_id, scenario, start_time
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        return {"success": False, "error": f"Scenario {scenario_id} not found"}

    session = {
        "session_id": str(uuid.uuid4())[:8].upper(),
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "start_time": time.time(),
        "start_time_str": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "ACTIVE",
        "teams_deployed": [],
        "response_time_seconds": None,
        "score": None,
        "completed": False,
    }

    return {"success": True, "session": session, "scenario": scenario}


def score_simulation(session: Dict, actual_severity: str,
                     actual_teams_deployed: int,
                     response_time_seconds: float) -> Dict:
    """
    Score a completed simulation session.

    Args:
        session: The session dict from start_simulation()
        actual_severity: The severity assigned by the responder
        actual_teams_deployed: Number of teams actually dispatched
        response_time_seconds: Total response time

    Returns:
        Scoring result with total score, breakdown, and grade
    """
    scenario_id = session.get("scenario_id")
    scenario = get_scenario(scenario_id)
    if not scenario:
        return {"error": "Scenario not found"}

    scoring_cfg = scenario.get("scoring", {})
    expected_sev = scenario.get("expected_severity", "HIGH")
    expected_teams = scenario.get("expected_teams", 2)
    time_limit = scenario.get("time_limit_seconds", 180)

    score = 0
    breakdown = []

    # ── Severity accuracy ──
    sev_points = scoring_cfg.get("correct_severity", 30)
    if actual_severity == expected_sev:
        score += sev_points
        breakdown.append({"item": "Correct severity", "points": sev_points})
    elif _severity_adjacent(actual_severity, expected_sev):
        partial = sev_points // 2
        score += partial
        breakdown.append({"item": f"Adjacent severity ({actual_severity} vs {expected_sev})", "points": partial})
    else:
        breakdown.append({"item": f"Wrong severity ({actual_severity} vs expected {expected_sev})", "points": 0})

    # ── Team deployment accuracy ──
    team_points = scoring_cfg.get("correct_team_count", 20)
    team_diff = abs(actual_teams_deployed - expected_teams)
    if team_diff == 0:
        score += team_points
        breakdown.append({"item": "Correct team count", "points": team_points})
    elif team_diff == 1:
        partial = team_points // 2
        score += partial
        breakdown.append({"item": f"Team count off by 1 ({actual_teams_deployed} vs {expected_teams})", "points": partial})
    else:
        breakdown.append({"item": f"Team count off by {team_diff}", "points": 0})

    # ── Speed bonus ──
    if response_time_seconds <= 60:
        bonus = scoring_cfg.get("speed_bonus_under_60s", 25)
        score += bonus
        breakdown.append({"item": "Speed bonus (<60s)", "points": bonus})
    elif response_time_seconds <= 90:
        bonus = scoring_cfg.get("speed_bonus_under_90s", 10)
        score += bonus
        breakdown.append({"item": "Speed bonus (<90s)", "points": bonus})
    elif response_time_seconds > time_limit:
        penalty = 15
        score = max(0, score - penalty)
        breakdown.append({"item": f"Time limit exceeded ({response_time_seconds:.0f}s > {time_limit}s)", "points": -penalty})

    # ── Grade ──
    max_possible = sev_points + team_points + scoring_cfg.get("speed_bonus_under_60s", 25)
    pct = (score / max_possible * 100) if max_possible > 0 else 0
    grade = "A+" if pct >= 95 else "A" if pct >= 85 else "B" if pct >= 70 else "C" if pct >= 55 else "D"

    result = {
        "session_id": session.get("session_id"),
        "scenario_id": scenario_id,
        "scenario_name": scenario.get("name"),
        "score": score,
        "max_score": max_possible,
        "percentage": round(pct, 1),
        "grade": grade,
        "response_time_seconds": round(response_time_seconds, 1),
        "breakdown": breakdown,
        "actual_severity": actual_severity,
        "expected_severity": expected_sev,
        "actual_teams": actual_teams_deployed,
        "expected_teams": expected_teams,
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # Persist to log
    log = _load_sim_log()
    log.append(result)
    _save_sim_log(log)

    return result


def _severity_adjacent(a: str, b: str) -> bool:
    """Check if two severities are adjacent in the scale."""
    order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    try:
        return abs(order.index(a) - order.index(b)) == 1
    except ValueError:
        return False


def get_simulation_leaderboard(top_n: int = 10) -> List[Dict]:
    """Return top N simulation scores."""
    log = _load_sim_log()
    sorted_log = sorted(log, key=lambda s: s.get("percentage", 0), reverse=True)
    return sorted_log[:top_n]


def get_simulation_stats() -> Dict:
    """Return aggregate simulation statistics."""
    log = _load_sim_log()
    if not log:
        return {"total_sessions": 0, "avg_score": 0, "top_score": 0}

    scores = [s.get("percentage", 0) for s in log]
    return {
        "total_sessions": len(log),
        "avg_score": round(sum(scores) / len(scores), 1),
        "top_score": round(max(scores), 1),
        "scenarios_attempted": len(set(s.get("scenario_id") for s in log)),
    }
