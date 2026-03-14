"""
agents/knowledge_graph_agent.py
────────────────────────────────
Knowledge Graph Agent: Models relationships between injuries, treatments,
required resources, and severity levels using NetworkX.

Graph structure:
  injury → treatment (edge type: "treats")
  injury → resource  (edge type: "requires")
  injury → severity  (edge type: "severity_level")
  resource → alternative (edge type: "alternative_for")

All runs fully offline with no external dependencies beyond networkx.
"""

import networkx as nx
from typing import Dict, List, Optional


def build_emergency_knowledge_graph() -> nx.DiGraph:
    """
    Construct the Emergency Knowledge Graph.

    Returns:
        NetworkX directed graph with medical emergency relationships
    """
    G = nx.DiGraph()

    # ── Node types: injuries, treatments, resources, alternatives ──

    # ─── Fractures ───
    G.add_edge("leg fracture",      "splint",           relation="requires")
    G.add_edge("leg fracture",      "immobilize leg",   relation="treats")
    G.add_edge("leg fracture",      "cold pack",        relation="requires")
    G.add_edge("leg fracture",      "painkiller",       relation="requires")
    G.add_edge("leg fracture",      "CRITICAL",         relation="severity_level")
    G.add_edge("arm fracture",      "splint",           relation="requires")
    G.add_edge("arm fracture",      "sling",            relation="requires")
    G.add_edge("arm fracture",      "apply sling",      relation="treats")
    G.add_edge("arm fracture",      "HIGH",             relation="severity_level")
    G.add_edge("spinal fracture",   "cervical collar",  relation="requires")
    G.add_edge("spinal fracture",   "immobilize spine", relation="treats")
    G.add_edge("spinal fracture",   "stretcher",        relation="requires")
    G.add_edge("spinal fracture",   "CRITICAL",         relation="severity_level")

    # ─── Bleeding / Wounds ───
    G.add_edge("bleeding",          "bandage",          relation="requires")
    G.add_edge("bleeding",          "gauze",            relation="requires")
    G.add_edge("bleeding",          "apply pressure",   relation="treats")
    G.add_edge("bleeding",          "tourniquet",       relation="requires")
    G.add_edge("bleeding",          "antiseptic",       relation="requires")
    G.add_edge("severe bleeding",   "tourniquet",       relation="requires")
    G.add_edge("severe bleeding",   "CRITICAL",         relation="severity_level")
    G.add_edge("minor cut",         "bandage",          relation="requires")
    G.add_edge("minor cut",         "antiseptic",       relation="requires")
    G.add_edge("minor cut",         "LOW",              relation="severity_level")

    # ─── Burns ───
    G.add_edge("burn",              "burn_gel",         relation="requires")
    G.add_edge("burn",              "cold pack",        relation="requires")
    G.add_edge("burn",              "apply cold water", relation="treats")
    G.add_edge("burn",              "bandage",          relation="requires")
    G.add_edge("burn",              "HIGH",             relation="severity_level")
    G.add_edge("third degree burn", "burn_gel",         relation="requires")
    G.add_edge("third degree burn", "CRITICAL",         relation="severity_level")

    # ─── Cardiac ───
    G.add_edge("cardiac arrest",    "defibrillator",    relation="requires")
    G.add_edge("cardiac arrest",    "perform CPR",      relation="treats")
    G.add_edge("cardiac arrest",    "oxygen_mask",      relation="requires")
    G.add_edge("cardiac arrest",    "CRITICAL",         relation="severity_level")
    G.add_edge("heart attack",      "oxygen_mask",      relation="requires")
    G.add_edge("heart attack",      "aspirin",          relation="requires")
    G.add_edge("heart attack",      "CRITICAL",         relation="severity_level")

    # ─── Respiratory ───
    G.add_edge("choking",           "perform Heimlich", relation="treats")
    G.add_edge("choking",           "CRITICAL",         relation="severity_level")
    G.add_edge("asthma",            "inhaler",          relation="requires")
    G.add_edge("asthma",            "oxygen_mask",      relation="requires")
    G.add_edge("asthma",            "HIGH",             relation="severity_level")

    # ─── Head Injuries ───
    G.add_edge("head injury",       "bandage",          relation="requires")
    G.add_edge("head injury",       "cervical collar",  relation="requires")
    G.add_edge("head injury",       "immobilize head",  relation="treats")
    G.add_edge("head injury",       "CRITICAL",         relation="severity_level")

    # ─── Hypothermia ───
    G.add_edge("hypothermia",       "blanket",          relation="requires")
    G.add_edge("hypothermia",       "warm patient",     relation="treats")
    G.add_edge("hypothermia",       "HIGH",             relation="severity_level")

    # ─── Situations ───
    G.add_edge("accident",          "stretcher",        relation="requires")
    G.add_edge("accident",          "first aid kit",    relation="requires")

    # ─── Resource alternatives (when primary not available) ───
    G.add_edge("splint",            "wooden plank",     relation="alternative_for")
    G.add_edge("splint",            "rolled newspaper", relation="alternative_for")
    G.add_edge("bandage",           "clean cloth",      relation="alternative_for")
    G.add_edge("gauze",             "clean fabric",     relation="alternative_for")
    G.add_edge("tourniquet",        "belt",             relation="alternative_for")
    G.add_edge("tourniquet",        "rope",             relation="alternative_for")
    G.add_edge("cold pack",         "ice wrapped in cloth", relation="alternative_for")
    G.add_edge("cervical collar",   "rolled towel",     relation="alternative_for")
    G.add_edge("stretcher",         "door plank",       relation="alternative_for")
    G.add_edge("burn_gel",          "cool running water", relation="alternative_for")
    G.add_edge("oxygen_mask",       "supplemental oxygen if available", relation="alternative_for")

    return G


