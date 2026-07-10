import os
import chromadb

# Set correct storage path
storage_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "vector_store")

try:
    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=storage_dir)
    
    # List all collections (like 'SHOW TABLES' in MySQL)
    collections = client.list_collections()
    print("="*60)
    print("   CHROMADB COLLECTIONS (TABLES)")
    print("="*60)
    for col in collections:
        print(f"- Collection Name: {col.name}")
    print("\n")
    
    collection = client.get_collection("knowledge_base")
    
    # Retrieve documents and their vector embeddings (embeddings)
    data = collection.get(include=["embeddings", "documents", "metadatas"])
    
    if data is not None and data.get('embeddings') is not None and len(data['embeddings']) > 0:
        total_items = len(data['embeddings'])
        print("="*60)
        print("   CHROMADB VECTOR EMBEDDINGS (KNOWLEDGE BASE)")
        print(f"   Total Chunks Stored: {total_items}")
        print("="*60)
        
        # Display the first 3 items as an example
        limit = min(3, total_items)
        for i in range(limit):
            print(f"\n[Item {i+1} - Chunk of the same article]")
            print(f"Title/Source: {data['metadatas'][i].get('title', 'N/A')}")
            print(f"Source URL  : {data['metadatas'][i].get('source_url', 'N/A')}")
            print(f"Text Content: {data['documents'][i][:150]}...")
            
            # Print the actual vector (first 5 dimensions)
            vector = data['embeddings'][i]
            print(f"Vector Dimensions: {len(vector)}")
            print(f"Vector Values (First 5 floats): {vector[:5]}")
            print("-" * 50)
            
    else:
        print("No vector embeddings found in the collection.")
        
except Exception as e:
    print(f"Error loading vectors: {e}")
