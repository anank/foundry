"""Tests for LiteLLMDispatcher with DB-based config."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from foundry.dashboard import db
from foundry.llm.audit import AuditLogger
from foundry.llm.base import LLMResponse, TriageLLM
from foundry.llm.dispatcher import LiteLLMDispatcher


def _make_litellm_response(text: str, input_tokens: int = 10, output_tokens: int = 20) -> MagicMock:
    response = MagicMock()
    response.choices[0].message.content = text
    response.usage.prompt_tokens = input_tokens
    response.usage.completion_tokens = output_tokens
    return response


@pytest.fixture
def tmp_db(tmp_path: Path):
    db.init_db(tmp_path / "test.db")
    yield tmp_path


def _setup_dispatcher(tmp_path: Path, provider_type: str = "anthropic") -> LiteLLMDispatcher:
    conn = db.get_conn()
    try:
        prov_id = db.llm_provider_create(conn, name="TestProvider", type=provider_type,
                                          api_key_env_var="TEST_API_KEY",
                                          base_url="http://localhost:11434/v1" if provider_type == "openai_compatible" else "")
        model_pk = db.llm_model_create(conn, prov_id, model_id="test-model", display_name="Test Model")
        db.llm_role_assign(conn, "default", model_pk)
        db.llm_role_assign(conn, "classifier", model_pk)
        db.llm_role_assign(conn, "idea_killer", model_pk)
    finally:
        conn.close()

    configs = []
    conn = db.get_conn()
    try:
        for role in ["default", "classifier", "idea_killer"]:
            cfg = db.llm_config_for_role(conn, role)
            if cfg:
                cfg["role_name"] = role
                configs.append(cfg)
    finally:
        conn.close()

    return LiteLLMDispatcher(configs, str(tmp_path))


class TestDispatcherAnalyze:
    def test_analyze_calls_litellm(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("classified")

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.0001):
            result = dispatcher.analyze("classifier", "sys", "prompt")

        assert result.text == "classified"
        assert result.provider == "TestProvider"
        assert result.model == "test-model"

    def test_analyze_returns_llm_response(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("result", input_tokens=5, output_tokens=15)

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.002):
            result = dispatcher.analyze("idea_killer", "sys", "prompt")

        assert isinstance(result, LLMResponse)
        assert result.input_tokens == 5
        assert result.output_tokens == 15
        assert result.cost_usd == 0.002

    def test_unknown_role_falls_back_to_default(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("ok")

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.0):
            result = dispatcher.analyze("unknown_role", "sys", "prompt")

        assert result.text == "ok"

    def test_no_config_raises(self, tmp_db):
        dispatcher = LiteLLMDispatcher([], str(tmp_db))
        with pytest.raises(ValueError, match="No LLM config"):
            dispatcher.analyze("classifier", "sys", "prompt")

    def test_openai_compatible_uses_openai_prefix(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db, provider_type="openai_compatible")
        mock_response = _make_litellm_response("ok")
        captured = {}

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("litellm.completion", side_effect=fake_completion), \
             patch("litellm.completion_cost", return_value=0.0):
            dispatcher.analyze("classifier", "sys", "prompt")

        assert captured["model"].startswith("openai/")
        assert "api_base" in captured

    def test_anthropic_uses_bare_model_name(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db, provider_type="anthropic")
        mock_response = _make_litellm_response("ok")
        captured = {}

        def fake_completion(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("litellm.completion", side_effect=fake_completion), \
             patch("litellm.completion_cost", return_value=0.0):
            dispatcher.analyze("classifier", "sys", "prompt")

        assert captured["model"] == "test-model"


class TestAuditLog:
    def test_audit_log_written_after_analyze(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("result")

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.001):
            dispatcher.analyze("classifier", "sys", "prompt")

        audit_file = tmp_db / "audit.jsonl"
        assert audit_file.exists()
        lines = [json.loads(l) for l in audit_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        assert lines[0]["role"] == "classifier"
        assert lines[0]["model"] == "test-model"

    def test_audit_log_appends_multiple_calls(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("result")

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.0):
            dispatcher.analyze("classifier", "sys", "p1")
            dispatcher.analyze("idea_killer", "sys", "p2")

        audit_file = tmp_db / "audit.jsonl"
        lines = [json.loads(l) for l in audit_file.read_text().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_audit_log_prompt_hash_not_plaintext(self, tmp_db):
        dispatcher = _setup_dispatcher(tmp_db)
        mock_response = _make_litellm_response("result")
        secret_prompt = "my secret trading strategy"

        with patch("litellm.completion", return_value=mock_response), \
             patch("litellm.completion_cost", return_value=0.0):
            dispatcher.analyze("classifier", "sys", secret_prompt)

        audit_file = tmp_db / "audit.jsonl"
        content = audit_file.read_text()
        assert secret_prompt not in content
        assert "sha256:" in content


class TestAuditLogger:
    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        logger = AuditLogger(str(nested))
        assert nested.exists()

    def test_timestamp_is_utc_iso8601(self, tmp_path):
        logger = AuditLogger(str(tmp_path))
        logger.log("role", "prov", "model", 1, 1, 0.0, "sha256:abc")
        line = json.loads((tmp_path / "audit.jsonl").read_text().strip())
        assert line["timestamp"].endswith("Z")
        assert "T" in line["timestamp"]
