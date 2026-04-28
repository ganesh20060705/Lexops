# LexOps | core/case_report.py
# Save structured case reports as .txt files for download

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")


def save_case_report(case_id: str, orchestrator_result: dict) -> str:
    """
    Save a structured case report as a .txt file.

    Args:
        case_id:            The case identifier
        orchestrator_result: Full result dict from LexOpsOrchestrator.run()

    Returns:
        Absolute path to the saved report file
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    guidance = orchestrator_result.get("guidance") or {}
    routing = orchestrator_result.get("routing") or {}
    urgency = orchestrator_result.get("urgency") or {}
    primary_court = routing.get("primary_court") or {}

    lines = [
        "=" * 60,
        "         LEXOPS LEGAL CASE REPORT",
        "=" * 60,
        f"Case ID       : {case_id}",
        f"Generated At  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Status        : {orchestrator_result.get('status', 'unknown').upper()}",
        f"Latency       : {orchestrator_result.get('latency_ms', 0)} ms",
        "-" * 60,
        "",
        "URGENCY ASSESSMENT",
        "-" * 60,
        f"Score  : {urgency.get('score', 'N/A')} / 10  [{urgency.get('level', 'N/A')}]",
        f"Reason : {urgency.get('reason', 'N/A')}",
        f"Recommended Response : Within {urgency.get('recommended_response_days', 'N/A')} day(s)",
        "",
        "LEGAL GUIDANCE SUMMARY",
        "-" * 60,
        guidance.get("summary", "No summary available."),
        "",
        "RECOMMENDED STEPS",
        "-" * 60,
    ]

    for step in guidance.get("recommended_steps", []):
        lines.append(f"  {step}")

    lines += [
        "",
        "CITED STATUTES",
        "-" * 60,
    ]

    for statute in guidance.get("cited_statutes", []):
        s = statute.get("statute", str(statute))
        lines.append(f"  • {s}")

    lines += [
        "",
        "COURT ROUTING",
        "-" * 60,
        f"Court      : {primary_court.get('court_name', 'N/A')}",
        f"Level      : {primary_court.get('jurisdiction_level', 'N/A')}",
        f"Filing Fee : {primary_court.get('filing_fee_range', 'N/A')}",
        f"Portal     : {primary_court.get('online_portal_url', 'N/A')}",
        f"Tip        : {primary_court.get('address_tip', 'N/A')}",
        "",
        "LEGAL AID OPTIONS",
        "-" * 60,
    ]

    for aid in routing.get("legal_aid_options", []):
        lines.append(f"  • {aid.get('name')} — Helpline: {aid.get('helpline', 'N/A')}")

    lines += [
        "",
        "DISCLAIMER",
        "-" * 60,
        guidance.get("disclaimer", "This report is for informational purposes only. Consult a qualified lawyer."),
        "",
        "=" * 60,
        "           NALSA Free Legal Aid: 15100",
        "=" * 60,
    ]

    report_path = os.path.join(REPORTS_DIR, f"case_{case_id[:12]}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[CaseReport] Saved: {report_path}")
    return report_path


def get_report_path(case_id: str) -> str:
    """Return the expected report path for a given case ID."""
    return os.path.join(REPORTS_DIR, f"case_{case_id[:12]}.txt")


def report_exists(case_id: str) -> bool:
    """Check whether a report file exists for a case."""
    return os.path.exists(get_report_path(case_id))
