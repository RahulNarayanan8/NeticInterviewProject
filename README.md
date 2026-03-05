# Home Services Chatbot

A Gradio-based customer chatbot for a home services company. Customers can book a technician appointment, cancel an existing booking, leave a review, or ask FAQ questions — all powered by Claude.

---

## Features

- **Appointment booking** — guided flow: identify customer → choose service → confirm address → describe when → dispatch the best available technician
- **Appointment cancellation** — lists all upcoming (future) appointments for the customer, numbered; the customer picks one to remove
- **Reviews** — customers can type a free-form review which is persisted to `reviews.json`
- **Early availability check** — if no technician serves the customer's zip with the requested skill, the bot says so immediately at service selection
- **Natural language date parsing** — Claude Haiku interprets free-form date/time input (*"next Tuesday at 2pm for 1.5 hours"*) and converts it to a structured datetime
- **FAQ assistant** — Claude Sonnet answers any home services question with full context: the customer's name, address on file, technician coverage, and their existing appointments
- **Smart scheduling** — technicians are filtered by zip and skill, conflict-checked, then ranked by a load-spreading score

---

## File Structure

```
Netic_Project/
├── app.py          # Gradio UI, state machine, booking helpers, LLM date parser
├── scheduler.py    # Technician filtering, conflict detection, scoring, dispatch
├── faq.py          # Claude FAQ handler with customer + technician + appointment context
├── models.py       # Appointment and Technician dataclasses + JSON helpers
├── storage.py      # Thread-safe JSON read/write for all data files
├── data/
│   ├── data.json           # Customer, location, and technician profiles (read-only)
│   ├── appointments.json   # Persisted bookings (created at startup as [])
│   └── reviews.json        # Persisted reviews (created at startup as [])
└── tests/          # pytest test suite (181 tests)
```

---

## Setup

**Prerequisites:** Python 3.10+, an Anthropic API key.

```bash
# 1. Create and activate a virtual environment
python -m venv env
source env/bin/activate

# 2. Install dependencies (there is a requirements.txt for your convenience)
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

After identifying yourself, you'll land at the main menu. All four options are available from there at any time.

### Book a technician

1. Type `book`
2. Enter the service: `plumbing`, `electrical`, or `hvac`
   - If no technician covers your area for that service, the bot says so immediately
3. Confirm or override your address on file
4. Describe when: *"March 10 at 2pm for 2 hours"* or *"2030-03-10 14:00 2"*
5. Review the summary and confirm — the best available technician is assigned

### Cancel an appointment

1. Type `cancel`
2. The bot lists all your upcoming appointments (future only), numbered
3. Enter the number of the appointment to cancel — it is removed from `appointments.json`
4. Type `back` at any point to return to the menu without cancelling

### Leave a review

1. Type `review`
2. Type anything — the full text is saved to `reviews.json` along with your customer ID, name, and a timestamp

### Ask a question

1. Type `faq`
2. Ask anything — the bot has full context: your address, technician coverage in your area, and all your booked appointments
3. Type `done` to return to the main menu

---

## Example Usage

Each example shows the full conversation for one flow. `🤖` is the bot, `👤` is the customer.

### Booking a plumbing appointment

```
🤖  Welcome! Please enter your customer ID or full name.
👤  6945
🤖  Found: Heather Russell. Is this you? (yes / no)
👤  yes
🤖  Welcome, Heather Russell! Type book, faq, review, or cancel.
👤  book
🤖  What service do you need? (plumbing / electrical / hvac)
👤  plumbing
🤖  Your address on file: 95281 Joshua Courts, San Francisco, CA, 94111.
    Use this address? Type yes or enter a new address.
👤  yes
🤖  When would you like the appointment, and how long should it be?
    You can say things like: 'March 10 at 2pm for 2 hours' or '2030-03-10 14:00 2'
👤  March 10th at 2pm for 2 hours
🤖  Summary:
    - Service: plumbing
    - Address: 95281 Joshua Courts, San Francisco, CA, 94111
    - From: 2030-03-10 14:00 to 2030-03-10 16:00
    Confirm? (yes / no)
👤  yes
🤖  Booked! Your technician is Michael Page.
    Appointment: plumbing on 2030-03-10 from 14:00 to 16:00.
    Type book, faq, review, or cancel.
```

### Attempting to book an unavailable service

```
👤  book
🤖  What service do you need? (plumbing / electrical / hvac)
👤  hvac
🤖  Sorry, we don't currently have any hvac technicians serving zip code 94111.
    Type book to choose a different service or faq for questions.
```

### Cancelling an appointment

```
👤  cancel
🤖  Your upcoming appointments:
      1. Plumbing — 2030-03-10 14:00 — 95281 Joshua Courts, San Francisco, CA, 94111 — Michael Page
      2. Electrical — 2030-04-02 09:00 — 95281 Joshua Courts, San Francisco, CA, 94111 — Michael Page

    Enter the number to cancel, or back to return to the menu.
