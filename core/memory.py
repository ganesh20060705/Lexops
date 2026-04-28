# LexOps | core/memory.py
# Session memory: store and recall recent cases in-memory (with optional JSON persistence)

import json
import os
from datetime import datetime
from collections import deque
from typing import Optional

MEMORY_FILE = os.getenv("MEMORY_FILE", "./data/session_memory.json")
MAX_CASES = int(os.getenv("MEMORY_MAX_CASES", "50"))

# In-memory deque — thread-safe for single-process use
_case_store: deque = deque(maxlen=MAX_CASES)


def _load_from_disk():
    """Load persisted cases from JSON on startup."""
    global _case_store
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _case_store = deque(data[-MAX_CASES:], maxlen=MAX_CASES)
        except Exception as e:
            print(f"[Memory] Could not load from disk: {e}")


def _save_to_disk():
    """Persist current memory to JSON."""
    try:
        os.makedirs(os.path.dirname(MEMORY_FILE) if os.path.dirname(MEMORY_FILE) else ".", exist_ok=True)
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(list(_case_store), f, indent=2, default=str)
    except Exception as e:
        print(f"[Memory] Could not save to disk: {e}")


def save_case(case_id: str, summary: str, case_type: str = "general",
              urgency: int = 5, extra: Optional[dict] = None) -> dict:
    """
    Store a case in session memory.

    Args:
        case_id:   Unique case identifier
        summary:   Brief summary of the guidance given
        case_type: Type of legal case
        urgency:   Urgency score 1–10
        extra:     Any additional metadata dict

    Returns:
        The stored case record
    """
    record = {
        "case_id": case_id,
        "summary": summary,
        "case_type": case_type,
        "urgency": urgency,
        "timestamp": datetime.now().isoformat(),
        **(extra or {})
    }
    _case_store.append(record)
    _save_to_disk()
    return record


def get_recent_cases(n: int = 10) -> list[dict]:
    """
    Return the N most recent cases from session memory.

    Args:
        n: Number of cases to return (default 10)

    Returns:
        List of case records, most recent last
    """
    return list(_case_store)[-n:]


def get_case_by_id(case_id: str) -> Optional[dict]:
    """
    Retrieve a specific case from memory by ID.

    Args:
        case_id: The case identifier to look up

    Returns:
        Case record dict or None if not found
    """
    for record in _case_store:
        if record.get("case_id") == case_id:
            return record
    return None


def clear_memory():
    """Clear all cases from session memory (does not delete disk file)."""
    _case_store.clear()


def memory_stats() -> dict:
    """Return memory statistics."""
    return {
        "total_stored": len(_case_store),
        "max_capacity": MAX_CASES,
        "oldest": _case_store[0]["timestamp"] if _case_store else None,
        "newest": _case_store[-1]["timestamp"] if _case_store else None,
    }


# Load from disk on module import
_load_from_disk()
