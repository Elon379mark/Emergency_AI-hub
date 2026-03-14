"""
agents/photo_triage_agent.py
─────────────────────────────
Photo Triage Agent — Disaster Command Center v4 ELITE

Allows responders to upload injury photos for AI-powered visual triage.
Uses Claude vision API to assess injury severity from images.
Merges photo severity with text-based severity (higher severity wins).
"""

import os
import sys
import json
import time
import base64
import urllib.request
import urllib.error
from typing import Dict, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Constants ──
API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-20250514"
TIMEOUT_SECONDS = 15
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Severity ordering for merge logic
SEVERITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}

PHOTO_TRIAGE_PROMPT = """You are a trauma nurse conducting visual triage in a disaster response scenario.
Analyze this injury photo and provide a rapid, structured triage assessment.

Respond ONLY with a valid JSON object in this exact format:
{
  "injury_visible": true|false,
  "severity": "CRITICAL|HIGH|MEDIUM|LOW",
  "confidence": 0.0-1.0,
  "injury_description": "brief description of visible injury",
  "immediate_actions": ["action1", "action2"],
  "do_not_do": ["contraindication1"],
  "estimated_treatment_time_minutes": integer,
  "requires_surgery": true|false,
  "body_region": "head|chest|abdomen|extremity|back|multiple|unknown",
  "wound_type": "laceration|burn|fracture|contusion|puncture|unknown",
  "bleeding_visible": true|false,
  "deformity_visible": true|false,
  "triage_notes": "any special observations"
}

If no injury is visible or the image is unclear, set injury_visible to false and severity to UNKNOWN.
Be conservative — when uncertain, escalate severity."""


