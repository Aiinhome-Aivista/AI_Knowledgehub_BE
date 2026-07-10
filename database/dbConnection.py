import os
import mysql.connector
from arango import ArangoClient
from dotenv import load_dotenv

# Load environment variables from api/.env if available
load_dotenv()

def get_mysql_connection():
    """Establish and return a connection to the MySQL database."""
    try:
        # Connect to MySQL first without selecting database to verify connection/create DB
        conn_params = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "3306"),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", "Root@123")
        }
        connection = mysql.connector.connect(**conn_params)
        if connection:
            try:
                cursor = connection.cursor()
                db_name = os.getenv("DB_NAME", "ai_knowledge_hub")
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
                cursor.execute(f"USE {db_name}")
                
                # Create topics table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS topics (
                        id          INT AUTO_INCREMENT PRIMARY KEY,
                        name        VARCHAR(255) NOT NULL,
                        category    VARCHAR(255),
                        description LONGTEXT,
                        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create articles_meta table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS articles_meta (
                        id         INT AUTO_INCREMENT PRIMARY KEY,
                        title      TEXT,
                        source_url VARCHAR(768) UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                connection.commit()
                # Create article_topics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS article_topics (
                        article_id INT,
                        topic_id INT,
                        PRIMARY KEY (article_id, topic_id),
                        FOREIGN KEY (article_id) REFERENCES articles_meta(id) ON DELETE CASCADE,
                        FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
                    )
                """)
                # Create connectors table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS connectors (
                        id VARCHAR(255) PRIMARY KEY,
                        url VARCHAR(768) NOT NULL UNIQUE,
                        type VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Create search_logs table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS search_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        query VARCHAR(255) NOT NULL UNIQUE,
                        count INT DEFAULT 1,
                        last_searched TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    )
                """)
                # Create scheduler_logs table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS scheduler_logs (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        run_at DATETIME NOT NULL,
                        next_run_at DATETIME,
                        interval_hours INT NOT NULL DEFAULT 6,
                        status VARCHAR(50) NOT NULL DEFAULT 'SUCCESS',
                        articles_processed INT DEFAULT 0,
                        nodes_added INT DEFAULT 0,
                        nodes_updated INT DEFAULT 0,
                        edges_added INT DEFAULT 0,
                        errors TEXT,
                        triggered_by VARCHAR(50) DEFAULT 'scheduler',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                connection.commit()

                # Migrate existing connectors from settings.json if table is empty
                cursor.execute("SELECT COUNT(*) FROM connectors")
                count = cursor.fetchone()[0]
                if count == 0:
                    settings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "settings.json")
                    if os.path.exists(settings_path):
                        try:
                            import json
                            import hashlib
                            with open(settings_path, "r", encoding="utf-8") as f:
                                settings = json.load(f)
                            connectors = settings.get("connectors", [])
                            for conn_data in connectors:
                                url = conn_data.get("url")
                                c_type = conn_data.get("type", "rss")
                                c_id = conn_data.get("id") or f"conn_{hashlib.md5(url.encode()).hexdigest()}"
                                if url:
                                    cursor.execute("INSERT IGNORE INTO connectors (id, url, type) VALUES (%s, %s, %s)", (c_id, url, c_type))
                            connection.commit()
                        except Exception as e:
                            print(f"Error migrating connectors to database: {e}")
                
                # Check and migrate roles and users table
                try:
                    # 1. Check and create roles table
                    cursor.execute("SHOW TABLES LIKE 'roles'")
                    if not cursor.fetchone():
                        cursor.execute("""
                            CREATE TABLE roles (
                                role_id INT AUTO_INCREMENT PRIMARY KEY,
                                role_name VARCHAR(50) NOT NULL UNIQUE,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                            )
                        """)
                        cursor.execute("INSERT INTO roles (role_name) VALUES ('admin'), ('viewer')")
                        connection.commit()

                    # 2. Check and migrate users table
                    cursor.execute("SHOW TABLES LIKE 'users'")
                    has_users_table = cursor.fetchone()
                    if has_users_table:
                        # Check if old string 'role' column exists
                        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
                        if cursor.fetchone():
                            # We have the old schema, migrate it
                            # Add 'role_id' column if missing
                            cursor.execute("SHOW COLUMNS FROM users LIKE 'role_id'")
                            if not cursor.fetchone():
                                cursor.execute("ALTER TABLE users ADD COLUMN role_id INT NULL")
                            
                            # Map old 'role' string values to role_id
                            cursor.execute("UPDATE users SET role_id = 1 WHERE role = 'admin'")
                            cursor.execute("UPDATE users SET role_id = 2 WHERE role = 'viewer'")
                            cursor.execute("UPDATE users SET role_id = 2 WHERE role_id IS NULL") # Default fallback
                            
                            # Modify role_id to be NOT NULL
                            cursor.execute("ALTER TABLE users MODIFY COLUMN role_id INT NOT NULL")
                            
                            # Drop old 'role' column
                            cursor.execute("ALTER TABLE users DROP COLUMN role")
                            
                            # Add foreign key constraint
                            try:
                                cursor.execute("ALTER TABLE users ADD FOREIGN KEY (role_id) REFERENCES roles(role_id)")
                            except Exception:
                                pass # In case constraint already exists
                            connection.commit()

                        # Ensure name column exists (rename from first_name if present)
                        cursor.execute("SHOW COLUMNS FROM users LIKE 'name'")
                        if not cursor.fetchone():
                            cursor.execute("SHOW COLUMNS FROM users LIKE 'first_name'")
                            if cursor.fetchone():
                                cursor.execute("ALTER TABLE users CHANGE COLUMN first_name name VARCHAR(100)")
                            else:
                                cursor.execute("ALTER TABLE users ADD COLUMN name VARCHAR(100)")
                            cursor.execute("UPDATE users SET name = 'Sonia' WHERE email = 'sonia123@gmail.com'")
                            cursor.execute("UPDATE users SET name = 'Anindita' WHERE email = 'anindita@gmail.com'")
                            connection.commit()

                        # Ensure old first_name column is dropped if still present
                        cursor.execute("SHOW COLUMNS FROM users LIKE 'first_name'")
                        if cursor.fetchone():
                            cursor.execute("ALTER TABLE users DROP COLUMN first_name")
                            connection.commit()
                    else:
                        # Create users table with new schema if it doesn't exist
                        cursor.execute("""
                            CREATE TABLE users (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                email VARCHAR(255) NOT NULL UNIQUE,
                                password VARCHAR(255) NOT NULL,
                                role_id INT NOT NULL,
                                name VARCHAR(100),
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                FOREIGN KEY (role_id) REFERENCES roles(role_id)
                            )
                        """)
                        cursor.execute("INSERT INTO users (email, password, role_id, name) VALUES ('sonia123@gmail.com', 'sonia@123', 1, 'Sonia')")
                        cursor.execute("INSERT INTO users (email, password, role_id, name) VALUES ('anindita@gmail.com', 'anindita@123', 2, 'Anindita')")
                        connection.commit()
                except mysql.connector.Error as err:
                    print(f"Error migrating database schemas: {err}")
                
                cursor.close()
            except mysql.connector.Error as err:
                print(f"Error initializing database tables: {err}")
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to MySQL: {err}")
        return None

def get_arango_db():
    """Establish and return a connection to the ArangoDB database."""
    try:
        url = os.getenv("ARANGO_URL", "https://7d4b6b5e72ba.arangodb.cloud:8529")
        client = ArangoClient(hosts=url)
        
        # Connect to "_system" db first to ensure our DB exists, though usually we just connect directly
        db_name = os.getenv("ARANGO_DB", "first_poc")
        user = os.getenv("ARANGO_USER", "root")
        password = os.getenv("ARANGO_PASSWORD", "WoeOZCaoknEPCSs6d0N5")
        
        db = client.db(db_name, username=user, password=password)
        return db
    except Exception as err:
        print(f"Error connecting to ArangoDB: {err}")
        return None
