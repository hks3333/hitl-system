# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    class Config:
        env_file = ".env"

settings = Settings()
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()