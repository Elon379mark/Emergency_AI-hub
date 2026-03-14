"""
command/qr_triage.py
──────────────────────
QR Triage Tags — Disaster Command Center v4 ELITE

Generates printable triage tags with embedded QR codes.
Uses qrcode + Pillow to produce A6-sized printable tag images.

QR payload: incident_id, victim, severity, injury, timestamp
Output: PNG image files in data/qr_tags/
"""

import os
import sys
import json
import time
from typing import Dict, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QR_OUTPUT_DIR = os.path.join(BASE_DIR, "data", "qr_tags")

# A6 in pixels at 150 DPI (105mm × 148mm)
A6_WIDTH_PX = 620
A6_HEIGHT_PX = 874

# Severity → background color (RGB tuples)
SEV_COLORS = {
    "CRITICAL": (200, 0, 0),       # Red
    "HIGH": (255, 140, 0),          # Orange
    "MEDIUM": (220, 180, 0),        # Yellow
    "LOW": (0, 150, 60),            # Green
    "UNKNOWN": (100, 100, 100),     # Grey
}

SEV_TEXT_COLORS = {
    "CRITICAL": (255, 255, 255),
    "HIGH": (255, 255, 255),
    "MEDIUM": (0, 0, 0),
    "LOW": (255, 255, 255),
    "UNKNOWN": (255, 255, 255),
}


def _build_qr_payload(incident_id: str, victim: str, severity: str,
                       injury: str, timestamp: Optional[str] = None) -> str:
    """Build JSON payload string for QR code."""
    payload = {
        "incident_id": incident_id,
        "victim": victim,
        "severity": severity,
        "injury": injury,
        "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "system": "DisasterCommandCenter_v4",
    }
    return json.dumps(payload, separators=(",", ":"))


