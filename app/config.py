from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    host: str = '127.0.0.1'
    port: int = 8000
    model_provider: str = 'clinic-policy'
    model_name: str = 'clinic-policy-v1'
    gemini_api_key: str = ''
    google_api_key: str = ''
    anthropic_api_key: str = ''
    openrouter_api_key: str = ''
    max_steps: int = Field(default=6, ge=1, le=6)
    max_tool_retries: int = Field(default=2, ge=0, le=2)
    max_output_tokens: int = Field(default=512, ge=1)
    run_timeout_seconds: float = Field(default=40, gt=0, le=40)
    max_concurrent_runs: int = Field(default=8, ge=1, le=32)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=600)
    max_spend_usd: float = Field(default=5.0, ge=0)


settings = Settings()
