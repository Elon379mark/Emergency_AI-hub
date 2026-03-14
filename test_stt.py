
import os
import sys
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from speech.multilingual_stt import transcribe_multilingual
    print("✅ Transcription module imported successfully")
except ImportError as e:
    print(f"❌ Failed to import transcription module: {e}")
    sys.exit(1)

# Create a 1-second silent audio buffer (16kHz)
sample_rate = 16000
duration_sec = 1
audio_array = np.zeros(sample_rate * duration_sec, dtype=np.float32)

print(f"Testing transcription with {duration_sec}s of silence...")
try:
    result = transcribe_multilingual(audio_array, sample_rate)
    print("Transcription result received:")
    print(f"  Detected Language: {result.get('detected_language')}")
    print(f"  Original Text: {result.get('text_original')}")
    print(f"  English Text: {result.get('text_english')}")
    print(f"  Processing Time: {result.get('processing_time_ms')}ms")
    if result.get('error'):
         print(f"  ⚠️ Internal Error reported: {result.get('error')}")
except Exception as e:
    print(f"❌ Critical error during test: {e}")
