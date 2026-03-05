"""Tests for models.py — Appointment / Technician dataclasses and serialization."""
import pytest
from datetime import datetime
from models import (
    Appointment,
    Technician,
    appointment_to_dict,
    dict_to_appointment,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_appt():
    return Appointment(
        addr="123 Main St, San Francisco, CA, 94111",
        start_time=datetime(2026, 3, 10, 9, 0),
        end_time=datetime(2026, 3, 10, 11, 0),
        appointment_type="plumbing",
        tech_id=42,
        customer_id=99,
    )


@pytest.fixture
def sample_tech(sample_appt):
    return Technician(
        id=42,
        name="Jane Doe",
        skills=["plumbing", "hvac"],
        zips=["94111", "94115"],
        appointments=[sample_appt],
    )


# ---------------------------------------------------------------------------
# Appointment dataclass
# ---------------------------------------------------------------------------

class TestAppointment:
    def test_fields_stored_correctly(self, sample_appt):
        assert sample_appt.addr == "123 Main St, San Francisco, CA, 94111"
        assert sample_appt.start_time == datetime(2026, 3, 10, 9, 0)
        assert sample_appt.end_time == datetime(2026, 3, 10, 11, 0)
        assert sample_appt.appointment_type == "plumbing"
        assert sample_appt.tech_id == 42
        assert sample_appt.customer_id == 99

    def test_equality(self):
        a1 = Appointment("addr", datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 10), "hvac", 1, 2)
        a2 = Appointment("addr", datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 10), "hvac", 1, 2)
        assert a1 == a2

    def test_inequality_on_time(self):
        a1 = Appointment("addr", datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 10), "hvac", 1, 2)
        a2 = Appointment("addr", datetime(2026, 1, 1, 9), datetime(2026, 1, 1, 11), "hvac", 1, 2)
        assert a1 != a2


# ---------------------------------------------------------------------------
# Technician dataclass
# ---------------------------------------------------------------------------

class TestTechnician:
    def test_fields_stored_correctly(self, sample_tech, sample_appt):
        assert sample_tech.id == 42
        assert sample_tech.name == "Jane Doe"
        assert sample_tech.skills == ["plumbing", "hvac"]
        assert sample_tech.zips == ["94111", "94115"]
        assert len(sample_tech.appointments) == 1
        assert sample_tech.appointments[0] == sample_appt

    def test_default_appointments_empty(self):
        t = Technician(id=1, name="Bob", skills=["electrical"], zips=["94101"])
        assert t.appointments == []

    def test_appointments_not_shared_between_instances(self):
        """Default factory must not share the same list across instances."""
        t1 = Technician(id=1, name="A", skills=[], zips=[])
        t2 = Technician(id=2, name="B", skills=[], zips=[])
        appt = Appointment("x", datetime(2026, 1, 1, 8), datetime(2026, 1, 1, 9), "hvac", 1, 1)
        t1.appointments.append(appt)
        assert t2.appointments == []


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_appointment_to_dict_keys(self, sample_appt):
        d = appointment_to_dict(sample_appt)
        assert set(d.keys()) == {"addr", "start_time", "end_time", "appointment_type", "tech_id", "customer_id"}

    def test_appointment_to_dict_iso_format(self, sample_appt):
        d = appointment_to_dict(sample_appt)
        assert d["start_time"] == "2026-03-10T09:00:00"
        assert d["end_time"] == "2026-03-10T11:00:00"

    def test_appointment_to_dict_values(self, sample_appt):
        d = appointment_to_dict(sample_appt)
        assert d["addr"] == sample_appt.addr
        assert d["appointment_type"] == "plumbing"
        assert d["tech_id"] == 42
        assert d["customer_id"] == 99

    def test_dict_to_appointment_round_trip(self, sample_appt):
        d = appointment_to_dict(sample_appt)
        restored = dict_to_appointment(d)
        assert restored == sample_appt

    def test_dict_to_appointment_parses_datetimes(self):
        d = {
            "addr": "somewhere",
            "start_time": "2026-06-15T14:30:00",
            "end_time": "2026-06-15T16:00:00",
            "appointment_type": "electrical",
            "tech_id": 7,
            "customer_id": 3,
        }
        appt = dict_to_appointment(d)
        assert appt.start_time == datetime(2026, 6, 15, 14, 30)
        assert appt.end_time == datetime(2026, 6, 15, 16, 0)
        assert appt.appointment_type == "electrical"
