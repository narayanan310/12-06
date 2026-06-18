"""
rag_resolver.py
Adapter to connect main.py to the FAISS RAG system in the rag/ folder.
"""
import sys
import os
import time

# Add the 'rag' folder to the system path so Python can find retriever.py
sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))

try:
    from retriever import Retriever 
except ImportError as e:
    print(f"[RAG] Failed to import from rag/ folder: {e}")
    Retriever = None

class RAGResolver:
    def __init__(self):
        if Retriever:
            self.retriever = Retriever()
            print("[RAG] FAISS Vector Database initialized.")
        else:
            self.retriever = None

    def resolve(self, text: str) -> dict | None:
        """Queries the FAISS RAG and formats the output for main.py."""
        if not self.retriever:
            return None

        start_time = time.time()
        
        try:
            # Matches the exact function name in your retriever.py
            results = self.retriever.retrieve(text) 
        except Exception as e:
            print(f"[RAG] FAISS Search Error: {e}")
            return None
        
        if not results:
            return None

        latency_ms = int((time.time() - start_time) * 1000)

        # FAISS returns a list of text chunks. 
        # We must join them into one string so the assistant can speak it!
        answer = "\n".join(results)

        # Return the intent format that main.py expects
        return {
            "command": "RAG_RESPONSE",
            "answer": answer,
            "confidence": 0.90, 
            "handled_by": "RAG_FAISS",
            "reason": "Retrieved from owner's manual vector index.",
            "latency": f"{latency_ms}ms",
        }