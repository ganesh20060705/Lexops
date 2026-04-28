# LexOps | mcp_server.py
# NEW: MCP (Model Context Protocol) Server
# Exposes LexOps tools so any MCP-compatible client (Claude Desktop, etc.) can call them

"""
LexOps MCP Server
-----------------
Tools exposed:
1. search_law           - Search Indian laws in ChromaDB
2. get_court            - Get the right court for a case type
3. check_limitation     - Check if a case is time-barred
4. create_ticket        - Save a case to the database
5. send_whatsapp        - Send WhatsApp notification via Twilio
6. score_urgency        - Rate urgency of a legal situation (1-10)
7. get_legal_aid        - Get free legal aid options by state
8. check_scope          - Check if a query is within LexOps scope

Run this server:
    python mcp_server.py

Connect from Claude Desktop by adding to claude_desktop_config.json:
{
  "mcpServers": {
    "lexops": {
      "command": "python",
      "args": ["/path/to/lexops/mcp_server.py"]
    }
  }
}
"""

import os
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── MCP SDK import ──────────────────────────────────────────────────────────
try:
    from mcp.server.fastmcp import FastMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("[MCP] mcp package not installed. Run: pip install mcp")

# ── ChromaDB engine ─────────────────────────────────────────────────────────
try:
    from core.chroma_engine import LexOpsChromaEngine
    _chroma = LexOpsChromaEngine()
    CHROMA_READY = True
except Exception as e:
    print(f"[MCP] ChromaDB not ready: {e}")
    _chroma = None
    CHROMA_READY = False

# ── Database path ────────────────────────────────────────────────────────────
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./lexops.db").replace("sqlite:///", "")


# ═══════════════════════════════════════════════════════════════════════════
# TOOL FUNCTIONS
# These are plain Python functions — used both by the MCP server
# AND called directly by agents inside the pipeline.
# ═══════════════════════════════════════════════════════════════════════════

def search_law(query: str, act_filter: str = None, top_k: int = 5) -> list[dict]:
    """
    Search Indian law database for relevant statutes.

    Args:
        query:      The legal question or problem description
        act_filter: Optional - filter to a specific act (e.g. 'Payment Of Wages Act')
        top_k:      Number of results to return (default 5)

    Returns:
        List of matching statute sections with act name, section number, and similarity score
    """
    if not CHROMA_READY or _chroma is None:
        return [{"error": "ChromaDB not initialized. Run ingest_chroma.py first."}]

    results = _chroma.search_laws(query, act_filter=act_filter, top_k=top_k)

    if not results:
        return [{"message": "No matching statutes found. Try a broader query."}]

    return results