👤  1
🤖  Your plumbing appointment on 2030-03-10 at 14:00 has been cancelled.
    Type book, faq, review, or cancel.
```

### Entering an invalid cancellation number

```
🤖  Enter the number to cancel, or back to return to the menu.
👤  5
🤖  Please enter a number between 1 and 2, or back to return.
👤  back
🤖  Type book, faq, review, or cancel.
```

### Asking a question

```
👤  faq
🤖  Ask your question (or type done to go back to the menu).
👤  Do you offer plumbing at my address?
🤖  Yes! We have Michael Page who covers your zip code (94111) and offers
    plumbing services. You can book an appointment by typing 'book' from
    the main menu.
👤  When is my next appointment?
🤖  Your next appointment is a plumbing visit on March 10, 2030 at 2:00 PM
    at 95281 Joshua Courts. Your technician will be Michael Page.
👤  done
🤖  Type book, faq, review, or cancel.
```

### Leaving a review

```
👤  review
🤖  Please type your review and press Send.
👤  Michael was punctual and fixed the leak quickly. Very happy with the service.
🤖  Thank you for your review! Type book, faq, review, or cancel.
```

### Validation errors during booking

```
🤖  When would you like the appointment, and how long should it be?
👤  yesterday at 3pm for 1 hour
🤖  Invalid input: Appointment date/time is in the past. Please choose a future time.
    Please try again (e.g. 'March 10 at 2pm for 2 hours').
👤  tomorrow at 4am for 1 hour
🤖  Invalid input: Start time must be at or after 06:00.
    Please try again.
👤  tomorrow at 11pm for 3 hours
🤖  Invalid input: Appointment must not cross midnight.
    Please try again.
👤  tomorrow at 2pm for 10 hours
🤖  Invalid input: Duration cannot exceed 8 hours.
    Please try again.
👤  tomorrow at 2pm for 2 hours
🤖  Summary:
    - Service: plumbing
    ...
```

---

## Core Logic

### State machine (`app.py`)

The chatbot advances through named stages. Each stage reads user input, validates it, and either moves forward or re-prompts. A constant `MENU_HINT` is used everywhere a list of options is shown, keeping all prompts consistent.

```
IDENTIFY → CONFIRM_IDENTITY → MAIN_MENU ─┬─► BOOKING_SERVICE
                                          │       │  (early availability check)
                                          │   BOOKING_ADDRESS
                                          │       │
                                          │   BOOKING_DATETIME
                                          │       │
                                          │   BOOKING_CONFIRM
                                          │       │
                                          │   (result) ──► MAIN_MENU
                                          │
                                          ├─► CANCEL_SELECT ──► MAIN_MENU
                                          │
                                          ├─► REVIEW ──► MAIN_MENU
                                          │
                                          └─► FAQ ──► MAIN_MENU
```

**Identity lookup** — `IDENTIFY` first tries to parse input as an integer customer ID; if that fails it falls back to a case-insensitive full-name match across `Customer_Profiles`.

**Early availability check** (`BOOKING_SERVICE`) — after the customer picks a service, the bot immediately checks whether any technician covers the customer's on-file zip *and* has that skill. If not, it replies with an error and returns to `MAIN_MENU`. Skipped if the customer has no address on file.

**Cancel flow** (`CANCEL_SELECT`) — upcoming appointments (those with `start_time > now`) are filtered to the current customer, displayed as a numbered list with service, date/time, address, and technician name. A valid integer selection removes the appointment via `storage.cancel_appointment`. Non-numeric, out-of-range, and negative inputs re-prompt with the valid range. `back` exits without changes.

**Review flow** (`REVIEW`) — any text the customer sends is saved as-is. No validation is applied; the full input is stored verbatim.

---

### Date/time parsing (`app.py`)

Parsing is split into two steps so the validation logic is independently testable.

**Step 1 — LLM extraction (`_llm_parse_datetime`)**

Calls `claude-haiku-4-5-20251001` with today's date in the system prompt:

```
Today's date is {today}. Extract the appointment start date/time and duration
in hours. Return ONLY valid JSON:
{"start": "YYYY-MM-DDTHH:MM:00", "duration_hours": <float>}.
Resolve relative expressions like 'tomorrow' against today's date.
If you cannot determine a value, use null for that field.
```

The response is parsed as JSON. Markdown code fences are stripped if present. Missing or null fields raise a `ValueError` with a user-friendly message.

**Step 2 — Business rule validation (`_validate_booking_window` + `parse_datetime_input`)**

| Rule | Error message |
|---|---|
| `duration_hours <= 0` | Duration must be greater than 0 hours. |
| `duration_hours > 8` | Duration cannot exceed 8 hours. |
| `start < now()` | Appointment date/time is in the past. |
| `start.hour < 6` | Start time must be at or after 06:00. |
| `end.date > start.date` | Appointment must not cross midnight. |

Decimal durations are fully supported (e.g. `1.5` → 90 minutes, `0.25` → 15 minutes).

---

### Scheduling (`scheduler.py`)

**Build** — `build_technicians(data, appointments)` merges `Technician_Profiles` from `data.json` with saved appointment records, attaching each `Appointment` to its technician.

**Filter** — `find_technician` narrows candidates to those who:
1. Have the requested zip code in their `zones`
2. Have the requested skill (case-insensitive) in their `business_units`
3. Have no existing appointment overlapping the requested window

Overlap rule:
```
a_start < b_end  AND  a_end > b_start
```
Windows sharing an exact boundary are **not** conflicts.

**Score** — pick the candidate with the highest load-spreading score:
```
score = gap_before + gap_after   (minutes)

