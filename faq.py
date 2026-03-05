import anthropic
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _build_system_prompt(
    customer: Optional[dict],
    location: Optional[dict],
    data: Optional[dict],
    appointments: Optional[list] = None,
) -> str:
    lines = [
        "You are a helpful FAQ assistant for a home services company offering "
        "plumbing, electrical, and HVAC services. Be concise and friendly. Dont ask things like 'Would you like to schedule an appointment'.",
    ]

    if customer:
        lines.append(f"\nThe customer you are speaking with is {customer['name']} (ID: {customer['id']}).")
    if location:
        lines.append(f"Their service address on file is: {location['address']}.")

    if data and data.get("Technician_Profiles"):
        tech_by_id = {t["id"]: t["name"] for t in data["Technician_Profiles"]}
        lines.append("\nAvailable technicians and their coverage:")
        for tech in data["Technician_Profiles"]:
            skills = ", ".join(tech["business_units"])
            zips = ", ".join(tech["zones"])
            lines.append(f"  - {tech['name']}: {skills} — serves zip codes {zips}")
        lines.append(
            "\nUse this information to give specific answers about service availability "
            "in the customer's area, which technicians can help them, and what services "
            "are offered. If the customer asks whether a service is available at their "
            "address, check their zip code against the technician coverage above."
        )
    else:
        tech_by_id = {}

    if appointments:
        lines.append("\nThis customer's booked appointments:")
        for appt in appointments:
            tech_name = tech_by_id.get(appt["tech_id"], f"Technician #{appt['tech_id']}")
            lines.append(
                f"  - {appt['appointment_type'].title()} at {appt['addr']} | "
                f"{appt['start_time']} → {appt['end_time']} | Technician: {tech_name}"
            )
    elif appointments is not None:
        lines.append("\nThis customer has no booked appointments.")

    return "\n".join(lines)


def answer_faq(
    question: str,
    customer: Optional[dict] = None,
    location: Optional[dict] = None,
    data: Optional[dict] = None,
    appointments: Optional[list] = None,
) -> str:
    """Call Claude to answer a home services FAQ question with optional context."""
    system_prompt = _build_system_prompt(customer, location, data, appointments)
    response = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": question}],
    )
    return response.content[0].text
