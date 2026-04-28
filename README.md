LexOps – AI-Powered Legal Assistant for India

LexOps is a multi-agent AI legal assistant that provides **accurate, actionable legal guidance** based on Indian laws.

Users can input a legal query or upload a document, and LexOps will:

* Understand the legal issue
* Retrieve relevant laws using RAG (ChromaDB)
* Generate structured legal guidance with citations
* Suggest the correct court and next steps
* Track and manage the case lifecycle

 Problem Statement

Millions of people in India lack access to timely and affordable legal guidance.
Legal systems are complex, slow, and difficult to navigate.



Solution

LexOps provides:

* Instant legal guidance
* Section-level law citations
* Court routing and next steps
* Document-based legal understanding

All within seconds using AI.



 Key Features

* Multi-agent legal reasoning system
*  RAG-based statute retrieval using ChromaDB
*  Legal document (PDF/text) analysis
*  Section-level law citation (e.g., Section 3, 15)
*  Guardrails for safe and accurate responses
* Observability with Phoenix (optional)
*  Email-based case intake (simulated)
*  Slack alerts for high urgency cases
*  Telegram notifications (simulation supported)
*  Automated case report generation
*  Persistent memory for recent cases



 Architecture

```text
User Input (Text / PDF)
        │
        ▼
  Orchestrator
        │
   ┌────────────────────────────────────────────┐
   │           Multi-Agent Pipeline              │
   │                                            │
   │  1. Intake Agent        → Parse input       │
   │  2. Intelligence Agent → RAG (ChromaDB)    │
   │  3. Guidance Agent     → Legal reasoning    │
   │  4. Routing Agent      → Court selection    │
   │  5. Tracking Agent     → Case tracking      │
   └────────────────────────────────────────────┘
        │
        ├── ChromaDB (laws + judgments)
        ├── MCP Server (12 tools)
        ├── SQLite (case storage)
        └── Observability (Phoenix)
```

 Tech Stack

| Component     | Technology       |
| ------------- | ---------------- |
| RAG Engine    | LlamaIndex       |
| Vector DB     | ChromaDB         |
| LLM           | Groq (LLaMA 3)   |
| Embeddings    | HuggingFace      |
| Backend       | FastAPI          |
| UI            | Streamlit        |
| Observability | Phoenix          |
| Notifications | Telegram + Slack |
| Database      | SQLite           |
| MCP Server    | FastMCP          |

 MCP Tools (12 Tools)

LexOps exposes 12 tools via MCP:

* search_law
* get_court
* check_limitation
* create_ticket
* send_telegram
* send_slack_alert
* email_intake
* save_case_report
* score_urgency
* get_legal_aid
* check_scope
* get_case_status

 Setup Instructions

 1. Install dependencies

bash
pip install -r requirements.txt


 2. Create `.env` file

env
GROQ_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token
SLACK_WEBHOOK_URL=your_webhook


 3. Ingest legal data

bash
python ingest_chroma.py


4. Start backend

bash
python api.py


 5. Run UI

bash
streamlit run app.py


 6. Run MCP server (optional)

bash
python mcp_server.py


Testing

Run all tests:

bash
pytest tests/test_lexops.py -v


Expected:


10 passed


Test Coverage

* Pipeline execution
* Legal accuracy (Section 3 & 15 detection)
* Output structure validation
* MCP tools availability
* Latency (< 4 seconds)

Demo Example

Input:


My employer has not paid salary for 3 months


Output:

*  Section 3 – Responsibility for wages
*  Section 15 – Claim recovery
*  3 clear legal steps
*  Labour court routing

📂 Project Structure


lexops/
├── agents/
├── core/
├── data/
│   ├── laws/
│   ├── judgments/
├── tests/
│   └── test_lexops.py
├── app.py
├── api.py
├── orchestrator.py
├── mcp_server.py
├── ingest_chroma.py
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example




 Law Coverage

* Payment of Wages Act
* Consumer Protection Act
* Domestic Violence Act
* IPC (selected sections)
* IT Act
* RERA Act
* Industrial Disputes Act

Guardrails

LexOps prevents:

* Unsafe legal advice
* Irrelevant law citations
* Unstructured outputs

All responses are grounded in retrieved legal data.

Performance

*  Response Time: < 4 seconds
*  High precision retrieval
*  Structured and reliable outputs






