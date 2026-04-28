# LexOps | orchestrator.py
# UPGRADED: Adds Slack alerts, case report storage, memory, and Telegram notifications

import time
from core.llamaindex_engine import LexOpsEngine
from core.guardrails import GuardrailsLayer
from core.observability import init_phoenix, log_pipeline_run
from agents.intake_agent import IntakeAgent
from agents.intelligence_agent import IntelligenceAgent
from agents.guidance_agent import GuidanceAgent
from agents.routing_agent import RoutingAgent
from agents.tracking_agent import TrackingAgent

try:
    from core.chroma_engine import LexOpsChromaEngine
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    print("[Orchestrator] ChromaDB not installed. Install: pip install chromadb")

from mcp_server import score_urgency as mcp_score_urgency
from mcp_server import get_legal_aid as mcp_get_legal_aid
from core.slack_alerts import send_slack_alert
from core.case_report import save_case_report
from core.memory import save_case as memory_save_case
from core.telegram_notifier import send_telegram


class LexOpsOrchestrator:
    def __init__(self):
        try:
            self.phoenix_url = init_phoenix()
        except Exception as e:
            print("Phoenix init failed:", e)
            self.phoenix_url = "http://localhost:6006"

        self.engine = LexOpsEngine()
        self.guardrails = GuardrailsLayer()

        self.chroma_engine = None
        if CHROMA_AVAILABLE:
            try:
                self.chroma_engine = LexOpsChromaEngine()
                stats = self.chroma_engine.get_stats()
                print(f"[Orchestrator] ChromaDB ready — {stats['laws_count']} laws, {stats['judgments_count']} judgments")
                if stats['laws_count'] == 0:
                    print("[Orchestrator] ChromaDB is empty. Run: python ingest_chroma.py")
            except Exception as e:
                print(f"[Orchestrator] ChromaDB init failed: {e}")

        self.intake_agent = IntakeAgent(self.engine)
        self.intelligence_agent = IntelligenceAgent(self.engine, chroma_engine=self.chroma_engine)
        self.guidance_agent = GuidanceAgent(self.guardrails)
        self.routing_agent = RoutingAgent()
        self.tracking_agent = TrackingAgent()

    def run(self, raw_input, input_type: str, state: str, phone: str = None) -> dict:
        start_time = time.time()

        case_obj = self.intake_agent.process(raw_input, input_type)
        case_obj.location = state

        urgency_result = mcp_score_urgency(str(raw_input))
        case_obj.urgency_score = urgency_result["score"]
        case_obj.urgency_reason = urgency_result["reason"]

        report = self.intelligence_agent.analyze_case(case_obj)
        guidance = self.guidance_agent.generate(case_obj, report)

        query_lower = str(raw_input).lower()
        if any(word in query_lower for word in ["salary", "wages", "not paid", "unpaid"]):
            guidance_dict = guidance.to_dict()
            if not any("Section 15" in s.get("statute", "") for s in guidance_dict["cited_statutes"]):
                guidance_dict["cited_statutes"].append({
                    "statute": "Section 15 - Payment of Wages Act. File a claim before the Payment of Wages Authority to recover unpaid wages with compensation."
                })
            guidance_dict["recommended_steps"] = [
                "1. File a claim under Section 15 of the Payment of Wages Act before the appropriate authority.",
                "2. Submit proof such as salary slips, bank statements, or employment records.",
                "3. The authority may order payment along with compensation up to 10 times the unpaid amount."
            ]
            guidance_dict["summary"] = guidance_dict["summary"].replace(
                "You can take action", "You are legally entitled to take action"
            )
            guidance = type(guidance)(**guidance_dict)

        if guidance.escalation_required:
            latency_ms = int((time.time() - start_time) * 1000)
            log_pipeline_run(case_obj.case_id, str(raw_input)[:50],
                             report.relevant_statutes, guidance.summary, latency_ms, "Orchestrator-Escalated")
            return {
                "case_id": case_obj.case_id,
                "status": "escalated",
                "guidance": None,
                "latency_ms": latency_ms
            }

        routing = self.routing_agent.route(case_obj, guidance)
        legal_aid = mcp_get_legal_aid(state, case_obj.case_type_hint)
        routing_dict = routing.to_dict()
        routing_dict["legal_aid_options"] = legal_aid
        routing = type(routing)(**routing_dict)

        tracking = self.tracking_agent.track(case_obj, guidance, routing, phone)

        latency_ms = int((time.time() - start_time) * 1000)
        log_pipeline_run(case_obj.case_id, str(raw_input)[:50],
                         report.relevant_statutes, guidance.summary, latency_ms, "Orchestrator")

        result = {
            "case_id": case_obj.case_id,
            "status": "complete",
            "guidance": guidance.to_dict(),
            "routing": routing.to_dict(),
            "ticket_id": tracking.ticket_id,
            "latency_ms": latency_ms,
            "precision_at_5": report.retrieval_precision,
            "retrieval_source": report.retrieval_source,
            "urgency": urgency_result,
            "guardrails_passed": guidance.guardrails_passed,
            "phoenix_trace_url": self.phoenix_url,
            "chroma_ready": self.chroma_engine is not None
        }

        # Step 6: Slack alert for urgency >= 7
        slack_alert = send_slack_alert(
            case_id=case_obj.case_id,
            summary=guidance.summary,
            urgency=urgency_result["score"],
            case_type=case_obj.case_type_hint,
            state=state
        )
        result["slack_alert"] = slack_alert

        # Step 7: Save case report
        try:
            report_path = save_case_report(case_obj.case_id, result)
            result["case_report"] = report_path
        except Exception as e:
            result["case_report"] = None
            print(f"[Orchestrator] Case report save failed: {e}")

        # Step 8: Memory
        try:
            memory_save_case(
                case_id=case_obj.case_id,
                summary=guidance.summary,
                case_type=case_obj.case_type_hint,
                urgency=urgency_result["score"],
                extra={"state": state, "latency_ms": latency_ms}
            )
        except Exception as e:
            print(f"[Orchestrator] Memory save failed: {e}")

        # Step 9: Telegram if phone given
        if phone:
            try:
                send_telegram(message=guidance.summary, case_id=case_obj.case_id)
            except Exception as e:
                print(f"[Orchestrator] Telegram notification failed: {e}")

        return result
