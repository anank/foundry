"""Audit logger — writes one JSONL line per LLM call to ~/.foundry/audit.jsonl."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class AuditLogger:
    def __init__(self, foundry_dir: str) -> None:
        self._audit_path = Path(foundry_dir) / "audit.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"

    def log(
        self,
        role: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        prompt_hash: str,
        verdict: Optional[str] = None,
    ) -> None:
        record: dict = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "role": role,
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "prompt_hash": prompt_hash,
        }
        if verdict is not None:
            record["verdict"] = verdict
        with self._audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
