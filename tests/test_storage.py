"""Tests for storage.py — JSON I/O with threading.Lock."""
import json
import threading
import pytest
from pathlib import Path
from unittest.mock import patch

import storage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data):
    path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# init()
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_appointments_file_when_missing(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        assert not appt_path.exists()
        storage.init()
        assert appt_path.exists()
        assert json.loads(appt_path.read_text()) == []

    def test_does_not_overwrite_existing_file(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        existing = [{"addr": "somewhere", "tech_id": 1}]
        _write_json(appt_path, existing)
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        storage.init()
        assert json.loads(appt_path.read_text()) == existing

    def test_creates_parent_directory(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "subdir" / "appointments.json"
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        storage.init()
        assert appt_path.exists()


# ---------------------------------------------------------------------------
# load_data()
# ---------------------------------------------------------------------------

class TestLoadData:
    def test_returns_dict_with_expected_keys(self):
        data = storage.load_data()
        assert "Customer_Profiles" in data
        assert "Location_Profiles" in data
        assert "Technician_Profiles" in data

    def test_customer_profiles_non_empty(self):
        data = storage.load_data()
        assert len(data["Customer_Profiles"]) > 0

    def test_technician_profiles_have_required_fields(self):
        data = storage.load_data()
        for tech in data["Technician_Profiles"]:
            assert "id" in tech
            assert "name" in tech
            assert "zones" in tech
            assert "business_units" in tech

    def test_customer_profiles_have_required_fields(self):
        data = storage.load_data()
        for customer in data["Customer_Profiles"]:
            assert "id" in customer
            assert "name" in customer
            assert "contact" in customer

    def test_location_profiles_have_required_fields(self):
        data = storage.load_data()
        for loc in data["Location_Profiles"]:
            assert "id" in loc
            assert "name" in loc
            assert "address" in loc

    def test_known_customer_present(self):
        data = storage.load_data()
        ids = {c["id"] for c in data["Customer_Profiles"]}
        assert 6945 in ids

    def test_known_technician_present(self):
        data = storage.load_data()
        names = {t["name"] for t in data["Technician_Profiles"]}
        assert "Tina Orozco" in names


# ---------------------------------------------------------------------------
# load_appointments() / save_appointment()
# ---------------------------------------------------------------------------

class TestLoadAppointments:
    def test_returns_empty_list_initially(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        _write_json(appt_path, [])
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        assert storage.load_appointments() == []

    def test_returns_saved_records(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        records = [{"addr": "123 St", "tech_id": 5}]
        _write_json(appt_path, records)
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        assert storage.load_appointments() == records


class TestSaveAppointment:
    def test_appends_to_empty_file(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        _write_json(appt_path, [])
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        record = {"addr": "10 Main", "tech_id": 1, "customer_id": 2}
        storage.save_appointment(record)
        saved = json.loads(appt_path.read_text())
        assert saved == [record]

    def test_appends_to_existing_records(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        existing = [{"addr": "old", "tech_id": 9}]
        _write_json(appt_path, existing)
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        new_record = {"addr": "new", "tech_id": 7}
        storage.save_appointment(new_record)
        saved = json.loads(appt_path.read_text())
        assert len(saved) == 2
        assert saved[0] == existing[0]
        assert saved[1] == new_record

    def test_multiple_saves_accumulate(self, tmp_path, monkeypatch):
        appt_path = tmp_path / "appointments.json"
        _write_json(appt_path, [])
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)
        for i in range(5):
            storage.save_appointment({"index": i})
        saved = json.loads(appt_path.read_text())
        assert len(saved) == 5
        assert [r["index"] for r in saved] == list(range(5))

    def test_thread_safety(self, tmp_path, monkeypatch):
        """Concurrent saves must not lose records."""
        appt_path = tmp_path / "appointments.json"
        _write_json(appt_path, [])
        monkeypatch.setattr(storage, "APPOINTMENTS_PATH", appt_path)

        errors = []

        def save_one(i):
            try:
                storage.save_appointment({"index": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_one, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        saved = json.loads(appt_path.read_text())
        assert len(saved) == 20
        assert sorted(r["index"] for r in saved) == list(range(20))