def get_court(case_type: str, claim_value: str = "0", state: str = "Unknown") -> dict:
    """
    Determine the correct court or legal authority for a case.

    Args:
        case_type:   Type of case (consumer, labour, family, property, criminal, cyber, general)
        claim_value: Monetary claim in rupees (e.g. '500000' for 5 lakh)
        state:       State where the case is filed

    Returns:
        Dict with court name, jurisdiction level, filing fee, and online portal URL
    """
    case_type = case_type.lower()

    # Parse claim value
    claim_val = 0
    try:
        if "cr" in str(claim_value).lower():
            claim_val = float(str(claim_value).lower().replace("cr", "").strip()) * 10_000_000
        elif "lakh" in str(claim_value).lower():
            claim_val = float(str(claim_value).lower().replace("lakh", "").strip()) * 100_000
        else:
            claim_val = float(claim_value)
    except Exception:
        pass

    if "consumer" in case_type:
        if claim_val < 10_000_000:
            court = {
                "court_name": "District Consumer Disputes Redressal Commission",
                "jurisdiction_level": "District",
                "filing_fee_range": "Rs. 0 – 500",
                "online_portal_url": "https://edaakhil.nic.in",
                "address_tip": f"File at the District Consumer Forum in {state}"
            }
        elif claim_val <= 100_000_000:
            court = {
                "court_name": "State Consumer Disputes Redressal Commission",
                "jurisdiction_level": "State",
                "filing_fee_range": "Rs. 2,000 – 4,000",
                "online_portal_url": "https://edaakhil.nic.in",
                "address_tip": f"File at the State Commission in {state} capital"
            }
        else:
            court = {
                "court_name": "National Consumer Disputes Redressal Commission (NCDRC)",
                "jurisdiction_level": "National",
                "filing_fee_range": "Rs. 5,000+",
                "online_portal_url": "https://ncdrc.nic.in",
                "address_tip": "File in New Delhi"
            }

    elif "labour" in case_type or "wage" in case_type or "employment" in case_type:
        court = {
            "court_name": "Labour Court / Industrial Tribunal",
            "jurisdiction_level": "District/State",
            "filing_fee_range": "Minimal or free",
            "online_portal_url": "https://samadhan.labour.gov.in",
            "address_tip": "Contact the Payment of Wages Authority in your district"
        }

    elif "family" in case_type or "divorce" in case_type or "domestic" in case_type:
        court = {
            "court_name": "Family Court",
            "jurisdiction_level": "District",
            "filing_fee_range": "Minimal",
            "online_portal_url": "None (visit court in person)",
            "address_tip": "Family courts are at the District Court complex"
        }

    elif "property" in case_type or "land" in case_type or "rent" in case_type or "rera" in case_type:
        court = {
            "court_name": "RERA Authority / Civil Court",
            "jurisdiction_level": "State",
            "filing_fee_range": "Based on claim value",
            "online_portal_url": f"https://rera.{state.lower().replace(' ', '')}.gov.in",
            "address_tip": "Check state RERA authority website"
        }

    elif "criminal" in case_type or "fir" in case_type or "ipc" in case_type:
        court = {
            "court_name": "Magistrate Court / Sessions Court",
            "jurisdiction_level": "District",
            "filing_fee_range": "N/A (file FIR at police station first)",
            "online_portal_url": "None",
            "address_tip": "File an FIR at the nearest police station first"
        }

    elif "cyber" in case_type or "online fraud" in case_type or "it act" in case_type:
        court = {
            "court_name": "Cyber Crime Cell",
            "jurisdiction_level": "District/State",
            "filing_fee_range": "Free",
            "online_portal_url": "https://cybercrime.gov.in",
            "address_tip": "File complaint online at cybercrime.gov.in — available 24/7"
        }

    elif "ip" in case_type or "trademark" in case_type or "copyright" in case_type:
        court = {
            "court_name": "Intellectual Property Appellate Board / High Court",
            "jurisdiction_level": "State/National",
            "filing_fee_range": "Varies",
            "online_portal_url": "https://ipindia.gov.in",
            "address_tip": "Contact a specialized IP lawyer"
        }

    else:
        court = {
            "court_name": "District Court",
            "jurisdiction_level": "District",
            "filing_fee_range": "Varies by claim",
            "online_portal_url": "None",
            "address_tip": "Consult NALSA helpline 15100 for guidance"
        }

    court["state"] = state
    return court


def check_limitation(case_type: str) -> dict:
    """
    Check the limitation period for a case type under the Limitation Act 1963.

    Args:
        case_type: Type of case (consumer, property, labour, criminal, cyber, general)

    Returns:
        Dict with limitation period, applicable section, and whether case may be time-barred
    """
    case_type = case_type.lower()

    if "consumer" in case_type:
        return {
            "period": "2 years from date of cause of action",
            "days": 730,
            "act_section": "Section 69 – Consumer Protection Act, 2019",
            "note": "Delay can be condoned if sufficient cause is shown",
            "is_time_barred_warning": False
        }
    elif "property" in case_type or "land" in case_type:
        return {
            "period": "12 years for possession; 3 years for recovery of money",
            "days": 4380,
            "act_section": "Article 65 – Limitation Act, 1963",
            "note": "Start date is when right to sue accrued",
            "is_time_barred_warning": False
        }
    elif "labour" in case_type or "wage" in case_type or "employment" in case_type:
        return {
            "period": "1 year from date of claim arising",
            "days": 365,
            "act_section": "Section 15 – Payment of Wages Act, 1936",
            "note": "File with Payment of Wages Authority in your district",
            "is_time_barred_warning": False
        }
    elif "criminal" in case_type or "ipc" in case_type:
        return {
            "period": "Varies (FIR can be filed anytime for serious offences)",
            "days": 0,
            "act_section": "Section 468 – Code of Criminal Procedure",
            "note": "For minor offences, 6-month limit applies",
            "is_time_barred_warning": False
        }
    elif "cyber" in case_type or "it act" in case_type:
        return {
            "period": "3 years from date of offence",
            "days": 1095,
            "act_section": "Limitation Act, 1963 read with IT Act, 2000",
            "note": "File FIR and complaint at cybercrime.gov.in immediately",
            "is_time_barred_warning": False
        }
    else:
        return {
            "period": "3 years (general contract/civil disputes)",
            "days": 1095,
            "act_section": "Article 113 – Limitation Act, 1963",
            "note": "Consult a lawyer for your specific situation",
            "is_time_barred_warning": False
        }


