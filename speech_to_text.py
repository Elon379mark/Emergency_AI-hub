"""
speech/speech_to_text.py

Real-time speech capture and transcription using faster-whisper.
Designed for CPU-only offline operation.
"""

import wave
import tempfile
import numpy as np

# ── Lazy imports ──
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


# ─────────────────────────────────────────────
# Whisper model cache
# ─────────────────────────────────────────────
_whisper_model = None


def get_whisper_model(model_size: str = "base"):
    global _whisper_model

    if _whisper_model is None:
        print(f"[Speech Module] Loading Whisper '{model_size}' model...")
        _whisper_model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8"
        )
        print("[Speech Module] Whisper model ready ✓")

    return _whisper_model


# ─────────────────────────────────────────────
# Record microphone audio
# ─────────────────────────────────────────────
def record_audio(duration: int = 5, sample_rate: int = 16000):

    if not SOUNDDEVICE_AVAILABLE:
        raise RuntimeError("sounddevice not installed. Run: pip install sounddevice")

    print(f"[Speech Module] 🎤 Recording for {duration} seconds...")

    audio = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="float32"
    )

    sd.wait()

    print("[Speech Module] Recording complete ✓")

    return audio.flatten()


# ─────────────────────────────────────────────
# Transcribe audio
# ─────────────────────────────────────────────
def transcribe_audio(audio_input, sample_rate: int = 16000) -> str:
    """
    Accepts either:
    - numpy audio array
    - file path to audio file
    """

    model = get_whisper_model()

    # ── CASE 1: file path provided ──
    if isinstance(audio_input, str):

        segments, _ = model.transcribe(audio_input,beam_size=5,vad_filter=True)

        text = " ".join(seg.text.strip() for seg in segments)

        print(f"[Speech Module] Transcription: \"{text}\"")

        return text.strip()

    # ── CASE 2: numpy audio array ──
    audio = audio_input.astype(np.float32)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:

        tmp_path = tmp.name

        with wave.open(tmp_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)

            audio_int16 = (audio * 32767).astype(np.int16)
            wf.writeframes(audio_int16.tobytes())

    segments, _ = model.transcribe(tmp_path, beam_size=1, language="en")

    text = " ".join(seg.text.strip() for seg in segments)

    print(f"[Speech Module] Transcription: \"{text}\"")

    return text.strip()


# ─────────────────────────────────────────────
# Record + transcribe convenience function
# ─────────────────────────────────────────────
def record_and_transcribe(duration: int = 5):

    audio = record_audio(duration)

    return transcribe_audio(audio)


# ─────────────────────────────────────────────
# Transcribe audio file
# ─────────────────────────────────────────────
def transcribe_file(file_path: str):

    return transcribe_audio(file_path)


# ─────────────────────────────────────────────
# Test
# ─────────────────────────────────────────────
if __name__ == "__main__":

    print("Testing speech module...")

    text = record_and_transcribe(5)

    print("Final transcription:", text)