import faiss

index = faiss.read_index("rag/index.faiss")

print("Vectors:", index.ntotal)
print("Dimensions:", index.d)