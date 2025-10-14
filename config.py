from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    RABBITMQ_URL: str
    LANGCHAIN_API_KEY: str
    GROQ_API_KEY: str
    LANGCHAIN_TRACING_V2: str = "false"
    LANGCHAIN_ENDPOINT: str
    LANGCHAIN_PROJECT: str

    class Config:
        env_file = ".env"

settings = Settings()