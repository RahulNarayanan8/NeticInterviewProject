from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class Appointment:
    addr: str
    start_time: datetime
    end_time: datetime
    appointment_type: str
    tech_id: int
    customer_id: int


@dataclass
class Technician:
    id: int
    name: str
    skills: List[str]        # from business_units (stored lowercase)
    zips: List[str]          # from zones
    appointments: List[Appointment] = field(default_factory=list)


def appointment_to_dict(appt: Appointment) -> dict:
    return {
        "addr": appt.addr,
        "start_time": appt.start_time.isoformat(),
        "end_time": appt.end_time.isoformat(),
        "appointment_type": appt.appointment_type,
        "tech_id": appt.tech_id,
        "customer_id": appt.customer_id,
    }


def dict_to_appointment(d: dict) -> Appointment:
    return Appointment(
        addr=d["addr"],
        start_time=datetime.fromisoformat(d["start_time"]),
        end_time=datetime.fromisoformat(d["end_time"]),
        appointment_type=d["appointment_type"],
        tech_id=d["tech_id"],
        customer_id=d["customer_id"],
    )
