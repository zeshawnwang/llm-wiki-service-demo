from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal
import os


class Settings(BaseSettings):
    """????"""

    # ========== LLM ????? ==========
    llm_provider: Literal["openai", "anthropic"] = "openai"

    # OpenAI ??
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # Anthropic ??
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_chat_model: str = "claude-sonnet-4-20250514"

    # ========== ?????? ==========
    enable_vector_search: bool = True
    vector_dim: int = 1536
    top_k: int = 5

    # ========== ?????? ==========
    qa_retrieval_mode: str = "ai"  # ai | auto
    qa_ai_direct_threshold: int = 200  # auto???,Wiki????????????AI

    # ========== ???? ==========
    app_name: str = "LLM Wiki Service"
    debug: bool = True
    log_level: str = "INFO"

    # ========== ?????? ==========
    data_dir: str = "./data"
    raw_dir: str = "./data/raw"
    wiki_dir: str = "./data/wiki"

    # ========== ???? ==========
    host: str = "0.0.0.0"
    port: int = 8000

    # ========== Git ???? ==========
    git_sync_enabled: bool = False
    git_sync_interval_minutes: int = 30
    git_repo_path: str = "./data"
    git_remote_url: str = ""
    git_user_name: str = "LLM Wiki Bot"
    git_user_email: str = "llm-wiki-service-demo-bot@example.com"
    git_branch: str = "main"
    git_commit_message: str = ""  # ???????

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def chat_model(self) -> str:
        """??????????????"""
        if self.llm_provider == "anthropic":
            return self.anthropic_chat_model
        return self.openai_chat_model

    @property
    def embedding_model(self) -> str:
        """??embedding????(???OpenAI??)"""
        return self.openai_embedding_model

    @property
    def is_openai(self) -> bool:
        return self.llm_provider == "openai"

    @property
    def is_anthropic(self) -> bool:
        return self.llm_provider == "anthropic"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def ensure_directories():
    """????????"""
    settings = get_settings()
    dirs = [
        settings.data_dir,
        settings.raw_dir,
        settings.wiki_dir,
        os.path.join(settings.wiki_dir, "pages"),
        os.path.join(settings.wiki_dir, "index"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
