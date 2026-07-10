import os
import chromadb
from chromadb.config import Settings

# Make sure the vector_store directory exists
storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "vector_store")
os.makedirs(storage_dir, exist_ok=True)

# Initialize ChromaDB persistent client
chroma_client = chromadb.PersistentClient(path=storage_dir)

def get_chroma_collection(collection_name="knowledge_base"):
    """
    Returns a ChromaDB collection. Creates it if it doesn't exist.
    """
    # We use the default embedding function (all-MiniLM-L6-v2) automatically provided by ChromaDB
    # when sentence-transformers is installed.
    collection = chroma_client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"} # Use cosine similarity for text search
    )
    return collection