def _encode_image(image_bytes: bytes, media_type: str = "image/jpeg") -> str:
    """Base64-encode image bytes for API transmission."""
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def _get_media_type(file_path: str) -> str:
    """Infer MIME type from file extension."""
    ext = os.path.splitext(file_path.lower())[1]
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def _call_vision_api(image_bytes: bytes, media_type: str) -> Optional[Dict]:
    """
    Send image to Claude vision API for injury assessment.

    Args:
        image_bytes: Raw image bytes
        media_type: MIME type string

    Returns:
        Parsed triage dict or None on failure
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    b64_image = _encode_image(image_bytes, media_type)

    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 600,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": PHOTO_TRIAGE_PROMPT,
                    },
                ],
            }
        ],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = body["content"][0]["text"].strip()

            # Strip markdown fences
            if "```" in text:
                parts = text.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:]
                    part = part.strip()
                    if part.startswith("{"):
                        text = part
                        break

            return json.loads(text)

    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "injury_visible": False}
    except urllib.error.URLError as e:
        return {"error": f"API unavailable: {e.reason}", "injury_visible": False}
    except Exception as e:
        return {"error": str(e), "injury_visible": False}


def _fallback_photo_triage() -> Dict:
    """Return safe fallback when vision API is unavailable."""
    return {
        "injury_visible": False,
        "severity": "MEDIUM",
        "confidence": 0.0,
        "injury_description": "Photo assessment unavailable — use manual triage",
        "immediate_actions": ["Conduct manual physical assessment", "Check ABC"],
        "do_not_do": [],
        "estimated_treatment_time_minutes": 15,
        "requires_surgery": False,
        "body_region": "unknown",
        "wound_type": "unknown",
        "bleeding_visible": False,
        "deformity_visible": False,
        "triage_notes": "Vision API unavailable — rule-based fallback",
        "photo_triage_method": "fallback",
    }


def analyze_injury_photo(image_bytes: bytes,
                          media_type: str = "image/jpeg") -> Dict:
    """
    Analyze injury from raw image bytes.

    Args:
        image_bytes: Raw bytes of the uploaded image
        media_type: MIME type (default image/jpeg)

    Returns:
        Structured photo triage dict
    """
    start = time.time()

    if not image_bytes:
        result = _fallback_photo_triage()
        result["error"] = "No image data provided"
        return result

    result = _call_vision_api(image_bytes, media_type)
    elapsed_ms = round((time.time() - start) * 1000, 1)

    if result and "error" not in result:
        result["photo_triage_method"] = "claude_vision"
        result["processing_time_ms"] = elapsed_ms
        return result

    fallback = _fallback_photo_triage()
    fallback["api_error"] = result.get("error", "unknown") if result else "no response"
    fallback["processing_time_ms"] = elapsed_ms
    return fallback


def analyze_photo_file(file_path: str) -> Dict:
    """
    Analyze injury photo from a file path.

    Args:
        file_path: Path to the image file

    Returns:
        Structured photo triage dict
    """
    ext = os.path.splitext(file_path.lower())[1]
    if ext not in SUPPORTED_FORMATS:
        return {
            **_fallback_photo_triage(),
            "error": f"Unsupported format: {ext}. Use {SUPPORTED_FORMATS}",
        }

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        media_type = _get_media_type(file_path)
        return analyze_injury_photo(image_bytes, media_type)
    except FileNotFoundError:
        return {**_fallback_photo_triage(), "error": f"File not found: {file_path}"}
    except Exception as e:
        return {**_fallback_photo_triage(), "error": str(e)}


def merge_photo_and_text_severity(text_triage: Dict,
                                   photo_triage: Dict) -> Dict:
    """
    Merge photo-based and text-based triage results.
    Higher severity wins.

    Args:
        text_triage: Result from run_triage_agent() or run_llm_triage_agent()
        photo_triage: Result from analyze_injury_photo()

    Returns:
        Merged triage dict with source tracking
    """
    text_sev = text_triage.get("severity", "MEDIUM")
    photo_sev = photo_triage.get("severity", "UNKNOWN")

    text_rank = SEVERITY_ORDER.get(text_sev, 2)
    photo_rank = SEVERITY_ORDER.get(photo_sev, 0)

    if photo_rank >= text_rank and photo_triage.get("injury_visible", False):
        winning_severity = photo_sev
        severity_source = "photo"
    else:
        winning_severity = text_sev
        severity_source = "text"

    merged = {**text_triage}
    merged["severity"] = winning_severity
    merged["severity_source"] = severity_source
    merged["text_severity"] = text_sev
    merged["photo_severity"] = photo_sev
    merged["photo_available"] = photo_triage.get("injury_visible", False)
    merged["photo_confidence"] = photo_triage.get("confidence", 0.0)
    merged["photo_injury_description"] = photo_triage.get("injury_description", "")
    merged["photo_immediate_actions"] = photo_triage.get("immediate_actions", [])
    merged["photo_do_not_do"] = photo_triage.get("do_not_do", [])
    merged["photo_treatment_time_min"] = photo_triage.get(
        "estimated_treatment_time_minutes", 15
    )
    merged["photo_triage_method"] = photo_triage.get("photo_triage_method", "unknown")

    if severity_source == "photo":
        merged["reasoning"] = (
            f"Photo triage escalated severity from {text_sev} to {photo_sev}. "
            + photo_triage.get("injury_description", "")
        )

    return merged


def run_photo_triage_agent(image_bytes: Optional[bytes],
                            text_triage: Optional[Dict] = None,
                            media_type: str = "image/jpeg") -> Dict:
    """
    Main entry point for photo triage pipeline.

    If text_triage is provided, merges results.
    If no image provided, returns text_triage unchanged.

    Args:
        image_bytes: Raw image bytes or None
        text_triage: Existing text triage result (optional)
        media_type: Image MIME type

    Returns:
        Final triage dict (merged or photo-only)
    """
    if not image_bytes:
        if text_triage:
            text_triage["photo_available"] = False
            return text_triage
        return _fallback_photo_triage()

    photo_result = analyze_injury_photo(image_bytes, media_type)

    if text_triage:
        return merge_photo_and_text_severity(text_triage, photo_result)

    photo_result["severity_source"] = "photo_only"
    return photo_result
