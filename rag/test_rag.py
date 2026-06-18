from retriever import Retriever


rag = Retriever()


while True:

    query = input("Query: ")

    results = rag.retrieve(query)

    print("\nRESULTS:\n")

    for r in results:

        print(r)

        print("=" * 80)