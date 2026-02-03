import sqlite3
import os

DB_FILE = "./velora_blast.db"

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Database {DB_FILE} not found. Skipping migration.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Check if name column exists
        cursor.execute("PRAGMA table_info(templates)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "name" not in columns:
            print("Adding 'name' column to 'templates' table...")
            cursor.execute("ALTER TABLE templates ADD COLUMN name VARCHAR DEFAULT 'Untitled'")
            conn.commit()
            print("Migration successful.")
        else:
            print("'name' column already exists.")
            
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
