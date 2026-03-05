import json
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import gradio as gr
from dotenv import load_dotenv

load_dotenv()

import storage
import scheduler
import faq as faq_module
from models import Appointment

_anthropic_client: Optional[anthropic.Anthropic] = None


def _get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client

VALID_SERVICES = {"plumbing", "electrical", "hvac"}

# ---------------------------------------------------------------------------
# Globals refreshed on each message (cheap for this scale)
# ---------------------------------------------------------------------------
_data: Optional[dict] = None


def get_data() -> dict:
    global _data
    if _data is None:
        _data = storage.load_data()
    return _data


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------

def find_customer_by_id(customer_id: int) -> Optional[dict]:
    for c in get_data()["Customer_Profiles"]:
        if c["id"] == customer_id:
            return c
    return None


def find_customer_by_name(name: str) -> Optional[dict]:
    normalized = name.strip().lower()
    for c in get_data()["Customer_Profiles"]:
        if c["name"].strip().lower() == normalized:
            return c
    return None


def find_location(customer_id: int) -> Optional[dict]:
    for loc in get_data()["Location_Profiles"]:
        if loc["id"] == customer_id:
            return loc
    return None


def lookup_customer(text: str):
    """Return (customer, location) or (None, None)."""
    # Try numeric ID first
    try:
        cid = int(text.strip())
        customer = find_customer_by_id(cid)
    except ValueError:
        customer = find_customer_by_name(text)
    if customer is None:
        return None, None
    location = find_location(customer["id"])
    return customer, location


# ---------------------------------------------------------------------------
# Booking helpers
# ---------------------------------------------------------------------------

