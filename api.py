# LexOps | api.py
# FastAPI Backend
# Competition: LlamaIndex Hackathon

import os
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from orchestrator import LexOpsOrchestrator
from core.observability import get_live_metrics
from typing import Optional
import uvicorn

app = FastAPI(title="LexOps API", description="Legal Case Intelligence & Management MCP System")

# Initialize orchestrator
orchestrator = None

@app.on_event("startup")
def startup_event():
    global orchestrator
    orchestrator = LexOpsOrchestrator()

class AnalyzeRequest(BaseModel):
    query: str
    state: str
    phone: Optional[str] = None
    input_type: str = "text"

class StatusUpdateRequest(BaseModel):
    status: str
    note: str

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        result = orchestrator.run(req.query, req.input_type, req.state, req.phone)
        return result
    except Exception as e:
        return {"error": str(e), "case_id": "unknown", "status": "failed"}

@app.post("/analyze/pdf")
async def analyze_pdf(file: UploadFile = File(...), state: str = Form(...), phone: str = Form(None)):
    """Analyze a PDF using full Document RAG pipeline."""
    try:
        content = await file.read()
        from core.document_rag import process_uploaded_document
        doc_result = process_uploaded_document(
            content, "pdf",
            laws_engine=orchestrator.chroma_engine
        )
        result = orchestrator.run(content, "pdf", state, phone)
        result["document_rag"] = {
            "doc_id": doc_result.get("doc_id"),
            "filename": file.filename,
            "chunks_created": doc_result.get("chunks_created", 0),
            "text_preview": doc_result.get("text_preview", ""),
            "cross_references": doc_result.get("cross_references", []),
        }
        return result
    except Exception as e:
        return {"error": str(e), "case_id": "unknown", "status": "failed"}


@app.post("/document/analyze")
async def analyze_document_rag(file: UploadFile = File(...), state: str = Form("Tamil Nadu")):
    """
    Pure Document RAG endpoint.
    Upload any legal document → chunked → embedded → cross-referenced with Indian law database.
    """
    try:
        content = await file.read()
        input_type = "pdf" if file.filename.endswith(".pdf") else "text"
        from core.document_rag import process_uploaded_document
        result = process_uploaded_document(
            content, input_type,
            laws_engine=orchestrator.chroma_engine
        )
        return {
            "status": "success",
            "filename": file.filename,
            "doc_id": result.get("doc_id"),
            "text_preview": result.get("text_preview"),
            "total_chars": result.get("total_chars"),
            "chunks_created": result.get("chunks_created"),
            "cross_references": result.get("cross_references", []),
            "message": f"Document split into {result.get('chunks_created', 0)} chunks and cross-referenced with Indian law database"
        }
    except Exception as e:
        return {"error": str(e), "status": "failed"}

@app.get("/case/{case_id}")
async def get_case(case_id: str):
    result = orchestrator.tracking_agent.get_case_summary(case_id)
    if not result:
        raise HTTPException(status_code=404, detail="Case not found")
    return result

@app.get("/cases")
async def get_cases():
    session = orchestrator.tracking_agent.Session()
    from agents.tracking_agent import CaseTicket
    cases = session.query(CaseTicket).all()
    res = []
    for t in cases:
        res.append({
            "case_id": t.case_id,
            "type": t.case_type,
            "urgency": t.urgency_score,
            "status": t.status,
            "created": t.created_at.isoformat() if t.created_at else None,
            "last_updated": t.last_updated.isoformat() if t.last_updated else None,
            "court": t.assigned_court
        })
    session.close()
    return res

@app.put("/case/{case_id}/status")
async def update_status(case_id: str, req: StatusUpdateRequest):
    orchestrator.tracking_agent.update_status(case_id, req.status, req.note)
    return {"status": "success"}

@app.get("/health")
async def health():
    session = orchestrator.tracking_agent.Session()
    from agents.tracking_agent import CaseTicket
    count = session.query(CaseTicket).count()
    session.close()
    
    return {
        "status": "ok",
        "phoenix_url": orchestrator.phoenix_url,
        "total_cases": count,
        "ollama_mode": os.getenv("USE_OLLAMA", "false").lower() == "true"
    }

