import os
from typing import List, Tuple
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", extra="allow")

    LLM_API_KEYS: str = "mock_key_1,mock_key_2"
    DATABASE_URL: str = "sqlite:///data/app.db"
    ALLOWED_ORIGINS: str = "*"
    ENABLE_FAILURE_SIMULATION: bool = True
    DEFAULT_MODEL: str = "gemini/gemini-2.0-flash"
    DEFAULT_SYSTEM_PROMPT: str = "You are a helpful and concise AI assistant."
    MOCK_LLM: bool = False

    @property
    def key_pool(self) -> List[Tuple[str, str]]:
        """
        Parses LLM_API_KEYS into ordered pairs: [('key_1', '...'), ('key_2', '...'), ...]
        """
        raw_keys = [k.strip() for k in self.LLM_API_KEYS.split(",") if k.strip()]
        if not raw_keys:
            raw_keys = ["mock_key_1", "mock_key_2"]
        return [(f"key_{i+1}", key) for i, key in enumerate(raw_keys)]

    @property
    def cors_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS or self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
