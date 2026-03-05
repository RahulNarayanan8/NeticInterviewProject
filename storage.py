import json
import threading
from pathlib import Path
from typing import List

DATA_PATH = Path(__file__).parent / "data" / "data.json"
APPOINTMENTS_PATH = Path(__file__).parent / "data" / "appointments.json"

_lock = threading.Lock()


def init():
    """Create appointments.json as [] if it doesn't exist."""
    APPOINTMENTS_PATH.parent.mkdir(exist_ok=True)
    if not APPOINTMENTS_PATH.exists():
        APPOINTMENTS_PATH.write_text("[]")


def load_data() -> dict:
    """Return raw data.json dict."""
    with open(DATA_PATH) as f:
        return json.load(f)


def load_appointments() -> List[dict]:
    """Return list of appointment dicts from appointments.json."""
    with _lock:
        with open(APPOINTMENTS_PATH) as f:
            return json.load(f)


def save_appointment(appt_dict: dict) -> None:
    """Append a new appointment dict to appointments.json."""
    with _lock:
        with open(APPOINTMENTS_PATH) as f:
            appointments = json.load(f)
        appointments.append(appt_dict)
        with open(APPOINTMENTS_PATH, "w") as f:
            json.dump(appointments, f, indent=2)
