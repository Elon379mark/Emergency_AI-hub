import re

LOCATION_PATTERNS = [
    r"near ([A-Za-z0-9\s]+)",
    r"at ([A-Za-z0-9\s]+)",
    r"in ([A-Za-z0-9\s]+)",
    r"beside ([A-Za-z0-9\s]+)",
    r"opposite ([A-Za-z0-9\s]+)",
]

def extract_location(text: str):
    text = text.lower()

    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    return None