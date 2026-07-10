import os
import mysql.connector
from arango import ArangoClient
import chromadb
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_mysql_connection():
    """Establish and return a connection to the MySQL database."""
    try:
        conn_params = {
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME")
        }
        connection = mysql.connector.connect(**conn_params)
        if connection.is_connected():
            print("Successfully connected to MySQL database.")
            return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None

def get_arango_db():
    """Establish and return a connection to the ArangoDB database."""
    try:
        url = os.getenv("ARANGO_URL")
        client = ArangoClient(hosts=url)
        db_name = os.getenv("ARANGO_DB")
        user = os.getenv("ARANGO_USER")
        password = os.getenv("ARANGO_PASSWORD")
        db = client.db(db_name, username=user, password=password)
        print("Successfully connected to ArangoDB.")
        return db
    except Exception as err:
        print(f"Error connecting to ArangoDB: {err}")
        return None

def get_chroma_collection(collection_name="knowledge_base"):
    """Returns a ChromaDB collection. Creates it if it doesn't exist."""
    try:
        api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        storage_dir = os.path.join(api_dir, "chroma_store")
        os.makedirs(storage_dir, exist_ok=True)
        chroma_client = chromadb.PersistentClient(path=storage_dir)
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        print("Successfully retrieved ChromaDB collection.")
        return collection
    except Exception as err:
        print(f"Error connecting to ChromaDB: {err}")
        return None
