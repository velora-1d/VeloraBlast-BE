
from database import engine
import models

print("Creating tables in PostgreSQL...")
try:
    models.Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully!")
except Exception as e:
    print(f"❌ Error creating tables: {e}")
