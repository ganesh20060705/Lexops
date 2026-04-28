import os
import json
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from .intake_agent import CaseObject
from .guidance_agent import GuidanceOutput
from .routing_agent import RoutingDecision

Base = declarative_base()

class CaseTicket(Base):
    __tablename__ = "cases"
    case_id = Column(String, primary_key=True)
    created_at = Column(DateTime)
    status = Column(String)
    case_type = Column(String)
    urgency_score = Column(Integer)
    assigned_court = Column(String)
    parties = Column(JSON)
    guidance_summary = Column(Text)
    limitation_warning = Column(Boolean)
    last_updated = Column(DateTime)
    contact_phone = Column(String)
    notification_log = Column(JSON)

class TrackingResult(BaseModel):
    ticket_id: str
    tracking_url: str
    status: str = "tracking_complete"

class TrackingAgent:
    def __init__(self):
        db_url = os.getenv("DATABASE_URL", "sqlite:///./lexops.db")
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
    def send_notification(self, case_id: str, phone: str, message: str):
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_phone = os.getenv("TWILIO_WHATSAPP_FROM")
        
        msg_body = f"LexOps Update | Case #{case_id} | {message} | Reply HELP for assistance. NALSA Helpline: 15100"
        
        if twilio_sid and twilio_token and twilio_sid != "your_twilio_sid":
            try:
                from twilio.rest import Client
                client = Client(twilio_sid, twilio_token)
                client.messages.create(
                    body=msg_body,
                    from_=from_phone,
                    to=f"whatsapp:{phone}" if not phone.startswith("whatsapp:") else phone
                )
                print(f"[NOTIFICATION] Sent to {phone}")
            except Exception as e:
                print(f"[NOTIFICATION FAILED] {e}")
        else:
            print(f"[NOTIFICATION] {msg_body}")
            
    def create_ticket(self, case_obj: CaseObject, guidance: GuidanceOutput, routing: RoutingDecision, phone: str = None) -> str:
        session = self.Session()
        ticket = CaseTicket(
            case_id=case_obj.case_id,
            created_at=case_obj.created_at,
            status="routed",
            case_type=case_obj.case_type_hint,
            urgency_score=case_obj.urgency_score,
            assigned_court=routing.primary_court.get("court_name", "Unknown"),
            parties=case_obj.parties,
            guidance_summary=guidance.summary,
            limitation_warning=routing.limitation_check.get("is_time_barred", False),
            last_updated=datetime.now(),
            contact_phone=phone or "",
            notification_log=[]
        )
        session.add(ticket)
        session.commit()
        session.close()
        return case_obj.case_id

    def update_status(self, case_id: str, new_status: str, note: str):
        session = self.Session()
        ticket = session.query(CaseTicket).filter(CaseTicket.case_id == case_id).first()
        if ticket:
            ticket.status = new_status
            ticket.last_updated = datetime.now()
            
            log_entry = {"time": datetime.now().isoformat(), "status": new_status, "note": note}
            
            if not ticket.notification_log:
                ticket.notification_log = []
            
            new_log = list(ticket.notification_log)
            new_log.append(log_entry)
            ticket.notification_log = new_log
            
            session.commit()
            
            if ticket.contact_phone:
                self.send_notification(case_id, ticket.contact_phone, f"Status: {new_status} | {note}")
        session.close()

    def flag_stale_cases(self) -> list:
        session = self.Session()
        seven_days_ago = datetime.now() - timedelta(days=7)
        stale = session.query(CaseTicket).filter(
            CaseTicket.last_updated < seven_days_ago,
            CaseTicket.status != "closed"
        ).all()
        result = [t.case_id for t in stale]
        session.close()
        return result

    def get_case_summary(self, case_id: str) -> dict:
        session = self.Session()
        ticket = session.query(CaseTicket).filter(CaseTicket.case_id == case_id).first()
        if not ticket:
            session.close()
            return {}
            
        result = {
            "case_id": ticket.case_id,
            "status": ticket.status,
            "case_type": ticket.case_type,
            "urgency_score": ticket.urgency_score,
            "assigned_court": ticket.assigned_court,
            "parties": ticket.parties,
            "guidance_summary": ticket.guidance_summary,
            "limitation_warning": ticket.limitation_warning,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "last_updated": ticket.last_updated.isoformat() if ticket.last_updated else None,
            "notification_log": ticket.notification_log
        }
        session.close()
        return result

    def track(self, case_obj: CaseObject, guidance: GuidanceOutput, routing: RoutingDecision, phone: str = None) -> TrackingResult:
        self.create_ticket(case_obj, guidance, routing, phone)
        
        if phone:
            self.send_notification(case_obj.case_id, phone, "Intake confirmation complete. We are processing your request.")
            
        return TrackingResult(
            ticket_id=case_obj.case_id,
            tracking_url=f"/case/{case_obj.case_id}",
            status="tracking_complete"
        )
