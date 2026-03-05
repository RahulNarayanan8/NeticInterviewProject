"""Tests for app.py helper functions and state machine (no Gradio UI needed)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import app as app_module
from app import (
    find_customer_by_id,
    find_customer_by_name,
    find_location,
    lookup_customer,
    parse_datetime_input,
    _validate_booking_window,
    _llm_parse_datetime,
    initial_state,
    process_message,
)


# ---------------------------------------------------------------------------
# Fixtures — inject known test data so tests don't depend on data.json content
# ---------------------------------------------------------------------------

FAKE_DATA = {
    "Customer_Profiles": [
        {"id": 6945, "name": "Heather Russell", "contact": "(923)951-0044"},
        {"id": 2238, "name": "Kathleen Callahan", "contact": "+1-671-151-1297"},
        {"id": 4376, "name": "Justin Long", "contact": "295-629-0443"},
    ],
    "Location_Profiles": [
        {"id": 6945, "name": "Primary Residence", "address": "95281 Joshua Courts, San Francisco, CA, 94111"},
        {"id": 2238, "name": "Town House", "address": "11536 West Rest, San Francisco, CA, 94133"},
        # 4376 has no location in this fake set
    ],
    "Technician_Profiles": [
        {"id": 8886, "name": "Tina Orozco", "zones": ["94133", "94119"], "business_units": ["plumbing", "hvac"]},
        {"id": 4697, "name": "Michael Page", "zones": ["94115", "94117", "94111", "94133"], "business_units": ["plumbing", "electrical"]},
    ],
}


@pytest.fixture(autouse=True)
def inject_fake_data(monkeypatch):
    """Replace the module-level _data cache with FAKE_DATA for every test."""
    monkeypatch.setattr(app_module, "_data", FAKE_DATA)


# ---------------------------------------------------------------------------
# find_customer_by_id
# ---------------------------------------------------------------------------

class TestFindCustomerById:
    def test_found(self):
        c = find_customer_by_id(6945)
        assert c is not None
        assert c["name"] == "Heather Russell"

    def test_not_found(self):
        assert find_customer_by_id(9999) is None

    def test_second_customer(self):
        c = find_customer_by_id(2238)
        assert c["name"] == "Kathleen Callahan"


# ---------------------------------------------------------------------------
# find_customer_by_name
# ---------------------------------------------------------------------------

class TestFindCustomerByName:
    def test_exact_match(self):
        c = find_customer_by_name("Heather Russell")
        assert c["id"] == 6945

    def test_case_insensitive(self):
        c = find_customer_by_name("heather russell")
        assert c is not None

    def test_leading_trailing_spaces(self):
        c = find_customer_by_name("  Heather Russell  ")
        assert c is not None

    def test_not_found(self):
        assert find_customer_by_name("Nobody Here") is None

    def test_partial_name_no_match(self):
        assert find_customer_by_name("Heather") is None


# ---------------------------------------------------------------------------
# find_location
# ---------------------------------------------------------------------------

class TestFindLocation:
    def test_found(self):
        loc = find_location(6945)
        assert loc is not None
        assert "94111" in loc["address"]

    def test_not_found(self):
        assert find_location(4376) is None  # 4376 has no location in FAKE_DATA

    def test_wrong_id(self):
        assert find_location(9999) is None


# ---------------------------------------------------------------------------
# lookup_customer
# ---------------------------------------------------------------------------

class TestLookupCustomer:
    def test_by_id_string(self):
        c, loc = lookup_customer("6945")
        assert c["name"] == "Heather Russell"
        assert loc is not None

    def test_by_name(self):
        c, loc = lookup_customer("Kathleen Callahan")
        assert c["id"] == 2238

    def test_not_found_returns_none_none(self):
        c, loc = lookup_customer("nobody")
        assert c is None
        assert loc is None

    def test_customer_without_location(self):
        c, loc = lookup_customer("4376")
        assert c["name"] == "Justin Long"
        assert loc is None

    def test_numeric_id_takes_priority(self):
        # "6945" should resolve by ID, not name search
        c, _ = lookup_customer("6945")
        assert c["id"] == 6945


# ---------------------------------------------------------------------------
# parse_datetime_input
# ---------------------------------------------------------------------------

FUTURE_START = datetime(2030, 6, 15, 14, 0)   # a known future datetime for tests
FUTURE_END   = datetime(2030, 6, 15, 16, 0)


class TestValidateBookingWindow:
    """Tests for _validate_booking_window — pure datetime validation, no LLM."""

    def test_valid_window_passes(self):
        _validate_booking_window(FUTURE_START, FUTURE_END)  # should not raise

    def test_rejects_past_start(self):
        past = datetime(2020, 1, 1, 10, 0)
        with pytest.raises(ValueError, match="past"):
            _validate_booking_window(past, past + timedelta(hours=2))

    def test_rejects_start_before_6am(self):
        start = datetime(2030, 6, 15, 5, 0)
        with pytest.raises(ValueError, match="06:00"):
            _validate_booking_window(start, start + timedelta(hours=1))

    def test_exactly_6am_allowed(self):
        start = datetime(2030, 6, 15, 6, 0)
        _validate_booking_window(start, start + timedelta(hours=1))  # no raise

    def test_rejects_midnight_crossover(self):
        start = datetime(2030, 6, 15, 23, 0)
        end   = datetime(2030, 6, 16,  1, 0)
        with pytest.raises(ValueError, match="midnight"):
            _validate_booking_window(start, end)

    def test_end_exactly_at_midnight_rejected(self):
        start = datetime(2030, 6, 15, 23, 0)
        end   = datetime(2030, 6, 16,  0, 0)
        with pytest.raises(ValueError, match="midnight"):
            _validate_booking_window(start, end)

    def test_end_before_midnight_passes(self):
        start = datetime(2030, 6, 15, 22, 0)
        end   = datetime(2030, 6, 15, 23, 0)
        _validate_booking_window(start, end)  # no raise


class TestParseDatetimeInput:
    """Tests for parse_datetime_input — mocks _llm_parse_datetime to avoid LLM calls."""

    def _mock_llm(self, start: datetime, duration: float):
        return patch("app._llm_parse_datetime", return_value=(start, duration))

    def test_valid_input_returns_start_and_end(self):
        with self._mock_llm(FUTURE_START, 2.0):
            start, end = parse_datetime_input("March 10 at 2pm for 2 hours")
        assert start == FUTURE_START
        assert end == FUTURE_START + timedelta(hours=2)

    def test_fractional_duration_accepted(self):
        with self._mock_llm(FUTURE_START, 1.5):
            start, end = parse_datetime_input("tomorrow at noon for 1.5 hours")
        assert end == FUTURE_START + timedelta(hours=1.5)

    def test_quarter_hour_duration_accepted(self):
        with self._mock_llm(FUTURE_START, 0.25):
            _, end = parse_datetime_input("2030-06-15 14:00 0.25")
        assert end == FUTURE_START + timedelta(minutes=15)

    def test_max_8_hours_accepted(self):
        with self._mock_llm(FUTURE_START, 8.0):
            start, end = parse_datetime_input("June 15 at 10am for 8 hours")
        assert (end - start).seconds // 3600 == 8

    def test_rejects_zero_duration(self):
        with self._mock_llm(FUTURE_START, 0.0):
            with pytest.raises(ValueError, match="greater than 0"):
                parse_datetime_input("tomorrow at 10am for 0 hours")

    def test_rejects_negative_duration(self):
        with self._mock_llm(FUTURE_START, -1.0):
            with pytest.raises(ValueError, match="greater than 0"):
                parse_datetime_input("some input")

    def test_rejects_duration_over_8(self):
        with self._mock_llm(FUTURE_START, 9.0):
            with pytest.raises(ValueError, match="8"):
                parse_datetime_input("all day")

    def test_rejects_duration_just_over_8(self):
        with self._mock_llm(FUTURE_START, 8.5):
            with pytest.raises(ValueError, match="8"):
                parse_datetime_input("some input")

    def test_rejects_past_start(self):
        past = datetime(2020, 1, 1, 10, 0)
        with self._mock_llm(past, 2.0):
            with pytest.raises(ValueError, match="past"):
                parse_datetime_input("last Monday at 10am for 2 hours")

    def test_rejects_start_before_6am(self):
        early = datetime(2030, 6, 15, 4, 0)
        with self._mock_llm(early, 1.0):
            with pytest.raises(ValueError, match="06:00"):
                parse_datetime_input("2030-06-15 04:00 1")

    def test_rejects_midnight_crossover(self):
        late = datetime(2030, 6, 15, 23, 0)
        with self._mock_llm(late, 2.0):
            with pytest.raises(ValueError, match="midnight"):
                parse_datetime_input("11pm for 2 hours")

    def test_llm_parse_error_propagates(self):
        with patch("app._llm_parse_datetime", side_effect=ValueError("couldn't understand")):
            with pytest.raises(ValueError, match="couldn't understand"):
                parse_datetime_input("gibberish")


# ---------------------------------------------------------------------------
# State machine — process_message
# ---------------------------------------------------------------------------

class TestStateMachineIdentify:
    def test_valid_id_moves_to_confirm(self):
        state = initial_state()
        _, history, new_state = process_message("6945", state, [])
        assert new_state["stage"] == "CONFIRM_IDENTITY"
        assert new_state["customer"]["name"] == "Heather Russell"
        assert "Found" in history[-1]["content"]

    def test_valid_name_moves_to_confirm(self):
        state = initial_state()
        _, history, new_state = process_message("Heather Russell", state, [])
        assert new_state["stage"] == "CONFIRM_IDENTITY"

    def test_unknown_input_stays_in_identify(self):
        state = initial_state()
        _, history, new_state = process_message("nobody", state, [])
        assert new_state["stage"] == "IDENTIFY"
        assert "couldn't find" in history[-1]["content"].lower()


class TestStateMachineConfirmIdentity:
    @pytest.fixture
    def confirm_state(self):
        s = initial_state()
        s["stage"] = "CONFIRM_IDENTITY"
        s["customer"] = {"id": 6945, "name": "Heather Russell", "contact": "x"}
        s["location"] = {"id": 6945, "name": "Primary Residence", "address": "95281 Joshua Courts, San Francisco, CA, 94111"}
        return s

    def test_yes_moves_to_main_menu(self, confirm_state):
        _, _, new_state = process_message("yes", confirm_state, [])
        assert new_state["stage"] == "MAIN_MENU"

    def test_y_moves_to_main_menu(self, confirm_state):
        _, _, new_state = process_message("y", confirm_state, [])
        assert new_state["stage"] == "MAIN_MENU"

    def test_no_resets_to_identify(self, confirm_state):
        _, _, new_state = process_message("no", confirm_state, [])
        assert new_state["stage"] == "IDENTIFY"
        assert new_state["customer"] is None

    def test_invalid_stays_in_confirm(self, confirm_state):
        _, history, new_state = process_message("maybe", confirm_state, [])
        assert new_state["stage"] == "CONFIRM_IDENTITY"
        assert "yes" in history[-1]["content"].lower()


class TestStateMachineMainMenu:
    @pytest.fixture
    def menu_state(self):
        s = initial_state()
        s["stage"] = "MAIN_MENU"
        s["customer"] = {"id": 6945, "name": "Heather Russell", "contact": "x"}
        return s

    def test_book_moves_to_booking_service(self, menu_state):
        _, _, new_state = process_message("book", menu_state, [])
        assert new_state["stage"] == "BOOKING_SERVICE"

    def test_faq_moves_to_faq(self, menu_state):
        _, _, new_state = process_message("faq", menu_state, [])
        assert new_state["stage"] == "FAQ"

    def test_invalid_stays_in_menu(self, menu_state):
        _, _, new_state = process_message("help", menu_state, [])
        assert new_state["stage"] == "MAIN_MENU"

    def test_case_insensitive_book(self, menu_state):
        _, _, new_state = process_message("BOOK", menu_state, [])
        assert new_state["stage"] == "BOOKING_SERVICE"


class TestStateMachineFAQ:
    @pytest.fixture
    def faq_state(self):
        s = initial_state()
        s["stage"] = "FAQ"
        return s

    def test_done_returns_to_menu(self, faq_state):
        _, _, new_state = process_message("done", faq_state, [])
        assert new_state["stage"] == "MAIN_MENU"

    def test_question_calls_faq_and_stays(self, faq_state):
        with patch("app.faq_module.answer_faq", return_value="It takes 1-2 hours.") as mock_faq:
            _, history, new_state = process_message("How long does plumbing take?", faq_state, [])
        assert new_state["stage"] == "FAQ"
        assert history[-1]["content"] == "It takes 1-2 hours."
        mock_faq.assert_called_once_with(
            "How long does plumbing take?",
            customer=faq_state["customer"],
            location=faq_state["location"],
            data=FAKE_DATA,
        )


class TestStateMachineBookingService:
    # FAKE_DATA: zip 94111 has Michael Page (plumbing, electrical) only.
    # hvac at 94111 → no coverage → early rejection.
    @pytest.fixture
    def booking_state(self):
        s = initial_state()
        s["stage"] = "BOOKING_SERVICE"
        s["location"] = {"id": 6945, "address": "95281 Joshua Courts, San Francisco, CA, 94111"}
        return s

    def test_valid_covered_service_moves_to_address(self, booking_state):
        # plumbing and electrical are covered at 94111 by Michael Page
        for svc in ["plumbing", "electrical"]:
            state = {**booking_state, "booking": {"service": None, "address": None, "start_time": None, "end_time": None}}
            state["stage"] = "BOOKING_SERVICE"
            _, _, new_state = process_message(svc, state, [])
            assert new_state["stage"] == "BOOKING_ADDRESS"
            assert new_state["booking"]["service"] == svc

    def test_case_insensitive_service(self, booking_state):
        _, _, new_state = process_message("PLUMBING", booking_state, [])
        assert new_state["stage"] == "BOOKING_ADDRESS"
        assert new_state["booking"]["service"] == "plumbing"

    def test_invalid_service_stays(self, booking_state):
        _, history, new_state = process_message("roofing", booking_state, [])
        assert new_state["stage"] == "BOOKING_SERVICE"
        assert "valid service" in history[-1]["content"].lower()

    def test_service_not_covered_in_zip_goes_to_menu(self, booking_state):
        # hvac has no technician at 94111 in FAKE_DATA
        _, history, new_state = process_message("hvac", booking_state, [])
        assert new_state["stage"] == "MAIN_MENU"
        assert "hvac" in history[-1]["content"].lower()
        assert "94111" in history[-1]["content"]

    def test_service_not_covered_clears_booking_service(self, booking_state):
        _, _, new_state = process_message("hvac", booking_state, [])
        assert new_state["booking"]["service"] is None

    def test_no_location_on_file_skips_early_check(self):
        # Without a location we can't do an early check — flow continues normally
        s = initial_state()
        s["stage"] = "BOOKING_SERVICE"
        s["location"] = None  # no address on file
        _, _, new_state = process_message("hvac", s, [])
        assert new_state["stage"] == "BOOKING_ADDRESS"

    def test_early_check_uses_on_file_zip(self, booking_state):
        # 94133 is covered for hvac by Tina Orozco — but customer is at 94111
        # so early check uses 94111, not 94133
        _, history, new_state = process_message("hvac", booking_state, [])
        assert "94111" in history[-1]["content"]  # reports the correct zip


class TestStateMachineBookingAddress:
    @pytest.fixture
    def addr_state(self):
        s = initial_state()
        s["stage"] = "BOOKING_ADDRESS"
        s["location"] = {"id": 6945, "address": "95281 Joshua Courts, San Francisco, CA, 94111"}
        s["booking"]["service"] = "plumbing"
        return s

    def test_yes_uses_location_address(self, addr_state):
        _, _, new_state = process_message("yes", addr_state, [])
        assert new_state["booking"]["address"] == "95281 Joshua Courts, San Francisco, CA, 94111"
        assert new_state["stage"] == "BOOKING_DATETIME"

    def test_custom_address_stored(self, addr_state):
        _, _, new_state = process_message("999 New St, San Francisco, CA, 94115", addr_state, [])
        assert new_state["booking"]["address"] == "999 New St, San Francisco, CA, 94115"
        assert new_state["stage"] == "BOOKING_DATETIME"


class TestStateMachineBookingDatetime:
    @pytest.fixture
    def dt_state(self):
        s = initial_state()
        s["stage"] = "BOOKING_DATETIME"
        s["booking"]["service"] = "plumbing"
        s["booking"]["address"] = "95281 Joshua Courts, San Francisco, CA, 94111"
        return s

    def test_valid_input_moves_to_confirm(self, dt_state):
        with patch("app.parse_datetime_input", return_value=(FUTURE_START, FUTURE_END)):
            _, _, new_state = process_message("March 10 at 2pm for 2 hours", dt_state, [])
        assert new_state["stage"] == "BOOKING_CONFIRM"
        assert new_state["booking"]["start_time"] == FUTURE_START

    def test_invalid_input_stays_in_datetime(self, dt_state):
        with patch("app.parse_datetime_input", side_effect=ValueError("Start time must be at or after 06:00.")):
            _, history, new_state = process_message("tonight at 4am for 1 hour", dt_state, [])
        assert new_state["stage"] == "BOOKING_DATETIME"
        assert "Invalid input" in history[-1]["content"]

    def test_midnight_crossover_rejected(self, dt_state):
        with patch("app.parse_datetime_input", side_effect=ValueError("Appointment must not cross midnight.")):
            _, _, new_state = process_message("11pm for 2 hours", dt_state, [])
        assert new_state["stage"] == "BOOKING_DATETIME"

    def test_past_date_rejected(self, dt_state):
        with patch("app.parse_datetime_input", side_effect=ValueError("Appointment date/time is in the past.")):
            _, history, new_state = process_message("last Tuesday at 2pm for 1 hour", dt_state, [])
        assert new_state["stage"] == "BOOKING_DATETIME"
        assert "Invalid input" in history[-1]["content"]


class TestStateMachineBookingConfirm:
    @pytest.fixture
    def confirm_state(self, tmp_path, monkeypatch):
        import storage as st
        appt_path = tmp_path / "appointments.json"
        appt_path.write_text("[]")
        monkeypatch.setattr(st, "APPOINTMENTS_PATH", appt_path)

        s = initial_state()
        s["stage"] = "BOOKING_CONFIRM"
        s["customer"] = {"id": 6945, "name": "Heather Russell", "contact": "x"}
        s["location"] = {"id": 6945, "address": "95281 Joshua Courts, San Francisco, CA, 94111"}
        s["booking"] = {
            "service": "plumbing",
            "address": "95281 Joshua Courts, San Francisco, CA, 94111",
            "start_time": datetime(2030, 6, 15, 14, 0),
            "end_time": datetime(2030, 6, 15, 16, 0),
        }
        return s

    def test_no_cancels_and_returns_to_menu(self, confirm_state):
        _, history, new_state = process_message("no", confirm_state, [])
        assert new_state["stage"] == "MAIN_MENU"
        assert "cancelled" in history[-1]["content"].lower()

    def test_invalid_stays_in_confirm(self, confirm_state):
        _, _, new_state = process_message("maybe", confirm_state, [])
        assert new_state["stage"] == "BOOKING_CONFIRM"

    def test_yes_with_available_tech_books(self, confirm_state):
        # Michael Page covers 94111 with plumbing
        with patch("app.scheduler.find_technician") as mock_find:
            mock_tech = MagicMock()
            mock_tech.name = "Michael Page"
            mock_tech.id = 4697
            mock_find.return_value = mock_tech
            with patch("app.scheduler.schedule_appointment"):
                _, history, new_state = process_message("yes", confirm_state, [])
        assert new_state["stage"] == "MAIN_MENU"
        assert "Michael Page" in history[-1]["content"]

    def test_yes_with_no_tech_available(self, confirm_state):
        with patch("app.scheduler.find_technician", return_value=None):
            _, history, new_state = process_message("yes", confirm_state, [])
        assert new_state["stage"] == "MAIN_MENU"
        assert "no technician" in history[-1]["content"].lower()

    def test_booking_reset_after_confirm(self, confirm_state):
        with patch("app.scheduler.find_technician", return_value=None):
            _, _, new_state = process_message("yes", confirm_state, [])
        assert new_state["booking"]["service"] is None
        assert new_state["booking"]["start_time"] is None


# ---------------------------------------------------------------------------
# History accumulation
# ---------------------------------------------------------------------------

class TestHistoryAccumulation:
    def test_history_grows_with_each_turn(self):
        state = initial_state()
        history = []
        _, history, state = process_message("nobody", state, history)
        assert len(history) == 2  # user + bot
        _, history, state = process_message("still nobody", state, history)
        assert len(history) == 4

    def test_history_entries_have_role_and_content(self):
        state = initial_state()
        _, history, _ = process_message("nobody", state, [])
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "nobody"
        assert history[1]["role"] == "assistant"
        assert isinstance(history[1]["content"], str)
