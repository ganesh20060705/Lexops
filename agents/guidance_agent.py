from pydantic import BaseModel
from typing import List, Dict, Any
from llama_index.core import PromptTemplate, Settings
from .intake_agent import CaseObject
from .intelligence_agent import IntelligenceReport

class GuidanceOutput(BaseModel):
    case_id: str
    summary: str
    recommended_steps: list[str]
    cited_statutes: list[dict]
    disclaimer: str
    language: str
    guardrails_passed: bool
    guardrails_violations: list[str]
    escalation_required: bool
    status: str = "guidance_complete"
    
    def to_dict(self):
        return self.model_dump()

class GuidanceAgent:
    def __init__(self, guardrails_layer):
        self.guardrails = guardrails_layer
        
        template_str = """
        You are a legal aid assistant. Using ONLY the context provided below,
        generate legal guidance for the following case.

        CASE FACTS: {case_summary}
        RELEVANT STATUTES: {statutes}
        PAST JUDGMENTS: {judgments}
        LANGUAGE TO RESPOND IN: {language}

        Rules you must follow:
        1. Only cite section numbers that appear verbatim in RELEVANT STATUTES above.
        2. Never invent case names or citation numbers.
        3. If you are uncertain, say "consult a lawyer for this specific point."
        4. Use plain language a non-lawyer can understand.
        5. Respond in {language}.
        6. Do not say "no relevant statutes found" if data is present. Always extract at least 1 relevant section.
        7. Ensure output ALWAYS includes a clear summary, legal basis, and actionable steps.
        8. DO NOT use markdown formatting (like ** or ##) for the section headers. Output exactly 'SUMMARY:', 'STEPS:', 'STATUTES:', 'DISCLAIMER:'.
        9. Use an authoritative, confident legal tone (e.g., "You are legally entitled to...", "You can file a claim..."). Avoid weak phrases like "you may try" or "you can take action".

        Generate your response in EXACTLY this format:
        SUMMARY:
        [3-sentence plain language summary of the issue, naming the legal basis, with a strong authoritative tone]
        
        STEPS:
        1. [Actionable Step 1]
        2. [Actionable Step 2]
        
        STATUTES:
        Section [Number] - [Brief explanation of the law]
        
        DISCLAIMER:
        [A safety disclaimer]
        """
        self.prompt_template = PromptTemplate(template_str)

    def generate(self, case_obj: CaseObject, report: IntelligenceReport) -> GuidanceOutput:
        scope_check = self.guardrails.check_scope(case_obj.raw_text)
        if not scope_check["in_scope"]:
            return GuidanceOutput(
                case_id=case_obj.case_id,
                summary=scope_check["escalation_message"],
                recommended_steps=[],
                cited_statutes=[],
                disclaimer="Escalation required.",
                language=case_obj.language,
                guardrails_passed=False,
                guardrails_violations=[scope_check["block_reason"]],
                escalation_required=True,
                status="guidance_failed"
            )
            
        statutes_str = "\n".join([f"{s['act']} - {s['section']}: {s['description']}" for s in report.relevant_statutes])
        judgments_str = "\n".join([f"{j['case_name']}: {j['ruling_summary']}" for j in report.relevant_judgments])
        
        prompt = self.prompt_template.format(
            case_summary=case_obj.raw_text,
            statutes=statutes_str or "None retrieved.",
            judgments=judgments_str or "None retrieved.",
            language=case_obj.language
        )
        
        llm = Settings.llm
        if not llm:
            raw_response = "SUMMARY:\nOffline mode summary.\nSTEPS:\n1. Step 1\nSTATUTES:\n- Section X - Law\nDISCLAIMER:\nDisclaimer here."
        else:
            try:
                raw_response = str(llm.complete(prompt))
            except Exception as e:
                print("LLM Error in guidance:", e)
                raw_response = "SUMMARY:\nError generating guidance.\nSTEPS:\n1. Consult lawyer\nSTATUTES:\n- None\nDISCLAIMER:\nError."
            
        import re
        summary = ""
        steps = []
        cited = []
        disclaimer = ""
        
        current_section = None
        for line in raw_response.split('\n'):
            line = line.strip()
            if line.startswith("SUMMARY:"):
                current_section = "SUMMARY"
            elif line.startswith("STEPS:"):
                current_section = "STEPS"
            elif line.startswith("STATUTES:"):
                current_section = "STATUTES"
            elif line.startswith("DISCLAIMER:"):
                current_section = "DISCLAIMER"
            elif line:
                if current_section == "SUMMARY":
                    summary += line + " "
                elif current_section == "STEPS" and (line[0].isdigit() or line.startswith("-")):
                    steps.append(line)
                elif current_section == "STATUTES" and (line.startswith("-") or line.startswith("Section")):
                    cited.append({"statute": line})
                elif current_section == "DISCLAIMER":
                    disclaimer += line + " "
                    
        # A & B. Normalize Steps and Statutes format
        cleaned_steps = []
        for i, step in enumerate(steps, 1):
            step = re.sub(r'^[\d\.\-\s]+', '', step)
            cleaned_steps.append(f"{i}. {step.strip()}")
            
        cleaned_cited = []
        for c in cited:
            statute_text = c["statute"]
            # Clean up '- 3 -' or '- Section 3 -' to 'Section 3 -'
            statute_text = re.sub(r'^[\-\s]*Section\s*(\d+[A-Z]?)\s*[\-\:]?\s*', r'Section \1 - ', statute_text, flags=re.IGNORECASE)
            statute_text = re.sub(r'^[\-\s]*(\d+[A-Z]?)\s*[\-\:]?\s*', r'Section \1 - ', statute_text)
            cleaned_cited.append({"statute": statute_text.strip()})
                    
        class MockNode:
            def __init__(self, text):
                self.text = text
        mock_nodes = [MockNode(f"{s['act']} {s['section']} {s['description']}") for s in report.relevant_statutes]
            
        verification = self.guardrails.verify_citations(raw_response, mock_nodes)
        
        clean_summary = self.guardrails.sanitize(summary.strip())
        
        # If there are violations, we might want to fail/escalate. 
        # The prompt says: "If guardrails fail: flag for EscalationAgent, do not return guidance"
        escalation_required = not verification["passed"]
        
        return GuidanceOutput(
            case_id=case_obj.case_id,
            summary=clean_summary if not escalation_required else "Escalation required due to hallucinated citations.",
            recommended_steps=cleaned_steps if not escalation_required else [],
            cited_statutes=cleaned_cited if not escalation_required else [],
            disclaimer=disclaimer.strip(),
            language=case_obj.language,
            guardrails_passed=verification["passed"],
            guardrails_violations=verification["violations"],
            escalation_required=escalation_required,
            status="guidance_complete" if not escalation_required else "guidance_failed"
        )