def create_ticket(case_id: str, case_type: str, summary: str,
                  urgency: int = 5, court: str = "Unknown",
                  phone: str = "") -> dict:
    """
    Save a new case ticket to the LexOps database.

    Args:
        case_id:   Unique case ID (UUID)
        case_type: Type of case
        summary:   Brief summary of guidance given
        urgency:   Urgency score 1-10
        court:     Assigned court name
        phone:     Contact phone number (optional)

    Returns:
        Dict confirming ticket creation with ticket ID and tracking URL
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Create table if it doesn't exist (safe to run multiple times)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                created_at TEXT,
                status TEXT,
                case_type TEXT,
                urgency_score INTEGER,
                assigned_court TEXT,
                guidance_summary TEXT,
                contact_phone TEXT,
                last_updated TEXT
            )
        """)

        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO cases
            (case_id, created_at, status, case_type, urgency_score,
             assigned_court, guidance_summary, contact_phone, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (case_id, now, "new", case_type, urgency, court, summary, phone, now))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "ticket_id": case_id,
            "tracking_url": f"/case/{case_id}",
            "status": "new",
            "message": "Case ticket created successfully"
        }

    except Exception as e:
        return {"success": False, "error": str(e), "ticket_id": case_id}


def send_whatsapp(phone: str, message: str, case_id: str = "") -> dict:
    """
    Send a WhatsApp notification to the user via Twilio.

    Args:
        phone:   Phone number with country code (e.g. +919876543210)
        message: Message to send
        case_id: Optional case ID to include in message

    Returns:
        Dict with success status and message SID (or simulation note)
    """
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_phone = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    full_message = f"LexOps Legal Aid"
    if case_id:
        full_message += f" | Case #{case_id[:8]}"
    full_message += f"\n\n{message}\n\nHelpline: NALSA 15100"

    # Normalize phone number
    to_phone = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"

    if twilio_sid and twilio_token and twilio_sid != "your_twilio_sid":
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            msg = client.messages.create(
                body=full_message,
                from_=from_phone,
                to=to_phone
            )
            return {
                "success": True,
                "message_sid": msg.sid,
                "to": to_phone,
                "note": "Message sent via Twilio WhatsApp"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "note": "Twilio error"}
    else:
        # Simulation mode — no real Twilio credentials
        print(f"[WhatsApp SIMULATION] To: {to_phone}")
        print(f"[WhatsApp SIMULATION] Message: {full_message}")
        return {
            "success": True,
            "simulated": True,
            "to": to_phone,
            "message": full_message,
            "note": "Simulated — add real Twilio credentials in .env to send"
        }


def score_urgency(text: str) -> dict:
    """
    Score the urgency of a legal situation from 1 (low) to 10 (critical).

    Args:
        text: The raw problem description from the user

    Returns:
        Dict with urgency score, level label, reason, and recommended response time
    """
    text_lower = text.lower()

    score = 5  # default: medium
    reason = "Standard legal matter"
    response_days = 14

    # Critical patterns (score 9-10)
    critical = ["arrested", "in jail", "custody", "bail", "eviction today",
                "suicide", "violence", "abuse", "domestic violence",
                "kidnapping", "death threat", "emergency"]
    if any(p in text_lower for p in critical):
        score = 9
        reason = "Immediate risk detected — emergency response needed"
        response_days = 0

    # High urgency (score 7-8)
    elif any(p in text_lower for p in ["eviction", "termination", "dismissed",
                                        "cheated", "fraud", "stolen", "fir",
                                        "not paid for months", "court date"]):
        score = 7
        reason = "Significant legal harm in progress"
        response_days = 3

    # Medium (score 4-6)
    elif any(p in text_lower for p in ["salary", "wages", "not paid",
                                        "dispute", "complaint", "notice"]):
        score = 5
        reason = "Active legal dispute — timely action recommended"
        response_days = 7

    # Low (score 1-3)
    else:
        score = 3
        reason = "General legal query — can be handled at your convenience"
        response_days = 21

    levels = {9: "CRITICAL", 7: "HIGH", 5: "MEDIUM", 3: "LOW"}
    level = levels.get(score, "MEDIUM")

    return {
        "score": score,
        "level": level,
        "reason": reason,
        "recommended_response_days": response_days,
        "tip": "Contact NALSA helpline 15100 for free legal aid" if score >= 7 else ""
    }


