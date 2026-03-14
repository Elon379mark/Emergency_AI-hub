"""
command/vitals_tracker.py
──────────────────────────
Patient Vitals Tracker — Disaster Command Center v4 ELITE

Logs and monitors patient vitals with deterioration detection.
Persists data to data/vitals_log.json.

Alert thresholds:
    • Pulse > 120 or < 50 bpm → Tachycardia / Bradycardia
    • SpO2 < 90% → Hypoxia
    • Systolic BP < 90 mmHg → Hypotension / Shock
"""

import os
import sys
import json
import time
import uuid
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── File paths ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VITALS_FILE = os.path.join(BASE_DIR, "data", "vitals_log.json")

# ── Alert thresholds ──
ALERT_THRESHOLDS = {
    "pulse_bpm": {"min": 50, "max": 120, "critical_min": 30, "critical_max": 150},
    "spo2_percent": {"min": 90, "critical_min": 80},
    "systolic_bp": {"min": 90, "critical_min": 70},
    "diastolic_bp": {"min": 50, "max": 110},
    "respiratory_rate": {"min": 8, "max": 30, "critical_min": 6, "critical_max": 40},
}

# Consciousness scale (AVPU)
CONSCIOUSNESS_LEVELS = {
    "Alert": 4,
    "Voice": 3,
    "Pain": 2,
    "Unresponsive": 1,
}


def _load_vitals() -> Dict:
    """Load vitals log from disk."""
    try:
        if os.path.exists(VITALS_FILE):
            with open(VITALS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"patients": {}}


