import pickle

with open("rag/chunks.pkl", "rb") as f:
    chunks = pickle.load(f)

print(type(chunks))
print("Chunks:", len(chunks))

print("\nFirst chunk:\n")
print(chunks[0])