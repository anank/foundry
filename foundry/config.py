from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings

load_dotenv()


class FoundryConfig(BaseSettings):
    anthropic_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    foundry_vault_path: str = "./vault"
    foundry_log_level: str = "INFO"

    # Populated after init from models.yaml
    models: dict[str, Any] = {}

    model_config = {"env_file": ".env", "extra": "ignore"}

    @field_validator("foundry_vault_path")
    @classmethod
    def vault_path_must_exist_or_be_set(cls, v: str) -> str:
        return v

    def load_models_yaml(self) -> None:
        models_path = Path(self.foundry_vault_path) / "models.yaml"
        if models_path.exists():
            with models_path.open("r", encoding="utf-8") as f:
                self.models = yaml.safe_load(f) or {}

    @property
    def vault_path(self) -> str:
        return self.foundry_vault_path

    @property
    def log_level(self) -> str:
        return self.foundry_log_level


def load_config() -> FoundryConfig:
    config = FoundryConfig()
    config.load_models_yaml()
    return config
