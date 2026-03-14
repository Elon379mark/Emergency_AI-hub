"""
utils/system_state.py
───────────────────────
Sections 7 & 8 — Battery Saver Mode + Panic Mode

System state singleton that controls dashboard behaviour.

States:
  NORMAL_MODE     — Full functionality
  LOW_POWER_MODE  — Auto-activated when battery < 30%
                    • Disables speech recognition
                    • Reduces UI refresh rate to 60s
                    • Shows only HIGH and CRITICAL incidents
  PANIC_MODE      — Manual toggle
                    • Only CRITICAL incidents shown
                    • Full-screen red emergency UI
                    • Hides MEDIUM and LOW incidents

State is persisted to data/system_state.json so Streamlit re-runs
can read the current mode.
"""

import os
import json
import sys
from datetime import datetime
from typing import Optional

_BASE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE  = os.path.join(_BASE, "data", "system_state.json")

# ── Mode constants ──
MODE_NORMAL     = "NORMAL"
MODE_LOW_POWER  = "LOW_POWER"
MODE_PANIC      = "PANIC"

# ── Default state ──
DEFAULT_STATE = {
    "mode":                MODE_NORMAL,
    "battery_level":       100,
    "speech_enabled":      True,
    "ui_refresh_seconds":  5,
    "min_severity_shown":  "LOW",
    "panic_active":        False,
    "low_power_active":    False,
    "last_updated":        None,
}

# Battery threshold for auto low-power activation
BATTERY_LOW_THRESHOLD = 30


def _read_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return DEFAULT_STATE.copy()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return DEFAULT_STATE.copy()


def _write_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["last_updated"] = datetime.now().isoformat(timespec="seconds")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_state() -> dict:
    """Return current system state."""
    return _read_state()


def set_battery_level(level: int) -> dict:
    """
    Update battery level and auto-activate LOW_POWER_MODE if < 30%.

    Args:
        level: Battery percentage (0–100)

    Returns:
        Updated state dict
    """
    state = _read_state()
    state["battery_level"] = max(0, min(100, level))

    if level < BATTERY_LOW_THRESHOLD and not state.get("panic_active", False):
        state = _apply_low_power_mode(state)
    elif level >= BATTERY_LOW_THRESHOLD and state.get("low_power_active", False):
        state = _apply_normal_mode(state)

    _write_state(state)
    return state


def _apply_low_power_mode(state: dict) -> dict:
    """Apply LOW_POWER_MODE settings."""
    state["mode"]              = MODE_LOW_POWER
    state["speech_enabled"]    = False        # disable voice input
    state["ui_refresh_seconds"] = 60          # slow refresh
    state["min_severity_shown"] = "HIGH"      # only HIGH + CRITICAL
    state["low_power_active"]  = True
    print(f"[System State] ⚡ LOW POWER MODE activated (battery: {state['battery_level']}%)")
    return state


def _apply_normal_mode(state: dict) -> dict:
    """Restore NORMAL_MODE settings."""
    state["mode"]              = MODE_NORMAL
    state["speech_enabled"]    = True
    state["ui_refresh_seconds"] = 5
    state["min_severity_shown"] = "LOW"
    state["low_power_active"]  = False
    print("[System State] ✅ NORMAL MODE restored")
    return state


# ────────────────────────────────────────────────────────────
# Panic Mode (Section 8)
# ────────────────────────────────────────────────────────────

def activate_panic_mode() -> dict:
    """
    Activate PANIC MODE:
      • Only CRITICAL incidents displayed
      • UI switches to large red emergency interface
      • All other modes overridden

    Returns:
        Updated state dict
    """
    state = _read_state()
    state["mode"]              = MODE_PANIC
    state["panic_active"]      = True
    state["min_severity_shown"] = "CRITICAL"
    state["ui_refresh_seconds"] = 3            # faster refresh in panic
    print("[System State] 🔴 PANIC MODE ACTIVATED")
    _write_state(state)
    return state


def deactivate_panic_mode() -> dict:
    """Deactivate PANIC MODE and restore previous mode."""
    state = _read_state()
    state["panic_active"] = False
    # Restore based on battery level
    if state.get("battery_level", 100) < BATTERY_LOW_THRESHOLD:
        state = _apply_low_power_mode(state)
    else:
        state = _apply_normal_mode(state)
    print("[System State] Panic mode deactivated")
    _write_state(state)
    return state


def should_show_incident(severity: str, state: Optional[dict] = None) -> bool:
    """
    Determine if an incident with given severity should be shown
    in the current system state.

    Args:
        severity: Incident severity level
        state:    Current state dict (reads from file if None)

    Returns:
        True if incident should be displayed
    """
    if state is None:
        state = _read_state()

    min_sev = state.get("min_severity_shown", "LOW")
    PRIORITY = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    return PRIORITY.get(severity, 0) >= PRIORITY.get(min_sev, 0)


def is_speech_enabled() -> bool:
    return _read_state().get("speech_enabled", True)


def get_ui_refresh_rate() -> int:
    return _read_state().get("ui_refresh_seconds", 5)


def is_panic_mode() -> bool:
    return _read_state().get("panic_active", False)


def is_low_power_mode() -> bool:
    return _read_state().get("low_power_active", False)
