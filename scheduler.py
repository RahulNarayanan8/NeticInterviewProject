from datetime import datetime, time
from typing import List, Optional

from models import Appointment, Technician, appointment_to_dict, dict_to_appointment
import storage


def extract_zip(address: str) -> str:
    return address.strip().split(",")[-1].strip()


def build_technicians(data: dict, appointments: List[dict]) -> List[Technician]:
    """Hydrate Technician objects from JSON profiles merged with saved appointments."""
    techs = []
    for profile in data["Technician_Profiles"]:
        tech = Technician(
            id=profile["id"],
            name=profile["name"],
            skills=[s.lower() for s in profile["business_units"]],
            zips=profile["zones"],
        )
        # Attach appointments belonging to this tech
        for appt_dict in appointments:
            if appt_dict["tech_id"] == tech.id:
                tech.appointments.append(dict_to_appointment(appt_dict))
        techs.append(tech)
    return techs


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def score_technician(tech: Technician, start: datetime, end: datetime) -> int:
    same_day = sorted(
        [a for a in tech.appointments if a.start_time.date() == start.date()],
        key=lambda a: a.start_time,
    )
    prev_appts = [a for a in same_day if a.end_time <= start]
    next_appts = [a for a in same_day if a.start_time >= end]
    ref_start = datetime.combine(start.date(), time(6, 0))
    ref_end = datetime.combine(start.date(), time(23, 59))
    gap_before = (
        (start - prev_appts[-1].end_time).seconds // 60
        if prev_appts
        else (start - ref_start).seconds // 60
    )
    gap_after = (
        (next_appts[0].start_time - end).seconds // 60
        if next_appts
        else (ref_end - end).seconds // 60
    )
    return gap_before + gap_after


def find_technician(
    technicians: List[Technician],
    zip_code: str,
    skill: str,
    start: datetime,
    end: datetime,
) -> Optional[Technician]:
    """
    1. Filter by zip and skill.
    2. Filter out techs with conflicting appointments.
    3. Score by load-spreading (gap_before + gap_after).
    4. Return highest-scoring tech or None.
    """
    skill_lower = skill.lower()
    candidates = [
        t for t in technicians
        if zip_code in t.zips and skill_lower in t.skills
    ]
    available = [
        t for t in candidates
        if not any(overlaps(start, end, a.start_time, a.end_time) for a in t.appointments)
    ]
    if not available:
        return None
    return max(available, key=lambda t: score_technician(t, start, end))


def schedule_appointment(tech: Technician, appt: Appointment) -> Appointment:
    """Save the appointment to storage and add to tech's in-memory list."""
    storage.save_appointment(appointment_to_dict(appt))
    tech.appointments.append(appt)
    return appt
