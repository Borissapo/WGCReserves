import json
import os
from datetime import datetime, timezone
from typing import Tuple, Optional

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state.json")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_state(data: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def has_changed(country: str, new_tonnes: float) -> Tuple[bool, Optional[float]]:
    """Compare new gold tonnes against stored state.

    Returns:
        (changed: bool, old_tonnes: float | None)
        old_tonnes is None when the country has no prior record.
    """
    state = load_state()
    record = state.get(country)

    if record is None:
        return True, None

    old_tonnes = record.get("gold_tonnes")
    if old_tonnes is None:
        return True, None

    if float(new_tonnes) != float(old_tonnes):
        return True, float(old_tonnes)

    return False, float(old_tonnes)


def update_country(country: str, gold_tonnes: float, report_date: str) -> None:
    """Persist a single country's latest reading into state.json."""
    state = load_state()
    state[country] = {
        "gold_tonnes": gold_tonnes,
        "date": report_date,
        "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_state(state)
