"""Pydantic verdict models for the triage pipeline.

These were previously in foundry/vault/schema.py. Moved here so the triage
modules don't depend on the vault layer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field


class BrainDumpEntry(BaseModel):
    model_config = {"populate_by_name": True}

    timestamp: str
    type: Literal["idea", "feature", "bug", "task"]
    project: Optional[str] = None
    content: str
    context: Optional[str] = None
    state: Optional[Literal["energized", "tired", "frustrated", "inspired", "bored"]] = None
    source: Optional[Literal["app", "obsidian"]] = None
    triage_status: Literal["pending", "classified", "killed", "advanced"] = "pending"


class CheckResult(BaseModel):
    model_config = {"populate_by_name": True}

    pass_: bool = Field(alias="pass")
    reasoning: str


class IdeaKillerVerdict(BaseModel):
    model_config = {"populate_by_name": True}

    verdict: Literal["KILL", "PARK", "ADVANCE"]
    checks: dict[str, CheckResult]
    verdict_reasoning: str
    park_revival_condition: Optional[str] = None
    related_killed_ideas: list[str] = Field(default_factory=list)


class FeatureKillerVerdict(BaseModel):
    model_config = {"populate_by_name": True}

    verdict: Literal["KILL", "PARK", "ADVANCE"]
    checks: dict[str, CheckResult]
    verdict_reasoning: str
    park_revival_condition: Optional[str] = None


class BugTriageResult(BaseModel):
    model_config = {"populate_by_name": True}

    reproducible: bool
    impact: Literal["data_loss", "wrong_output", "annoyance", "cosmetic"]
    workaround_exists: bool
    severity: Literal["critical", "high", "low"]
    notes: str


class Task(BaseModel):
    model_config = {"populate_by_name": True}

    id: str
    title: str
    status: Literal["queued", "building", "review", "approved", "rejected"]
    project: str
    review_tag: Literal["behavioral", "output", "code"] = "code"
    estimated_diff: Optional[int] = None
    token_budget: Optional[int] = None
    created: date
    spec_locked: bool = False
    spec: Optional[str] = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    files_expected: list[str] = Field(default_factory=list)
