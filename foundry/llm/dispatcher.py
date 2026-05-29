"""LiteLLMDispatcher — reads provider/model config from the DB instead of YAML."""

from __future__ import annotations

import os
from typing import Any, Optional

import litellm

from foundry.llm.audit import AuditLogger
from foundry.llm.base import LLMResponse, TriageLLM


class LiteLLMDispatcher(TriageLLM):
    def __init__(self, db_config: list[dict], audit_path: str) -> None:
        """
        db_config: list of role-config dicts from db.llm_config_for_role().
        Each dict has: provider_name, provider_type, base_url, api_key_env_var, model_id.
        Keyed by role_name for fast lookup.
        """
        self._roles: dict[str, dict] = {c["role_name"]: c for c in db_config if "role_name" in c}
        self._audit = AuditLogger(audit_path)

    @classmethod
    def from_db(cls) -> "LiteLLMDispatcher":
        from foundry.dashboard import db as _db
        conn = _db.get_conn()
        try:
            roles = _db.llm_roles_list(conn)
            configs = []
            for r in roles:
                if r.get("model_id") is None:
                    continue
                cfg = _db.llm_config_for_role(conn, r["role_name"])
                if cfg:
                    cfg["role_name"] = r["role_name"]
                    configs.append(cfg)
        finally:
            conn.close()

        import os as _os
        audit_path = str(
            __import__("pathlib").Path(_os.environ.get("FOUNDRY_DB_PATH", "")).parent
            if _os.environ.get("FOUNDRY_DB_PATH")
            else __import__("pathlib").Path.home() / ".foundry"
        )
        return cls(configs, audit_path)

    def _config_for(self, role: str) -> dict[str, Any]:
        cfg = self._roles.get(role) or self._roles.get("default")
        if cfg is None:
            raise ValueError(
                f"No LLM config for role {role!r} and no default role configured. "
                "Add a provider/model/role in Settings."
            )
        return cfg

    def _litellm_model_string(self, cfg: dict) -> str:
        if cfg["provider_type"] == "anthropic":
            return cfg["model_id"]
        return f"openai/{cfg['model_id']}"

    def analyze(
        self,
        role: str,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        content_hint: Optional[str] = None,
    ) -> LLMResponse:
        cfg = self._config_for(role)
        model_str = self._litellm_model_string(cfg)

        kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
        }

        if cfg.get("base_url"):
            kwargs["api_base"] = cfg["base_url"]

        api_key_env = cfg.get("api_key_env_var", "")
        if api_key_env:
            api_key = os.environ.get(api_key_env, "")
            if api_key:
                kwargs["api_key"] = api_key

        response = litellm.completion(**kwargs)

        text = response.choices[0].message.content or ""
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost_usd = litellm.completion_cost(completion_response=response)

        self._audit.log(
            role=role,
            provider=cfg["provider_name"],
            model=cfg["model_id"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            prompt_hash=AuditLogger.hash_prompt(prompt),
        )

        return LLMResponse(
            text=text,
            provider=cfg["provider_name"],
            model=cfg["model_id"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
