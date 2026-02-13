from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):
    GEMINI_API_KEY: str = Field(..., min_length=1, description="Google Gemini API Key")
    DATABASE_URL: str = Field(..., description="PostgreSQL Connection String")
    ENVIRONMENT: str = Field("local", description="Environment: local, dev, prod")
    
    # Model config to read from .env file
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the Settings object.
    Dependency injection helper.
    """
    return Settings()

settings = get_settings()