def generate_qr_tag(incident_id: str, victim: str, severity: str,
                     injury: str, location: str = "",
                     timestamp: Optional[str] = None) -> Dict:
    """
    Generate a printable A6 triage tag with embedded QR code.

    Args:
        incident_id: The incident identifier
        victim: Patient description (e.g., "Adult male ~40yr")
        severity: CRITICAL | HIGH | MEDIUM | LOW
        injury: Injury description
        location: Optional location string
        timestamp: ISO timestamp (defaults to now)

    Returns:
        Dict with file_path, qr_data, success, message
    """
    os.makedirs(QR_OUTPUT_DIR, exist_ok=True)

    ts = timestamp or time.strftime("%Y-%m-%dT%H:%M:%S")
    qr_payload = _build_qr_payload(incident_id, victim, severity, injury, ts)

    filename = f"tag_{incident_id}_{severity}_{time.strftime('%H%M%S')}.png"
    output_path = os.path.join(QR_OUTPUT_DIR, filename)

    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont

        # ── Generate QR code image ──
        qr = qrcode.QRCode(
            version=None,  # Auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(qr_payload)
        qr.make(fit=True)

        sev_bg = SEV_COLORS.get(severity, SEV_COLORS["UNKNOWN"])
        sev_fg = SEV_TEXT_COLORS.get(severity, (255, 255, 255))

        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        qr_size = min(260, qr_img.size[0])
        qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)

        # ── Build A6 tag canvas ──
        canvas = Image.new("RGB", (A6_WIDTH_PX, A6_HEIGHT_PX), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Header band (severity color)
        header_h = 160
        draw.rectangle([(0, 0), (A6_WIDTH_PX, header_h)], fill=sev_bg)

        # Border
        border_w = 6
        draw.rectangle(
            [(border_w//2, border_w//2), (A6_WIDTH_PX - border_w//2, A6_HEIGHT_PX - border_w//2)],
            outline=sev_bg, width=border_w
        )

        # Try to load a font, fall back to default
        try:
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            font_med = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
            font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
        except Exception:
            font_large = ImageFont.load_default()
            font_med = font_large
            font_small = font_large
            font_xs = font_large

        # Severity text in header
        draw.text((A6_WIDTH_PX // 2, 55), f"⬛ {severity} ⬛",
                  fill=sev_fg, font=font_large, anchor="mm")
        draw.text((A6_WIDTH_PX // 2, 120), "TRIAGE TAG",
                  fill=sev_fg, font=font_med, anchor="mm")

        # Content area
        y = header_h + 20
        line_h = 42

        def draw_field(label: str, value: str, bold: bool = False):
            nonlocal y
            draw.text((30, y), f"{label}:", fill=(80, 80, 80), font=font_xs)
            draw.text((170, y), str(value)[:45], fill=(0, 0, 0),
                      font=font_med if bold else font_small)
            y += line_h

        draw_field("ID", incident_id, bold=True)
        draw_field("VICTIM", victim[:40])
        draw_field("INJURY", injury[:40])
        if location:
            draw_field("LOCATION", location[:40])
        draw_field("TIME", ts[-8:] if "T" in ts else ts[:8])

        # Divider line
        draw.line([(30, y + 5), (A6_WIDTH_PX - 30, y + 5)], fill=(200, 200, 200), width=2)
        y += 20

        # QR code placement (right-aligned)
        qr_x = A6_WIDTH_PX - qr_size - 30
        qr_y = y
        canvas.paste(qr_img, (qr_x, qr_y))

        # Scan instruction
        draw.text((30, qr_y + qr_size // 2 - 15), "SCAN FOR\nFULL DATA",
                  fill=(80, 80, 80), font=font_xs)

        # Bottom emergency strip
        strip_y = A6_HEIGHT_PX - 80
        draw.rectangle([(0, strip_y), (A6_WIDTH_PX, A6_HEIGHT_PX)], fill=sev_bg)
        draw.text((A6_WIDTH_PX // 2, strip_y + 40),
                  f"DISASTER COMMAND CENTER v4 | {severity}",
                  fill=sev_fg, font=font_xs, anchor="mm")

        canvas.save(output_path, "PNG", dpi=(150, 150))

        return {
            "success": True,
            "file_path": output_path,
            "filename": filename,
            "qr_data": qr_payload,
            "incident_id": incident_id,
            "severity": severity,
            "generated_at": ts,
            "method": "pillow_qrcode",
        }

    except ImportError as e:
        # Fallback: save QR payload as JSON text file
        json_path = output_path.replace(".png", "_qr_data.json")
        with open(json_path, "w") as f:
            json.dump(json.loads(qr_payload), f, indent=2)
        return {
            "success": True,
            "file_path": json_path,
            "filename": filename.replace(".png", "_qr_data.json"),
            "qr_data": qr_payload,
            "incident_id": incident_id,
            "severity": severity,
            "generated_at": ts,
            "method": "json_fallback",
            "note": f"qrcode/Pillow not installed ({e}) — saved QR data as JSON",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "qr_data": qr_payload,
            "incident_id": incident_id,
        }


def generate_batch_tags(incidents: List[Dict]) -> List[Dict]:
    """
    Generate QR triage tags for a batch of incidents.

    Args:
        incidents: List of incident dicts

    Returns:
        List of generation results
    """
    results = []
    for inc in incidents:
        result = generate_qr_tag(
            incident_id=inc.get("incident_id", "UNK"),
            victim=inc.get("victim", "Unknown"),
            severity=inc.get("severity", "MEDIUM"),
            injury=inc.get("injury", "Unknown"),
            location=inc.get("location", ""),
            timestamp=inc.get("created_at"),
        )
        results.append(result)
    return results


def list_generated_tags() -> List[Dict]:
    """Return list of all generated tag files."""
    if not os.path.exists(QR_OUTPUT_DIR):
        return []

    tags = []
    for fname in sorted(os.listdir(QR_OUTPUT_DIR), reverse=True):
        if fname.endswith((".png", ".json")):
            fpath = os.path.join(QR_OUTPUT_DIR, fname)
            tags.append({
                "filename": fname,
                "file_path": fpath,
                "size_bytes": os.path.getsize(fpath),
                "created": time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.localtime(os.path.getctime(fpath))
                ),
            })
    return tags
