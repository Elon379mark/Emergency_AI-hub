"""
command/report_generator.py
────────────────────────────
Incident Report Generator — Disaster Command Center v4 ELITE

Generates professional PDF incident reports using ReportLab.
Sections: summary, timeline, triage, resources, team, vitals, survival.

Functions:
    generate_incident_report(incident_id) → PDF file path
    generate_mass_report() → PDF covering all incidents
"""

import os
import sys
import json
import time
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(BASE_DIR, "data", "reports")
INCIDENTS_FILE = os.path.join(BASE_DIR, "data", "incident_table.json")
VITALS_FILE = os.path.join(BASE_DIR, "data", "vitals_log.json")


def _load_incidents() -> List[Dict]:
    """Load all incidents from incident table."""
    try:
        if os.path.exists(INCIDENTS_FILE):
            with open(INCIDENTS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _load_vitals() -> Dict:
    """Load vitals log."""
    try:
        if os.path.exists(VITALS_FILE):
            with open(VITALS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"patients": {}}


def _get_incident(incident_id: str) -> Optional[Dict]:
    """Find a single incident by ID."""
    incidents = _load_incidents()
    for inc in incidents:
        if inc.get("incident_id") == incident_id:
            return inc
    return None


def _try_reportlab_pdf(incident: Dict, output_path: str) -> str:
    """
    Generate PDF using ReportLab.
    Returns file path on success, raises on failure.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Color palette ──
    RED = colors.HexColor("#CC0000")
    DARK = colors.HexColor("#1a1a1a")
    ACCENT = colors.HexColor("#FF4444")
    LIGHT_GREY = colors.HexColor("#F5F5F5")

    sev = incident.get("severity", "MEDIUM")
    sev_color = {
        "CRITICAL": colors.red,
        "HIGH": colors.orangered,
        "MEDIUM": colors.goldenrod,
        "LOW": colors.green,
    }.get(sev, colors.grey)

    # ─ Header ─
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        textColor=RED, fontSize=20, spaceAfter=4,
        alignment=TA_CENTER,
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"],
        textColor=DARK, fontSize=10, alignment=TA_CENTER, spaceAfter=8,
    )
    story.append(Paragraph("🚨 DISASTER RESPONSE INCIDENT REPORT", title_style))
    story.append(Paragraph("Offline Disaster Command Center v4 ELITE", sub_style))
    story.append(Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", sub_style))
    story.append(HRFlowable(width="100%", thickness=2, color=RED, spaceAfter=12))

    # ─ Section heading helper ─
    def section_head(text):
        h_style = ParagraphStyle(
            "SecHead", parent=styles["Heading2"],
            textColor=RED, fontSize=13, spaceBefore=12, spaceAfter=4,
        )
        story.append(Paragraph(text, h_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=6))

    def body_text(text):
        story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 4))

    def kv_table(rows: List[tuple]) -> Table:
        data = [[Paragraph(f"<b>{k}</b>", styles["Normal"]),
                 Paragraph(str(v), styles["Normal"])] for k, v in rows]
        t = Table(data, colWidths=[5*cm, 12*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    # ── 1. Incident Summary ──
    section_head("1. INCIDENT SUMMARY")
    story.append(kv_table([
        ("Incident ID", incident.get("incident_id", "N/A")),
        ("Severity", sev),
        ("Status", incident.get("status", "N/A")),
        ("Victim", incident.get("victim", "N/A")),
        ("Injury", incident.get("injury", "N/A")),
        ("Location", incident.get("location", "N/A")),
        ("Priority Score", incident.get("priority_score", "N/A")),
    ]))
    story.append(Spacer(1, 10))

    # ── 2. Timeline ──
    section_head("2. TIMELINE")
    created = incident.get("created_at") or incident.get("timestamp") or "N/A"
    updated = incident.get("updated_at") or created
    resolved = incident.get("resolved_at") or "None"
    story.append(kv_table([
        ("Created", created),
        ("Last Updated", updated),
        ("Resolved", resolved),
        ("Assigned Team", incident.get("assigned_team") or "None"),
    ]))
    story.append(Spacer(1, 10))

    # ── 3. Triage Analysis ──
    section_head("3. TRIAGE ANALYSIS")
    triage = incident.get("triage")
    if not triage:
        # Construct fallback triage from top-level fields for older records
        triage = {
            "severity": incident.get("severity", sev),
            "confidence": incident.get("confidence", 0.0),
            "triage_method": incident.get("triage_method", "rule_based"),
            "reasoning": incident.get("reasoning") or incident.get("triage_reasoning") or "—",
            "immediate_actions": incident.get("immediate_actions", [])
        }
    
    # Handle confidence format (decimal vs percentage)
    conf = triage.get("confidence", 0.0)
    if isinstance(conf, (int, float)):
        conf_str = f"{conf*100:.0f}%" if conf <= 1.0 else f"{conf:.0f}%"
    else:
        conf_str = str(conf)

    story.append(kv_table([
        ("Severity", triage.get("severity", sev)),
        ("Confidence", conf_str),
        ("Method", triage.get("triage_method", "rule_based")),
        ("Reasoning", triage.get("reasoning", "—")),
        ("Immediate Actions", " • ".join(triage.get("immediate_actions", [])) if triage.get("immediate_actions") else "—"),
    ]))
    story.append(Spacer(1, 10))

    # ── 4. Resources Dispatched ──
    section_head("4. RESOURCES DISPATCHED")
    try:
        from command.equipment_dispatch import get_dispatch_log
        resources = get_dispatch_log(incident.get("incident_id"))
    except ImportError:
        resources = incident.get("dispatched_resources", [])

    if resources:
        res_data = [["Item", "Qty", "Status"]]
        for r in resources:
            res_data.append([r.get("item", "?"), str(r.get("quantity", 1)), r.get("status", "?")])
        res_table = Table(res_data, colWidths=[8*cm, 3*cm, 6*cm])
        res_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RED),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(res_table)
    else:
        body_text("No resources dispatched or data unavailable.")
    story.append(Spacer(1, 10))

    # ── 5. Team Assignment ──
    section_head("5. TEAM ASSIGNMENT")
    story.append(kv_table([
        ("Assigned Team", incident.get("assigned_team", "Unassigned")),
        ("Assignment Status", incident.get("status", "N/A")),
    ]))
    story.append(Spacer(1, 10))

    # ── 6. Vitals Log ──
    section_head("6. VITALS LOG")
    vitals_data = _load_vitals()
    patient_key = f"{incident.get('incident_id', '')}_{incident.get('victim', '')}".replace(" ", "_")
    patient = vitals_data.get("patients", {}).get(patient_key)

    if patient and patient.get("readings"):
        vitals_table_data = [["Time", "Pulse", "BP", "SpO2", "RR", "Consciousness"]]
        for r in patient["readings"][-10:]:  # Last 10 readings
            vitals_table_data.append([
                r.get("timestamp", "")[-8:],
                f"{r.get('pulse_bpm', '—')} bpm",
                f"{r.get('systolic_bp', '—')}/{r.get('diastolic_bp', '—')}",
                f"{r.get('spo2_percent', '—')}%",
                f"{r.get('respiratory_rate', '—')}/min",
                r.get("consciousness", "—"),
            ])
        vt = Table(vitals_table_data, colWidths=[3*cm, 2.8*cm, 3.2*cm, 2.5*cm, 2.5*cm, 3*cm])
        vt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(vt)
    else:
        body_text("No vitals recorded for this patient.")
    story.append(Spacer(1, 10))

    # ── 7. Survival Probability ──
    section_head("7. SURVIVAL PROBABILITY")
    survival = incident.get("survival_data", {})
    if survival:
        # Check both possible keys: survival_probability and survival_probability_percent
        prob = survival.get('survival_probability') or survival.get('survival_probability_percent', '?')
        story.append(kv_table([
            ("Survival Probability", f"{prob}%"),
            ("Urgency", survival.get("urgency", "—")),
            ("Injury Type", survival.get("injury_type", "—")),
            ("Response Delay", f"{survival.get('response_delay_minutes', '?')} min"),
        ]))
    else:
        body_text("Survival probability data not available.")

    # ─ Footer ─
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=RED))
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=8, textColor=colors.grey, alignment=TA_CENTER,
    )
    story.append(Paragraph(
        "CONFIDENTIAL — Offline Disaster Response Command Center v4 ELITE | "
        f"Report generated {time.strftime('%Y-%m-%d %H:%M:%S')}",
        footer_style
    ))

    doc.build(story)
    return output_path


def generate_incident_report(incident_id: str) -> Dict:
    """
    Generate PDF report for a single incident.

    Args:
        incident_id: The incident ID to report on

    Returns:
        Dict with file_path, success, and message
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    incident = _get_incident(incident_id)
    if not incident:
        return {"success": False, "error": f"Incident {incident_id} not found"}

    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"incident_{incident_id}_{ts}.pdf"
    output_path = os.path.join(REPORTS_DIR, filename)

    try:
        _try_reportlab_pdf(incident, output_path)
        return {
            "success": True,
            "file_path": output_path,
            "filename": filename,
            "incident_id": incident_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    except ImportError:
        # ReportLab not installed — generate plain text report
        txt_path = output_path.replace(".pdf", ".txt")
        _generate_text_report(incident, txt_path)
        return {
            "success": True,
            "file_path": txt_path,
            "filename": filename.replace(".pdf", ".txt"),
            "incident_id": incident_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "ReportLab not installed — generated plain text report",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "incident_id": incident_id}


def _generate_text_report(incident: Dict, output_path: str) -> None:
    """Plain text fallback report."""
    lines = [
        "=" * 70,
        "DISASTER RESPONSE INCIDENT REPORT",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        f"Incident ID: {incident.get('incident_id')}",
        f"Severity:    {incident.get('severity')}",
        f"Victim:      {incident.get('victim')}",
        f"Injury:      {incident.get('injury')}",
        f"Location:    {incident.get('location')}",
        f"Status:      {incident.get('status')}",
        f"Assigned:    {incident.get('assigned_team', 'Unassigned')}",
        f"Created:     {incident.get('created_at')}",
        "=" * 70,
    ]
    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def generate_mass_report() -> Dict:
    """
    Generate a comprehensive PDF covering all incidents.

    Returns:
        Dict with file_path, success, incident count
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    incidents = _load_incidents()

    if not incidents:
        return {"success": False, "error": "No incidents found"}

    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"mass_report_{ts}.pdf"
    output_path = os.path.join(REPORTS_DIR, filename)

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table,
            TableStyle, HRFlowable, PageBreak
        )

        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []

        RED = colors.HexColor("#CC0000")
        LIGHT_GREY = colors.HexColor("#F5F5F5")

        # Cover page
        story.append(Spacer(1, 3*cm))
        story.append(Paragraph(
            "🚨 MASS CASUALTY INCIDENT REPORT",
            getSampleStyleSheet()["Title"]
        ))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(
            f"Total Incidents: {len(incidents)} | Generated: {time.strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        ))
        story.append(PageBreak())

        # Summary table
        story.append(Paragraph("ALL INCIDENTS SUMMARY", styles["Heading1"]))
        data = [["ID", "Severity", "Victim", "Injury", "Status", "Team"]]
        for inc in incidents:
            data.append([
                inc.get("incident_id", "?")[:12],
                inc.get("severity", "?"),
                inc.get("victim", "?")[:20],
                inc.get("injury", "?")[:25],
                inc.get("status", "?"),
                inc.get("assigned_team", "—"),
            ])

        t = Table(data, colWidths=[3*cm, 2.5*cm, 4*cm, 4.5*cm, 2.5*cm, 2.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), RED),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ]))
        story.append(t)

        doc.build(story)
        return {
            "success": True,
            "file_path": output_path,
            "filename": filename,
            "incident_count": len(incidents),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    except ImportError:
        txt_path = output_path.replace(".pdf", ".txt")
        lines = [f"MASS REPORT — {len(incidents)} incidents\n",
                 "=" * 60]
        for inc in incidents:
            lines.append(f"{inc.get('incident_id')} | {inc.get('severity')} | {inc.get('victim')}")
        with open(txt_path, "w") as f:
            f.write("\n".join(lines))
        return {
            "success": True,
            "file_path": txt_path,
            "filename": filename.replace(".pdf", ".txt"),
            "incident_count": len(incidents),
            "note": "ReportLab not installed",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
