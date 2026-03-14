"""
utils/geocoder.py
─────────────────
Hybrid geocoding utility for Disaster Command Center.

Features
- Extract location phrases from natural language reports
- Detect direct coordinates (lat, lon)
- Offline landmark lookup with fuzzy matching
- Online geocoding fallback via Nominatim
"""

import re
from difflib import get_close_matches
from typing import Optional, Tuple

from geopy.geocoders import Nominatim
from geopy.exc import GeopyError


# ─────────────────────────────────────────
# Geolocator instance (shared)
# ─────────────────────────────────────────

_geopy_instance = Nominatim(user_agent="disaster_command_center_v4")


# ─────────────────────────────────────────
# Local landmark database (offline)
# Add more district landmarks here
# ─────────────────────────────────────────

LOCAL_LANDMARKS = {
    "mg road": (12.9767, 77.5993),
    "vidhana soudha": (12.9796, 77.5912),
    "majestic": (12.9772, 77.5707),
    "bangalore airport": (13.1986, 77.7066),
    "kia": (13.1986, 77.7066),
    "gateway of india": (18.9220, 72.8347),
    "victoria memorial": (22.5448, 88.3425),
    "india gate": (28.6129, 77.2295),
}


# ─────────────────────────────────────────
# Extract location phrase from sentence
# Example:
# "bus accident near mg road" → "mg road"
# ─────────────────────────────────────────

def extract_location(text: str) -> str:

    if not text:
        return ""

    patterns = [
        r"near ([A-Za-z0-9\s]+)",
        r"at ([A-Za-z0-9\s]+)",
        r"in ([A-Za-z0-9\s]+)",
        r"beside ([A-Za-z0-9\s]+)",
        r"opposite ([A-Za-z0-9\s]+)",
    ]

    lower_text = text.lower()

    for pattern in patterns:
        match = re.search(pattern, lower_text)
        if match:
            return match.group(1).strip()

    return text.strip()


# ─────────────────────────────────────────
# Try coordinate detection
# Example:
# "12.97, 77.59"
# ─────────────────────────────────────────

def try_parse_coordinates(text: str) -> Optional[Tuple[float, float]]:

    coord_match = re.search(
        r"([-+]?\d*\.\d+|\d+)\s*[,\s]\s*([-+]?\d*\.\d+|\d+)",
        text
    )

    if coord_match:
        try:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))

            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return lat, lon

        except ValueError:
            pass

    return None


# ─────────────────────────────────────────
# Offline landmark matching
# ─────────────────────────────────────────

def try_landmark_match(text: str) -> Optional[Tuple[float, float]]:

    clean = text.lower().strip()

    # Exact substring match
    for landmark, coords in LOCAL_LANDMARKS.items():
        if landmark in clean:
            return coords

    # Fuzzy matching
    match = get_close_matches(clean, LOCAL_LANDMARKS.keys(), n=1, cutoff=0.6)

    if match:
        return LOCAL_LANDMARKS[match[0]]

    return None


# ─────────────────────────────────────────
# Main geocode function
# ─────────────────────────────────────────

def geocode_location(text: str) -> Optional[Tuple[float, float]]:
    """
    Hybrid geocoder

    Flow:
    1. Extract location phrase from sentence
    2. Try coordinate parsing
    3. Try offline landmark match
    4. Fallback to online geocoding
    """

    if not text:
        return None

    # Extract location phrase from sentence
    location_text = extract_location(text)

    # 1️⃣ Coordinates
    coords = try_parse_coordinates(location_text)
    if coords:
        return coords

    # 2️⃣ Offline landmarks
    landmark_coords = try_landmark_match(location_text)
    if landmark_coords:
        return landmark_coords

    # 3️⃣ Online geocoding fallback
    try:

        query = (
            location_text
            if "india" in location_text.lower()
            else f"{location_text}, India"
        )

        location = _geopy_instance.geocode(
            query,
            timeout=5,
            country_codes="in"
        )

        if location:
            return location.latitude, location.longitude

    except (GeopyError, Exception) as e:
        print(f"[Geocoder] Online geocoding failed: {e}")

    return None