def _save_vitals(data: Dict) -> None:
    """Persist vitals to disk."""
    try:
        os.makedirs(os.path.dirname(VITALS_FILE), exist_ok=True)
        with open(VITALS_FILE, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        print(f"[Vitals] Save error: {e}")


def _check_alerts(vitals: Dict) -> List[Dict]:
    """
    Evaluate vitals against alert thresholds.

    Args:
        vitals: Dict of vital signs

    Returns:
        List of alert dicts with severity and message
    """
    alerts = []

    pulse = vitals.get("pulse_bpm")
    if pulse is not None:
        if pulse > ALERT_THRESHOLDS["pulse_bpm"]["critical_max"]:
            alerts.append({
                "vital": "pulse_bpm",
                "value": pulse,
                "severity": "CRITICAL",
                "message": f"SEVERE TACHYCARDIA: {pulse} bpm (>150)"
            })
        elif pulse > ALERT_THRESHOLDS["pulse_bpm"]["max"]:
            alerts.append({
                "vital": "pulse_bpm",
                "value": pulse,
                "severity": "HIGH",
                "message": f"Tachycardia: {pulse} bpm (>120)"
            })
        elif pulse < ALERT_THRESHOLDS["pulse_bpm"]["critical_min"]:
            alerts.append({
                "vital": "pulse_bpm",
                "value": pulse,
                "severity": "CRITICAL",
                "message": f"SEVERE BRADYCARDIA: {pulse} bpm (<30)"
            })
        elif pulse < ALERT_THRESHOLDS["pulse_bpm"]["min"]:
            alerts.append({
                "vital": "pulse_bpm",
                "value": pulse,
                "severity": "HIGH",
                "message": f"Bradycardia: {pulse} bpm (<50)"
            })

    spo2 = vitals.get("spo2_percent")
    if spo2 is not None:
        if spo2 < ALERT_THRESHOLDS["spo2_percent"]["critical_min"]:
            alerts.append({
                "vital": "spo2_percent",
                "value": spo2,
                "severity": "CRITICAL",
                "message": f"CRITICAL HYPOXIA: SpO2 {spo2}% (<80%) — Airway emergency"
            })
        elif spo2 < ALERT_THRESHOLDS["spo2_percent"]["min"]:
            alerts.append({
                "vital": "spo2_percent",
                "value": spo2,
                "severity": "HIGH",
                "message": f"Hypoxia: SpO2 {spo2}% (<90%) — Oxygen required"
            })

    systolic = vitals.get("systolic_bp")
    if systolic is not None:
        if systolic < ALERT_THRESHOLDS["systolic_bp"]["critical_min"]:
            alerts.append({
                "vital": "systolic_bp",
                "value": systolic,
                "severity": "CRITICAL",
                "message": f"DECOMPENSATED SHOCK: BP {systolic} mmHg (<70) — IV access NOW"
            })
        elif systolic < ALERT_THRESHOLDS["systolic_bp"]["min"]:
            alerts.append({
                "vital": "systolic_bp",
                "value": systolic,
                "severity": "HIGH",
                "message": f"Hypotension: BP {systolic} mmHg (<90) — Possible shock"
            })

    rr = vitals.get("respiratory_rate")
    if rr is not None:
        if rr < ALERT_THRESHOLDS["respiratory_rate"]["critical_min"]:
            alerts.append({
                "vital": "respiratory_rate",
                "value": rr,
                "severity": "CRITICAL",
                "message": f"CRITICAL RESPIRATORY DEPRESSION: RR {rr}/min — BVM ready"
            })
        elif rr > ALERT_THRESHOLDS["respiratory_rate"]["critical_max"]:
            alerts.append({
                "vital": "respiratory_rate",
                "value": rr,
                "severity": "CRITICAL",
                "message": f"SEVERE RESPIRATORY DISTRESS: RR {rr}/min"
            })
        elif rr < ALERT_THRESHOLDS["respiratory_rate"]["min"] or rr > ALERT_THRESHOLDS["respiratory_rate"]["max"]:
            alerts.append({
                "vital": "respiratory_rate",
                "value": rr,
                "severity": "HIGH",
                "message": f"Abnormal RR: {rr}/min (normal 8-30)"
            })

    consciousness = vitals.get("consciousness")
    if consciousness in ("Pain", "Unresponsive"):
        alerts.append({
            "vital": "consciousness",
            "value": consciousness,
            "severity": "CRITICAL",
            "message": f"ALTERED CONSCIOUSNESS: {consciousness} — Neurological assessment required"
        })

    return sorted(alerts, key=lambda a: {"CRITICAL": 2, "HIGH": 1}.get(a["severity"], 0), reverse=True)


def _detect_deterioration(patient_history: List[Dict]) -> Dict:
    """
    Detect if patient is deteriorating across multiple readings.

    Args:
        patient_history: List of vitals dicts, oldest first

    Returns:
        Dict with deterioration status and trend info
    """
    if len(patient_history) < 2:
        return {"deteriorating": False, "trend": "insufficient_data"}

    latest = patient_history[-1]
    previous = patient_history[-2]

    trends = []

    # Pulse trend
    if latest.get("pulse_bpm") and previous.get("pulse_bpm"):
        delta = latest["pulse_bpm"] - previous["pulse_bpm"]
        if delta > 20:
            trends.append(f"Pulse rising +{delta} bpm")
        elif delta < -20:
            trends.append(f"Pulse falling {delta} bpm")

    # SpO2 trend
    if latest.get("spo2_percent") and previous.get("spo2_percent"):
        delta = latest["spo2_percent"] - previous["spo2_percent"]
        if delta < -3:
            trends.append(f"SpO2 dropping {delta}%")

    # BP trend
    if latest.get("systolic_bp") and previous.get("systolic_bp"):
        delta = latest["systolic_bp"] - previous["systolic_bp"]
        if delta < -15:
            trends.append(f"BP falling {delta} mmHg")

    # Consciousness decline
    latest_cons = CONSCIOUSNESS_LEVELS.get(latest.get("consciousness", "Alert"), 4)
    prev_cons = CONSCIOUSNESS_LEVELS.get(previous.get("consciousness", "Alert"), 4)
    if latest_cons < prev_cons:
        trends.append("Consciousness level declining")

    deteriorating = len(trends) >= 1
    return {
        "deteriorating": deteriorating,
        "trend": "DETERIORATING" if deteriorating else "STABLE",
        "trend_details": trends,
        "readings_compared": len(patient_history),
    }


def log_vitals(incident_id: str, victim_name: str, vitals: Dict) -> Dict:
    """
    Log a new vitals reading for a patient.

    Args:
        incident_id: Associated incident ID
        victim_name: Patient identifier
        vitals: Dict with vital sign values

    Returns:
        Logging result with alerts and deterioration status
    """
    data = _load_vitals()

    patient_key = f"{incident_id}_{victim_name}".replace(" ", "_")

    if patient_key not in data["patients"]:
        data["patients"][patient_key] = {
            "incident_id": incident_id,
            "victim_name": victim_name,
            "readings": [],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    reading = {
        "reading_id": str(uuid.uuid4())[:8],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pulse_bpm": vitals.get("pulse_bpm"),
        "systolic_bp": vitals.get("systolic_bp"),
        "diastolic_bp": vitals.get("diastolic_bp"),
        "spo2_percent": vitals.get("spo2_percent"),
        "respiratory_rate": vitals.get("respiratory_rate"),
        "consciousness": vitals.get("consciousness", "Alert"),
        "notes": vitals.get("notes", ""),
    }

    alerts = _check_alerts(reading)
    reading["alerts"] = alerts
    reading["alert_count"] = len(alerts)
    reading["has_critical"] = any(a["severity"] == "CRITICAL" for a in alerts)

    data["patients"][patient_key]["readings"].append(reading)

    # Deterioration detection
    deterioration = _detect_deterioration(data["patients"][patient_key]["readings"])
    data["patients"][patient_key]["deterioration_status"] = deterioration
    data["patients"][patient_key]["last_updated"] = reading["timestamp"]

    _save_vitals(data)

    return {
        "patient_key": patient_key,
        "reading_id": reading["reading_id"],
        "timestamp": reading["timestamp"],
        "alerts": alerts,
        "alert_count": len(alerts),
        "has_critical": reading["has_critical"],
        "deterioration": deterioration,
    }


def get_patient_vitals(incident_id: str, victim_name: str) -> Optional[Dict]:
    """Retrieve vitals history for a specific patient."""
    data = _load_vitals()
    patient_key = f"{incident_id}_{victim_name}".replace(" ", "_")
    return data["patients"].get(patient_key)


def get_all_critical_patients() -> List[Dict]:
    """Return list of patients with active critical alerts."""
    data = _load_vitals()
    critical = []
    for key, patient in data["patients"].items():
        readings = patient.get("readings", [])
        if readings:
            latest = readings[-1]
            if latest.get("has_critical") or patient.get("deterioration_status", {}).get("deteriorating"):
                critical.append({
                    "patient_key": key,
                    "victim_name": patient["victim_name"],
                    "incident_id": patient["incident_id"],
                    "latest_reading": latest,
                    "deterioration": patient.get("deterioration_status", {}),
                })
    return critical


def get_vitals_summary() -> Dict:
    """Return high-level summary for dashboard display."""
    data = _load_vitals()
    patients = data.get("patients", {})
    total = len(patients)
    critical_count = len(get_all_critical_patients())
    total_readings = sum(len(p.get("readings", [])) for p in patients.values())

    return {
        "total_patients_monitored": total,
        "critical_patients": critical_count,
        "total_readings_logged": total_readings,
        "patients": list(patients.keys()),
    }
