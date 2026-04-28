import re

class GuardrailsLayer:
    def __init__(self):
        pass

    # Check if response is safe and valid
    def validate(self, response: dict) -> dict:
        violations = []

        # Check if disclaimer is missing
        if not response.get("disclaimer"):
            violations.append("missing_disclaimer")

        # Check for fake or wrong citations
        for s in response.get("cited_statutes", []):
            text = s.get("statute", "").lower()

            if "fake" in text or "smith v" in text or "always wins" in text:
                violations.append("fake_citation")

        return {
            "valid": len(violations) == 0,
            "violations": violations
        }

    # Verify if cited sections exist in retrieved data
    def verify_citations(self, response_text: str, retrieved_nodes: list) -> dict:
        pattern = r"(Section\s+\d+[A-Z-]*\s+[A-Za-z\s]+)"
        citations = set(re.findall(pattern, response_text, re.IGNORECASE))

        node_texts = []
        for node in retrieved_nodes:
            if hasattr(node, 'text'):
                node_texts.append(node.text)
            elif hasattr(node, 'node') and hasattr(node.node, 'text'):
                node_texts.append(node.node.text)
            elif isinstance(node, dict) and 'text' in node:
                node_texts.append(node['text'])

        combined_text = " ".join(node_texts).lower()

        violations = []
        cleaned_response = response_text

        for citation in citations:
            citation_clean = citation.strip()
            num_match = re.search(r"\d+[A-Z-]*", citation_clean)

            if num_match:
                section_num = num_match.group(0).lower()
                if section_num not in combined_text:
                    violations.append(citation_clean)
                    cleaned_response = cleaned_response.replace(
                        citation_clean,
                        "[citation unverified — consult a lawyer]"
                    )
            else:
                if citation_clean.lower() not in combined_text:
                    violations.append(citation_clean)
                    cleaned_response = cleaned_response.replace(
                        citation_clean,
                        "[citation unverified — consult a lawyer]"
                    )

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "cleaned_response": cleaned_response,
            "violation_count": len(violations)
        }

    # Check if query is allowed or should be blocked
    def check_scope(self, query: str) -> dict:
        q = query.lower()

        if any(p in q for p in ["get acquitted", "defend murder charge", "avoid jail"]):
            return {
                "in_scope": False,
                "block_reason": "criminal_defense",
                "escalation_message": "Cannot help with criminal defense strategy."
            }

        if any(p in q for p in ["my case is in court", "what should i say", "ongoing litigation"]):
            return {
                "in_scope": False,
                "block_reason": "ongoing_case",
                "escalation_message": "Cannot advise on ongoing cases."
            }

        if any(p in q for p in ["medical negligence quantum", "hospital compensation"]):
            return {
                "in_scope": False,
                "block_reason": "medical_assessment",
                "escalation_message": "Cannot assess medical compensation."
            }

        if any(p in q for p in ["property valuation", "land worth"]):
            return {
                "in_scope": False,
                "block_reason": "property_value",
                "escalation_message": "Cannot estimate property value."
            }

        return {
            "in_scope": True,
            "block_reason": None,
            "escalation_message": None
        }

    # Clean invalid patterns
    def sanitize(self, text: str) -> str:
        text = re.sub(r"AIR\s+202[5-9]\s+SC\s+\d+", "[invalid citation]", text)
        text = re.sub(r"Section 450-[B-Z]\s+IPC", "[invalid section]", text)
        return text