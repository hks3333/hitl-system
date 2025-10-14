from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str
    LANGCHAIN_API_KEY: str
    GROQ_API_KEY: str
    langchain_tracing_v2: str = "false"

    class Config:
        env_file = ".env"

settings = Settings()