def _llm_parse_datetime(text: str) -> tuple:
    """
    Use Claude to extract a start datetime and duration from free-form text.
    Returns (start: datetime, duration_hours: float) or raises ValueError.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    response = _get_anthropic_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=128,
        system=(
            f"Today's date is {today}. "
            "Extract the appointment start date/time and duration in hours from the user's message. "
            'Return ONLY valid JSON with two keys: {"start": "YYYY-MM-DDTHH:MM:00", "duration_hours": <float>}. '
            "Resolve relative expressions like 'tomorrow' or 'next Monday' against today's date. "
            "If you cannot determine a value, use null for that field."
        ),
        messages=[{"role": "user", "content": text}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(
            f"I couldn't understand '{text}' as a date and duration. "
            "Try something like: 'March 10 at 2pm for 2 hours' or '2030-03-10 14:00 2'."
        )
    if parsed.get("start") is None:
        raise ValueError("I couldn't find a start date/time. Please include a date and time.")
    if parsed.get("duration_hours") is None:
        raise ValueError("I couldn't find a duration. Please say how long (e.g. '2 hours').")
    try:
        start = datetime.fromisoformat(parsed["start"])
    except (ValueError, TypeError):
        raise ValueError(f"Invalid date/time returned: {parsed['start']}. Please try again.")
    return start, float(parsed["duration_hours"])


def _validate_booking_window(start: datetime, end: datetime) -> None:
    """
    Raise ValueError if the booking window violates any business rule.
    Checks: not in the past, starts at or after 06:00, doesn't cross midnight.
    """
    if start < datetime.now():
        raise ValueError("Appointment date/time is in the past. Please choose a future time.")
    if start.hour < 6:
        raise ValueError("Start time must be at or after 06:00.")
    if end.date() > start.date():
        raise ValueError("Appointment must not cross midnight.")


def parse_datetime_input(text: str) -> tuple:
    """
    Parse free-form text into (start, end) datetimes.
    Uses an LLM to understand natural language, then validates business rules.
    """
    start, duration_hours = _llm_parse_datetime(text)

    if duration_hours <= 0:
        raise ValueError("Duration must be greater than 0 hours.")
    if duration_hours > 8:
        raise ValueError("Duration cannot exceed 8 hours.")

    end = start + timedelta(hours=duration_hours)
    _validate_booking_window(start, end)
    return start, end


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def initial_state() -> dict:
    return {
        "stage": "IDENTIFY",
        "customer": None,
        "location": None,
        "booking": {
            "service": None,
            "address": None,
            "start_time": None,
            "end_time": None,
        },
    }


def process_message(user_input: str, state: dict, history: list):
    """
    Handle one user turn. Returns (bot_reply, new_state, new_history).
    """
    user_input = user_input.strip()
    stage = state["stage"]
    reply = ""

    # -----------------------------------------------------------------------
    if stage == "IDENTIFY":
        customer, location = lookup_customer(user_input)
        if customer is None:
            reply = (
                "Sorry, I couldn't find that customer. "
                "Please enter your customer ID (number) or full name."
            )
        else:
            state["customer"] = customer
            state["location"] = location
            state["stage"] = "CONFIRM_IDENTITY"
            reply = (
                f"Found: **{customer['name']}**. Is this you? (yes / no)"
            )

    # -----------------------------------------------------------------------
    elif stage == "CONFIRM_IDENTITY":
        if user_input.lower() in ("yes", "y"):
            state["stage"] = "MAIN_MENU"
            name = state["customer"]["name"]
            reply = (
                f"Welcome, {name}! What can I help you with?\n"
                "Type **book** to schedule a service, **faq** to ask a question, or **review** to leave a review."
            )
        elif user_input.lower() in ("no", "n"):
            state["stage"] = "IDENTIFY"
            state["customer"] = None
            state["location"] = None
            reply = "No problem. Please enter your customer ID or full name."
        else:
            reply = "Please type **yes** or **no**."

    # -----------------------------------------------------------------------
    elif stage == "MAIN_MENU":
        cmd = user_input.lower()
        if cmd == "book":
            state["stage"] = "BOOKING_SERVICE"
            reply = "What service do you need? (plumbing / electrical / hvac)"
        elif cmd == "faq":
            state["stage"] = "FAQ"
            reply = "Ask your question (or type **done** to go back to the menu)."
        elif cmd == "review":
            state["stage"] = "REVIEW"
            reply = "Please type your review and press Send."
        else:
            reply = "Please type **book**, **faq**, or **review**."

    # -----------------------------------------------------------------------
    elif stage == "FAQ":
        if user_input.lower() == "done":
            state["stage"] = "MAIN_MENU"
            reply = "Back to the main menu. Type **book**, **faq**, or **review**."
        else:
            all_appts = storage.load_appointments()
            customer_appts = [
                a for a in all_appts
                if a["customer_id"] == state["customer"]["id"]
            ]
            answer = faq_module.answer_faq(
                user_input,
                customer=state["customer"],
                location=state["location"],
                data=get_data(),
                appointments=customer_appts,
            )
            reply = answer
            # Stay in FAQ stage

    # -----------------------------------------------------------------------
    elif stage == "REVIEW":
        customer = state["customer"]
        storage.save_review({
            "customer_id": customer["id"],
            "customer_name": customer["name"],
            "text": user_input,
            "submitted_at": datetime.now().isoformat(),
        })
        state["stage"] = "MAIN_MENU"
        reply = "Thank you for your review! Type **book**, **faq**, or **review**."

    # -----------------------------------------------------------------------
    elif stage == "BOOKING_SERVICE":
        svc = user_input.lower().strip()
        if svc in VALID_SERVICES:
            loc = state["location"]
            # Early check: if the customer has an address on file, verify a
            # technician with that skill actually serves their zip before going further.
            if loc:
                zip_code = scheduler.extract_zip(loc["address"])
                technicians = scheduler.build_technicians(get_data(), storage.load_appointments())
                capable = [t for t in technicians if zip_code in t.zips and svc in t.skills]
                if not capable:
                    reply = (
                        f"Sorry, we don't currently have any **{svc}** technicians "
                        f"serving zip code **{zip_code}**.\n"
                        "Type **book** to choose a different service or **faq** for questions."
                    )
                    # Leave stage as BOOKING_SERVICE so they can try another service
                    # without having to type 'book' again
                    state["stage"] = "MAIN_MENU"
                    new_history = history + [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": reply},
                    ]
                    return "", new_history, state

            state["booking"]["service"] = svc
            state["stage"] = "BOOKING_ADDRESS"
            if loc:
                reply = (
                    f"Your address on file: **{loc['address']}**.\n"
                    "Use this address? Type **yes** or enter a new address."
                )
            else:
                reply = "Please enter your service address."
        else:
            reply = "Please enter a valid service: **plumbing**, **electrical**, or **hvac**."

    # -----------------------------------------------------------------------
    elif stage == "BOOKING_ADDRESS":
        loc = state["location"]
        if user_input.lower() in ("yes", "y") and loc:
            state["booking"]["address"] = loc["address"]
        else:
            state["booking"]["address"] = user_input
        state["stage"] = "BOOKING_DATETIME"
        reply = (
            "When would you like the appointment, and how long should it be?\n"
            "You can say things like: *'March 10 at 2pm for 2 hours'* or *'2030-03-10 14:00 2'*"
        )

    # -----------------------------------------------------------------------
    elif stage == "BOOKING_DATETIME":
        try:
            start, end = parse_datetime_input(user_input)
            state["booking"]["start_time"] = start
            state["booking"]["end_time"] = end
            state["stage"] = "BOOKING_CONFIRM"
            b = state["booking"]
            reply = (
                f"**Summary:**\n"
                f"- Service: {b['service']}\n"
                f"- Address: {b['address']}\n"
                f"- From: {start.strftime('%Y-%m-%d %H:%M')} "
                f"to {end.strftime('%Y-%m-%d %H:%M')}\n\n"
                "Confirm? (yes / no)"
            )
        except ValueError as e:
            reply = f"Invalid input: {e}\nPlease try again (e.g. *'March 10 at 2pm for 2 hours'*)."

    # -----------------------------------------------------------------------
    elif stage == "BOOKING_CONFIRM":
        if user_input.lower() in ("yes", "y"):
            state["stage"] = "BOOKING_RESULT"
            b = state["booking"]
            customer = state["customer"]

            # Build technician list fresh from storage each time
            data = get_data()
            saved_appts = storage.load_appointments()
            technicians = scheduler.build_technicians(data, saved_appts)

            zip_code = scheduler.extract_zip(b["address"])
            tech = scheduler.find_technician(
                technicians, zip_code, b["service"], b["start_time"], b["end_time"]
            )

            if tech:
                appt = Appointment(
                    addr=b["address"],
                    start_time=b["start_time"],
                    end_time=b["end_time"],
                    appointment_type=b["service"],
                    tech_id=tech.id,
                    customer_id=customer["id"],
                )
                scheduler.schedule_appointment(tech, appt)
                reply = (
                    f"Booked! Your technician is **{tech.name}**.\n"
                    f"Appointment: {b['service']} on "
                    f"{b['start_time'].strftime('%Y-%m-%d')} "
                    f"from {b['start_time'].strftime('%H:%M')} "
                    f"to {b['end_time'].strftime('%H:%M')}."
                )
            else:
                reply = (
                    "Sorry, no technician is available for that time and location. "
                    "Please try a different time."
                )

            # Reset booking and return to menu
            state["booking"] = {
                "service": None, "address": None,
                "start_time": None, "end_time": None,
            }
            state["stage"] = "MAIN_MENU"
            reply += "\n\nType **book**, **faq**, or **review**."

        elif user_input.lower() in ("no", "n"):
            state["stage"] = "MAIN_MENU"
            state["booking"] = {
                "service": None, "address": None,
                "start_time": None, "end_time": None,
            }
            reply = "Booking cancelled. Type **book** or **faq**."
        else:
            reply = "Please type **yes** or **no**."

    else:
        reply = "Something went wrong. Please refresh and start over."

    new_history = history + [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": reply},
    ]
    return "", new_history, state


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

def build_ui():
    with gr.Blocks(title="Home Services Chatbot") as demo:
        gr.Markdown("## Home Services Chatbot")
        gr.Markdown(
            "Book a technician appointment or ask any home services question."
        )

        chatbot = gr.Chatbot(height=500)
        state = gr.State(initial_state())

        with gr.Row():
            txt = gr.Textbox(
                placeholder="Type your message here…",
                show_label=False,
                scale=8,
            )
            send_btn = gr.Button("Send", scale=1, variant="primary")

        # Welcome message
        welcome = (
            "Welcome to the Home Services Chatbot!\n"
            "Please enter your **customer ID** (number) or **full name** to get started."
        )

        def on_load():
            return [{"role": "assistant", "content": welcome}]

        demo.load(on_load, outputs=[chatbot])

        send_btn.click(
            process_message,
            inputs=[txt, state, chatbot],
            outputs=[txt, chatbot, state],
        )
        txt.submit(
            process_message,
            inputs=[txt, state, chatbot],
            outputs=[txt, chatbot, state],
        )

    return demo


if __name__ == "__main__":
    storage.init()
    app = build_ui()
    app.launch(server_name="0.0.0.0", server_port=7860)
