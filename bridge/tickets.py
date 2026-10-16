"""Text-only layouts for Cellnet schedule and reminder receipts."""
from datetime import datetime

def daily_schedule(day: str, appointments: list[dict], heading: str = "CELLNET - NAPI IDŐPONTOK") -> str:
    if len(appointments) > 60:
        raise ValueError("Maximum 60 appointments per receipt")
    lines = [heading, day, "=" * 26]
    if not appointments:
        lines.append("Nincs foglalt időpont.")
    for index, appt in enumerate(appointments, 1):
        at = appt["time"]
        customer = appt["customer"]
        service = appt["service"]
        lines.extend([f"{index:02}. {at}  {customer}", f"    {service}"])
        if appt.get("notes"):
            lines.append(f"    {appt['notes']}")
        lines.append("-" * 26)
    lines.append(f"ÖSSZESEN: {len(appointments)} IDŐPONT")
    return "\n".join(lines)

def reminder(title: str, message: str, when: str = "", priority: str = "normal") -> str:
    lines = ["CELLNET - EMLÉKEZTETŐ", "=" * 26]
    if priority == "urgent":
        lines.append("!!! S Ü R G Ő S !!!")
    lines.append(title)
    if when:
        lines.append(f"Időpont: {when}")
    lines.extend(["-" * 26, message, "=" * 26])
    return "\n".join(lines)
