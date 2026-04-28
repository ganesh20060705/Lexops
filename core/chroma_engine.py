# LexOps | core/chroma_engine.py
# NEW: Replaces FAISS with ChromaDB for persistent, metadata-filtered vector search

"""
ChromaDB Engine
Concepts covered:
- ChromaDB: persistent vector database (replaces FAISS JSON files)
- Metadata filtering: filter statutes by act name, state, case type
- SentenceTransformer embeddings: same model as before (all-MiniLM-L6-v2)
- Collection management: separate collections for laws and judgments
"""

import os
import uuid
import chromadb
from chromadb.utils import embedding_functions

DATA_PATH = os.getenv("DATA_PATH", "./data/laws/")
CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma_db/")


class LexOpsChromaEngine:
    """
    Manages two ChromaDB collections:
    - 'indian_laws'    : statute sections with act/section/state metadata
    - 'indian_judgments': case rulings with case_name/year/court metadata
    """

    def __init__(self):
        # Persistent client — data survives restarts (unlike FAISS in-memory)
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Use the same embedding model as LlamaIndex engine for consistency
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Get or create collections
        self.laws_collection = self.client.get_or_create_collection(
            name="indian_laws",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}  # cosine similarity for legal text
        )

        self.judgments_collection = self.client.get_or_create_collection(
            name="indian_judgments",
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

        print(f"[ChromaDB] Laws collection: {self.laws_collection.count()} docs")
        print(f"[ChromaDB] Judgments collection: {self.judgments_collection.count()} docs")

    # ─────────────────────────────────────────────
    # INGESTION
    # ─────────────────────────────────────────────

    def ingest_laws_from_folder(self, folder_path: str = None):
        """
        Read every .txt file in the laws folder.
        Each non-empty line becomes one document with rich metadata.
        """
        folder_path = folder_path or DATA_PATH
        if not os.path.exists(folder_path):
            print(f"[ChromaDB] Folder not found: {folder_path}")
            return

        files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
        if not files:
            print(f"[ChromaDB] No .txt files in {folder_path}")
            return

        documents, metadatas, ids = [], [], []

        for filename in files:
            # Derive act name from filename e.g. payment_of_wages_act.txt
            act_name = filename.replace(".txt", "").replace("_", " ").title()
            year = next(
                (part for part in filename.replace(".txt", "").split("_") if part.isdigit()),
                "Unknown"
            )

            filepath = os.path.join(folder_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            section_counter = 0
            for line in lines:
                line = line.strip()
                if not line or len(line) < 10:  # skip very short lines
                    continue

                section_counter += 1
                doc_id = f"{filename}_{section_counter}"

                # Detect section number from line (e.g. "Section 15 -")
                import re
                sec_match = re.search(r"[Ss]ection\s+(\d+[A-Za-z]?)", line)
                section_num = sec_match.group(1) if sec_match else str(section_counter)

                documents.append(line)
                metadatas.append({
                    "act": act_name,
                    "section": section_num,
                    "year": year,
                    "state": "all",           # central laws apply to all states
                    "filename": filename,
                    "case_type": self._guess_case_type(act_name)
                })
                ids.append(doc_id)

        if documents:
            # Add in batches of 100 to avoid memory issues
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                self.laws_collection.add(
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
            print(f"[ChromaDB] Ingested {len(documents)} law sections from {len(files)} files")

    def ingest_judgments_from_folder(self, folder_path: str = None):
        """Read judgment .txt files into the judgments collection."""
        folder_path = folder_path or os.getenv("JUDGMENT_PATH", "./data/judgments/")
        if not os.path.exists(folder_path):
            print(f"[ChromaDB] Judgment folder not found: {folder_path}")
            return

        files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
        if not files:
            print(f"[ChromaDB] No judgment files found")
            return

        documents, metadatas, ids = [], [], []

        for filename in files:
            filepath = os.path.join(folder_path, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                continue

            doc_id = filename.replace(".txt", "")
            documents.append(content)
            metadatas.append({
                "case_name": filename.replace(".txt", "").replace("_", " ").title(),
                "year": "Unknown",
                "court": "Unknown",
                "filename": filename
            })
            ids.append(doc_id)

        if documents:
            self.judgments_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            print(f"[ChromaDB] Ingested {len(documents)} judgments")

    # ─────────────────────────────────────────────
    # SEARCH
    # ─────────────────────────────────────────────

    def search_laws(self, query: str, act_filter: str = None, top_k: int = 5) -> list[dict]:
        """
        Search statutes. Optionally filter by act name.
        Returns list of dicts with text + metadata.
        """
        if self.laws_collection.count() == 0:
            return []

        where_clause = None
        if act_filter:
            where_clause = {"act": {"$eq": act_filter}}

        results = self.laws_collection.query(
            query_texts=[query],
            n_results=min(top_k, self.laws_collection.count()),
            where=where_clause,
            include=["documents", "metadatas", "distances"]
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text": doc,
                "act": results["metadatas"][0][i].get("act", "Unknown"),
                "section": results["metadatas"][0][i].get("section", "Unknown"),
                "state": results["metadatas"][0][i].get("state", "all"),
                "case_type": results["metadatas"][0][i].get("case_type", "general"),
                "score": round(1 - results["distances"][0][i], 3)  # cosine → similarity
            })

        return output

    def search_judgments(self, query: str, top_k: int = 3) -> list[dict]:
        """Search past judgments."""
        if self.judgments_collection.count() == 0:
            return []

        results = self.judgments_collection.query(
            query_texts=[query],
            n_results=min(top_k, self.judgments_collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text": doc,
                "case_name": results["metadatas"][0][i].get("case_name", "Unknown"),
                "year": results["metadatas"][0][i].get("year", "Unknown"),
                "court": results["metadatas"][0][i].get("court", "Unknown"),
                "score": round(1 - results["distances"][0][i], 3)
            })

        return output

    # ─────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────

    def _guess_case_type(self, act_name: str) -> str:
        """Guess the case type from act name for metadata."""
        act_lower = act_name.lower()
        if "consumer" in act_lower:
            return "consumer"
        if "wage" in act_lower or "labour" in act_lower or "industrial" in act_lower:
            return "labour"
        if "domestic" in act_lower or "family" in act_lower:
            return "family"
        if "rera" in act_lower or "real estate" in act_lower:
            return "property"
        if "it act" in act_lower or "information technology" in act_lower:
            return "cyber"
        if "ipc" in act_lower or "penal" in act_lower:
            return "criminal"
        if "trade" in act_lower:
            return "ip"
        return "general"

    def get_stats(self) -> dict:
        """Return collection stats for display in UI/API."""
        return {
            "laws_count": self.laws_collection.count(),
            "judgments_count": self.judgments_collection.count(),
            "chroma_path": CHROMA_PATH
        }
