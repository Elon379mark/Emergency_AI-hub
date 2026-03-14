"""
speech/multilingual_stt.py
───────────────────────────
Multilingual Speech-to-Text — Disaster Command Center v4 ELITE

Uses faster-whisper for offline multilingual transcription.
Supports 10 disaster-relevant languages with auto-detection
and English translation.

Supported languages:
    English, Tamil, Hindi, Sinhala, Arabic,
    French, Spanish, Portuguese, Swahili, Indonesian
"""

import os
import sys
import time
import numpy as np
from typing import Dict, Optional, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Emergency vocabulary for Whisper context bias ──
EMERGENCY_VOCABULARY = """
Emergency response conversation.
Possible medical and disaster words:

accident, bus accident, car crash, collapse
ambulance, call ambulance, ambulance bulao
injured, bleeding, heavy bleeding, hemorrhage
unconscious, not breathing, CPR required
fracture, broken leg, broken arm
burn injury, severe burn
trapped, rescue team needed
patient critical, patient stable
help needed, madad chahiye

Hinglish phrases:
accident hua hai
teen log unconscious
patient bleeding hai
jaldi ambulance bhejo
madad chahiye
"""


# ── Emergency vocabulary correction map ──
EMERGENCY_CORRECTIONS = {
    "ambyulance": "ambulance",
    "ambu lance": "ambulance",
    "bus acident": "bus accident",
    "accidant": "accident",
    "unconcious": "unconscious",
    "bleeding hevily": "bleeding heavily",
    "madat": "madad",
    "ambulance bulao": "call an ambulance",
}

# ── Language configuration ──
SUPPORTED_LANGUAGES = {
    "en": "English (India)",
    "hi": "Hindi / Hinglish",
}

# ISO 639-1 → display name
LANG_DISPLAY = {code: name for code, name in SUPPORTED_LANGUAGES.items()}

# Language badge colors for dashboard
LANG_BADGE_COLOR = {
    "en": "#1f77b4",
    "hi": "#2ca02c",
}
# Cached model to avoid re-loading
_whisper_model = None


