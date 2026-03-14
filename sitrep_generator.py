"""
command/sitrep_generator.py
─────────────────────────────
Section 14 — Situation Report Generation
Section 16 — Resource Prediction / Inventory Depletion Forecasting

Situation Report:
  Aggregates all incident data into a formatted summary.
  Auto-generated every 10 minutes (Streamlit timer) or on demand.

Resource Prediction:
  Tracks consumption rate of each inventory item and predicts
  when stock will run out.

  Depletion model:
    rate = items_dispatched / time_elapsed_minutes
    time_to_depletion = current_stock / rate (minutes)
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ────────────────────────────────────────────────────────────
# Section 14 — Situation Report
# ────────────────────────────────────────────────────────────

def generate_sitrep() -> Dict:
    """
    Generate a complete situation report from all incident and resource data.

    Returns:
        Sitrep dict with summary text and structured stats
    """
    from command.incident_manager import get_stats, get_sorted_queue
    from command.equipment_dispatch import get_inventory_snapshot, get_low_stock_items
    from command.responder_manager import get_all_teams, get_available_teams

    stats      = get_stats()
    queue      = get_sorted_queue()
    inventory  = get_inventory_snapshot()
    low_stock  = get_low_stock_items()
    teams      = get_all_teams()
    avail_teams = get_available_teams()

    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build summary text
    lines = [
        "=" * 55,
        "📋  SITUATION REPORT",
        f"    Generated: {timestamp}",
        "=" * 55,
        f"",
        f"  INCIDENT SUMMARY",
        f"  ─────────────────────────────",
        f"  Total Incidents  : {stats['total']}",
        f"  🔴 Critical       : {stats['critical']}",
        f"  🟠 High           : {stats['high']}",
        f"  🟡 Medium         : {stats['medium']}",
        f"  🟢 Low            : {stats['low']}",
        f"  ─────────────────────────────",
        f"  ⏳ Pending        : {stats['pending']}",
        f"  🚑 Assigned       : {stats['assigned']}",
        f"  ✅ Resolved       : {stats['resolved']}",
        f"",
        f"  RESPONDER STATUS",
        f"  ─────────────────────────────",
        f"  Total Teams      : {len(teams)}",
        f"  Available        : {len(avail_teams)}",
        f"  Deployed         : {len(teams) - len(avail_teams)}",
    ]

    if low_stock:
        lines += [
            f"",
            f"  ⚠️  LOW STOCK ALERTS",
            f"  ─────────────────────────────",
        ]
        for item in low_stock:
            lines.append(f"  {item['item']:<20} Qty: {item['quantity']}")

    # Top 3 active incidents
    active = [i for i in queue if i.get("status") != "resolved"][:3]
    if active:
        lines += [f"", f"  TOP PRIORITY INCIDENTS", f"  ─────────────────────────────"]
        for inc in active:
            lines.append(
                f"  [{inc['severity']:<8}] {inc['incident_id']} — "
                f"{inc['injury'][:25]} @ {inc['location'][:20]}"
            )

    lines.append("=" * 55)
    summary_text = "\n".join(lines)

    return {
        "timestamp":          timestamp,
        "summary":            summary_text,
        "stats":              stats,
        "low_stock_items":    [i["item"] for i in low_stock],
        "available_teams":    len(avail_teams),
        "top_incidents":      active,
    }


# ────────────────────────────────────────────────────────────
# Section 16 — Resource Prediction
# ────────────────────────────────────────────────────────────

def predict_resource_depletion(window_minutes: int = 60) -> List[Dict]:
    """
    Predict when each inventory item will run out based on dispatch rate.

    Algorithm:
      1. Load dispatch log — filter to last `window_minutes` minutes
      2. Count total dispatched quantity per item
      3. Rate = total_dispatched / window_minutes (units per minute)
      4. Depletion time = current_stock / rate
      5. Flag items that will deplete within 30 minutes

    Args:
        window_minutes: Historical window for rate calculation (default 60 min)

    Returns:
        List of prediction dicts per item
    """
    dispatch_path   = os.path.join(_BASE, "data", "dispatched_equipment.csv")
    inventory_path  = os.path.join(_BASE, "data", "inventory.csv")

    # Load current inventory
    if not os.path.exists(inventory_path):
        return []
    inventory = pd.read_csv(inventory_path)

    predictions = []

    # Load dispatch log if exists
    if os.path.exists(dispatch_path):
        try:
            dispatch_log = pd.read_csv(dispatch_path)
            if not dispatch_log.empty and "dispatched_at" in dispatch_log.columns:
                dispatch_log["dispatched_at"] = pd.to_datetime(
                    dispatch_log["dispatched_at"], errors="coerce"
                )
                cutoff = datetime.now() - timedelta(minutes=window_minutes)
                recent = dispatch_log[
                    (dispatch_log["dispatched_at"] >= cutoff) &
                    (dispatch_log["status"] == "dispatched")
                ]
            else:
                recent = pd.DataFrame()
        except Exception:
            recent = pd.DataFrame()
    else:
        recent = pd.DataFrame()

    for _, row in inventory.iterrows():
        item_name    = row["item"]
        current_qty  = int(row.get("quantity", 0))

        # Calculate dispatch rate for this item
        if not recent.empty and "item" in recent.columns:
            item_dispatched = recent[recent["item"] == item_name]["quantity"].sum()
        else:
            item_dispatched = 0

        rate_per_min = item_dispatched / window_minutes if window_minutes > 0 else 0

        if rate_per_min > 0:
            time_to_depletion = current_qty / rate_per_min
        else:
            time_to_depletion = float("inf")   # not being used

        # Classify depletion urgency
        if time_to_depletion == float("inf"):
            depletion_label = "Stable"
            urgent = False
        elif time_to_depletion <= 10:
            depletion_label = f"⚠️  Depletes in ~{time_to_depletion:.0f} min"
            urgent = True
        elif time_to_depletion <= 30:
            depletion_label = f"⚡ Depletes in ~{time_to_depletion:.0f} min"
            urgent = True
        elif time_to_depletion <= 60:
            depletion_label = f"📦 Depletes in ~{time_to_depletion:.0f} min"
            urgent = False
        else:
            depletion_label = "Stable"
            urgent = False

        predictions.append({
            "item":                item_name,
            "current_qty":         current_qty,
            "dispatch_rate_per_min": round(rate_per_min, 3),
            "dispatched_last_hour": int(item_dispatched),
            "time_to_depletion_min": round(time_to_depletion, 1) if time_to_depletion != float("inf") else None,
            "depletion_label":     depletion_label,
            "urgent":              urgent,
            "location":            row.get("location", ""),
        })

    # Sort: urgent items first, then by lowest quantity
    predictions.sort(key=lambda x: (not x["urgent"], x["current_qty"]))
    return predictions
