"""
utils/audio_alerts.py
──────────────────────
Audio Critical Alerts — Disaster Command Center v4 ELITE

Plays synthesized sound alerts for critical system events.
Primary: pygame.mixer | Fallback: numpy waveform generation

Alert types:
    CRITICAL_INCIDENT   — 3 rapid high-pitched beeps
    HIGH_INCIDENT       — 2 medium beeps
    LOW_STOCK_WARNING   — 1 low beep
    TEAM_ALL_DEPLOYED   — ascending tone pattern
    PANIC_ACTIVATED     — continuous urgent alarm pattern
"""

import os
import sys
import math
import time
import threading
from typing import Optional, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Alert type registry ──
ALERT_TYPES = {
    "CRITICAL_INCIDENT": {
        "description": "Critical incident detected",
        "pattern": "triple_high",
        "frequency_hz": 1200,
        "duration_ms": 200,
        "repeats": 3,
        "gap_ms": 100,
    },
    "HIGH_INCIDENT": {
        "description": "High priority incident",
        "pattern": "double_med",
        "frequency_hz": 880,
        "duration_ms": 300,
        "repeats": 2,
        "gap_ms": 150,
    },
    "LOW_STOCK_WARNING": {
        "description": "Equipment stock low",
        "pattern": "single_low",
        "frequency_hz": 440,
        "duration_ms": 500,
        "repeats": 1,
        "gap_ms": 0,
    },
    "TEAM_ALL_DEPLOYED": {
        "description": "All responder teams deployed",
        "pattern": "ascending",
        "frequency_hz": 660,
        "duration_ms": 250,
        "repeats": 4,
        "gap_ms": 80,
    },
    "PANIC_ACTIVATED": {
        "description": "PANIC MODE activated",
        "pattern": "panic",
        "frequency_hz": 1400,
        "duration_ms": 150,
        "repeats": 6,
        "gap_ms": 80,
    },
}

# Track muted state
_muted = False
_initialized = False


def _generate_sine_wave(frequency: float, duration_ms: int,
                         sample_rate: int = 44100,
                         amplitude: float = 0.5) -> "np.ndarray":
    """
    Generate a sine wave as numpy array.

    Args:
        frequency: Tone frequency in Hz
        duration_ms: Duration in milliseconds
        sample_rate: Audio sample rate
        amplitude: Volume 0.0-1.0

    Returns:
        numpy float32 array
    """
    import numpy as np
    n_samples = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, n_samples, endpoint=False)

    # Apply slight fade in/out to avoid clicks
    wave = amplitude * np.sin(2 * np.pi * frequency * t)
    fade_samples = min(int(sample_rate * 0.01), n_samples // 4)
    if fade_samples > 0:
        fade = np.linspace(0, 1, fade_samples)
        wave[:fade_samples] *= fade
        wave[-fade_samples:] *= fade[::-1]

    return wave.astype(np.float32)


def _init_pygame():
    """Initialize pygame mixer. Returns True on success."""
    global _initialized
    if _initialized:
        return True
    try:
        import pygame
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=1, buffer=256)
        pygame.mixer.init()
        _initialized = True
        return True
    except Exception:
        return False


def _play_pygame(frequency: float, duration_ms: int):
    """Play tone using pygame."""
    import pygame
    import numpy as np

    wave = _generate_sine_wave(frequency, duration_ms)
    wave_int16 = (wave * 32767).astype(np.int16)
    sound = pygame.sndarray.make_sound(wave_int16)
    sound.play()
    pygame.time.wait(duration_ms)


def _play_numpy_fallback(frequency: float, duration_ms: int):
    """
    Numpy-only fallback: write WAV to temp file and attempt OS playback.
    Silent failure if no audio hardware available.
    """
    try:
        import numpy as np
        import wave
        import struct
        import tempfile
        import subprocess

        wave_data = _generate_sine_wave(frequency, duration_ms)
        wave_int16 = (wave_data * 32767).astype(np.int16)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        with wave.open(tmp_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(44100)
            wf.writeframes(wave_int16.tobytes())

        # Try aplay (Linux) or afplay (macOS) or powershell (Windows)
        for cmd in [
            ["aplay", "-q", tmp_path],
            ["afplay", tmp_path],
            ["powershell", "-c", f"(New-Object Media.SoundPlayer '{tmp_path}').PlaySync()"],
        ]:
            try:
                subprocess.run(cmd, timeout=duration_ms/1000 + 1,
                               capture_output=True, check=True)
                break
            except Exception:
                continue

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    except Exception:
        pass  # Silent failure — audio not available


def _play_tone(frequency: float, duration_ms: int):
    """Play a single tone using pygame or numpy fallback."""
    if _muted:
        return

    try:
        if _init_pygame():
            _play_pygame(frequency, duration_ms)
        else:
            _play_numpy_fallback(frequency, duration_ms)
    except Exception:
        _play_numpy_fallback(frequency, duration_ms)


def play_alert(alert_type: str, blocking: bool = False) -> Dict:  # type: ignore
    """
    Play an audio alert for the given event type.

    Args:
        alert_type: One of the ALERT_TYPES keys
        blocking: If True, block until sound finishes

    Returns:
        Dict with success status and description
    """
    from typing import Dict

    if _muted:
        return {"success": True, "muted": True, "alert_type": alert_type}

    if alert_type not in ALERT_TYPES:
        return {"success": False, "error": f"Unknown alert type: {alert_type}"}

    config = ALERT_TYPES[alert_type]

    def _play_sequence():
        base_freq = config["frequency_hz"]
        duration = config["duration_ms"]
        repeats = config["repeats"]
        gap = config["gap_ms"]
        pattern = config["pattern"]

        for i in range(repeats):
            if pattern == "ascending":
                freq = base_freq + (i * 120)
            elif pattern == "panic":
                freq = base_freq if i % 2 == 0 else base_freq * 1.3
            else:
                freq = base_freq

            _play_tone(freq, duration)

            if i < repeats - 1 and gap > 0:
                time.sleep(gap / 1000)

    if blocking:
        _play_sequence()
    else:
        thread = threading.Thread(target=_play_sequence, daemon=True)
        thread.start()

    return {
        "success": True,
        "alert_type": alert_type,
        "description": config["description"],
        "muted": False,
    }


def mute_alerts() -> None:
    """Mute all audio alerts."""
    global _muted
    _muted = True


def unmute_alerts() -> None:
    """Unmute audio alerts."""
    global _muted
    _muted = False


def is_muted() -> bool:
    """Return current mute state."""
    return _muted


def alert_critical_incident(incident_id: str = "") -> None:
    """Convenience: play CRITICAL_INCIDENT alert."""
    play_alert("CRITICAL_INCIDENT")


def alert_high_incident() -> None:
    """Convenience: play HIGH_INCIDENT alert."""
    play_alert("HIGH_INCIDENT")


def alert_low_stock(item: str = "") -> None:
    """Convenience: play LOW_STOCK_WARNING alert."""
    play_alert("LOW_STOCK_WARNING")


def alert_all_deployed() -> None:
    """Convenience: play TEAM_ALL_DEPLOYED alert."""
    play_alert("TEAM_ALL_DEPLOYED")


def alert_panic_activated() -> None:
    """Convenience: play PANIC_ACTIVATED alert (blocking=True for full effect)."""
    play_alert("PANIC_ACTIVATED", blocking=True)


def get_alert_registry() -> list:
    """Return list of all available alert types for dashboard."""
    return [
        {"type": k, "description": v["description"],
         "frequency": v["frequency_hz"], "repeats": v["repeats"]}
        for k, v in ALERT_TYPES.items()
    ]



