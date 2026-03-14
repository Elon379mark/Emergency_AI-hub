"""
utils/access_control.py
────────────────────────
Role-Based Access Control — Disaster Command Center v4 ELITE

PIN-based login system with four roles and permission levels.
PINs are stored as SHA-256 hashes in data/access_config.json.

Roles:
    INCIDENT_COMMANDER  — Full access, all controls
    FIRST_RESPONDER     — Incident + triage operations
    VOLUNTEER           — Read-only, basic updates
    TRAINER             — Simulation mode access + read

Default PINs (CHANGE IN PRODUCTION):
    INCIDENT_COMMANDER  → 1234
    FIRST_RESPONDER     → 2345
    VOLUNTEER           → 3456
    TRAINER             → 4567
"""

import os
import sys
import json
import time
import hashlib
import secrets
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCESS_CONFIG_FILE = os.path.join(BASE_DIR, "data", "access_config.json")
SESSION_FILE = os.path.join(BASE_DIR, "data", ".session.json")

# ── Role definitions ──
ROLES = {
    "INCIDENT_COMMANDER": {
        "display_name": "Incident Commander",
        "badge_color": "#CC0000",
        "badge_emoji": "🎖️",
        "permissions": [
            "view_incidents", "create_incident", "resolve_incident",
            "assign_teams", "dispatch_equipment", "manage_responders",
            "view_vitals", "log_vitals", "generate_reports",
            "activate_panic", "change_profile", "change_mode",
            "view_hotspots", "generate_qr", "sync_lan",
            "manage_access", "run_simulation", "view_drug_db",
            "photo_triage", "llm_triage",
        ],
        "level": 4,
    },
    "FIRST_RESPONDER": {
        "display_name": "First Responder",
        "badge_color": "#FF4400",
        "badge_emoji": "🚑",
        "permissions": [
            "view_incidents", "create_incident",
            "view_vitals", "log_vitals",
            "view_hotspots", "generate_qr",
            "view_drug_db", "photo_triage", "llm_triage",
            "assign_teams", "dispatch_equipment",
        ],
        "level": 3,
    },
    "VOLUNTEER": {
        "display_name": "Volunteer",
        "badge_color": "#0066CC",
        "badge_emoji": "🤝",
        "permissions": [
            "view_incidents",
            "view_vitals",
            "view_hotspots",
            "view_drug_db",
        ],
        "level": 2,
    },
    "TRAINER": {
        "display_name": "Trainer",
        "badge_color": "#006600",
        "badge_emoji": "📚",
        "permissions": [
            "view_incidents", "run_simulation",
            "view_hotspots", "view_drug_db",
            "generate_reports",
        ],
        "level": 1,
    },
}

# Default PIN hashes (PIN → SHA-256)
DEFAULT_PINS = {
    "INCIDENT_COMMANDER": "1234",
    "FIRST_RESPONDER": "2345",
    "VOLUNTEER": "3456",
    "TRAINER": "4567",
}


def _hash_pin(pin: str) -> str:
    """SHA-256 hash a PIN with a fixed salt for consistency."""
    salted = f"DisasterCommandCenter_v4_{pin.strip()}"
    return hashlib.sha256(salted.encode()).hexdigest()


