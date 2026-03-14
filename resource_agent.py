"""
agents/resource_agent.py
─────────────────────────
Resource Agent: Matches required medical items against local CSV inventory.

Features:
- Fast pandas-based lookup
- Fuzzy item name matching
- Alternative suggestions from knowledge graph
- Stock availability status
"""

import os
from typing import Dict, List, Optional
import pandas as pd


INVENTORY_PATH = os.path.join(os.path.dirname(__file__), "../data/inventory.csv")

# Global inventory cache
_inventory_df: Optional[pd.DataFrame] = None


def load_inventory() -> pd.DataFrame:
    """
    Load inventory CSV into a pandas DataFrame.
    Cached after first load.

    Returns:
        DataFrame with columns: item, location, quantity, category
    """
    global _inventory_df
    if _inventory_df is None:
        if not os.path.exists(INVENTORY_PATH):
            raise FileNotFoundError(f"Inventory not found: {INVENTORY_PATH}")
        _inventory_df = pd.read_csv(INVENTORY_PATH)
        # Normalize item names for matching
        _inventory_df["item_normalized"] = _inventory_df["item"].str.lower().str.replace("_", " ")
        print(f"[Resource Agent] Loaded inventory: {len(_inventory_df)} items ✓")
    return _inventory_df


def find_item(item_name: str) -> Optional[Dict]:
    """
    Look up an item in the inventory.
    Tries exact match, then partial match.

    Args:
        item_name: Item name to look up

    Returns:
        Dict with item details, or None if not found
    """
    df = load_inventory()
    item_lower = item_name.lower().replace("_", " ")

    # Exact match
    mask = df["item_normalized"] == item_lower
    match = df[mask]

    # Partial match if no exact
    if match.empty:
        mask = df["item_normalized"].str.contains(item_lower, na=False)
        match = df[mask]

    # Reverse partial: item name contains query word
    if match.empty:
        for word in item_lower.split():
            if len(word) > 3:  # skip short words
                mask = df["item_normalized"].str.contains(word, na=False)
                match = df[mask]
                if not match.empty:
                    break

    if match.empty:
        return None

    # Return first match
    row = match.iloc[0]
    return {
        "item": row["item"],
        "location": row["location"],
        "quantity": int(row["quantity"]),
        "category": row.get("category", "general"),
        "available": int(row["quantity"]) > 0,
    }


def check_resource_availability(
    required_resources: List[str],
    resource_alternatives: Dict[str, List[str]],
    victim_analysis: Optional[Dict] = None
) -> List[Dict]:
    """
    Check availability for all required resources.
    Falls back to alternatives if primary not in stock.

    Args:
        required_resources: List of required item names
        resource_alternatives: Dict mapping item → list of substitutes
        victim_analysis: Dict containing calculated resource needs

    Returns:
        List of resource status dicts
    """
    results = []

    for resource in required_resources:
        required_qty = 1
        if victim_analysis:
            # Match item name to keys calculated in multi_victim_detector
            res_key = resource.lower().replace(" ", "_")
            if res_key == "first_aid_kit": res_key = "first_aid_kits"
            elif res_key == "bandage": res_key = "bandages"
            elif res_key == "stretcher": res_key = "stretchers"
            elif res_key == "oxygen_mask": res_key = "oxygen_masks"
            
            required_qty = victim_analysis.get(f"required_{res_key}", 1)

        item_data = find_item(resource)

        if item_data and item_data["available"]:
            # ✅ Primary item available — check for low-stock warning against required amount
            low_stock = item_data["quantity"] < required_qty
            results.append({
                "item": resource,
                "status": "AVAILABLE",
                "location": item_data["location"],
                "quantity": item_data["quantity"],
                "alternative": None,
                "low_stock_warning": low_stock,
                "warning_message": f"⚠️ Low stock warning: only {item_data['quantity']} available for {required_qty} needed" if low_stock else None,
            })
        elif item_data and not item_data["available"]:
            # ⚠️ Item exists but out of stock
            alternatives = resource_alternatives.get(resource, [])
            alt_found = _find_alternative_in_inventory(alternatives)

            results.append({
                "item": resource,
                "status": "OUT_OF_STOCK",
                "location": item_data["location"],
                "quantity": 0,
                "alternative": alt_found,
                "low_stock_warning": False,
                "warning_message": None,
            })
        else:
            # ❌ Item not in inventory at all
            alternatives = resource_alternatives.get(resource, [])
            alt_found = _find_alternative_in_inventory(alternatives)

            results.append({
                "item": resource,
                "status": "NOT_IN_INVENTORY",
                "location": None,
                "quantity": None,
                "alternative": alt_found,
                "low_stock_warning": False,
                "warning_message": None,
            })

    return results


def _find_alternative_in_inventory(alternatives: List[str]) -> Optional[Dict]:
    """
    Check if any alternative item is available in inventory.

    Args:
        alternatives: List of alternative item names

    Returns:
        First available alternative, or None
    """
    for alt in alternatives:
        alt_data = find_item(alt)
        if alt_data and alt_data["available"]:
            return {
                "item": alt,
                "location": alt_data["location"],
                "quantity": alt_data["quantity"],
            }

    # If none found in inventory, return first alternative as improvised option
    if alternatives:
        return {
            "item": alternatives[0],
            "location": "Improvise on site",
            "quantity": "N/A",
        }

    return None


def run_resource_agent(kg_data: Dict, victim_analysis: Optional[Dict] = None) -> Dict:
    """
    Main resource agent function.
    Checks inventory for all knowledge-graph-recommended resources.

    Args:
        kg_data: Knowledge graph agent output with 'required_resources' and 'resource_alternatives'
        victim_analysis: Dictionary containing mathematical estimates of needed quantities

    Returns:
        Dict with resource availability results
    """
    print("[Resource Agent] Checking local inventory...")

    required = kg_data.get("required_resources", [])
    alternatives = kg_data.get("resource_alternatives", {})

    if not required:
        print("[Resource Agent] No specific resources required.")
        return {
            "resources": [],
            "all_available": True,
            "critical_missing": [],
        }

    resource_status = check_resource_availability(required, alternatives, victim_analysis)

    # Summary stats
    available_count = sum(1 for r in resource_status if r["status"] == "AVAILABLE")
    missing = [r for r in resource_status if r["status"] == "NOT_IN_INVENTORY" and not r["alternative"]]
    low_stock_alerts = [r for r in resource_status if r.get("low_stock_warning")]

    if low_stock_alerts:
        for alert in low_stock_alerts:
            print(f"[Resource Agent] ⚠️  LOW STOCK: {alert['item']} — only {alert['quantity']} remaining")

    print(f"[Resource Agent] {available_count}/{len(required)} resources available ✓")

    return {
        "resources": resource_status,
        "all_available": available_count == len(required),
        "available_count": available_count,
        "total_count": len(required),
        "critical_missing": [m["item"] for m in missing],
        "low_stock_alerts": [
            {"item": r["item"], "quantity": r["quantity"], "location": r["location"]}
            for r in low_stock_alerts
        ],
        "has_low_stock": len(low_stock_alerts) > 0,
    }
