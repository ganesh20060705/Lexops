# LexOps | core/email_intake.py

import os
import imaplib
import email
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_PASS", "")

# ── Simulated email cases ────────────────────────────────────────────────────

SIMULATED_EMAILS = [
    {
        "id": "sim_001",
        "from": "ramesh.kumar@example.com",
        "subject": "Salary not paid for 4 months",
        "body": (
            "Dear Sir/Madam, I am Ramesh Kumar, employed as a factory worker in Chennai. "
            "My employer has not paid my salary for the last 4 months (December 2024 to March 2025). "
            "The total unpaid amount is Rs. 48,000. I have reminded my employer multiple times but "
            "he refuses to pay. I have 2 kids and cannot afford this delay. Please help me file a "
            "complaint and recover my wages under the Payment of Wages Act."
        ),
        "state": "Tamil Nadu",
        "case_type_hint": "labour"
    },
    {
        "id": "sim_002",
        "from": "priya.sharma@example.com",
        "subject": "Online fraud - lost Rs 75,000 on fake investment site",
        "body": (
            "Hello LexOps team. My name is Priya Sharma from Pune. I was contacted on WhatsApp "
            "by someone claiming to be a SEBI-registered investment advisor. I transferred Rs 75,000 "
            "to their 'trading account' over 3 transactions. After that, they stopped responding and "
            "the website disappeared. I have screenshots of all conversations and bank receipts. "
            "I want to file a cybercrime complaint and recover my money. What steps should I take?"
        ),
        "state": "Maharashtra",
        "case_type_hint": "cyber"
    }
]


def get_simulated_emails() -> list[dict]:
    """
    Return realistic simulated email cases for demo/testing.

    Returns:
        List of simulated email case dicts
    """
    return SIMULATED_EMAILS.copy()


def fetch_gmail_cases(max_emails: int = 5) -> list[dict]:
    """
    Fetch unread emails from Gmail via IMAP (optional integration).
    Falls back to simulation mode if credentials are not set.

    Args:
        max_emails: Maximum number of emails to fetch

    Returns:
        List of case dicts extracted from emails
    """
    if not GMAIL_USER or not GMAIL_PASS:
        print("[EmailIntake] No Gmail credentials. Using simulation mode.")
        return get_simulated_emails()

    cases = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("inbox")

        _, message_numbers = mail.search(None, "UNSEEN")
        ids = message_numbers[0].split()[-max_emails:]

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject_raw, encoding = decode_header(msg["Subject"])[0]
            subject = subject_raw.decode(encoding or "utf-8") if isinstance(subject_raw, bytes) else subject_raw

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            cases.append({
                "id": num.decode(),
                "from": msg.get("From", ""),
                "subject": subject,
                "body": body[:2000],
                "state": "Unknown",
                "case_type_hint": "general"
            })

        mail.logout()
    except Exception as e:
        print(f"[EmailIntake] Gmail error: {e}. Falling back to simulation.")
        return get_simulated_emails()

    return cases if cases else get_simulated_emails()


def parse_email_to_query(email_case: dict) -> str:
    """
    Convert an email case dict to a plain text query for the orchestrator.

    Args:
        email_case: Dict with subject and body keys

    Returns:
        Combined query string
    """
    return f"{email_case.get('subject', '')}. {email_case.get('body', '')}"
