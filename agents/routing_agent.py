from pydantic import BaseModel
from typing import List, Dict, Any
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.core import Settings
from .intake_agent import CaseObject
from .guidance_agent import GuidanceOutput
import json

class RoutingDecision(BaseModel):
    case_id: str
    primary_court: dict
    alternative_courts: list[dict]
    limitation_check: dict
    legal_aid_options: list[dict]
    mediation_required: bool
    confidence_score: float
    routing_reasoning: str
    next_action: str
    status: str = "routing_complete"
    
    def to_dict(self):
        return self.model_dump()

def determine_court(case_type: str, claim_value: str, state: str) -> dict:
    case_type = case_type.lower()
    claim_val = 0
    try:
        if "cr" in claim_value.lower():
            claim_val = float(claim_value.lower().replace("cr", "").strip()) * 10000000
        else:
            claim_val = float(claim_value)
    except:
        pass
        
    if "consumer" in case_type:
        if claim_val < 10000000:
            return {"court_name": "District Consumer Disputes Redressal Commission", "jurisdiction_level": "District", "filing_fee_range": "Rs. 0 - 500", "online_portal_url": "edaakhil.nic.in"}
        elif claim_val <= 100000000:
            return {"court_name": "State Consumer Commission", "jurisdiction_level": "State", "filing_fee_range": "Rs. 2000 - 4000", "online_portal_url": "edaakhil.nic.in"}
        else:
            return {"court_name": "National Consumer Commission (NCDRC)", "jurisdiction_level": "National", "filing_fee_range": "Rs. 5000+", "online_portal_url": "ncdrc.nic.in"}
    elif "labour" in case_type:
        return {"court_name": "Labour Court / Industrial Tribunal", "jurisdiction_level": "District/State", "filing_fee_range": "Minimal", "online_portal_url": "samadhan.labour.gov.in"}
    elif "family" in case_type:
        return {"court_name": "Family Court", "jurisdiction_level": "District", "filing_fee_range": "Minimal", "online_portal_url": "None"}
    elif "property" in case_type or "land" in case_type or "rent" in case_type:
        return {"court_name": "Civil Court", "jurisdiction_level": "District", "filing_fee_range": "Based on claim", "online_portal_url": "None"}
    elif "criminal" in case_type:
        return {"court_name": "Magistrate Court or Sessions Court", "jurisdiction_level": "District", "filing_fee_range": "N/A", "online_portal_url": "None"}
    elif "cyber" in case_type:
        return {"court_name": "Cyber Crime Cell", "jurisdiction_level": "District/State", "filing_fee_range": "None", "online_portal_url": "cybercrime.gov.in"}
    else:
        return {"court_name": "District Court", "jurisdiction_level": "District", "filing_fee_range": "Varies", "online_portal_url": "None"}

def check_limitation_period(case_type: str, incident_date: str) -> dict:
    case_type = case_type.lower()
    days_rem = 365
    is_barred = False
    warning = ""
    section = "Unknown"
    
    if "consumer" in case_type:
        section = "Section 69 Consumer Protection Act 2019"
        days_rem = 730
    elif "property" in case_type:
        section = "Article 65 Limitation Act 1963"
        days_rem = 4380
    else:
        section = "Limitation Act 1963"
        days_rem = 1095
        
    return {
        "is_time_barred": is_barred,
        "days_remaining": days_rem,
        "limitation_act_section": section,
        "warning": warning
    }

def find_legal_aid(state: str, case_type: str) -> list:
    return [
        {"name": f"{state} State Legal Services Authority", "helpline": "15100", "type": "SLSA"},
        {"name": "National Legal Services Authority (NALSA)", "helpline": "15100", "type": "National"}
    ]

def check_mandatory_mediation(case_type: str) -> dict:
    case_type = case_type.lower()
    if "family" in case_type or "commercial" in case_type:
        return {"required": True, "mediation_body": "Court Annexed Mediation Centre", "typical_duration": "60-90 days"}
    return {"required": False, "mediation_body": "None", "typical_duration": "0 days"}

class RoutingAgent:
    def __init__(self):
        self.court_tool = FunctionTool.from_defaults(fn=determine_court)
        self.limit_tool = FunctionTool.from_defaults(fn=check_limitation_period)
        self.aid_tool = FunctionTool.from_defaults(fn=find_legal_aid)
        self.mediation_tool = FunctionTool.from_defaults(fn=check_mandatory_mediation)
        
    def route(self, case_obj: CaseObject, guidance: GuidanceOutput) -> RoutingDecision:
        try:
            # Emulating the AgentRunner using the tools for reliability.
            c_type = case_obj.case_type_hint
            state = case_obj.location
            claim = "0"
            
            court = determine_court(c_type, claim, state)
            limit = check_limitation_period(c_type, "unknown")
            aid = find_legal_aid(state, c_type)
            med = check_mandatory_mediation(c_type)
            
            reasoning = f"Case is {c_type}. Routed to {court['court_name']}."
            action = "file_immediately"
            if med['required']:
                action = "seek_mediation"
            if limit['is_time_barred']:
                action = "time_barred_review"
                
            return RoutingDecision(
                case_id=case_obj.case_id,
                primary_court=court,
                alternative_courts=[],
                limitation_check=limit,
                legal_aid_options=aid,
                mediation_required=med["required"],
                confidence_score=0.9,
                routing_reasoning=reasoning,
                next_action=action,
                status="routing_complete"
            )
        except Exception as e:
            print("Routing Error:", e)
            return RoutingDecision(
                case_id=case_obj.case_id,
                primary_court={},
                alternative_courts=[],
                limitation_check={},
                legal_aid_options=[],
                mediation_required=False,
                confidence_score=0.0,
                routing_reasoning="Error in routing",
                next_action="consult_lawyer",
                status="routing_failed"
            )
