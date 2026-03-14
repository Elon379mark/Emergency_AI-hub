"""
command/location_cluster.py
─────────────────────────────
Section 5 — Location Clustering Optimisation

Merges nearby incidents into clusters to optimise team dispatch.

Clustering Algorithm:
  1. Compare every pair of incidents
  2. Two incidents merge if:
       a) location strings are identical/very similar (fuzzy match ≥ 0.75), OR
       b) Haversine distance < CLUSTER_RADIUS_METRES
  3. Build connected components (Union-Find) from merge pairs
  4. Each component becomes one cluster

Cluster fields:
  cluster_id, incident_ids, location, number_of_requests,
  combined_priority, combined_resources
"""

import os
import json
import re
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLUSTER_PATH = os.path.join(_BASE, "data", "clusters.json")

CLUSTER_RADIUS_METRES = 200.0   # merge if within 200 m
FUZZY_MATCH_THRESHOLD = 0.75    # Jaccard similarity threshold

PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}


# ────────────────────────────────────────────────────────────
# String similarity (Jaccard on word sets — no external deps)
# ────────────────────────────────────────────────────────────

def _jaccard_similarity(a: str, b: str) -> float:
    """Compute word-level Jaccard similarity between two strings."""
    def normalise(s: str):
        return set(re.sub(r"[^a-z0-9 ]", "", s.lower()).split())

    set_a = normalise(a)
    set_b = normalise(b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union        = set_a | set_b
    return len(intersection) / len(union)


# ────────────────────────────────────────────────────────────
# Haversine distance (reused from responder_manager pattern)
# ────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.asin(math.sqrt(a))


# ────────────────────────────────────────────────────────────
# Union-Find for connected components
# ────────────────────────────────────────────────────────────

class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])   # path compression
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


# ────────────────────────────────────────────────────────────
# Clustering logic
# ────────────────────────────────────────────────────────────

def _should_merge(inc_a: Dict, inc_b: Dict) -> bool:
    """
    Decide whether two incidents should be merged into one cluster.

    Merges if:
      (1) Location strings are sufficiently similar (Jaccard ≥ threshold), OR
      (2) GPS coordinates are within CLUSTER_RADIUS_METRES
    """
    loc_a = inc_a.get("location", "")
    loc_b = inc_b.get("location", "")

    # Condition 1: location name similarity
    if loc_a and loc_b:
        sim = _jaccard_similarity(loc_a, loc_b)
        if sim >= FUZZY_MATCH_THRESHOLD:
            return True

    # Condition 2: GPS proximity (only if both have coordinates)
    lat_a = inc_a.get("lat")
    lon_a = inc_a.get("lon")
    lat_b = inc_b.get("lat")
    lon_b = inc_b.get("lon")
    if all(v is not None for v in [lat_a, lon_a, lat_b, lon_b]):
        dist = _haversine(lat_a, lon_a, lat_b, lon_b)
        if dist < CLUSTER_RADIUS_METRES:
            return True

    return False


def _highest_priority(incidents: List[Dict]) -> str:
    """Return the highest severity among a list of incidents."""
    best = max(incidents, key=lambda i: PRIORITY_ORDER.get(i.get("severity", "LOW"), 0))
    return best.get("severity", "LOW")


def _combine_resources(incidents: List[Dict]) -> List[str]:
    """Merge resource lists from all incidents in a cluster."""
    combined = set()
    for inc in incidents:
        for r in inc.get("resources_needed", []):
            combined.add(r)
    return list(combined)


def build_clusters(incidents: List[Dict]) -> List[Dict]:
    """
    Build clusters from a list of incidents using Union-Find.

    Args:
        incidents: List of incident dicts (from incident_manager)

    Returns:
        List of cluster dicts
    """
    n = len(incidents)
    if n == 0:
        return []

    uf = UnionFind(n)

    # Compare all pairs O(n²) — acceptable for emergency scale (n < 1000)
    for i in range(n):
        for j in range(i + 1, n):
            if _should_merge(incidents[i], incidents[j]):
                uf.union(i, j)

    # Group incidents by component root
    components: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        components.setdefault(root, []).append(i)

    clusters = []
    for cluster_idx, (root, member_indices) in enumerate(components.items()):
        members = [incidents[i] for i in member_indices]
        cluster = {
            "cluster_id":          f"CLU-{cluster_idx+1:04d}",
            "incident_ids":        [m["incident_id"] for m in members],
            "location":            members[0].get("location", "unknown"),
            "number_of_requests":  len(members),
            "combined_priority":   _highest_priority(members),
            "combined_resources":  _combine_resources(members),
            "total_victims":       sum(m.get("victim_count", 1) for m in members),
            "created_at":          datetime.now().isoformat(timespec="seconds"),
        }
        clusters.append(cluster)

    # Sort clusters: highest combined priority first
    clusters.sort(key=lambda c: PRIORITY_ORDER.get(c["combined_priority"], 0), reverse=True)

    # Persist
    os.makedirs(os.path.dirname(CLUSTER_PATH), exist_ok=True)
    with open(CLUSTER_PATH, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=2, default=str)

    print(f"[Location Cluster] Built {len(clusters)} clusters from {n} incidents")
    return clusters


def get_clusters() -> List[Dict]:
    if not os.path.exists(CLUSTER_PATH):
        return []
    try:
        with open(CLUSTER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []
