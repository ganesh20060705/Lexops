# LexOps | core/document_rag.py
# Document RAG Pipeline
# User uploads a legal document (PDF/text) → chunked → embedded → 
# stored in ChromaDB temporarily → queried against Indian law database
# This is the core RAG demonstration feature

import os
import uuid
import io
import re
import pypdf
from dotenv import load_dotenv

load_dotenv()

CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma_db/")
CHUNK_SIZE = 500      # characters per chunk
CHUNK_OVERLAP = 100   # overlap between chunks


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF file."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"[DocumentRAG] PDF extraction error: {e}")
        return ""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Split text into overlapping chunks for embedding.
    Each chunk becomes one document in ChromaDB.
    """
    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundary
        if end < len(text):
            last_period = text.rfind(".", start, end)
            last_newline = text.rfind("\n", start, end)
            break_point = max(last_period, last_newline)
            if break_point > start + (chunk_size // 2):
                end = break_point + 1

        chunk = text[start:end].strip()
        if len(chunk) > 50:  # skip very short chunks
            chunks.append({
                "text": chunk,
                "chunk_index": chunk_index,
                "start_char": start,
                "end_char": end
            })
            chunk_index += 1

        start = end - overlap

    return chunks


def ingest_document_to_chroma(text: str, doc_id: str,
                               filename: str = "uploaded_doc") -> dict:
    """
    Chunk a document and store it in ChromaDB under a temporary collection.
    Each upload session gets a unique collection so they don't mix.

    Args:
        text:     Full document text
        doc_id:   Unique session ID for this document
        filename: Original filename for metadata

    Returns:
        Dict with chunk count and collection name
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=CHROMA_PATH)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # Unique collection per document session
        collection_name = f"doc_{doc_id[:12].replace('-', '_')}"
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

        chunks = chunk_text(text)
        if not chunks:
            return {"error": "No text could be extracted from document"}

        documents = []
        metadatas = []
        ids = []

        for chunk in chunks:
            documents.append(chunk["text"])
            metadatas.append({
                "filename": filename,
                "doc_id": doc_id,
                "chunk_index": chunk["chunk_index"],
                "start_char": chunk["start_char"]
            })
            ids.append(f"{doc_id}_{chunk['chunk_index']}")

        # Ingest in batches
        batch_size = 50
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
                ids=ids[i:i+batch_size]
            )

        print(f"[DocumentRAG] Ingested {len(chunks)} chunks from '{filename}'")
        return {
            "success": True,
            "collection": collection_name,
            "chunks": len(chunks),
            "doc_id": doc_id,
            "filename": filename
        }

    except Exception as e:
        print(f"[DocumentRAG] Ingest error: {e}")
        return {"error": str(e)}