@app.get("/eval")
async def run_eval():
    try:
        from eval.eval import run_evaluation
        result = run_evaluation(orchestrator)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/metrics")
async def metrics():
    return get_live_metrics()

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

# ── NEW: ChromaDB stats endpoint ────────────────────────────────────────────
@app.get("/chroma/stats")
async def chroma_stats():
    """Show ChromaDB collection statistics."""
    if orchestrator.chroma_engine is None:
        return {"error": "ChromaDB not initialized. Run: python ingest_chroma.py"}
    return orchestrator.chroma_engine.get_stats()

@app.get("/chroma/search")
async def chroma_search(q: str, act: str = None, top_k: int = 5):
    """Search ChromaDB directly — useful for demos."""
    if orchestrator.chroma_engine is None:
        return {"error": "ChromaDB not initialized"}
    results = orchestrator.chroma_engine.search_laws(q, act_filter=act, top_k=top_k)
    return {"query": q, "act_filter": act, "results": results}


@app.post("/email_intake")
async def email_intake_endpoint(max_emails: int = 5):
    """Fetch pending legal cases from email inbox (simulation or Gmail)."""
    from core.email_intake import fetch_gmail_cases
    cases = fetch_gmail_cases(max_emails=max_emails)
    return {"cases": cases, "count": len(cases), "source": "simulation" if not __import__("os").getenv("GMAIL_USER") else "gmail"}


@app.get("/memory/cases")
async def get_memory_cases(n: int = 10):
    """Return N most recent cases from session memory."""
    from core.memory import get_recent_cases, memory_stats
    return {"cases": get_recent_cases(n), "stats": memory_stats()}


@app.get("/case/{case_id}/report")
async def download_report(case_id: str):
    """Download a case report .txt file."""
    from core.case_report import get_report_path, report_exists
    from fastapi.responses import FileResponse
    if not report_exists(case_id):
        raise HTTPException(status_code=404, detail="Report not found. Analyze case first.")
    return FileResponse(
        path=get_report_path(case_id),
        media_type="text/plain",
        filename=f"lexops_case_{case_id[:12]}.txt"
    )

@app.get("/mcp/tools")
async def list_mcp_tools():
    """List all available MCP tools and their descriptions."""
    return {
        "server": "LexOps MCP Server",
        "tools": [
            {"name": "search_law", "description": "Search Indian statutes in ChromaDB", "params": ["query", "act_filter", "top_k"]},
            {"name": "get_court", "description": "Get the correct court for a case type", "params": ["case_type", "claim_value", "state"]},
            {"name": "check_limitation", "description": "Check limitation period under Limitation Act 1963", "params": ["case_type"]},
            {"name": "create_ticket", "description": "Save case ticket to SQLite database", "params": ["case_id", "case_type", "summary", "urgency", "court", "phone"]},
            {"name": "send_whatsapp", "description": "Send WhatsApp notification via Twilio", "params": ["phone", "message", "case_id"]},
            {"name": "score_urgency", "description": "Rate urgency of legal situation 1-10", "params": ["text"]},
            {"name": "get_legal_aid", "description": "Get free legal aid organizations by state", "params": ["state", "case_type"]},
            {"name": "check_scope", "description": "Check if query is within LexOps scope", "params": ["query"]},
            {"name": "send_telegram", "description": "Send Telegram notification (replaces Twilio)", "params": ["phone_or_chat", "message", "case_id"]},
            {"name": "email_intake", "description": "Fetch pending cases from email inbox", "params": ["max_emails"]},
            {"name": "send_slack_alert", "description": "Send Slack alert for urgency >= 7", "params": ["case_id", "summary", "urgency", "case_type", "state"]},
            {"name": "save_case_report", "description": "Save structured case report as .txt file", "params": ["case_id", "summary", "guidance_steps", "court", "urgency"]}
        ],
        "connect_claude_desktop": "Add mcp_server.py path to claude_desktop_config.json"
    }