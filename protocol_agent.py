"""
agents/protocol_agent.py
─────────────────────────
Protocol Agent: Retrieves relevant medical treatment instructions
using offline RAG (FAISS vector search over emergency protocols).

Pipeline:
  1. Load emergency protocol document
  2. Build/load FAISS index
  3. Query with injury + situation
  4. Return top-k most relevant protocol sections
"""

import os
from typing import Dict, List

# Global vector store instance
_vector_store = None
PROTOCOL_PATH = os.path.join(os.path.dirname(__file__), "../data/emergency_protocols.txt")
# Fallback to PDF if exists
PDF_PATH = os.path.join(os.path.dirname(__file__), "../data/emergency_protocols.pdf")


def get_vector_store():
    """
    Return singleton vector store, building it if needed.
    On first call: loads document, chunks it, embeds, and saves to FAISS.
    On subsequent calls: loads from disk cache.
    """
    global _vector_store
    if _vector_store is None:
        from rag.vector_store import build_or_load_vector_store

        # Use PDF if available, otherwise text file
        protocol_path = PDF_PATH if os.path.exists(PDF_PATH) else PROTOCOL_PATH

        if not os.path.exists(protocol_path):
            raise FileNotFoundError(
                f"Emergency protocol document not found at:\n"
                f"  {PDF_PATH}\n  {PROTOCOL_PATH}\n"
                "Please place emergency_protocols.pdf or emergency_protocols.txt in /data/"
            )

        _vector_store = build_or_load_vector_store(protocol_path)
    return _vector_store


def format_protocol_text(chunks: List[Dict], max_length: int = 1500) -> str:
    """
    Format retrieved chunks into clean protocol text.

    Args:
        chunks: List of retrieved chunk dicts with 'text' and 'score'
        max_length: Maximum total character length

    Returns:
        Formatted protocol string
    """
    combined = []
    total_length = 0

    for i, chunk in enumerate(chunks):
        text = chunk["text"].strip()
        score = chunk.get("score", 0)

        if total_length + len(text) > max_length:
            # Truncate last chunk to fit
            remaining = max_length - total_length
            if remaining > 100:
                text = text[:remaining] + "..."
            else:
                break

        combined.append(f"[Relevance: {score:.2f}]\n{text}")
        total_length += len(text)

    return "\n\n---\n\n".join(combined)


def build_search_query(context: Dict) -> str:
    """
    Construct a rich search query from emergency context.
    More specific queries → better retrieval.

    Args:
        context: Intake agent output

    Returns:
        Search query string
    """
    parts = []

    injury = context.get("injury", "")
    situation = context.get("situation", "")
    victim = context.get("victim", "")
    keywords = context.get("keywords", [])

    if injury and injury != "unspecified injury":
        parts.append(f"{injury} treatment protocol")
    if situation and situation != "emergency situation":
        parts.append(situation)
    if victim and victim != "unknown person":
        parts.append(victim)

    # Add top keywords
    parts.extend(keywords[:3])

    query = " ".join(parts)

    # Fallback if all fields are unknown
    if not query.strip():
        query = "emergency first aid treatment"

    return query


def run_protocol_agent(context: Dict, kg_data: Dict) -> Dict:
    """
    Main protocol agent function.
    Retrieves relevant treatment protocol sections via RAG.

    Args:
        context: Intake agent output
        kg_data: Knowledge graph agent output (for resource-aware querying)

    Returns:
        Dict with retrieved protocol text and source metadata
    """
    print("[Protocol Agent] Retrieving treatment protocols via RAG...")

    query = build_search_query(context)
    print(f"[Protocol Agent] Search query: '{query}'")

    try:
        store = get_vector_store()
        results = store.search(query, top_k=3)

        protocol_text = format_protocol_text(results)
        sources = [r.get("metadata", {}) for r in results]

        print(f"[Protocol Agent] Retrieved {len(results)} protocol sections ✓")

        return {
            "query_used": query,
            "protocol_text": protocol_text,
            "num_sources": len(results),
            "sources": sources,
            "top_relevance": results[0]["score"] if results else 0,
        }

    except Exception as e:
        print(f"[Protocol Agent] RAG error: {e}. Using fallback protocol.")
        return {
            "query_used": query,
            "protocol_text": _get_fallback_protocol(context),
            "num_sources": 0,
            "sources": [],
            "top_relevance": 0,
            "error": str(e),
        }


def _get_fallback_protocol(context: Dict) -> str:
    """
    Fallback protocol text when RAG is unavailable.
    Uses hardcoded common protocols.
    """
    injury = context.get("injury", "").lower()

    fallbacks = {
        "fracture": (
            "FRACTURE PROTOCOL:\n"
            "1. Do not move the victim unnecessarily\n"
            "2. Immobilize the fracture with a splint\n"
            "3. Apply cold pack to reduce swelling\n"
            "4. Elevate limb if no spinal injury\n"
            "5. Control any bleeding with bandages\n"
            "6. Monitor circulation below fracture"
        ),
        "bleeding": (
            "BLEEDING PROTOCOL:\n"
            "1. Apply direct pressure with sterile gauze\n"
            "2. Maintain pressure for 10+ minutes\n"
            "3. Do not remove soaked dressings — add more\n"
            "4. Apply tourniquet if pressure fails (limb only)\n"
            "5. Elevate the limb above heart level\n"
            "6. Monitor for signs of shock"
        ),
        "burn": (
            "BURN PROTOCOL:\n"
            "1. Remove from heat source immediately\n"
            "2. Cool with cool running water for 20 minutes\n"
            "3. Do NOT use ice or butter\n"
            "4. Cover loosely with sterile dressing\n"
            "5. Do not burst blisters\n"
            "6. Seek medical attention for severe burns"
        ),
        "cardiac": (
            "CARDIAC ARREST PROTOCOL:\n"
            "1. Check responsiveness\n"
            "2. Call for emergency services\n"
            "3. Begin CPR: 30 compressions + 2 breaths\n"
            "4. Use AED as soon as available\n"
            "5. Continue until help arrives"
        ),
    }

    for key, protocol in fallbacks.items():
        if key in injury:
            return protocol

    return (
        "GENERAL EMERGENCY PROTOCOL:\n"
        "1. Ensure scene safety\n"
        "2. Check victim responsiveness\n"
        "3. Call for emergency services\n"
        "4. Provide appropriate first aid\n"
        "5. Keep victim calm and warm\n"
        "6. Monitor vital signs until help arrives"
    )
