"""Fix the PostgreSQL enrollmentstatus enum to include saved_for_later."""
import sys
sys.path.insert(0, ".")

from sqlalchemy import text
from app.db.session import SessionLocal

db = SessionLocal()
try:
    # PostgreSQL requires the enum value be added before any transaction that uses it
    # We must run this outside a regular transaction block
    db.execute(text("COMMIT"))
    db.execute(text("ALTER TYPE enrollmentstatus ADD VALUE IF NOT EXISTS 'saved_for_later' BEFORE 'selected'"))
    db.execute(text("COMMIT"))
    print("SUCCESS: enrollmentstatus enum updated with saved_for_later")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    db.close()
