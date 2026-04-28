# LexOps | ingest_chroma.py
# NEW: Ingest Indian law files into ChromaDB
# Run this ONCE before starting the server: python ingest_chroma.py

"""
Run this script to populate ChromaDB with your law files.
It reads every .txt file in data/laws/ and data/judgments/
and stores them in ChromaDB with metadata.

Usage:
    python ingest_chroma.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("LexOps ChromaDB Ingestion")
print("=" * 50)

from core.chroma_engine import LexOpsChromaEngine

engine = LexOpsChromaEngine()

# Show current state
stats = engine.get_stats()
print(f"\nBefore ingestion:")
print(f"  Laws in ChromaDB:      {stats['laws_count']}")
print(f"  Judgments in ChromaDB: {stats['judgments_count']}")

# Ingest laws
laws_path = os.getenv("DATA_PATH", "./data/laws/")
print(f"\nIngesting laws from: {laws_path}")
engine.ingest_laws_from_folder(laws_path)

# Ingest judgments
judgments_path = os.getenv("JUDGMENT_PATH", "./data/judgments/")
print(f"Ingesting judgments from: {judgments_path}")
engine.ingest_judgments_from_folder(judgments_path)

# Final state
stats = engine.get_stats()
print(f"\nAfter ingestion:")
print(f"  Laws in ChromaDB:      {stats['laws_count']}")
print(f"  Judgments in ChromaDB: {stats['judgments_count']}")
print(f"  Stored at:             {stats['chroma_path']}")

# Quick test query
print("\nTest query: 'unpaid wages salary not paid'")
results = engine.search_laws("unpaid wages salary not paid", top_k=3)
for r in results:
    print(f"  [{r['score']}] {r['act']} — Section {r['section']}: {r['text'][:80]}...")

print("\nDone! ChromaDB is ready. Start the server: python api.py")
