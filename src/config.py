from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://arethey:changeme@localhost:5432/arethey"
    web_port: int = 8000
    base_url: str = "http://localhost:8000"
    scrape_schedule: str = "06:00,12:00,18:00"
    scrape_retry_max: int = 3
    scrape_delay_seconds: int = 2
    ollama_model: str = "qwen2.5:1.5b"
    ollama_host: str = "http://localhost:11434"
    ollama_timeout_seconds: float = 60.0
    classify_concurrency: int = 4
    classify_enabled: bool = True
    anthropic_careers_url: str = "https://www.anthropic.com/careers"
    openai_careers_url: str = "https://openai.com/careers"
    deepmind_careers_url: str = "https://deepmind.google/about/careers/"
    tz: str = "UTC"
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