# ── Singleton graph (loaded once) ──
_knowledge_graph: Optional[nx.DiGraph] = None


def get_knowledge_graph() -> nx.DiGraph:
    """Return the singleton knowledge graph, building it if needed."""
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = build_emergency_knowledge_graph()
        print(f"[Knowledge Graph] Built graph: {_knowledge_graph.number_of_nodes()} nodes, "
              f"{_knowledge_graph.number_of_edges()} edges ✓")
    return _knowledge_graph


def find_treatments(injury: str) -> List[str]:
    """Get treatment actions for a given injury."""
    G = get_knowledge_graph()
    injury_lower = injury.lower()

    # Exact match first
    treatments = [
        target for source, target, data in G.edges(data=True)
        if source == injury_lower and data.get("relation") == "treats"
    ]

    # Fuzzy fallback: partial match
    if not treatments:
        treatments = [
            target for source, target, data in G.edges(data=True)
            if any(word in source for word in injury_lower.split())
            and data.get("relation") == "treats"
        ]

    return treatments


def find_required_resources(injury: str) -> List[str]:
    """Get required resources for treating a given injury."""
    G = get_knowledge_graph()
    injury_lower = injury.lower()

    resources = [
        target for source, target, data in G.edges(data=True)
        if source == injury_lower and data.get("relation") == "requires"
        and target not in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    ]

    if not resources:
        # Fuzzy partial match
        resources = [
            target for source, target, data in G.edges(data=True)
            if any(word in source for word in injury_lower.split())
            and data.get("relation") == "requires"
            and target not in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        ]

    return resources


def find_alternatives(resource: str) -> List[str]:
    """Get substitute resources when primary is unavailable."""
    G = get_knowledge_graph()
    return [
        target for source, target, data in G.edges(data=True)
        if source == resource.lower() and data.get("relation") == "alternative_for"
    ]


def run_knowledge_graph_agent(context: Dict, triage: Dict) -> Dict:
    """
    Main knowledge graph agent function.
    Recommends treatments and required resources for the detected injury.

    Args:
        context: Intake agent output (includes 'injury')
        triage: Triage agent output (includes 'severity')

    Returns:
        Dict with recommended treatments, required resources, alternatives
    """
    print("[Knowledge Graph Agent] Querying emergency knowledge graph...")

    injury = context.get("injury", "unspecified injury")
    severity = triage.get("severity", "MEDIUM")

    treatments = find_treatments(injury)
    resources = find_required_resources(injury)

    # Also try the situation for additional resources
    situation = context.get("situation", "")
    situation_resources = find_required_resources(situation)
    all_resources = list(dict.fromkeys(resources + situation_resources))  # deduplicate

    # Build alternatives for each required resource
    resource_alternatives = {
        resource: find_alternatives(resource)
        for resource in all_resources
    }

    kg_result = {
        "injury": injury,
        "severity": severity,
        "recommended_treatments": treatments if treatments else ["Follow standard first aid protocol"],
        "required_resources": all_resources,
        "resource_alternatives": resource_alternatives,
    }

    print(f"[Knowledge Graph Agent] Treatments: {treatments}, Resources: {all_resources}")
    return kg_result
