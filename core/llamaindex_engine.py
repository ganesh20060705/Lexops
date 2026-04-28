# LexOps | core/llamaindex_engine.py

import os
from dotenv import load_dotenv

from llama_index.core import (
    VectorStoreIndex,
    KnowledgeGraphIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings,
    load_index_from_storage
)

from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.tools import QueryEngineTool
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector

from llama_index.vector_stores.faiss import FaissVectorStore
import faiss

from llama_index.llms.groq import Groq
from llama_index.llms.ollama import Ollama

load_dotenv()

DATA_PATH = os.getenv("DATA_PATH", "./data/laws/")
JUDGMENT_PATH = os.getenv("JUDGMENT_PATH", "./data/judgments/")
STORAGE_PATH = os.getenv("STORAGE_PATH", "./data/storage/")
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() == "true"


class LexOpsEngine:
    def __init__(self):

        Settings.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            cache_folder="./models"
        )

        if USE_OLLAMA:
            Settings.llm = Ollama(
                model="llama3",
                request_timeout=120.0
            )
        else:
            Settings.llm = Groq(
                model="llama-3.1-8b-instant",
                api_key=os.getenv("GROQ_API_KEY")
            )

        self.vector_index = None
        self.graph_index = None
        self.router_query_engine = None

        self._initialize_indices()
        self._initialize_router()

    def _initialize_indices(self):
        vec_path = os.path.join(STORAGE_PATH, "vector")
        graph_path = os.path.join(STORAGE_PATH, "graph")

        # -------- VECTOR INDEX --------
        try:
            if os.path.exists(vec_path) and os.listdir(vec_path):
                storage_context = StorageContext.from_defaults(persist_dir=vec_path)
                self.vector_index = load_index_from_storage(storage_context)
                print("[LlamaIndex] Loaded vector index from storage.")
            else:
                if os.path.exists(DATA_PATH) and os.listdir(DATA_PATH):
                    docs = SimpleDirectoryReader(DATA_PATH).load_data()

                    d = 384
                    faiss_index = faiss.IndexFlatL2(d)
                    vector_store = FaissVectorStore(faiss_index=faiss_index)
                    storage_context = StorageContext.from_defaults(
                        vector_store=vector_store
                    )

                    self.vector_index = VectorStoreIndex.from_documents(
                        docs,
                        storage_context=storage_context
                    )

                    os.makedirs(vec_path, exist_ok=True)
                    self.vector_index.storage_context.persist(persist_dir=vec_path)
                    print("[LlamaIndex] Built and saved vector index.")
                else:
                    print("[LlamaIndex] No law documents found. Vector index skipped.")
                    self.vector_index = None
        except Exception as e:
            print(f"[LlamaIndex] Vector index error: {e}. Skipping.")
            self.vector_index = None

        # -------- GRAPH INDEX --------
        try:
            if os.path.exists(graph_path) and os.listdir(graph_path):
                storage_context = StorageContext.from_defaults(persist_dir=graph_path)
                self.graph_index = load_index_from_storage(storage_context)
                print("[LlamaIndex] Loaded graph index from storage.")
            else:
                if os.path.exists(JUDGMENT_PATH) and os.listdir(JUDGMENT_PATH):
                    docs = SimpleDirectoryReader(JUDGMENT_PATH).load_data()

                    self.graph_index = KnowledgeGraphIndex.from_documents(
                        docs,
                        max_triplets_per_chunk=2,
                        include_embeddings=True
                    )

                    os.makedirs(graph_path, exist_ok=True)
                    self.graph_index.storage_context.persist(persist_dir=graph_path)
                    print("[LlamaIndex] Built and saved graph index.")
                else:
                    print("[LlamaIndex] No judgment documents found. Graph index skipped.")
                    self.graph_index = None
        except Exception as e:
            print(f"[LlamaIndex] Graph index skipped (LLM error or no data): {e}")
            self.graph_index = None

    def _initialize_router(self):
        if not self.vector_index or not self.graph_index:
            print("[LlamaIndex] Router skipped — one or both indices unavailable.")
            return

        try:
            vec_query_engine = self.vector_index.as_query_engine(
                similarity_top_k=3,
                response_mode="compact"
            )

            graph_query_engine = self.graph_index.as_query_engine(
                similarity_top_k=3,
                response_mode="compact"
            )

            vec_tool = QueryEngineTool.from_defaults(
                query_engine=vec_query_engine,
                description="Useful for retrieving statutes, laws, and legal sections."
            )

            graph_tool = QueryEngineTool.from_defaults(
                query_engine=graph_query_engine,
                description="Useful for retrieving judgments, cases, and rulings."
            )

            self.router_query_engine = RouterQueryEngine(
                selector=LLMSingleSelector.from_defaults(),
                query_engine_tools=[vec_tool, graph_tool]
            )
            print("[LlamaIndex] Router query engine ready.")
        except Exception as e:
            print(f"[LlamaIndex] Router init failed: {e}")
            self.router_query_engine = None

    def retrieve_statutes(self, query: str, top_k: int = 5):
        if not self.vector_index:
            return []
        try:
            retriever = self.vector_index.as_retriever(similarity_top_k=top_k)
            return retriever.retrieve(query)
        except Exception as e:
            print(f"[LlamaIndex] retrieve_statutes error: {e}")
            return []

    def retrieve_judgments(self, query: str, top_k: int = 3):
        if not self.graph_index:
            return []
        try:
            retriever = self.graph_index.as_retriever(similarity_top_k=top_k)
            return retriever.retrieve(query)
        except Exception as e:
            print(f"[LlamaIndex] retrieve_judgments error: {e}")
            return []

    def smart_retrieve(self, query: str):
        if not self.router_query_engine:
            return {
                "statutes": [],
                "judgments": [],
                "router_decision": "none"
            }

        try:
            response = self.router_query_engine.query(query)
            decision = (
                response.metadata.get("selector_result", "unknown")
                if response.metadata else "unknown"
            )

            statutes = []
            judgments = []

            if "statute" in str(decision).lower():
                statutes = response.source_nodes
            else:
                judgments = response.source_nodes

            return {
                "statutes": statutes,
                "judgments": judgments,
                "router_decision": str(decision)
            }
        except Exception as e:
            print(f"[LlamaIndex] smart_retrieve error: {e}")
            return {"statutes": [], "judgments": [], "router_decision": "error"}

    def get_retriever(self):
        if not self.vector_index:
            return None
        return self.vector_index.as_retriever(similarity_top_k=5)


if __name__ == "__main__":
    print("Testing LexOpsEngine initialization...")
    engine = LexOpsEngine()
    print("LexOpsEngine initialized successfully.")