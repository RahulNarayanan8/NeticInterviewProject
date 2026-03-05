"""Tests for scheduler.py — the core scheduling / dispatching logic."""
import json
import pytest
from datetime import datetime, date, time
from unittest.mock import patch, MagicMock

from models import Appointment, Technician
import scheduler
from scheduler import (
    extract_zip,
    build_technicians,
    overlaps,
    score_technician,
    find_technician,
    schedule_appointment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DAY = date(2026, 3, 10)


def dt(h, m=0, d=DAY):
    return datetime.combine(d, time(h, m))


def make_appt(start_h, end_h, tech_id=1, customer_id=99, addr="123 St", svc="plumbing", day=DAY):
    return Appointment(
        addr=addr,
        start_time=dt(start_h, d=day),
        end_time=dt(end_h, d=day),
        appointment_type=svc,
        tech_id=tech_id,
        customer_id=customer_id,
    )


def make_tech(id=1, name="Tech", skills=None, zips=None, appointments=None):
    return Technician(
        id=id,
        name=name,
        skills=skills or ["plumbing"],
        zips=zips or ["94111"],
        appointments=appointments or [],
    )


SAMPLE_DATA = {
    "Technician_Profiles": [
        {"id": 8886, "name": "Tina Orozco",  "zones": ["94133", "94119"], "business_units": ["plumbing", "hvac"]},
        {"id": 2564, "name": "Gregory Chen", "zones": ["94107", "94106"], "business_units": ["electrical", "plumbing"]},
        {"id": 4697, "name": "Michael Page", "zones": ["94115", "94117", "94111", "94133"], "business_units": ["plumbing", "electrical"]},
    ],
    "Customer_Profiles": [],
    "Location_Profiles": [],
}


# ---------------------------------------------------------------------------
# extract_zip
# ---------------------------------------------------------------------------

class TestExtractZip:
    def test_standard_sf_address(self):
        assert extract_zip("876 Paul Vista Apt. 335, San Francisco, CA, 94115") == "94115"

    def test_short_address(self):
        assert extract_zip("123 Main, CA, 94101") == "94101"

    def test_leading_trailing_whitespace(self):
        assert extract_zip("  123 St, SF, CA, 94107  ") == "94107"

    def test_zip_with_internal_spaces(self):
        # last token after comma split
        assert extract_zip("address, CA,  94133 ") == "94133"

    def test_no_comma_returns_whole_string(self):
        assert extract_zip("94999") == "94999"


# ---------------------------------------------------------------------------
# build_technicians
# ---------------------------------------------------------------------------

class TestBuildTechnicians:
    def test_returns_correct_count(self):
        techs = build_technicians(SAMPLE_DATA, [])
        assert len(techs) == 3

    def test_skills_lowercased(self):
        techs = build_technicians(SAMPLE_DATA, [])
        tina = next(t for t in techs if t.name == "Tina Orozco")
        assert tina.skills == ["plumbing", "hvac"]

    def test_zips_preserved(self):
        techs = build_technicians(SAMPLE_DATA, [])
        tina = next(t for t in techs if t.name == "Tina Orozco")
        assert "94119" in tina.zips
        assert "94133" in tina.zips

    def test_no_appointments_when_none_saved(self):
        techs = build_technicians(SAMPLE_DATA, [])
        for t in techs:
            assert t.appointments == []

    def test_appointments_attached_to_correct_tech(self):
        appt_dict = {
            "addr": "somewhere",
            "start_time": "2026-03-10T09:00:00",
            "end_time": "2026-03-10T11:00:00",
            "appointment_type": "plumbing",
            "tech_id": 8886,
            "customer_id": 1,
        }
        techs = build_technicians(SAMPLE_DATA, [appt_dict])
        tina = next(t for t in techs if t.id == 8886)
        gregory = next(t for t in techs if t.id == 2564)
        assert len(tina.appointments) == 1
        assert len(gregory.appointments) == 0

    def test_multiple_appointments_same_tech(self):
        appts = [
            {"addr": "A", "start_time": "2026-03-10T09:00:00", "end_time": "2026-03-10T10:00:00",
             "appointment_type": "hvac", "tech_id": 8886, "customer_id": 1},
            {"addr": "B", "start_time": "2026-03-10T13:00:00", "end_time": "2026-03-10T14:00:00",
             "appointment_type": "plumbing", "tech_id": 8886, "customer_id": 2},
        ]
        techs = build_technicians(SAMPLE_DATA, appts)
        tina = next(t for t in techs if t.id == 8886)
        assert len(tina.appointments) == 2

    def test_appointment_wrong_tech_id_not_attached(self):
        appt_dict = {
            "addr": "somewhere", "start_time": "2026-03-10T09:00:00",
            "end_time": "2026-03-10T10:00:00", "appointment_type": "plumbing",
            "tech_id": 9999, "customer_id": 1,
        }
        techs = build_technicians(SAMPLE_DATA, [appt_dict])
        for t in techs:
            assert t.appointments == []

    def test_business_units_uppercase_lowercased(self):
        data = {
            "Technician_Profiles": [
                {"id": 1, "name": "X", "zones": ["94101"], "business_units": ["Plumbing", "HVAC"]},
            ],
            "Customer_Profiles": [],
            "Location_Profiles": [],
        }
        techs = build_technicians(data, [])
        assert techs[0].skills == ["plumbing", "hvac"]

    def test_uses_real_data_json(self):
        import storage
        data = storage.load_data()
        techs = build_technicians(data, [])
        names = {t.name for t in techs}
        assert "Tina Orozco" in names
        assert "Michael Page" in names


# ---------------------------------------------------------------------------
# overlaps
# ---------------------------------------------------------------------------

class TestOverlaps:
    def test_non_overlapping_before(self):
        assert overlaps(dt(8), dt(10), dt(11), dt(13)) is False

    def test_non_overlapping_after(self):
        assert overlaps(dt(12), dt(14), dt(9), dt(11)) is False

    def test_touching_boundary_start(self):
        # a ends exactly when b starts → no overlap
        assert overlaps(dt(8), dt(10), dt(10), dt(12)) is False

    def test_touching_boundary_end(self):
        # b ends exactly when a starts → no overlap
        assert overlaps(dt(10), dt(12), dt(8), dt(10)) is False

    def test_full_overlap(self):
        assert overlaps(dt(8), dt(12), dt(9), dt(11)) is True

    def test_partial_overlap_start(self):
        assert overlaps(dt(8), dt(11), dt(10), dt(13)) is True

    def test_partial_overlap_end(self):
        assert overlaps(dt(10), dt(13), dt(8), dt(11)) is True

    def test_identical_windows(self):
        assert overlaps(dt(9), dt(11), dt(9), dt(11)) is True

    def test_one_inside_other(self):
        assert overlaps(dt(8), dt(14), dt(10), dt(12)) is True


# ---------------------------------------------------------------------------
# score_technician
# ---------------------------------------------------------------------------

class TestScoreTechnician:
    def test_no_appointments_score(self):
        tech = make_tech()
        start, end = dt(10), dt(12)
        # gap_before = 10:00 - 06:00 = 240 min
        # gap_after  = 23:59 - 12:00 = 719 min
        score = score_technician(tech, start, end)
        assert score == 240 + 719

    def test_appointment_before_gives_gap_before(self):
        prior = make_appt(8, 9)
        tech = make_tech(appointments=[prior])
        start, end = dt(10), dt(12)
        # gap_before = 10:00 - 09:00 = 60 min
        # gap_after  = 23:59 - 12:00 = 719 min
        score = score_technician(tech, start, end)
        assert score == 60 + 719

    def test_appointment_after_gives_gap_after(self):
        nxt = make_appt(14, 16)
        tech = make_tech(appointments=[nxt])
        start, end = dt(10), dt(12)
        # gap_before = 10:00 - 06:00 = 240 min
        # gap_after  = 14:00 - 12:00 = 120 min
        score = score_technician(tech, start, end)
        assert score == 240 + 120

    def test_appointments_both_sides(self):
        prior = make_appt(8, 9)
        nxt = make_appt(14, 16)
        tech = make_tech(appointments=[prior, nxt])
        start, end = dt(10), dt(12)
        # gap_before = 60, gap_after = 120
        score = score_technician(tech, start, end)
        assert score == 60 + 120

    def test_appointments_on_different_day_ignored(self):
        other_day = date(2026, 3, 11)
        prior = make_appt(8, 9, day=other_day)
        tech = make_tech(appointments=[prior])
        start, end = dt(10), dt(12)
        # No same-day appts → full ref gaps
        score = score_technician(tech, start, end)
        assert score == 240 + 719

    def test_multiple_before_uses_last(self):
        a1 = make_appt(7, 8)
        a2 = make_appt(8, 9)
        # Two appointments before start=10: ends at 08:00 and 09:00
        # gap_before should use the latest (09:00)
        a1 = Appointment("x", dt(7), dt(8), "plumbing", 1, 1)
        a2 = Appointment("x", dt(8, 30), dt(9, 0), "plumbing", 1, 1)
        tech = make_tech(appointments=[a1, a2])
        start, end = dt(10), dt(12)
        score = score_technician(tech, start, end)
        gap_before = (dt(10) - dt(9)).seconds // 60   # 60
        gap_after = (dt(23, 59) - dt(12)).seconds // 60  # 719
        assert score == gap_before + gap_after

    def test_score_increases_with_larger_gaps(self):
        """A tech with larger surrounding gaps scores higher."""
        tech_a = make_tech(id=1, appointments=[
            Appointment("x", dt(8), dt(9), "plumbing", 1, 1),
            Appointment("x", dt(14), dt(15), "plumbing", 1, 1),
        ])
        tech_b = make_tech(id=2, appointments=[
            Appointment("x", dt(9, 30), dt(9, 45), "plumbing", 2, 1),
            Appointment("x", dt(12, 15), dt(13), "plumbing", 2, 1),
        ])
        start, end = dt(10), dt(12)
        score_a = score_technician(tech_a, start, end)  # 60 + 120 = 180
        score_b = score_technician(tech_b, start, end)  # 15 + 15 = 30
        assert score_a > score_b


# ---------------------------------------------------------------------------
# find_technician
# ---------------------------------------------------------------------------

class TestFindTechnician:
    def test_returns_none_when_no_techs(self):
        result = find_technician([], "94111", "plumbing", dt(10), dt(12))
        assert result is None

    def test_returns_none_wrong_zip(self):
        tech = make_tech(zips=["94111"])
        result = find_technician([tech], "99999", "plumbing", dt(10), dt(12))
        assert result is None

    def test_returns_none_wrong_skill(self):
        tech = make_tech(skills=["plumbing"])
        result = find_technician([tech], "94111", "electrical", dt(10), dt(12))
        assert result is None

    def test_returns_none_wrong_zip_and_skill(self):
        tech = make_tech(zips=["94111"], skills=["plumbing"])
        result = find_technician([tech], "99999", "electrical", dt(10), dt(12))
        assert result is None

    def test_skill_match_is_case_insensitive(self):
        tech = make_tech(skills=["plumbing"])
        result = find_technician([tech], "94111", "PLUMBING", dt(10), dt(12))
        assert result is tech

    def test_single_eligible_tech_returned(self):
        tech = make_tech()
        result = find_technician([tech], "94111", "plumbing", dt(10), dt(12))
        assert result is tech

    def test_conflicting_appointment_excludes_tech(self):
        conflict = make_appt(10, 12)
        tech = make_tech(appointments=[conflict])
        result = find_technician([tech], "94111", "plumbing", dt(10), dt(12))
        assert result is None

    def test_touching_boundary_not_conflicting(self):
        prior = make_appt(8, 10)
        tech = make_tech(appointments=[prior])
        # New slot starts exactly when prior ends → no conflict
        result = find_technician([tech], "94111", "plumbing", dt(10), dt(12))
        assert result is tech

    def test_partial_overlap_excluded(self):
        existing = make_appt(9, 11)
        tech = make_tech(appointments=[existing])
        result = find_technician([tech], "94111", "plumbing", dt(10), dt(12))
        assert result is None

    def test_returns_highest_scored_tech(self):
        """When two techs are available, pick the one with higher load-spread score."""
        # tech_a: gap_before=240 (no prior), gap_after=719 (no next) = 959
        tech_a = make_tech(id=1, name="A", zips=["94111"], skills=["plumbing"])
        # tech_b: has a prior appt ending at 09:30, so gap_before=30, gap_after=719 = 749
        tech_b = make_tech(
            id=2, name="B", zips=["94111"], skills=["plumbing"],
            appointments=[Appointment("x", dt(9), dt(9, 30), "plumbing", 2, 1)],
        )
        result = find_technician([tech_a, tech_b], "94111", "plumbing", dt(10), dt(12))
        assert result is tech_a

    def test_picks_best_when_all_busy_except_one(self):
        conflict = make_appt(10, 12)
        busy_tech = make_tech(id=1, name="Busy", appointments=[conflict])
        free_tech = make_tech(id=2, name="Free", appointments=[])
        result = find_technician([busy_tech, free_tech], "94111", "plumbing", dt(10), dt(12))
        assert result is free_tech

    def test_multiple_zips_any_match(self):
        tech = make_tech(zips=["94111", "94115", "94119"])
        for zip_code in ["94111", "94115", "94119"]:
            assert find_technician([tech], zip_code, "plumbing", dt(10), dt(12)) is tech

    def test_zip_not_in_list_fails(self):
        tech = make_tech(zips=["94111", "94115"])
        assert find_technician([tech], "94119", "plumbing", dt(10), dt(12)) is None

    def test_real_data_plumbing_94119(self):
        """Tina Orozco and Gina Garza both cover 94119 with plumbing skill."""
        import storage
        data = storage.load_data()
        techs = build_technicians(data, [])
        result = find_technician(techs, "94119", "plumbing", dt(10), dt(12))
        assert result is not None
        assert result.name in {"Tina Orozco", "Gina Garza"}

    def test_real_data_electrical_94115(self):
        """Michael Page and Christopher Johnson cover 94115; only Page does electrical."""
        import storage
        data = storage.load_data()
        techs = build_technicians(data, [])
        result = find_technician(techs, "94115", "electrical", dt(10), dt(12))
        assert result is not None
        assert result.name in {"Michael Page", "Christopher Johnson"}

    def test_real_data_no_tech_for_unknown_zip(self):
        import storage
        data = storage.load_data()
        techs = build_technicians(data, [])
        result = find_technician(techs, "00000", "plumbing", dt(10), dt(12))
        assert result is None

    def test_real_data_no_tech_for_unknown_skill(self):
        import storage
        data = storage.load_data()
        techs = build_technicians(data, [])
        result = find_technician(techs, "94119", "roofing", dt(10), dt(12))
        assert result is None


# ---------------------------------------------------------------------------
# schedule_appointment
# ---------------------------------------------------------------------------

class TestScheduleAppointment:
    def test_appends_to_tech_appointments(self, tmp_path, monkeypatch):
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        tech = make_tech()
        appt = make_appt(10, 12)
        schedule_appointment(tech, appt)
        assert appt in tech.appointments

    def test_persists_to_storage(self, tmp_path, monkeypatch):
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        tech = make_tech()
        appt = make_appt(10, 12)
        schedule_appointment(tech, appt)

        saved = json.loads(appt_path.read_text())
        assert len(saved) == 1
        assert saved[0]["tech_id"] == tech.id

    def test_returns_the_appointment(self, tmp_path, monkeypatch):
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        tech = make_tech()
        appt = make_appt(10, 12)
        returned = schedule_appointment(tech, appt)
        assert returned is appt

    def test_second_schedule_still_finds_tech_busy(self, tmp_path, monkeypatch):
        """After scheduling, overlapping slot should no longer find this tech."""
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        tech = make_tech()
        appt = make_appt(10, 12)
        schedule_appointment(tech, appt)

        # Same slot → conflict
        result = find_technician([tech], "94111", "plumbing", dt(10), dt(12))
        assert result is None

    def test_adjacent_slot_still_available_after_schedule(self, tmp_path, monkeypatch):
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        tech = make_tech()
        appt = make_appt(10, 12)
        schedule_appointment(tech, appt)

        # Non-overlapping adjacent slot → still available
        result = find_technician([tech], "94111", "plumbing", dt(12), dt(14))
        assert result is tech
