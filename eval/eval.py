# LexOps | eval/eval.py
import json
import time
import sys
import os

# Ensure the parent directory is in the path so we can import modules properly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.observability import compute_precision_at_k, compute_response_quality

def run_evaluation(orchestrator=None):
    if orchestrator is None:
        from orchestrator import LexOpsOrchestrator
        orchestrator = LexOpsOrchestrator()
        
    try:
        with open("eval/eval_labels.json", "r") as f:
            labels = json.load(f)
    except FileNotFoundError:
        print("Error: eval_labels.json not found")
        return {}
        
    total_queries = len(labels)
    total_precision = 0.0
    total_quality = 0.0
    guardrails_caught = 0
    escalations = 0
    
    latencies = []
    
    print("Starting Evaluation...")
    
    for item in labels:
        query = item["query"]
        state = "Tamil Nadu" # default mock
        
        statute_nodes = orchestrator.engine.retrieve_statutes(query, top_k=5)
        precision = compute_precision_at_k(query, statute_nodes, k=5)
        total_precision += precision
        
        start_time = time.time()
        result = orchestrator.run(query, "text", state)
        latency = int((time.time() - start_time) * 1000)
        latencies.append(latency)
        
        if result["status"] == "complete":
            guidance = result.get("guidance", {})
            summary = guidance.get("summary", "")
            quality = compute_response_quality(summary)
            total_quality += quality
            
            if not guidance.get("guardrails_passed", True):
                guardrails_caught += 1
        else:
            escalations += 1
            
    avg_precision = total_precision / total_queries if total_queries > 0 else 0
    avg_quality = (total_quality / (total_queries - escalations)) if (total_queries - escalations) > 0 else 0
    
    latencies.sort()
    p50 = latencies[len(latencies)//2] if latencies else 0
    p95 = latencies[int(len(latencies)*0.95)] if latencies else 0
    
    report = {
        "precision_at_5": round(avg_precision, 2),
        "response_quality": round(avg_quality * 5, 1),
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
        "guardrails_catch_rate": round(guardrails_caught / total_queries, 2) if total_queries > 0 else 0,
        "escalation_rate": round(escalations / total_queries, 2) if total_queries > 0 else 0
    }
    
    report_text = f"""
==========================================
LexOps Evaluation Report
==========================================
Queries tested:        {total_queries}
RAG Precision@5:       {report['precision_at_5']}
Response Quality:      {report['response_quality']} / 5
Latency p50:           {report['latency_p50_ms']}ms
Latency p95:           {report['latency_p95_ms']}ms
Guardrails catch rate: {report['guardrails_catch_rate']}
Escalation rate:       {report['escalation_rate']}
==========================================
"""
    print(report_text)
    
    with open("eval/eval_results.json", "w") as f:
        json.dump(report, f, indent=2)
        
    return report

if __name__ == "__main__":
    run_evaluation()
