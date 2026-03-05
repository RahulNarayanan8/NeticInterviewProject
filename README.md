# Home Services Chatbot

A Gradio-based customer chatbot for a home services company. Customers can book a technician appointment or ask FAQ questions powered by Claude.

---

## Features

- **Appointment booking** — guided flow: identify customer → choose service → confirm address → describe when → dispatch the best available technician
- **Early availability check** — if no technician serves the customer's zip with the requested skill, the bot says so immediately at service selection, before the customer fills in any further details
- **Natural language date parsing** — Claude Haiku interprets free-form date/time input ("next Tuesday at 2pm for 1.5 hours") and converts it to a structured datetime
- **FAQ assistant** — Claude Sonnet answers any home services question with full context: the customer's name, their address on file, and every technician's skills and zip coverage
- **Smart scheduling** — technicians are filtered by zip and skill, conflict-checked, then ranked by a load-spreading score

---

## File Structure

```
Netic_Project/
├── app.py          # Gradio UI, state machine, booking helpers, LLM date parser
├── scheduler.py    # Technician filtering, conflict detection, scoring, dispatch
├── faq.py          # Claude FAQ handler with customer + technician context
├── models.py       # Appointment and Technician dataclasses + JSON helpers
├── storage.py      # Thread-safe JSON read/write
├── data/
│   ├── data.json           # Customer, location, and technician profiles (read-only)
│   └── appointments.json   # Persisted bookings (created at startup as [])
└── tests/          # pytest test suite (147 tests)
```

---

## Setup

**Prerequisites:** Python 3.10+, an Anthropic API key.

```bash
# 1. Create and activate a virtual environment
python -m venv env
source env/bin/activate

# 2. Install dependencies
pip install gradio anthropic python-dotenv pytest

# 3. Set your API key — either export it or put it in a .env file
export ANTHROPIC_API_KEY=sk-ant-...
# or:
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 4. Run
python app.py
```

The app opens at **http://localhost:7860**.

---

## How to Use

### Booking a technician

1. Enter your **customer ID** (e.g. `6945`) or **full name**
2. Confirm your identity
3. Type `book`
4. Enter the service: `plumbing`, `electrical`, or `hvac`
   - If no technician covers your area for that service, the bot tells you immediately
5. Confirm or override your address on file
6. Describe when: *"March 10 at 2pm for 2 hours"* or *"2030-03-10 14:00 2"*
7. Review the summary and confirm — the best available technician is assigned

### Asking a question

1. After identifying yourself, type `faq`
2. Ask anything — the bot knows your address, your zip, and which technicians can help you
3. Type `done` to return to the main menu

---

## Core Logic

### State machine (`app.py`)

The chatbot advances through named stages. Each stage reads user input, validates it, and either moves forward or re-prompts.

```
IDENTIFY → CONFIRM_IDENTITY → MAIN_MENU ─┬─► BOOKING_SERVICE
                                          │       │
                                          │       │  (early availability check)
                                          │       │
                                          │   BOOKING_ADDRESS
                                          │       │
                                          │   BOOKING_DATETIME
                                          │       │
                                          │   BOOKING_CONFIRM
                                          │       │
                                          │   (result) ──► MAIN_MENU
                                          │
                                          └─► FAQ ──► MAIN_MENU
```

**Identity lookup** — the `IDENTIFY` stage first tries to parse the input as an integer ID; if that fails it falls back to a case-insensitive full-name match across `Customer_Profiles`.

**Early availability check** (`BOOKING_SERVICE`) — immediately after the customer picks a service, the bot checks whether any technician in `data.json` covers the customer's on-file zip *and* has that skill. If not, it returns an error message right away and goes back to `MAIN_MENU`. This check is skipped if the customer has no address on file.

---

### Date/time parsing (`app.py`)

Parsing is split into two steps so the validation logic is independently testable.

**Step 1 — LLM extraction (`_llm_parse_datetime`)**

Calls `claude-haiku-4-5-20251001` with today's date in the system prompt:

```
System: Today's date is {today}. Extract the appointment start date/time and
        duration in hours from the user's message. Return ONLY valid JSON:
        {"start": "YYYY-MM-DDTHH:MM:00", "duration_hours": <float>}.
        Resolve relative expressions like 'tomorrow' against today's date.
        If you cannot determine a value, use null for that field.
```

The response is parsed as JSON. Markdown code fences are stripped if present. Missing or null fields raise a `ValueError` with a user-friendly message.

