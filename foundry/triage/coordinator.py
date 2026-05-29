"""Coordinator — orchestrates the full triage pipeline.

Routes a BrainDumpEntry through the appropriate path:

  entry → Classifier →
    idea    → IdeaKiller → (KILL/PARK: graveyard written, status=killed/parked)
                         | (ADVANCE: Interviewer → Critic loop → Atomizer →
                                     TaskTagger → tasks written → status=advanced)
    feature → FeatureKiller → (KILL/PARK: graveyard written, status=killed/parked)
                             | (ADVANCE: single task written → status=advanced)
    bug     → BugTriager → task written directly → status=advanced
                         | not reproducible → status=needs_input

The Coordinator is stateless between calls. Interview history is passed in
by the caller so the coordinator can be used in both CLI and web contexts.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from foundry.llm.base import TriageLLM
from foundry.triage.atomizer import Atomizer, AtomizedTask
from foundry.triage.bug_triage import BugTriager
from foundry.triage.classifier import Classifier, ClassifierResult
from foundry.triage.critic import Critic
from foundry.triage.feature_killer import FeatureKiller
from foundry.triage.idea_killer import IdeaKiller
from foundry.triage.interviewer import Interviewer
from foundry.triage.task_tagger import TaskTagger
from foundry.vault.schema import (
    BrainDumpEntry,
    BugTriageResult,
    FeatureKillerVerdict,
    IdeaKillerVerdict,
    Task,
)
from foundry.vault.writer import VaultWriter


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class TriageResult(BaseModel):
    """The output of a single coordinator run."""

    entry: BrainDumpEntry
    classifier_result: ClassifierResult
    verdict: Optional[Union[IdeaKillerVerdict, FeatureKillerVerdict, BugTriageResult]] = None
    tasks: list[Task] = Field(default_factory=list)
    status: Literal["killed", "parked", "advanced", "needs_input", "error"]
    message: str = ""


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class Coordinator:
    """Orchestrates the full triage pipeline for a single brain dump entry.

    Args:
        llm: A TriageLLM implementation (real dispatcher or FakeLLM in tests).
        vault_path: Path to the vault root directory.
    """

    def __init__(self, llm: TriageLLM, vault_path: Path) -> None:
        self._llm = llm
        self._vault_path = Path(vault_path)
        self._writer = VaultWriter(self._vault_path)

    def run(
        self,
        entry: BrainDumpEntry,
        interview_history: list[dict] | None = None,
    ) -> TriageResult:
        """Run the full triage pipeline for *entry*.

        Args:
            entry: The brain dump entry to triage.
            interview_history: Prior Q&A pairs for the interviewer, each a dict
                with keys "question" and "answer". Pass an empty list (or None)
                on the first call. Pass the accumulated history on subsequent
                calls after the user has answered a question.

        Returns:
            TriageResult describing the outcome. Check ``status`` first:
              - "killed"      — idea/feature killed, graveyard file written
              - "parked"      — idea/feature parked, graveyard file written
              - "advanced"    — tasks written to vault
              - "needs_input" — waiting for user; ``message`` contains the
                                question or spec gaps to resolve
              - "error"       — unexpected failure; ``message`` contains details
        """
        if interview_history is None:
            interview_history = []

        # ------------------------------------------------------------------
        # Step 1: Classify
        # ------------------------------------------------------------------
        try:
            classifier = Classifier(self._llm, self._vault_path)
            classifier_result = classifier.classify(entry)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=_fallback_classifier_result(entry),
                status="error",
                message=f"Classifier failed: {exc}",
            )

        # If the classifier needs more info from the user, surface that first.
        if classifier_result.action == "ask":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                status="needs_input",
                message=classifier_result.question or "Please clarify your entry.",
            )

        # ------------------------------------------------------------------
        # Route by type
        # ------------------------------------------------------------------
        entry_type = classifier_result.type

        if entry_type == "idea":
            return self._run_idea_path(entry, classifier_result, interview_history)
        elif entry_type == "feature":
            return self._run_feature_path(entry, classifier_result)
        else:  # bug
            return self._run_bug_path(entry, classifier_result)

    # ------------------------------------------------------------------
    # Idea path
    # ------------------------------------------------------------------

    def _run_idea_path(
        self,
        entry: BrainDumpEntry,
        classifier_result: ClassifierResult,
        interview_history: list[dict],
    ) -> TriageResult:
        # Step 2a: Idea Killer
        try:
            killer = IdeaKiller(self._llm, self._vault_path)
            verdict = killer.kill(entry)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                status="error",
                message=f"IdeaKiller failed: {exc}",
            )

        if verdict.verdict == "KILL":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="killed",
                message=verdict.verdict_reasoning,
            )

        if verdict.verdict == "PARK":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="parked",
                message=verdict.verdict_reasoning,
            )

        # ADVANCE — proceed to interviewer
        # Step 2b: Interviewer (one round)
        try:
            interviewer = Interviewer(self._llm)
            interview_response = interviewer.interview(entry, interview_history)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="error",
                message=f"Interviewer failed: {exc}",
            )

        if interview_response.status == "NEEDS_USER_INPUT":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="needs_input",
                message=interview_response.question or "Please answer the interviewer's question.",
            )

        # SPEC_DRAFT — proceed to critic
        spec_draft = interview_response.spec_draft or {}

        # Step 2c: Critic
        try:
            critic = Critic(self._llm)
            critic_response = critic.review(spec_draft)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="error",
                message=f"Critic failed: {exc}",
            )

        if critic_response.status == "RETURN":
            gaps_text = "\n".join(f"- {g}" for g in critic_response.gaps)
            questions_text = "\n".join(f"- {q}" for q in critic_response.questions)
            parts = [critic_response.reasoning]
            if gaps_text:
                parts.append(f"Gaps:\n{gaps_text}")
            if questions_text:
                parts.append(f"Questions:\n{questions_text}")
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="needs_input",
                message="\n\n".join(parts),
            )

        # LOCKED — proceed to atomizer
        # Step 2d: Atomizer
        try:
            atomizer = Atomizer(self._llm)
            atomized_tasks = atomizer.atomize(spec_draft, content_hint=entry.content)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="error",
                message=f"Atomizer failed: {exc}",
            )

        # Step 2e: Tag each task and write to vault
        tagger = TaskTagger(self._llm)
        project_name = _derive_project_name(entry, spec_draft)
        written_tasks: list[Task] = []

        for i, atomized in enumerate(atomized_tasks, start=1):
            try:
                review_tag = tagger.tag(atomized, content_hint=entry.content)
            except Exception:
                review_tag = "code"  # safe fallback

            task = Task(
                id=f"{i:03d}",
                title=atomized.title,
                status="queued",
                project=project_name,
                review_tag=review_tag,
                estimated_diff=atomized.estimated_diff,
                created=date.today(),
                spec_locked=True,
                spec=atomized.spec,
                acceptance_criteria=atomized.acceptance_criteria,
                out_of_scope=atomized.out_of_scope,
                files_expected=atomized.files_expected,
            )

            self._writer.write_task(project=project_name, task=task)
            written_tasks.append(task)

        return TriageResult(
            entry=entry,
            classifier_result=classifier_result,
            verdict=verdict,
            tasks=written_tasks,
            status="advanced",
            message=f"{len(written_tasks)} task(s) written for project '{project_name}'.",
        )

    # ------------------------------------------------------------------
    # Feature path
    # ------------------------------------------------------------------

    def _run_feature_path(
        self,
        entry: BrainDumpEntry,
        classifier_result: ClassifierResult,
    ) -> TriageResult:
        # Step 2: Feature Killer
        try:
            killer = FeatureKiller(self._llm, self._vault_path)
            verdict = killer.kill(entry)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                status="error",
                message=f"FeatureKiller failed: {exc}",
            )

        if verdict.verdict == "KILL":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="killed",
                message=verdict.verdict_reasoning,
            )

        if verdict.verdict == "PARK":
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=verdict,
                status="parked",
                message=verdict.verdict_reasoning,
            )

        # ADVANCE — write a single task directly into the project queue
        project_name = entry.project or classifier_result.project or "unknown"

        # Determine next task id
        tasks_dir = self._vault_path / "projects" / project_name / "tasks"
        task_id = _next_task_id(tasks_dir)

        task = Task(
            id=task_id,
            title=_short_title(entry.content),
            status="queued",
            project=project_name,
            review_tag="code",
            created=date.today(),
            spec_locked=True,
            spec=entry.content,
            acceptance_criteria=[],
            out_of_scope=[],
        )

        self._writer.write_task(project=project_name, task=task)

        return TriageResult(
            entry=entry,
            classifier_result=classifier_result,
            verdict=verdict,
            tasks=[task],
            status="advanced",
            message=f"Feature task written to project '{project_name}'.",
        )

    # ------------------------------------------------------------------
    # Bug path
    # ------------------------------------------------------------------

    def _run_bug_path(
        self,
        entry: BrainDumpEntry,
        classifier_result: ClassifierResult,
    ) -> TriageResult:
        try:
            triager = BugTriager(self._llm, self._vault_path)
            bug_result = triager.triage(entry)
        except Exception as exc:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                status="error",
                message=f"BugTriager failed: {exc}",
            )

        if not bug_result.reproducible:
            return TriageResult(
                entry=entry,
                classifier_result=classifier_result,
                verdict=bug_result,
                status="needs_input",
                message=bug_result.notes,
            )

        # Reproducible — BugTriager already wrote the task; reconstruct a
        # Task object for the result so callers can inspect it.
        project_name = entry.project or classifier_result.project or "unknown"
        tasks_dir = self._vault_path / "projects" / project_name / "tasks"

        # Find the task file that was just written (highest numeric id)
        task_id = _last_task_id(tasks_dir, bug_result.severity == "critical")

        task = Task(
            id=task_id,
            title=_short_title(entry.content),
            status="queued",
            project=project_name,
            review_tag="code",
            created=date.today(),
            spec_locked=True,
            spec=entry.content,
        )

        return TriageResult(
            entry=entry,
            classifier_result=classifier_result,
            verdict=bug_result,
            tasks=[task],
            status="advanced",
            message=f"Bug task written (severity={bug_result.severity}).",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fallback_classifier_result(entry: BrainDumpEntry) -> ClassifierResult:
    """Return a safe ClassifierResult when the classifier itself errors."""
    from foundry.triage.classifier import ClassifierResult as CR
    return CR(
        action="ask",
        type=entry.type,
        project=None,
        question="Classifier encountered an error. Please retry.",
        reasoning="error",
    )


def _derive_project_name(entry: BrainDumpEntry, spec_draft: dict) -> str:
    """Derive a project name from the entry or spec draft."""
    if entry.project:
        return entry.project
    title = spec_draft.get("title", "")
    if title:
        import re
        slug = re.sub(r"[^\w\s-]", "", title.lower().strip())
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug[:40].strip("-") or "new-project"
    return "new-project"


def _short_title(content: str) -> str:
    """Derive a short title from content (first sentence or 60 chars)."""
    first = content.split(".")[0].strip()
    if len(first) > 60:
        first = first[:60].rsplit(" ", 1)[0]
    return first or content[:60]


def _next_task_id(tasks_dir: Path) -> str:
    """Return the next available numeric task id (zero-padded to 3 digits)."""
    import re
    highest = 0
    if tasks_dir.exists():
        for f in tasks_dir.iterdir():
            m = re.search(r"(?:^|-)(\d{3})-", f.name)
            if m:
                n = int(m.group(1))
                if n > highest:
                    highest = n
    return f"{highest + 1:03d}"


def _last_task_id(tasks_dir: Path, is_critical: bool) -> str:
    """Return the id of the most recently written task file."""
    import re
    highest = 0
    if tasks_dir.exists():
        for f in tasks_dir.iterdir():
            m = re.search(r"(?:^|-)(\d{3})-", f.name)
            if m:
                n = int(m.group(1))
                if n > highest:
                    highest = n
    prefix = "CRITICAL-" if is_critical else ""
    return f"{prefix}{highest:03d}" if highest else f"{prefix}001"
