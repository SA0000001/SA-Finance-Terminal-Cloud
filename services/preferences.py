from __future__ import annotations

import json
from pathlib import Path

PREFERENCES_PATH = Path(__file__).resolve().parents[1] / ".local_state" / "preferences.json"
DEFAULT_PREFERENCES = {
    "view_mode": "Pro",
    "pinned_metrics": ["BTC_P", "BTC_C", "FNG", "FR", "VIX", "ETF_FLOW_TOTAL"],
    "thresholds": {
        "funding_above": 0.01,
        "vix_above": 25.0,
        "etf_flow_below": 0.0,
    },
    "report_depth": "Orta",
}


def load_preferences() -> dict:
    if not PREFERENCES_PATH.exists():
        return dict(DEFAULT_PREFERENCES)
    try:
        stored = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_PREFERENCES)

    preferences = dict(DEFAULT_PREFERENCES)
    preferences.update({key: value for key, value in stored.items() if key != "thresholds"})
    thresholds = dict(DEFAULT_PREFERENCES["thresholds"])
    thresholds.update(stored.get("thresholds", {}))
    preferences["thresholds"] = thresholds
    return preferences


def save_preferences(preferences: dict):
    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFERENCES_PATH.write_text(json.dumps(preferences, ensure_ascii=True, indent=2), encoding="utf-8")
