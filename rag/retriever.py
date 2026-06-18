import os
import faiss
import pickle
import numpy as np  # <-- ADDED: FAISS requires numpy to format the arrays!

class Retriever:
    def __init__(self):
        # Get the absolute path of the 'rag' folder
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Build the correct paths to your database files
        index_path = os.path.join(base_dir, "index.faiss")
        chunks_path = os.path.join(base_dir, "chunks.pkl")
        
        # Load the files using the absolute paths
        self.index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            self.chunks = pickle.load(f)

        # =================================================================
        # ⚠️ CRITICAL: Initialize your embedding model here!
        # If you built this database using sentence-transformers, it should look like:
        # from sentence_transformers import SentenceTransformer
        # self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        # =================================================================
        
        # self.embedder = ... (Add your embedder initialization here)

    def retrieve(self, query, k=3):
        # Generate the embedding for the user's voice prompt
        try:
            query_embedding = next(self.embedder.embed([query]))
        except AttributeError:
            # Fallback just in case you are using the standard sentence-transformers syntax instead
            query_embedding = self.embedder.encode([query])[0]

        # Convert to a float32 numpy array (Required by FAISS)
        query_embedding = np.array([query_embedding], dtype=np.float32)

        # Search the FAISS index for the 'k' closest matches
        scores, indices = self.index.search(query_embedding, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            # Fetch the actual text chunk matching the FAISS index
            results.append(self.chunks[idx])

        return results