"""
command/equipment_dispatch.py
───────────────────────────────
Section 4 — Equipment Dispatch Management

Tracks dispatched and returned equipment per incident.
Automatically deducts from inventory on dispatch and restores on return.

Data files:
  data/dispatched_equipment.csv  — dispatch log
  data/inventory.csv             — live inventory (quantity updated in-place)
"""

import os
import sys
import csv
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

_BASE        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_PATH  = os.path.join(_BASE, "data", "inventory.csv")
DISPATCH_PATH   = os.path.join(_BASE, "data", "dispatched_equipment.csv")

DISPATCH_STATUS_DISPATCHED = "dispatched"
DISPATCH_STATUS_RETURNED   = "returned"

# ── Ensure dispatch CSV exists with correct headers ──
_DISPATCH_HEADERS = ["dispatch_id", "incident_id", "item", "quantity", "status", "dispatched_at", "returned_at"]


def _init_dispatch_file() -> None:
    if not os.path.exists(DISPATCH_PATH):
        os.makedirs(os.path.dirname(DISPATCH_PATH), exist_ok=True)
        with open(DISPATCH_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_DISPATCH_HEADERS)


def _load_inventory() -> pd.DataFrame:
    df = pd.read_csv(INVENTORY_PATH)
    df["item_normalized"] = df["item"].str.lower().str.replace("_", " ")
    return df


def _save_inventory(df: pd.DataFrame) -> None:
    df_save = df.drop(columns=["item_normalized"], errors="ignore")
    df_save.to_csv(INVENTORY_PATH, index=False)


def _load_dispatch_log() -> pd.DataFrame:
    _init_dispatch_file()
    try:
        df = pd.read_csv(DISPATCH_PATH)
        if df.empty:
            return pd.DataFrame(columns=_DISPATCH_HEADERS)
        return df
    except Exception:
        return pd.DataFrame(columns=_DISPATCH_HEADERS)


# ────────────────────────────────────────────────────────────
# Core dispatch operations
# ────────────────────────────────────────────────────────────

def dispatch_equipment(incident_id: str, items: List[Dict]) -> List[Dict]:
    """
    Dispatch a list of items to an incident.

    Args:
        incident_id: Target incident ID
        items: List of {"item": str, "quantity": int} dicts

    Returns:
        List of dispatch result dicts
    """
    _init_dispatch_file()
    inventory = _load_inventory()
    dispatch_log = _load_dispatch_log()
    results = []

    for item_req in items:
        item_name = item_req["item"].lower().replace("_", " ")
        qty_needed = int(item_req.get("quantity", 1))

        # Find item in inventory
        mask = inventory["item_normalized"] == item_name
        if not mask.any():
            # Try partial match
            mask = inventory["item_normalized"].str.contains(item_name.split()[0], na=False)

        if not mask.any():
            results.append({
                "item": item_req["item"], "status": "NOT_IN_INVENTORY",
                "dispatched": 0
            })
            continue

        idx = inventory[mask].index[0]
        available = int(inventory.at[idx, "quantity"])

        if available <= 0:
            results.append({
                "item": item_req["item"], "status": "OUT_OF_STOCK",
                "dispatched": 0
            })
            continue

        qty_dispatched = min(qty_needed, available)
        inventory.at[idx, "quantity"] = available - qty_dispatched

        dispatch_id = f"DISP-{len(dispatch_log)+1:05d}"
        new_row = {
            "dispatch_id":   dispatch_id,
            "incident_id":   incident_id,
            "item":          inventory.at[idx, "item"],
            "quantity":      qty_dispatched,
            "status":        DISPATCH_STATUS_DISPATCHED,
            "dispatched_at": datetime.now().isoformat(timespec="seconds"),
            "returned_at":   "",
        }
        dispatch_log = pd.concat([dispatch_log, pd.DataFrame([new_row])], ignore_index=True)

        results.append({
            "item": item_req["item"], "status": "DISPATCHED",
            "dispatched": qty_dispatched,
            "dispatch_id": dispatch_id,
            "new_stock": available - qty_dispatched,
        })
        print(f"[Equipment Dispatch] {item_req['item']} x{qty_dispatched} → {incident_id}")

    _save_inventory(inventory)
    dispatch_log.to_csv(DISPATCH_PATH, index=False)
    return results


def return_equipment(dispatch_id: str) -> bool:
    """
    Return equipment from a dispatch record back to inventory.

    Args:
        dispatch_id: The dispatch record to return

    Returns:
        True if successful
    """
    dispatch_log = _load_dispatch_log()
    inventory    = _load_inventory()

    mask = dispatch_log["dispatch_id"] == dispatch_id
    if not mask.any():
        print(f"[Equipment Dispatch] Dispatch ID {dispatch_id} not found")
        return False

    idx = dispatch_log[mask].index[0]
    if dispatch_log.at[idx, "status"] == DISPATCH_STATUS_RETURNED:
        print(f"[Equipment Dispatch] {dispatch_id} already returned")
        return False

    item_name = dispatch_log.at[idx, "item"]
    qty       = int(dispatch_log.at[idx, "quantity"])

    # Restore to inventory
    inv_mask = inventory["item"] == item_name
    if inv_mask.any():
        inv_idx = inventory[inv_mask].index[0]
        inventory.at[inv_idx, "quantity"] += qty
        print(f"[Equipment Dispatch] Returned {item_name} x{qty} to inventory ✓")

    dispatch_log.at[idx, "status"]      = DISPATCH_STATUS_RETURNED
    dispatch_log.at[idx, "returned_at"] = datetime.now().isoformat(timespec="seconds")

    _save_inventory(inventory)
    dispatch_log.to_csv(DISPATCH_PATH, index=False)
    return True


def get_dispatch_log(incident_id: Optional[str] = None) -> List[Dict]:
    """Return dispatch records, optionally filtered by incident."""
    log = _load_dispatch_log()
    if incident_id:
        log = log[log["incident_id"] == incident_id]
    return log.to_dict("records")


def get_inventory_snapshot() -> List[Dict]:
    """Return current inventory as list of dicts."""
    df = _load_inventory()
    df["low_stock"] = df["quantity"] <= 2
    return df.drop(columns=["item_normalized"], errors="ignore").to_dict("records")


def get_low_stock_items(threshold: int = 2) -> List[Dict]:
    """Return items with quantity at or below threshold."""
    df = _load_inventory()
    return df[df["quantity"] <= threshold].to_dict("records")
