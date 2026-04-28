# LexOps | app.py
# UPGRADED: 4-tab Streamlit UI with Slack badge, report download, email intake, MCP tools panel

import streamlit as st
import requests
import os
import json
import time

st.set_page_config(page_title="LexOps Legal AI", layout="wide", page_icon="⚖️")

API_BASE = "http://localhost:8000"

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("⚖️ LexOps")
st.sidebar.caption("AI-Powered Indian Legal Assistant")

st.sidebar.markdown("### 🔭 Observability")
if st.sidebar.button("Open Phoenix Dashboard"):
    st.sidebar.markdown("[Click to open](http://localhost:6006)", unsafe_allow_html=True)

st.sidebar.markdown("### 📊 Live Metrics")
metrics = {}
try:
    metrics = requests.get(f"{API_BASE}/metrics", timeout=3).json()
    st.sidebar.success(f"RAG Precision@5: {metrics.get('precision_at_5', 0)}")
    st.sidebar.success(f"Response Quality: {metrics.get('avg_response_quality', 0)*5:.1f}/5")
    st.sidebar.warning(f"Avg Latency: {metrics.get('avg_latency_ms', 0)/1000:.2f}s")
    st.sidebar.info(f"Total Cases: {metrics.get('total_cases', 0)}")
except Exception:
    st.sidebar.error("API not running — start with: python api.py")

st.sidebar.markdown("### 🤖 Ecosystem Status")
try:
    chroma = requests.get(f"{API_BASE}/chroma/stats", timeout=3).json()
    if "error" not in chroma:
        st.sidebar.success(f"ChromaDB: {chroma.get('laws_count',0)} laws, {chroma.get('judgments_count',0)} judgments")
    else:
        st.sidebar.warning("ChromaDB: Run ingest_chroma.py")
except Exception:
    st.sidebar.warning("ChromaDB: API offline")

st.sidebar.markdown("### ⚙️ Offline Mode")
use_ollama = st.sidebar.checkbox("Switch to Ollama", value=os.getenv("USE_OLLAMA","false").lower()=="true")
if use_ollama:
    os.environ["USE_OLLAMA"] = "true"
    st.sidebar.success("Offline Mode (Ollama)")
else:
    os.environ["USE_OLLAMA"] = "false"

if st.sidebar.button("Run Evaluation"):
    with st.spinner("Running Eval..."):
        try:
            res = requests.get(f"{API_BASE}/eval", timeout=30).json()
            st.sidebar.json(res)
        except Exception:
            st.sidebar.error("Evaluation failed")