def query_document(query: str, doc_id: str, top_k: int = 3) -> list[dict]:
    """
    Search within an uploaded document using semantic similarity.

    Args:
        query:  The legal question to answer
        doc_id: Document session ID
        top_k:  Number of chunks to retrieve

    Returns:
        List of relevant document chunks with similarity scores
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.PersistentClient(path=CHROMA_PATH)
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        collection_name = f"doc_{doc_id[:12].replace('-', '_')}"

        try:
            collection = client.get_collection(
                name=collection_name,
                embedding_function=embed_fn
            )
        except Exception:
            return []

        if collection.count() == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"]
        )

        output = []
        for i, doc in enumerate(results["documents"][0]):
            output.append({
                "text": doc,
                "chunk_index": results["metadatas"][0][i].get("chunk_index", i),
                "score": round(1 - results["distances"][0][i], 3),
                "filename": results["metadatas"][0][i].get("filename", "unknown")
            })

        return output

    except Exception as e:
        print(f"[DocumentRAG] Query error: {e}")
        return []


def cross_reference_with_laws(doc_chunks: list[dict],
                               laws_engine) -> list[dict]:
    """
    Cross-reference document chunks with the Indian law database.
    For each relevant chunk, find matching statutes from ChromaDB.

    Args:
        doc_chunks:   Chunks retrieved from uploaded document
        laws_engine:  LexOpsChromaEngine instance

    Returns:
        List of matches with document text + relevant statutes
    """
    cross_refs = []

    for chunk in doc_chunks:
        try:
            # Search Indian law database for statutes matching this chunk
            law_results = laws_engine.search_laws(chunk["text"], top_k=2)

            cross_refs.append({
                "document_excerpt": chunk["text"][:200] + "...",
                "chunk_score": chunk["score"],
                "matching_statutes": [
                    {
                        "act": r.get("act", ""),
                        "section": r.get("section", ""),
                        "relevance": r.get("score", 0),
                        "text": r.get("text", "")[:150]
                    }
                    for r in law_results
                ]
            })
        except Exception as e:
            print(f"[DocumentRAG] Cross-reference error: {e}")

    return cross_refs


def cleanup_document(doc_id: str):
    """Delete a document's ChromaDB collection after session ends."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection_name = f"doc_{doc_id[:12].replace('-', '_')}"
        client.delete_collection(collection_name)
        print(f"[DocumentRAG] Cleaned up collection: {collection_name}")
    except Exception as e:
        print(f"[DocumentRAG] Cleanup error: {e}")


def process_uploaded_document(raw_input, input_type: str,
                               laws_engine=None) -> dict:
    """
    Full Document RAG pipeline:
    1. Extract text from PDF or plain text
    2. Chunk the document
    3. Embed and store in ChromaDB
    4. Cross-reference with Indian law database
    5. Return structured analysis

    Args:
        raw_input:    PDF bytes or text string
        input_type:   'pdf' or 'text'
        laws_engine:  LexOpsChromaEngine for cross-referencing

    Returns:
        Dict with extracted text, chunks, cross-references
    """
    doc_id = str(uuid.uuid4())

    # Step 1: Extract text
    if input_type == "pdf":
        text = extract_text_from_pdf(raw_input)
        filename = "uploaded_document.pdf"
    else:
        text = str(raw_input)
        filename = "uploaded_text.txt"

    if not text or len(text) < 50:
        return {
            "doc_id": doc_id,
            "error": "Could not extract sufficient text from document",
            "text": "",
            "chunks": 0,
            "cross_references": []
        }

    # Step 2 & 3: Chunk and embed into ChromaDB
    ingest_result = ingest_document_to_chroma(text, doc_id, filename)

    if "error" in ingest_result:
        return {
            "doc_id": doc_id,
            "error": ingest_result["error"],
            "text": text[:500],
            "chunks": 0,
            "cross_references": []
        }

    # Step 4: Find most relevant parts of the document
    key_queries = [
        "legal violation rights entitlement claim",
        "complaint dispute resolution remedy",
        "employer employee salary wages payment"
    ]

    all_chunks = []
    for q in key_queries:
        chunks = query_document(q, doc_id, top_k=2)
        all_chunks.extend(chunks)

    # Deduplicate by chunk index
    seen = set()
    unique_chunks = []
    for c in all_chunks:
        if c["chunk_index"] not in seen:
            seen.add(c["chunk_index"])
            unique_chunks.append(c)

    # Sort by relevance score
    unique_chunks.sort(key=lambda x: x["score"], reverse=True)
    top_chunks = unique_chunks[:4]

    # Step 5: Cross-reference with Indian law database
    cross_refs = []
    if laws_engine and top_chunks:
        cross_refs = cross_reference_with_laws(top_chunks, laws_engine)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "text": text,
        "text_preview": text[:300] + "..." if len(text) > 300 else text,
        "total_chars": len(text),
        "chunks_created": ingest_result.get("chunks", 0),
        "top_chunks": top_chunks,
        "cross_references": cross_refs,
        "rag_ready": True
    }