def _get_model(model_size: str = "base"):
    """
    Lazily load faster-whisper model.
    Uses 'base' for speed on disaster hardware.
    Falls back gracefully if faster-whisper not installed.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    try:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",  # CPU-optimized quantization
        )
        return _whisper_model
    except ImportError:
        return None
    except Exception as e:
        print(f"[STT] Model load error: {e}")
        return None


def _normalize_audio(audio_array: np.ndarray) -> np.ndarray:
    """Normalize audio to float32 in [-1, 1] range."""
    if audio_array.dtype != np.float32:
        audio_array = audio_array.astype(np.float32)
    max_val = np.abs(audio_array).max()
    if max_val > 0:
        audio_array = audio_array / max_val
    return audio_array

def _correct_emergency_terms(text: str) -> str:
    """Fix common emergency speech recognition mistakes."""
    if not text:
        return text

    corrected = text.lower()

    for wrong, correct in EMERGENCY_CORRECTIONS.items():
        corrected = corrected.replace(wrong, correct)

    return corrected

def _simple_language_detect(transcription_result: Any) -> Tuple[str, float]:
    """
    Extract detected language and probability from faster-whisper result.
    Returns (language_code, probability).
    """
    try:
        lang = transcription_result.language or "en"
        prob = transcription_result.language_probability or 0.5
        return lang, prob
    except AttributeError:
        return "en", 0.5


def detect_language(audio_array: np.ndarray, sample_rate: int = 16000) -> Dict:
    """
    Detect spoken language from audio array.

    Args:
        audio_array: NumPy array of audio samples
        sample_rate: Sample rate in Hz (default 16000)

    Returns:
        Dict with:
            detected_language: ISO 639-1 code
            language_name: Human-readable name
            confidence: float 0-1
            is_supported: bool
    """
    model = _get_model()
    if model is None:
        return {
            "detected_language": "en",
            "language_name": "English",
            "confidence": 0.0,
            "is_supported": True,
            "error": "faster-whisper not available",
        }

    audio = _normalize_audio(audio_array)

    try:
        # Run detection-only (no full transcription)
        _, info = model.transcribe(audio, beam_size=1, language=None,
                                   task="transcribe", without_timestamps=True)
        lang = info.language if hasattr(info, "language") else "en"
        prob = info.language_probability if hasattr(info, "language_probability") else 0.5

        return {
            "detected_language": lang,
            "language_name": LANG_DISPLAY.get(lang, lang.upper()),
            "confidence": round(float(prob), 3),
            "is_supported": lang in SUPPORTED_LANGUAGES,
            "badge_color": LANG_BADGE_COLOR.get(lang, "#888888"),
        }
    except Exception as e:
        return {
            "detected_language": "en",
            "language_name": "English",
            "confidence": 0.0,
            "is_supported": True,
            "error": str(e),
        }


def transcribe_multilingual(audio_array: np.ndarray,
                             sample_rate: int = 16000,
                             force_language: Optional[str] = None) -> Dict:
    """
    Transcribe audio in any supported language and translate to English.

    Args:
        audio_array: NumPy array of audio samples
        sample_rate: Sample rate (default 16000 for Whisper)
        force_language: Optional ISO code to skip auto-detection

    Returns:
        Dict with:
            text_original: Transcription in original language
            text_english: English translation
            detected_language: ISO 639-1 code
            language_name: Human-readable language name
            translation_method: "whisper_translate" | "passthrough" | "fallback"
            confidence: float 0-1
            processing_time_ms: float
    """
    start = time.time()

    model = _get_model()

    if model is None:
        # Graceful fallback when faster-whisper unavailable
        return {
            "text_original": "[faster-whisper not installed]",
            "text_english": "[faster-whisper not installed]",
            "detected_language": "en",
            "language_name": "English",
            "translation_method": "fallback",
            "confidence": 0.0,
            "processing_time_ms": 0.0,
            "error": "faster-whisper package not installed",
        }

    audio = _normalize_audio(audio_array)

    try:
        # ── Step 1: Transcribe in original language ──
        lang_hint = force_language  # None = auto-detect
        segments_orig, info = model.transcribe(
            audio,
            beam_size=8,
            language=lang_hint,
            task="transcribe",
            without_timestamps=True,
            vad_filter=True,
            initial_prompt=EMERGENCY_VOCABULARY
)
        text_original = " ".join(seg.text.strip() for seg in segments_orig).strip()
        text_original = _correct_emergency_terms(text_original)
        detected_lang = info.language if hasattr(info, "language") else "en"
        lang_prob = float(info.language_probability) if hasattr(info, "language_probability") else 0.5

        # ── Step 2: Translate to English if needed ──
        if detected_lang == "en":
            text_english = text_original
            translation_method = "passthrough"
        else:
            segments_en, _ = model.transcribe(
                audio,
                beam_size=8,
                language=detected_lang,
                task="translate",
                without_timestamps=True,
                vad_filter=True,
                initial_prompt=(
                    "Translate emergency medical speech clearly into English. "
                    + EMERGENCY_VOCABULARY
)
            )
            text_english = " ".join(seg.text.strip() for seg in segments_en).strip()
            text_english = _correct_emergency_terms(text_english)
            translation_method = "whisper_translate"

        processing_time_ms = round((time.time() - start) * 1000, 1)

        return {
            "text_original": text_original or "[no speech detected]",
            "text_english": text_english or "[no speech detected]",
            "detected_language": detected_lang,
            "language_name": LANG_DISPLAY.get(detected_lang, detected_lang.upper()),
            "translation_method": translation_method,
            "confidence": round(lang_prob, 3),
            "processing_time_ms": processing_time_ms,
            "is_supported": detected_lang in SUPPORTED_LANGUAGES,
            "badge_color": LANG_BADGE_COLOR.get(detected_lang, "#888888"),
        }

    except Exception as e:
        return {
            "text_original": "[transcription error]",
            "text_english": "[transcription error]",
            "detected_language": "en",
            "language_name": "English",
            "translation_method": "fallback",
            "confidence": 0.0,
            "processing_time_ms": round((time.time() - start) * 1000, 1),
            "error": str(e),
        }


def record_and_transcribe_multilingual(duration: int = 7,
                                        sample_rate: int = 16000) -> Dict:
    """
    Record audio from microphone and transcribe multilingually.

    Args:
        duration: Recording duration in seconds
        sample_rate: Sample rate (default 16000)

    Returns:
        Full transcription dict from transcribe_multilingual()
    """
    try:
        import sounddevice as sd
        print(f"[STT] 🎤 Recording {duration}s in any language...")
        audio = sd.rec(
            int(duration * sample_rate),
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        audio_array = audio.flatten()
        return transcribe_multilingual(audio_array, sample_rate)

    except ImportError:
        return {
            "text_original": "[sounddevice not installed]",
            "text_english": "[sounddevice not installed]",
            "detected_language": "en",
            "language_name": "English",
            "translation_method": "fallback",
            "confidence": 0.0,
            "processing_time_ms": 0.0,
            "error": "sounddevice not installed",
        }
    except Exception as e:
        return {
            "text_original": f"[recording error: {e}]",
            "text_english": f"[recording error: {e}]",
            "detected_language": "en",
            "language_name": "English",
            "translation_method": "fallback",
            "confidence": 0.0,
            "processing_time_ms": 0.0,
            "error": str(e),
        }


def get_language_badge_html(result: Dict) -> str:
    """
    Generate HTML badge for dashboard display of detected language.

    Args:
        result: Dict from transcribe_multilingual()

    Returns:
        HTML string for Streamlit unsafe_allow_html
    """
    lang = result.get("language_name", "Unknown")
    code = result.get("detected_language", "?")
    conf = result.get("confidence", 0)
    color = result.get("badge_color", "#888888")
    method = result.get("translation_method", "")

    method_label = {
        "passthrough": "Native EN",
        "whisper_translate": "Auto-translated",
        "fallback": "Fallback",
    }.get(method, method)

    return (
        f'<span style="background:{color};color:white;padding:3px 10px;'
        f'border-radius:12px;font-size:0.85em;font-weight:bold;margin:2px">'
        f'🌐 {lang} ({code.upper()}) · {method_label} · {conf:.0%}'
        f'</span>'
    )