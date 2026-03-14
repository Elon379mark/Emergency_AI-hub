"""
agents/response_agent.py
─────────────────────────
Response Agent: Synthesizes outputs from all upstream agents into a
final structured emergency response report.

Combines:
- Intake context (victim, injury, situation)
- Triage severity
- Knowledge graph treatments
- RAG protocol steps
- Resource availability

Outputs a clean, actionable emergency report.
"""

import re
from typing import Dict, List


def extract_protocol_steps(protocol_text: str) -> List[str]:
    """
    Parse numbered steps from protocol text.

    Args:
        protocol_text: Raw protocol text from RAG

    Returns:
        List of numbered step strings
    """
    if not protocol_text:
        return ["Follow standard first aid procedures", "Contact emergency services"]

    steps = []

    # Find numbered steps (1. Step, 1) Step, Step 1:)
    numbered = re.findall(
        r"(?:^|\n)\s*(?:\d+[\.\)]|Step \d+:?)\s*(.+?)(?=\n\s*(?:\d+[\.\)]|Step \d+:?)|\Z)",
        protocol_text,
        re.DOTALL
    )

    for step in numbered:
        cleaned = step.strip().replace("\n", " ")
        if cleaned and len(cleaned) > 5:
            steps.append(cleaned[:200])  # Cap step length

    # If no numbered steps found, split by newlines and filter
    if not steps:
        lines = [line.strip() for line in protocol_text.split("\n")]
        steps = [
            line for line in lines
            if len(line) > 15 and not line.startswith("[") and not line.startswith("─")
        ][:8]  # Max 8 steps

    return steps[:10] if steps else ["Follow standard emergency protocol"]


def format_resource_summary(resource_data: Dict) -> List[Dict]:
    """
    Format resource availability into clean status entries.

    Args:
        resource_data: Output from resource agent

    Returns:
        List of formatted resource dicts
    """
    formatted = []
    for r in resource_data.get("resources", []):
        entry = {
            "item": r["item"].replace("_", " ").title(),
            "status": r["status"],
            "location": r.get("location") or "Not found",
            "quantity": r.get("quantity"),
        }

        if r["status"] == "AVAILABLE":
            entry["display"] = f"✅ {entry['item']} — {entry['location']} (Qty: {entry['quantity']})"
        elif r.get("alternative"):
            alt = r["alternative"]
            alt_name = alt["item"].replace("_", " ").title()
            entry["display"] = (
                f"⚠️  {entry['item']} unavailable → Use: {alt_name} "
                f"({alt.get('location', 'improvise')})"
            )
            entry["alternative"] = alt
        else:
            entry["display"] = f"❌ {entry['item']} — Not available, improvise substitute"

        formatted.append(entry)

    return formatted


def build_immediate_actions(severity: str, treatments: List[str]) -> List[str]:
    """
    Build prioritized immediate action steps based on severity.

    Args:
        severity: CRITICAL / HIGH / MEDIUM / LOW
        treatments: Knowledge graph treatment recommendations

    Returns:
        List of immediate action strings
    """
    # Universal first steps by severity
    preamble = {
        "CRITICAL": [
            "⚠️  CALL EMERGENCY SERVICES IMMEDIATELY",
            "Ensure scene safety before approaching victim",
        ],
        "HIGH": [
            "Request emergency medical support",
            "Ensure scene safety",
        ],
        "MEDIUM": [
            "Assess victim and begin first aid",
        ],
        "LOW": [
            "Provide basic first aid",
        ],
    }

    actions = preamble.get(severity, preamble["MEDIUM"])

    # Add knowledge graph treatments as next steps
    for treatment in treatments:
        action = treatment.replace("_", " ").capitalize()
        if action not in actions:
            actions.append(action)

    return actions


def run_response_agent(
    context: Dict,
    triage: Dict,
    kg_data: Dict,
    protocol_data: Dict,
    resource_data: Dict,
) -> Dict:
    """
    Main response agent function.
    Synthesizes all agent outputs into a final emergency report.

    Args:
        context: Intake agent output
        triage: Triage agent output
        kg_data: Knowledge graph agent output
        protocol_data: Protocol agent output
        resource_data: Resource agent output

    Returns:
        Complete emergency response dict
    """
    print("[Response Agent] Generating final emergency response...")

    severity = triage.get("severity", "MEDIUM")
    injury = context.get("injury", "unspecified injury")
    victim = context.get("victim", "unknown person")
    situation = context.get("situation", "emergency situation")
    environment = context.get("environment", "unknown")

    # Extract clean protocol steps from RAG text
    protocol_steps = extract_protocol_steps(protocol_data.get("protocol_text", ""))

    # Format resource summary
    resource_summary = format_resource_summary(resource_data)

    # Build immediate actions list
    immediate_actions = build_immediate_actions(
        severity,
        kg_data.get("recommended_treatments", [])
    )

    # Severity label with visual indicator
    severity_indicator = {
        "CRITICAL": "🔴 CRITICAL",
        "HIGH": "🟠 HIGH",
        "MEDIUM": "🟡 MEDIUM",
        "LOW": "🟢 LOW",
    }.get(severity, severity)

    # Build complete response
    response = {
        # ── Summary ──
        "severity": severity,
        "severity_display": severity_indicator,
        "confidence": triage.get("confidence", 0),
        "confidence_label": triage.get("confidence_label", ""),

        # ── Victim & Scene ──
        "victim": victim.replace("_", " ").capitalize(),
        "injury": injury.replace("_", " ").capitalize(),
        "situation": situation.replace("_", " ").capitalize(),
        "environment": environment.replace("_", " ").capitalize(),
        "location": context.get("location_hint", "unknown location").capitalize(),  # Feature 2+6
        "raw_request": context.get("raw_text", ""),

        # ── Actions ──
        "immediate_actions": immediate_actions,
        "protocol_steps": protocol_steps,

        # ── Resources ──
        "resources": resource_summary,
        "resources_available": resource_data.get("available_count", 0),
        "resources_total": resource_data.get("total_count", 0),
        "critical_missing": resource_data.get("critical_missing", []),
        "low_stock_alerts": resource_data.get("low_stock_alerts", []),  # Feature 5+6
        "has_low_stock": resource_data.get("has_low_stock", False),

        # ── Metadata ──
        "rag_query": protocol_data.get("query_used", ""),
        "rag_relevance": protocol_data.get("top_relevance", 0),
        "kg_treatments": kg_data.get("recommended_treatments", []),
        "kg_resources": kg_data.get("required_resources", []),
    }

    print(f"[Response Agent] Final report generated: {severity_indicator}")
    return response