def get_legal_aid(state: str, case_type: str = "general") -> list[dict]:
    """
    Get free legal aid organizations available for a given state and case type.

    Args:
        state:     Indian state name
        case_type: Type of case

    Returns:
        List of legal aid organizations with name, type, and helpline
    """
    aid_list = [
        {
            "name": f"{state} State Legal Services Authority (SLSA)",
            "type": "Government",
            "helpline": "15100",
            "website": "https://nalsa.gov.in",
            "eligibility": "Free for SC/ST, women, children, disabled, income < 1 lakh/year"
        },
        {
            "name": "National Legal Services Authority (NALSA)",
            "type": "Government",
            "helpline": "15100",
            "website": "https://nalsa.gov.in",
            "eligibility": "Free for eligible persons across India"
        }
    ]

    # Add specialized resources by case type
    if "consumer" in case_type.lower():
        aid_list.append({
            "name": "Consumer Helpline",
            "type": "Government",
            "helpline": "1800-11-4000",
            "website": "https://consumerhelpline.gov.in",
            "eligibility": "All consumers — free"
        })
    elif "cyber" in case_type.lower():
        aid_list.append({
            "name": "National Cyber Crime Reporting Portal",
            "type": "Government",
            "helpline": "1930",
            "website": "https://cybercrime.gov.in",
            "eligibility": "All — free online complaint filing"
        })
    elif "labour" in case_type.lower() or "wage" in case_type.lower():
        aid_list.append({
            "name": "Labour Commissioner Office",
            "type": "Government",
            "helpline": "1800-11-2142",
            "website": "https://labour.gov.in",
            "eligibility": "All workers — free conciliation services"
        })
    elif "domestic" in case_type.lower() or "family" in case_type.lower():
        aid_list.append({
            "name": "National Commission for Women",
            "type": "Government",
            "helpline": "7827170170",
            "website": "https://ncw.nic.in",
            "eligibility": "Women facing domestic violence or harassment — free"
        })

    return aid_list


def check_scope(query: str) -> dict:
    """
    Check whether a legal query is within LexOps scope.

    Args:
        query: The user's legal problem description

    Returns:
        Dict with in_scope (bool), reason if out of scope, and escalation message
    """
    query_lower = query.lower()

    out_of_scope_patterns = {
        "criminal_defense": ["get acquitted", "defend murder", "avoid jail", "escape charges"],
        "ongoing_litigation": ["my case is in court", "what should i say in court", "ongoing litigation"],
        "property_valuation": ["how much is my land worth", "property valuation", "market value"],
        "investment_advice": ["should i invest", "stock market", "mutual fund"],
        "tax_advice": ["how much tax", "tax evasion", "income tax return"]
    }

    for reason, patterns in out_of_scope_patterns.items():
        if any(p in query_lower for p in patterns):
            return {
                "in_scope": False,
                "reason": reason,
                "escalation_message": (
                    f"LexOps cannot assist with {reason.replace('_', ' ')}. "
                    f"Please consult a qualified lawyer. NALSA helpline: 15100"
                )
            }

    return {
        "in_scope": True,
        "reason": None,
        "escalation_message": None
    }


# ═══════════════════════════════════════════════════════════════════════════
# NEW TOOL FUNCTIONS (9-12)
# ═══════════════════════════════════════════════════════════════════════════