def _load_config() -> Dict:
    """Load access config from disk, creating defaults if missing."""
    if os.path.exists(ACCESS_CONFIG_FILE):
        try:
            with open(ACCESS_CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass

    # Create default config
    config = {
        "version": "4.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "roles": {},
    }
    for role, default_pin in DEFAULT_PINS.items():
        config["roles"][role] = {
            "pin_hash": _hash_pin(default_pin),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_login": None,
            "login_count": 0,
            "active": True,
        }

    _save_config(config)
    return config


def _save_config(config: Dict) -> None:
    """Save access config to disk."""
    try:
        os.makedirs(os.path.dirname(ACCESS_CONFIG_FILE), exist_ok=True)
        with open(ACCESS_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[AccessControl] Config save error: {e}")


def _load_session() -> Optional[Dict]:
    """Load current session from disk."""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                session = json.load(f)
            # Validate session is not expired (8 hour timeout)
            login_time = session.get("login_time", 0)
            if time.time() - login_time < 8 * 3600:
                return session
    except Exception:
        pass
    return None


def _save_session(session: Optional[Dict]) -> None:
    """Save or clear session."""
    try:
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        if session is None:
            if os.path.exists(SESSION_FILE):
                os.unlink(SESSION_FILE)
        else:
            with open(SESSION_FILE, "w") as f:
                json.dump(session, f, indent=2)
    except Exception:
        pass


def login(pin: str) -> Dict:
    """
    Authenticate a user by PIN.

    Args:
        pin: The PIN entered by the user

    Returns:
        Login result with role, permissions, session token
    """
    config = _load_config()
    pin_hash = _hash_pin(pin.strip())

    for role, role_config in config["roles"].items():
        if (role_config.get("active", True) and
                role_config.get("pin_hash") == pin_hash):

            # Update login stats
            config["roles"][role]["last_login"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            config["roles"][role]["login_count"] = role_config.get("login_count", 0) + 1
            _save_config(config)

            # Create session
            session_token = secrets.token_hex(16)
            session = {
                "role": role,
                "session_token": session_token,
                "login_time": time.time(),
                "login_time_str": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _save_session(session)

            role_info = ROLES.get(role, {})
            return {
                "success": True,
                "role": role,
                "display_name": role_info.get("display_name", role),
                "badge_color": role_info.get("badge_color", "#888"),
                "badge_emoji": role_info.get("badge_emoji", "👤"),
                "permissions": role_info.get("permissions", []),
                "level": role_info.get("level", 1),
                "session_token": session_token,
            }

    return {
        "success": False,
        "error": "Invalid PIN",
        "hint": "Contact your Incident Commander to reset PIN",
    }


def logout() -> None:
    """Clear current session."""
    _save_session(None)


def get_current_session() -> Optional[Dict]:
    """
    Get the current active session.

    Returns:
        Session dict with role and permissions, or None if not logged in
    """
    session = _load_session()
    if not session:
        return None

    role = session.get("role")
    role_info = ROLES.get(role, {})

    return {
        "role": role,
        "display_name": role_info.get("display_name", role),
        "badge_color": role_info.get("badge_color", "#888"),
        "badge_emoji": role_info.get("badge_emoji", "👤"),
        "permissions": role_info.get("permissions", []),
        "level": role_info.get("level", 1),
        "login_time_str": session.get("login_time_str"),
        "session_token": session.get("session_token"),
    }


def has_permission(permission: str, session: Optional[Dict] = None) -> bool:
    """
    Check if current session has a specific permission.

    Args:
        permission: Permission string to check
        session: Session dict (if None, loads from disk)

    Returns:
        True if permitted
    """
    if session is None:
        session = get_current_session()
    if session is None:
        return False
    return permission in session.get("permissions", [])


def require_permission(permission: str) -> bool:
    """
    Check permission and return False if not authorized.
    Use in dashboard: if not require_permission("create_incident"): st.stop()
    """
    return has_permission(permission)


def change_pin(role: str, old_pin: str, new_pin: str) -> Dict:
    """
    Change PIN for a role.

    Args:
        role: Role name
        old_pin: Current PIN (for verification)
        new_pin: New PIN (min 4 chars)

    Returns:
        Result dict
    """
    if len(new_pin.strip()) < 4:
        return {"success": False, "error": "PIN must be at least 4 digits"}

    config = _load_config()
    if role not in config["roles"]:
        return {"success": False, "error": f"Role {role} not found"}

    old_hash = _hash_pin(old_pin.strip())
    if config["roles"][role].get("pin_hash") != old_hash:
        return {"success": False, "error": "Current PIN is incorrect"}

    config["roles"][role]["pin_hash"] = _hash_pin(new_pin.strip())
    config["roles"][role]["pin_changed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save_config(config)

    return {"success": True, "role": role, "message": "PIN changed successfully"}


def get_role_badge_html(session: Optional[Dict] = None) -> str:
    """
    Generate HTML role badge for dashboard display.

    Args:
        session: Session dict (if None, loads from disk)

    Returns:
        HTML string for Streamlit unsafe_allow_html
    """
    if session is None:
        session = get_current_session()

    if not session:
        return (
            '<span style="background:#888;color:white;padding:3px 10px;'
            'border-radius:12px;font-size:0.85em">👤 Not Logged In</span>'
        )

    emoji = session.get("badge_emoji", "👤")
    name = session.get("display_name", "Unknown")
    color = session.get("badge_color", "#888")
    role = session.get("role", "?")
    level = session.get("level", 1)

    return (
        f'<span style="background:{color};color:white;padding:4px 12px;'
        f'border-radius:12px;font-size:0.9em;font-weight:bold">'
        f'{emoji} {name} (L{level}) — {role}'
        f'</span>'
    )


def list_roles() -> List[Dict]:
    """Return list of all roles with display info (no PINs)."""
    config = _load_config()
    roles_out = []
    for role, info in ROLES.items():
        role_config = config.get("roles", {}).get(role, {})
        roles_out.append({
            "role": role,
            "display_name": info["display_name"],
            "badge_emoji": info["badge_emoji"],
            "badge_color": info["badge_color"],
            "level": info["level"],
            "permission_count": len(info["permissions"]),
            "last_login": role_config.get("last_login"),
            "login_count": role_config.get("login_count", 0),
            "active": role_config.get("active", True),
        })
    return sorted(roles_out, key=lambda r: r["level"], reverse=True)


def initialize_access_config() -> None:
    """Ensure access config exists with defaults. Call at startup."""
    _load_config()  # Creates defaults if missing