gap_before = start − end_of_last_prior_appt_that_day
             (or start − 06:00 if none)

gap_after  = start_of_next_appt_that_day − end
             (or 23:59 − end if none)
```
A higher score means the slot fits more naturally into the day, avoiding short awkward gaps.

---

### FAQ assistant (`faq.py`)

`answer_faq(question, customer, location, data, appointments)` builds a context-rich system prompt before calling `claude-sonnet-4-6`. The prompt includes:

- **Customer** — name and ID
- **Location** — service address on file
- **Technicians** — each technician's name, skills, and zip codes served
- **Appointments** — all appointments previously booked by this customer (filtered by `customer_id` before being passed in); if none, explicitly says so to prevent hallucination

This lets Claude answer questions like *"When is my next plumbing visit?"*, *"Is HVAC available at my address?"*, or *"Who is my technician?"* with accurate, specific information.

---

### Storage (`storage.py`)

All writes use `threading.Lock` to be safe under concurrent requests. Appointments and reviews have separate locks.

| Function | File | Description |
|---|---|---|
| `load_data()` | `data.json` | Read-only load of all profiles |
| `load_appointments()` | `appointments.json` | Read full appointments list |
| `save_appointment(dict)` | `appointments.json` | Append a new booking |
| `cancel_appointment(dict)` | `appointments.json` | Remove by exact dict match |
| `save_review(dict)` | `reviews.json` | Append a new review |

`cancel_appointment` removes all entries that exactly match the provided dict. Since each appointment is uniquely identified by the combination of `customer_id`, `tech_id`, and `start_time`, this is effectively a targeted delete.

**Persisted record shapes:**

```python
# appointments.json entry
{
  "addr": "...",
  "start_time": "2030-06-15T14:00:00",
  "end_time":   "2030-06-15T16:00:00",
  "appointment_type": "plumbing",
  "tech_id": 4697,
  "customer_id": 6945
}

# reviews.json entry
{
  "customer_id": 6945,
  "customer_name": "Heather Russell",
  "text": "Great service!",
  "submitted_at": "2030-06-15T14:32:00.123456"
}
```

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
    skills: List[str]       # business_units, stored lowercase
    zips: List[str]         # zones
    appointments: List[Appointment]
```

`appointment_to_dict` / `dict_to_appointment` handle serialization with ISO-format datetimes.

---

## Running Tests

```bash
source env/bin/activate
python -m pytest tests/ -v
```

181 tests across four files:

| File | What it covers |
|---|---|
| `test_models.py` | Dataclass fields, equality, default list isolation, serialization round-trip |
| `test_storage.py` | `init`, `load_data` schema, `save_appointment` append + concurrency, `cancel_appointment` (removes target, leaves others, no-match is a no-op) |
| `test_scheduler.py` | `extract_zip`, `build_technicians`, `overlaps` boundary cases, `score_technician` gap math, `find_technician` (filter/conflict/score/real-data), `schedule_appointment` |
| `test_app_helpers.py` | `_validate_booking_window`, `parse_datetime_input` (mocked LLM), customer lookup, every state machine stage and transition including early availability check, cancel flow, review flow |

**Test design notes:**
- Datetime validation tests call `_validate_booking_window` with `datetime` objects directly — no LLM calls
- `parse_datetime_input` tests mock `_llm_parse_datetime` to stay fast and deterministic
- Cancel and review tests use `tmp_path` + `monkeypatch` to redirect file paths — the real `appointments.json` and `reviews.json` are never touched
- All hardcoded test dates use 2030 or later to avoid failing the past-date check as time passes

---

## Data Notes

- **Customer IDs** are shared across `Customer_Profiles` and `Location_Profiles` — a customer's address is looked up by matching `id` fields.
- **Technician skills** are normalised to lowercase internally regardless of how they appear in `data.json`.
- **Zip codes** are extracted from addresses by splitting on commas and taking the last token.
- A customer without a location on file can still book by entering a custom address; the early availability check is skipped for them. If their custom address is in an uncovered zip, that is caught at confirmation time.
