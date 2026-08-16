from pathlib import Path
import os

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = Path(os.getenv("SBI_DATABASE_PATH", str(BASE_DIR / "sbi.db")))
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def migrate_database():
    inspector = inspect(engine)
    if "manual_assets" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("manual_assets")}
    if "institution" in columns:
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE manual_assets DROP COLUMN institution")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