# ── Main Tabs ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["⚖️ Analyze Case", "📧 Email Intake", "📁 Resolved Cases", "🛠️ MCP Tools"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: Analyze Case
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.header("Case Submission & Analysis")
    col1, col2 = st.columns(2)

    with col1:
        text_input = st.text_area("Describe the legal problem in detail", height=200,
                                   placeholder="e.g. My employer has not paid my salary for 3 months...")
        pdf_upload = st.file_uploader("OR: Upload a PDF document", type=["pdf"])
        states = ["Tamil Nadu", "Maharashtra", "Delhi", "Karnataka", "Kerala", "Gujarat",
                  "Uttar Pradesh", "West Bengal", "Rajasthan", "Madhya Pradesh"]
        state_input = st.selectbox("State", states)
        phone_input = st.text_input("Phone / Telegram Chat ID (optional, for notifications)")

        if st.button("🔍 Analyze Case", type="primary"):
            if text_input or pdf_upload:
                with st.spinner("Running multi-agent pipeline..."):
                    start_t = time.time()
                    try:
                        if text_input:
                            payload = {"query": text_input, "state": state_input,
                                       "phone": phone_input, "input_type": "text"}
                            res = requests.post(f"{API_BASE}/analyze", json=payload, timeout=60).json()
                        else:
                            files = {"file": pdf_upload}
                            data = {"state": state_input, "phone": phone_input}
                            res = requests.post(f"{API_BASE}/analyze/pdf", files=files, data=data, timeout=60).json()
                        st.session_state["result"] = res
                        st.session_state["latency"] = time.time() - start_t
                    except Exception as e:
                        st.error(f"Error connecting to API: {e}")
            else:
                st.warning("Please enter case details or upload a PDF.")

    with col2:
        st.subheader("Analysis Results")
        if "result" in st.session_state:
            res = st.session_state["result"]

            # Slack urgency badge
            urgency = res.get("urgency", {})
            u_score = urgency.get("score", 0)
            u_level = urgency.get("level", "")
            slack_alert = res.get("slack_alert", {})
            if u_score >= 7:
                badge_color = "🔴" if u_score >= 9 else "🟠"
                st.error(f"{badge_color} **Urgency {u_score}/10 — {u_level}** | {urgency.get('reason','')}")
                if slack_alert.get("triggered"):
                    alert_note = "✅ Slack alert sent" if not slack_alert.get("simulated") else "📢 Slack alert simulated"
                    st.caption(alert_note)
            else:
                st.info(f"🟢 Urgency {u_score}/10 — {u_level}")

            if res.get("status") == "escalated":
                st.warning("⚠️ ESCALATION REQUIRED: Lawyer review needed.")
            else:
                st.success(f"✅ Case ID: `{res.get('case_id','')[:16]}`")
                guidance = res.get("guidance", {}) or {}
                routing = res.get("routing", {}) or {}

                with st.expander("📋 Legal Guidance", expanded=True):
                    st.write("**Summary:**", guidance.get("summary"))
                    st.write("**Recommended Steps:**")
                    for s in guidance.get("recommended_steps", []):
                        st.write(s)
                    st.write("**Cited Statutes:**")
                    for s in guidance.get("cited_statutes", []):
                        st.write(f"• {s.get('statute', s)}")
                    st.caption(f"_{guidance.get('disclaimer')}_")

                with st.expander("🏛️ Court Routing"):
                    primary = routing.get("primary_court", {}) or {}
                    st.write(f"**Court:** {primary.get('court_name','N/A')}")
                    st.write(f"**Level:** {primary.get('jurisdiction_level','N/A')}")
                    st.write(f"**Fee:** {primary.get('filing_fee_range','N/A')}")
                    portal = primary.get("online_portal_url","")
                    if portal and portal != "None (visit court in person)":
                        st.markdown(f"**Portal:** [{portal}]({portal})")
                    if routing.get("mediation_required"):
                        st.warning("Mandatory mediation required.")

                with st.expander("🆘 Legal Aid"):
                    for aid in routing.get("legal_aid_options", []):
                        st.write(f"• **{aid.get('name')}** — ☎️ {aid.get('helpline','')}")

                # Document RAG results
                doc_rag = res.get("document_rag")
                if doc_rag and doc_rag.get("chunks_created", 0) > 0:
                    with st.expander("📄 Document RAG Analysis", expanded=True):
                        st.success(f"✅ Document split into **{doc_rag['chunks_created']} chunks** and embedded into ChromaDB")
                        if doc_rag.get("text_preview"):
                            st.caption("**Document Preview:**")
                            st.text(doc_rag["text_preview"][:300])
                        cross_refs = doc_rag.get("cross_references", [])
                        if cross_refs:
                            st.write("**📚 Cross-referenced with Indian Law:**")
                            for ref in cross_refs[:3]:
                                with st.container():
                                    st.caption(f"📝 *Document excerpt:* {ref.get('document_excerpt','')[:150]}")
                                    for statute in ref.get("matching_statutes", [])[:2]:
                                        st.write(f"  ⚖️ **{statute.get('act','')}** — Section {statute.get('section','')} (relevance: {statute.get('relevance',0):.2f})")

                # Case report download
                report_path = res.get("case_report")
                if report_path and os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as rf:
                        report_text = rf.read()
                    st.download_button(
                        label="📥 Download Case Report (.txt)",
                        data=report_text,
                        file_name=f"lexops_case_{res.get('case_id','unknown')[:12]}.txt",
                        mime="text/plain"
                    )

                st.caption(f"⏱️ Latency: {res.get('latency_ms',0)} ms | Source: {res.get('retrieval_source','')}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: Email Intake
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.header("📧 Email Case Intake")
    st.caption("Fetch legal cases from email inbox. Uses Gmail if credentials are set, otherwise shows realistic simulations.")

    max_e = st.number_input("Max emails to fetch", min_value=1, max_value=20, value=5)

    if st.button("📥 Fetch Email Cases"):
        with st.spinner("Fetching cases..."):
            try:
                res = requests.post(f"{API_BASE}/email_intake", params={"max_emails": max_e}, timeout=15).json()
                st.session_state["email_cases"] = res.get("cases", [])
                source = res.get("source", "simulation")
                st.success(f"Fetched {res.get('count', 0)} cases from {source}")
            except Exception as e:
                st.error(f"Could not fetch emails: {e}")

    if "email_cases" in st.session_state:
        for i, case in enumerate(st.session_state["email_cases"]):
            with st.expander(f"📬 Case {i+1}: {case.get('subject','No Subject')}", expanded=(i==0)):
                st.write(f"**From:** {case.get('from','')}")
                st.write(f"**State:** {case.get('state','Unknown')}")
                st.write(f"**Type Hint:** {case.get('case_type_hint','general').title()}")
                st.text_area("Email Body", value=case.get("body",""), height=120, key=f"email_{i}", disabled=True)

                if st.button(f"⚖️ Analyze This Case", key=f"analyze_email_{i}"):
                    with st.spinner("Analyzing..."):
                        try:
                            payload = {
                                "query": f"{case.get('subject','')}. {case.get('body','')}",
                                "state": case.get("state", "Tamil Nadu"),
                                "input_type": "text"
                            }
                            r = requests.post(f"{API_BASE}/analyze", json=payload, timeout=60).json()
                            st.session_state[f"email_result_{i}"] = r
                        except Exception as e:
                            st.error(str(e))

                if f"email_result_{i}" in st.session_state:
                    r = st.session_state[f"email_result_{i}"]
                    guidance = r.get("guidance") or {}
                    st.success(f"Case ID: `{r.get('case_id','')[:16]}`")
                    st.write("**Summary:**", guidance.get("summary",""))
                    report_path = r.get("case_report")
                    if report_path and os.path.exists(report_path):
                        with open(report_path) as rf:
                            st.download_button("📥 Download Report", data=rf.read(),
                                               file_name=f"lexops_{r.get('case_id','')[:12]}.txt",
                                               mime="text/plain", key=f"dl_email_{i}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: Resolved Cases
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.header("📁 Resolved Cases & Memory")

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Database Cases")
        if st.button("🔄 Refresh Cases"):
            try:
                cases = requests.get(f"{API_BASE}/cases", timeout=5).json()
                st.session_state["db_cases"] = cases
            except Exception as e:
                st.error(str(e))

        if "db_cases" in st.session_state:
            cases = st.session_state["db_cases"]
            if cases:
                st.dataframe(cases, use_container_width=True)
                case_id_input = st.text_input("Enter Case ID to update status")
                new_status = st.selectbox("New Status", ["new", "in_progress", "resolved", "escalated"])
                note = st.text_input("Note")
                if st.button("Update Status"):
                    try:
                        requests.put(f"{API_BASE}/case/{case_id_input}/status",
                                     json={"status": new_status, "note": note}, timeout=5)
                        st.success("Status updated")
                    except Exception as e:
                        st.error(str(e))
            else:
                st.info("No cases found. Analyze a case first.")

    with col_b:
        st.subheader("Session Memory (Recent Cases)")
        if st.button("🧠 Load Memory"):
            try:
                mem = requests.get(f"{API_BASE}/memory/cases", params={"n": 20}, timeout=5).json()
                st.session_state["memory_cases"] = mem
            except Exception as e:
                st.error(str(e))

        if "memory_cases" in st.session_state:
            mem = st.session_state["memory_cases"]
            stats = mem.get("stats", {})
            st.caption(f"Stored: {stats.get('total_stored',0)} / {stats.get('max_capacity',50)} | Newest: {stats.get('newest','N/A')}")
            for c in reversed(mem.get("cases", [])):
                urgency_icon = "🔴" if c.get("urgency",0) >= 9 else "🟠" if c.get("urgency",0) >= 7 else "🟢"
                with st.expander(f"{urgency_icon} {c.get('case_id','')[:12]} — {c.get('case_type','').title()} — {c.get('timestamp','')[:10]}"):
                    st.write(c.get("summary",""))

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4: MCP Tools
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.header("🛠️ MCP Tools Ecosystem")
    st.caption("All tools exposed via the LexOps MCP Server (12 total)")

    if st.button("🔃 Refresh Tools List"):
        try:
            tools_data = requests.get(f"{API_BASE}/mcp/tools", timeout=5).json()
            st.session_state["mcp_tools"] = tools_data
        except Exception as e:
            st.error(str(e))
    else:
        try:
            if "mcp_tools" not in st.session_state:
                tools_data = requests.get(f"{API_BASE}/mcp/tools", timeout=3).json()
                st.session_state["mcp_tools"] = tools_data
        except Exception:
            pass

    if "mcp_tools" in st.session_state:
        data = st.session_state["mcp_tools"]
        st.success(f"Server: **{data.get('server','')}** — {len(data.get('tools',[]))} tools registered")

        cols = st.columns(3)
        for i, tool in enumerate(data.get("tools", [])):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"**🔧 {tool['name']}**")
                    st.caption(tool.get("description",""))
                    params = tool.get("params", [])
                    if params:
                        st.code(", ".join(params), language=None)
    else:
        st.info("Click 'Refresh Tools List' to load MCP tools (requires API to be running).")

    st.divider()
    st.subheader("🔍 Live ChromaDB Search")
    q = st.text_input("Search Indian law database", placeholder="e.g. unpaid wages remedy")
    act_f = st.selectbox("Filter by Act (optional)", ["All", "Payment Of Wages Act",
        "Consumer Protection Act 2019", "Domestic Violence Act 2005",
        "It Act 2000", "Ipc Key Sections", "Rera Act 2016", "Trade Marks Act 1999",
        "Industrial Disputes Act"])
    if st.button("🔍 Search"):
        try:
            params = {"q": q}
            if act_f != "All":
                params["act"] = act_f
            res = requests.get(f"{API_BASE}/chroma/search", params=params, timeout=10).json()
            for r in res.get("results", []):
                with st.expander(f"{r.get('act','')} — Section {r.get('section','')} (score: {r.get('score',0):.2f})"):
                    st.write(r.get("text",""))
        except Exception as e:
            st.error(str(e))