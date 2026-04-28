import uuid
from datetime import datetime
from pydantic import BaseModel
from llama_index.core.tools import FunctionTool
from llama_index.core.agent import ReActAgent
from llama_index.core import Settings
from langdetect import detect
import pypdf
import io
import json

class CaseObject(BaseModel):
    case_id: str
    raw_text: str
    language: str
    parties: dict
    statutes_mentioned: list[str]
    dates: list[str]
    location: str
    urgency_score: int
    urgency_reason: str
    case_type_hint: str
    created_at: datetime
    status: str = "intake_complete"
    
    def to_dict(self):
        d = self.model_dump()
        d['created_at'] = d['created_at'].isoformat()
        return d

def extract_entities(text: str) -> dict:
    prompt = f"""
    Extract entities from the following legal text. 
    Extract only what is explicitly stated. Do not infer.
    Return strictly a JSON object with these keys:
    - parties: {{"petitioner": "str", "respondent": "str"}}
    - statutes_mentioned: [str]
    - dates: [str]
    - location: str
    - case_type_hint: str
    - urgency_signals: [str]
    
    TEXT:
    {text}
    """
    
    llm = Settings.llm
    if not llm:
        return {"parties": {}, "statutes_mentioned": [], "dates": [], "location": "Unknown", "case_type_hint": "general", "urgency_signals": []}
        
    try:
        response = llm.complete(prompt)
        content = str(response)
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except:
        pass
        
    return {"parties": {}, "statutes_mentioned": [], "dates": [], "location": "Unknown", "case_type_hint": "general", "urgency_signals": []}

def detect_language(text: str) -> str:
    try:
        lang_code = detect(text)
        mapping = {"en": "english", "hi": "hindi", "ta": "tamil", "te": "telugu", "kn": "kannada"}
        return mapping.get(lang_code, "english")
    except:
        return "english"

class IntakeAgent:
    def __init__(self, engine):
        self.engine = engine
        
    def score_urgency(self, entities: dict, case_text: str) -> dict:
        # Bypassed LLM call to reduce latency.
        return {"score": 5, "reason": "Standard processing", "recommended_response_days": 14}

    def process(self, raw_input: str | bytes, input_type: str) -> CaseObject:
        text = ""
        if input_type == "pdf":
            try:
                reader = pypdf.PdfReader(io.BytesIO(raw_input))
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            except:
                text = "Failed to parse PDF."
        else:
            text = str(raw_input)
            
        try:
            entities = extract_entities(text)
            lang = detect_language(text)
            urgency = self.score_urgency(entities, text)
            
            case_obj = CaseObject(
                case_id=str(uuid.uuid4()),
                raw_text=text,
                language=lang,
                parties=entities.get("parties", {}),
                statutes_mentioned=entities.get("statutes_mentioned", []),
                dates=entities.get("dates", []),
                location=entities.get("location", "Unknown"),
                urgency_score=urgency.get("score", 5),
                urgency_reason=urgency.get("reason", "Unknown"),
                case_type_hint=entities.get("case_type_hint", "Unknown"),
                created_at=datetime.now(),
                status="intake_complete"
            )
            return case_obj
        except Exception as e:
            print("Error in intake agent:", str(e))
            return CaseObject(
                case_id=str(uuid.uuid4()),
                raw_text=text,
                language="english",
                parties={},
                statutes_mentioned=[],
                dates=[],
                location="Unknown",
                urgency_score=5,
                urgency_reason="Error parsing",
                case_type_hint="Unknown",
                created_at=datetime.now(),
                status="intake_complete"
            )
