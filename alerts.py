"""Build and send the Charter-case alert email.

Kept network code (send_email) separate from the pure formatting function
(format_alert_email) so the formatting can be unit-tested without a network.
"""
import smtplib
from email.message import EmailMessage

# Human-readable labels for the deadline "kind" codes from scc_parse.parse_schedule
KIND_LABELS = {
    "notice_of_appeal": "Notice of appeal filed",
    "ag_notice_of_intervention": "AG notice of intervention (constitutional question)",
    "appellant_factum": "Appellant's factum due",
    "respondent_factum": "Respondent's factum due",
    "intervention_motion": "Motion for leave to intervene due",
    "response_to_intervention_motions": "Responses to intervention motions due",
    "reply_on_intervention_motions": "Replies on intervention motions due",
    "intervener_factum": "Intervener factum due",
    "ag_intervener_factum": "AG intervener factum due",
    "other": "Other deadline",
}


def format_alert_email(cases: list[dict]) -> tuple[str, str]:
    """cases: [{case_no, title, granted_on, appeal_from, charter_basis, docket_url, deadlines: [(kind, due_date)]}]

    Returns (subject, plain-text body). Cases should already be sorted the way
    you want them to appear (run_monitor sorts by granted_on).
    """
    if not cases:
        return "", ""

    subject = (
        f"1 new Charter case granted leave to appeal at the SCC"
        if len(cases) == 1
        else f"{len(cases)} new Charter cases granted leave to appeal at the SCC"
    )

    lines = [
        "The Charter Intervention Monitor found the following newly granted case(s):",
        "",
    ]
    for c in cases:
        lines.append(f"{c['title']}")
        lines.append(f"  Case No. {c['case_no']}  |  leave granted {c['granted_on']}  |  from {c['appeal_from']}")
        lines.append(f"  {c['docket_url']}")
        if c["deadlines"]:
            most_relevant = next(
                (d for d in c["deadlines"] if d[0] == "intervention_motion"), c["deadlines"][0]
            )
            lines.append(f"  --> {KIND_LABELS.get(most_relevant[0], most_relevant[0])}: {most_relevant[1]}")
            lines.append("  All key dates:")
            for kind, due in c["deadlines"]:
                lines.append(f"    {due}  {KIND_LABELS.get(kind, kind)}")
        else:
            lines.append("  --> Deadlines not yet posted by the Registrar; will appear once published.")
        lines.append("")

    lines.append("-- A2J Charter Intervention Accelerator (SCC Charter Intervention Monitor)")
    return subject, "\n".join(lines)


def send_email(*, smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
               from_addr: str, to_addr: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises on any SMTP failure (caller decides what to do)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