def send_telegram(phone_or_chat: str, message: str, case_id: str = "") -> dict:
    """
    Send a Telegram notification (replaces send_whatsapp / Twilio).

    Args:
        phone_or_chat: Telegram chat_id or user identifier
        message:       Message text to send
        case_id:       Optional case ID

    Returns:
        Dict with success status and delivery note
    """
    from core.telegram_notifier import send_telegram as _send_tg
    return _send_tg(message=message, case_id=case_id, chat_id=phone_or_chat or None)


def email_intake(max_emails: int = 5) -> list[dict]:
    """
    Fetch pending legal cases from email inbox (simulation or Gmail).

    Args:
        max_emails: Maximum number of emails to fetch (default 5)

    Returns:
        List of email case dicts with subject, body, state, case_type_hint
    """
    from core.email_intake import fetch_gmail_cases
    return fetch_gmail_cases(max_emails=max_emails)


def send_slack_alert(case_id: str, summary: str, urgency: int,
                     case_type: str = "general", state: str = "") -> dict:
    """
    Send a Slack alert for high-urgency cases (urgency >= 7).

    Args:
        case_id:   Unique case identifier
        summary:   Brief guidance summary
        urgency:   Urgency score 1-10
        case_type: Type of legal case
        state:     State where case is filed

    Returns:
        Dict with triggered flag, success, and urgency level
    """
    from core.slack_alerts import send_slack_alert as _slack
    return _slack(case_id=case_id, summary=summary, urgency=urgency,
                  case_type=case_type, state=state)


def save_case_report(case_id: str, summary: str, guidance_steps: list = None,
                     court: str = "", urgency: int = 5) -> dict:
    """
    Save a structured case report as a .txt file.

    Args:
        case_id:        Case identifier
        summary:        Guidance summary text
        guidance_steps: List of recommended action steps
        court:          Assigned court name
        urgency:        Urgency score

    Returns:
        Dict with success status and file path
    """
    from core.case_report import save_case_report as _save_report
    mock_result = {
        "case_id": case_id,
        "status": "complete",
        "guidance": {
            "summary": summary,
            "recommended_steps": guidance_steps or [],
            "cited_statutes": [],
            "disclaimer": "This is for informational purposes only. Consult a qualified lawyer."
        },
        "routing": {
            "primary_court": {"court_name": court, "jurisdiction_level": "District",
                               "filing_fee_range": "Varies", "online_portal_url": "N/A",
                               "address_tip": ""},
            "legal_aid_options": []
        },
        "urgency": {"score": urgency, "level": "HIGH" if urgency >= 7 else "MEDIUM",
                    "reason": "", "recommended_response_days": 7},
        "latency_ms": 0
    }
    try:
        path = _save_report(case_id, mock_result)
        return {"success": True, "file_path": path, "case_id": case_id}
    except Exception as e:
        return {"success": False, "error": str(e), "case_id": case_id}


# ═══════════════════════════════════════════════════════════════════════════
# MCP SERVER SETUP
# ═══════════════════════════════════════════════════════════════════════════

if MCP_AVAILABLE:
    mcp = FastMCP("LexOps Legal AI")

    # Register all 12 tools with the MCP server
    mcp.tool()(search_law)
    mcp.tool()(get_court)
    mcp.tool()(check_limitation)
    mcp.tool()(create_ticket)
    mcp.tool()(send_whatsapp)
    mcp.tool()(score_urgency)
    mcp.tool()(get_legal_aid)
    mcp.tool()(check_scope)
    # NEW tools (9-12)
    mcp.tool()(send_telegram)
    mcp.tool()(email_intake)
    mcp.tool()(send_slack_alert)
    mcp.tool()(save_case_report)


if __name__ == "__main__":
    if MCP_AVAILABLE:
        print("[LexOps MCP Server] Starting...")
        print("[LexOps MCP Server] Tools: search_law, get_court, check_limitation,")
        print("                           create_ticket, send_whatsapp, score_urgency,")
        print("                           get_legal_aid, check_scope")
        mcp.run()
    else:
        print("Install MCP: pip install mcp")
        print("Verifying tool functions work independently...")
        # Test tools without MCP
        print(score_urgency("My employer has not paid my salary for 3 months"))
        print(get_court("labour", "0", "Tamil Nadu"))
        print(check_limitation("labour"))
