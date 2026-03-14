"""
maps/offline_routing.py
─────────────────────────
Section 6 — Offline Map Routing

Computes road-network distances and travel times without internet.

Architecture:
  1. Download OSM data with osmnx (ONE-TIME, while internet available)
  2. Save as compressed GraphML file locally
  3. At runtime: load graph, run Dijkstra shortest path via NetworkX
  4. Estimate travel time from path length and average speed

Libraries: osmnx, networkx (both CPU-only)

OFFLINE OPERATION:
  - After first download, the map file (maps/city_graph.graphml.gz)
    is the only file needed — no internet required.
  - If osmnx is unavailable, falls back to Haversine straight-line distance.
"""

import os
import math
from typing import Dict, List, Optional, Tuple

_BASE      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPS_DIR   = os.path.join(_BASE, "maps")
MAP_FILE   = os.path.join(MAPS_DIR, "city_graph.graphml.gz")

# Average speeds in km/h for travel time estimation
SPEED_EMERGENCY_KMH = 50.0    # emergency vehicle on urban roads
SPEED_WALKING_KMH   = 5.0

# Import osmnx/networkx with graceful fallback
try:
    import osmnx as ox
    import networkx as nx
    OSMNX_AVAILABLE = True
except ImportError:
    OSMNX_AVAILABLE = False


# ────────────────────────────────────────────────────────────
# Map download (run once while internet is available)
# ────────────────────────────────────────────────────────────

def download_map(place_name: str = "Karnataka, India", network_type: str = "drive") -> bool:
    """
    Download road network for a city and save locally.

    Call this ONCE before going offline:
      python -c "from maps.offline_routing import download_map; download_map('Your City, Country')"

    Args:
        place_name:   City/region to download (OpenStreetMap geocoder)
        network_type: "drive" (roads), "walk", or "all"

    Returns:
        True if successful
    """
    if not OSMNX_AVAILABLE:
        print("[Offline Routing] osmnx not installed. Run: pip install osmnx")
        return False

    os.makedirs(MAPS_DIR, exist_ok=True)
    print(f"[Offline Routing] Downloading map: {place_name} (type={network_type})...")
    try:
        G = ox.graph_from_place(place_name, network_type=network_type)
        ox.save_graphml(G, MAP_FILE)
        print(f"[Offline Routing] Map saved → {MAP_FILE} ✓")
        return True
    except Exception as e:
        print(f"[Offline Routing] Download failed: {e}")
        return False


def load_map() -> Optional[object]:
    """
    Load the locally stored road graph.

    Returns:
        NetworkX DiGraph or None if map not available
    """
    if not OSMNX_AVAILABLE:
        return None
    if not os.path.exists(MAP_FILE):
        print(f"[Offline Routing] Map file not found at {MAP_FILE}")
        print("[Offline Routing] Run download_map() once while online to prepare offline maps.")
        return None
    try:
        G = ox.load_graphml(MAP_FILE)
        print(f"[Offline Routing] Map loaded: {len(G.nodes)} nodes, {len(G.edges)} edges ✓")
        return G
    except Exception as e:
        print(f"[Offline Routing] Failed to load map: {e}")
        return None


# ────────────────────────────────────────────────────────────
# Route computation
# ────────────────────────────────────────────────────────────

# Global graph cache (load once per session)
_graph_cache = None


def _get_graph():
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = load_map()
    return _graph_cache


def compute_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    speed_kmh: float = SPEED_EMERGENCY_KMH,
) -> Dict:
    """
    Compute shortest road route between two GPS coordinates.

    Uses Dijkstra on road graph if available,
    falls back to Haversine great-circle distance otherwise.

    Args:
        origin_lat, origin_lon: Start coordinates
        dest_lat, dest_lon:     Destination coordinates
        speed_kmh:              Travel speed for time estimate

    Returns:
        Route dict with distance_m, time_minutes, method, path_nodes
    """
    G = _get_graph()

    if G is not None and OSMNX_AVAILABLE:
        try:
            import networkx as nx
            import osmnx as ox

            # Snap coordinates to nearest graph nodes
            orig_node = ox.nearest_nodes(G, origin_lon, origin_lat)
            dest_node = ox.nearest_nodes(G, dest_lon, dest_lat)

            # Dijkstra shortest path (weight=length in metres)
            route_nodes = nx.shortest_path(G, orig_node, dest_node, weight="length")
            route_edges = ox.routing.route_to_gdf(G, route_nodes)
            distance_m  = float(route_edges["length"].sum())
            time_min    = (distance_m / 1000.0) / speed_kmh * 60.0

            return {
                "distance_m":    round(distance_m, 1),
                "distance_km":   round(distance_m / 1000, 2),
                "time_minutes":  round(time_min, 1),
                "method":        "road_graph",
                "path_nodes":    route_nodes,
                "waypoints":     len(route_nodes),
            }
        except Exception as e:
            print(f"[Offline Routing] Graph routing failed: {e}, using Haversine fallback")

    # ── Fallback: straight-line Haversine ──
    R = 6_371_000.0
    phi1, phi2 = math.radians(origin_lat), math.radians(dest_lat)
    dphi   = math.radians(dest_lat - origin_lat)
    dlambda = math.radians(dest_lon - origin_lon)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    distance_m = 2 * R * math.asin(math.sqrt(a))
    # Add 30% for road detour factor
    distance_m *= 1.3
    time_min = (distance_m / 1000.0) / speed_kmh * 60.0

    return {
        "distance_m":   round(distance_m, 1),
        "distance_km":  round(distance_m / 1000, 2),
        "time_minutes": round(time_min, 1),
        "method":       "haversine_estimate",
        "path_nodes":   [],
        "waypoints":    0,
    }


def get_nearest_team_route(incident: Dict, teams: List[Dict]) -> List[Dict]:
    """
    Compute routes from all available teams to an incident.

    Args:
        incident: Incident dict with optional lat/lon
        teams:    List of team dicts with lat/lon

    Returns:
        List of {"team_id", "route"} dicts sorted by travel time
    """
    inc_lat = incident.get("lat", 0.0)
    inc_lon = incident.get("lon", 0.0)

    routes = []
    for team in teams:
        route = compute_route(team["lat"], team["lon"], inc_lat, inc_lon)
        routes.append({
            "team_id":      team["team_id"],
            "team_name":    team.get("name", team["team_id"]),
            "route":        route,
            "travel_time":  route["time_minutes"],
        })

    routes.sort(key=lambda x: x["travel_time"])
    return routes