**Step 2 — Business rule validation (`_validate_booking_window` + `parse_datetime_input`)**

After extraction, `parse_datetime_input` applies these rules in order:

| Rule | Error |
|---|---|
| `duration_hours <= 0` | "Duration must be greater than 0 hours." |
| `duration_hours > 8` | "Duration cannot exceed 8 hours." |
| `start < now()` | "Appointment date/time is in the past." |
| `start.hour < 6` | "Start time must be at or after 06:00." |
| `end.date > start.date` | "Appointment must not cross midnight." |

Decimal durations are fully supported (e.g. `1.5` → 90 minutes).

---

### Scheduling (`scheduler.py`)

**Build** — `build_technicians(data, appointments)` merges `Technician_Profiles` from `data.json` with saved appointment records, attaching each `Appointment` object to its technician.

**Filter** — `find_technician` narrows candidates to those who:
1. Have the requested zip code in their `zones`
2. Have the requested skill (case-insensitive) in their `business_units`
3. Have no existing appointment that overlaps the requested window

Overlap rule — two windows conflict when:
```
a_start < b_end  AND  a_end > b_start
```
Windows that share an exact boundary (one ends at 10:00, the next starts at 10:00) are **not** conflicts.

**Score** — among available candidates, pick the one with the highest load-spreading score:

```
score = gap_before + gap_after   (minutes)

gap_before = start − end_of_last_prior_appt_that_day
             (or start − 06:00 if no prior appointment)

gap_after  = start_of_next_appt_that_day − end
             (or 23:59 − end if no later appointment)
```

A higher score means the new slot fits more naturally into the technician's day, preferring technicians with room on either side rather than those with tight back-to-back schedules.

---

### FAQ assistant (`faq.py`)

`answer_faq(question, customer, location, data)` builds a context-rich system prompt before calling `claude-sonnet-4-6`:

- **Customer context** — name and ID of the authenticated customer
- **Location context** — service address on file
- **Technician context** — for every technician: name, skills, and zip codes served

This allows Claude to answer specific questions like *"Is plumbing available at my address?"* or *"Who would come to fix my HVAC?"* by cross-referencing the customer's zip against actual technician coverage.

---

### Data flow

```
data/data.json  ──►  storage.load_data()
                          │
                          ▼
                  scheduler.build_technicians()  ◄──  appointments.json
                          │
                          ▼
                  scheduler.find_technician()    (filter → conflict-check → score)
                          │
                          ▼
                  scheduler.schedule_appointment()  ──►  appointments.json
```

`data.json` is read-only. All bookings are appended to `appointments.json`, which is created as an empty list on first run. Writes use a `threading.Lock` to be safe under concurrent requests.

---

### Models (`models.py`)

```python
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
    skills: List[str]        # business_units lowercased
    zips: List[str]          # zones
    appointments: List[Appointment]
```

`appointment_to_dict` / `dict_to_appointment` handle JSON serialization with ISO-format datetimes.

---

## Running Tests

```bash
source env/bin/activate
python -m pytest tests/ -v
```

147 tests across four files:

| File | What it covers |
|---|---|
| `test_models.py` | Dataclass fields, equality, default list isolation, serialization round-trip |
| `test_storage.py` | `init`, `load_data` schema, `save_appointment` append semantics, 20-thread concurrency |
| `test_scheduler.py` | `extract_zip`, `build_technicians`, `overlaps` boundaries, `score_technician` gap math, `find_technician` (filter/conflict/score/real-data), `schedule_appointment` |
| `test_app_helpers.py` | `_validate_booking_window` (direct datetime inputs), `parse_datetime_input` (mocked LLM), customer lookup, all state machine transitions including early availability check |

Datetime validation tests call `_validate_booking_window` directly with `datetime` objects — no LLM calls. Tests for `parse_datetime_input` mock `_llm_parse_datetime` to stay fast and deterministic. All hardcoded test dates use 2030 or later to avoid failing the past-date check as time passes.

---

## Data Notes

- **Customer IDs** are shared across `Customer_Profiles` and `Location_Profiles` — a customer's address is looked up by matching `id` fields.
- **Technician skills** are normalised to lowercase internally regardless of how they appear in `data.json`.
- **Zip codes** are extracted from addresses by splitting on commas and taking the last token.
- A customer without a location on file (`Location_Profiles` has no matching `id`) can still book by entering a custom address; the early availability check is skipped for them.
