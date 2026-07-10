import os
import shutil
import sys
from dotenv import load_dotenv

# Ensure correct path resolution
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.dbConnection import get_mysql_connection, get_arango_db

def reset_databases():
    print("==================================================")
    print("STARTING DATABASE RESET (FRESH INDEXING PREPARATION)")
    print("==================================================")
    
    # 1. Reset MySQL Tables (preserving users, roles, and connectors)
    print("\n1. Resetting MySQL database tables...")
    conn = get_mysql_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            tables_to_truncate = ["article_topics", "articles_meta", "topics", "scheduler_logs", "search_logs"]
            for table in tables_to_truncate:
                try:
                    cursor.execute(f"TRUNCATE TABLE {table};")
                    print(f"   -> Truncated MySQL table: {table}")
                except Exception as ex:
                    print(f"   -> Failed to truncate {table}: {ex}")
                    
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            conn.commit()
            cursor.close()
            conn.close()
            print("MySQL tables cleared successfully.")
        except Exception as e:
            print(f"Error resetting MySQL: {e}")
    else:
        print("MySQL connection could not be established. Skipping MySQL reset.")

    # 2. Reset ArangoDB Collections
    print("\n2. Resetting ArangoDB collections...")
    db = get_arango_db()
    if db:
        try:
            collections_to_truncate = ["ai_hub_relations", "ai_hub_entities"]
            for col in collections_to_truncate:
                if db.has_collection(col):
                    db.collection(col).truncate()
                    print(f"   -> Truncated ArangoDB collection: {col}")
                else:
                    print(f"   -> ArangoDB collection does not exist: {col}")
            print("ArangoDB collections cleared successfully.")
        except Exception as e:
            print(f"Error resetting ArangoDB: {e}")
    else:
        print("ArangoDB connection could not be established. Skipping ArangoDB reset.")

    # 3. Reset ChromaDB Store
    print("\n3. Wiping ChromaDB vector storage...")
    api_dir = os.path.dirname(os.path.abspath(__file__))
    chroma_dir = os.path.join(api_dir, "chroma_store")
    if os.path.exists(chroma_dir):
        try:
            shutil.rmtree(chroma_dir, ignore_errors=True)
            print("   -> Successfully deleted chroma_store/ folder.")
        except Exception as e:
            print(f"Error deleting chroma_store: {e}")
    else:
        print("   -> chroma_store/ folder does not exist. Already clean.")

    # 4. Wipe Local Graph Visualizations
    print("\n4. Wiping generated local HTML graphs...")
    graph_dir = os.path.join(api_dir, "graph")
    if os.path.exists(graph_dir):
        try:
            shutil.rmtree(graph_dir, ignore_errors=True)
            print("   -> Successfully deleted graph/ visualization folder.")
        except Exception as e:
            print(f"Error deleting graph folder: {e}")
    else:
        print("   -> graph/ folder does not exist. Already clean.")

    print("\n==================================================")
    print("RESET COMPLETED! You can now start fresh indexing.")
    print("==================================================")

if __name__ == "__main__":
    # Load environment variables
    load_dotenv()
    
    # Prompt confirmation
    confirm = input("Are you sure you want to reset all collected/indexed data? This cannot be undone! (y/n): ")
    if confirm.lower().strip() == 'y':
        reset_databases()
    else:
        print("Reset operation aborted by user.")
