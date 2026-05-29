import os
import sys
from pathlib import Path

import typer

app = typer.Typer(name="foundry", help="The Foundry — task execution system.")

device_app = typer.Typer(help="Device management commands.")
app.add_typer(device_app, name="device")


def _get_db_path() -> Path:
    raw = os.getenv("FOUNDRY_DB_PATH", "")
    if raw:
        return Path(raw)
    return Path.home() / ".foundry" / "foundry.db"


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes."),
):
    """Start the Foundry dashboard (FastAPI + HTMX)."""
    import uvicorn
    uvicorn.run(
        "foundry.dashboard.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# ---------------------------------------------------------------------------
# triage
# ---------------------------------------------------------------------------

@app.command()
def triage(
    text: str = typer.Argument(..., help="Idea, feature, or bug text to triage."),
):
    """Run triage on a piece of text and print the verdict."""
    from datetime import datetime
    from foundry.dashboard import db as _db
    from foundry.dashboard.llm import get_dispatcher
    from foundry.triage.coordinator import Coordinator
    from foundry.triage.schema import BrainDumpEntry

    _db.init_db(_get_db_path())

    entry = BrainDumpEntry(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        type="idea",
        content=text,
    )

    try:
        llm = get_dispatcher()
    except Exception as exc:
        print(f"error: could not load LLM config: {exc}", file=sys.stderr)
        print("Add a provider/model/role in the dashboard Settings page first.", file=sys.stderr)
        raise typer.Exit(code=1)

    import tempfile
    dummy_vault = Path(tempfile.gettempdir()) / "foundry_triage_dummy"
    dummy_vault.mkdir(exist_ok=True)

    result = Coordinator(llm, dummy_vault).run(entry)
    print(f"status:  {result.status}")
    if result.verdict and hasattr(result.verdict, "verdict"):
        print(f"verdict: {result.verdict.verdict}")
    if result.message:
        print(f"message: {result.message}")
    if result.tasks:
        print(f"tasks:   {len(result.tasks)}")
        for t in result.tasks:
            print(f"  - {t.title}")


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

@app.command()
def audit(
    since: int = typer.Option(7, "--since", help="Show entries from the last N days.", metavar="N"),
):
    """Show LLM usage and cost from the audit log."""
    import json
    from datetime import datetime, timezone, timedelta

    audit_file = _get_db_path().parent / "audit.jsonl"
    if not audit_file.exists():
        print(f"no audit log found at {audit_file}")
        return

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=since)
    total_calls = 0
    total_cost = 0.0
    total_in = 0
    total_out = 0

    with audit_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                continue
            if ts < cutoff:
                continue
            total_calls += 1
            total_cost += float(rec.get("cost_usd", 0))
            total_in += int(rec.get("input_tokens", 0))
            total_out += int(rec.get("output_tokens", 0))

    if total_calls == 0:
        print(f"no audit entries in the last {since} day(s)")
        return

    print(f"audit — last {since} day(s)")
    print(f"  calls:       {total_calls}")
    print(f"  input tok:   {total_in:,}")
    print(f"  output tok:  {total_out:,}")
    print(f"  cost:        ${total_cost:.4f}")


# ---------------------------------------------------------------------------
# device commands
# ---------------------------------------------------------------------------

@device_app.command("current")
def device_current():
    """Print the current device ID (FOUNDRY_DEVICE_ID env var)."""
    device_id = os.environ.get("FOUNDRY_DEVICE_ID", "")
    if device_id:
        print(device_id)
    else:
        print("FOUNDRY_DEVICE_ID is not set", file=sys.stderr)
        raise typer.Exit(code=1)


@device_app.command("test")
def device_test(
    device_id: str = typer.Argument(..., help="device_id slug to test SSH connectivity for."),
):
    """Test SSH connectivity to a device."""
    from foundry.dashboard import db as _db
    from foundry.executor.ssh import SSHRunner

    _db.init_db(_get_db_path())
    conn = _db.get_conn()
    try:
        device = _db.device_get_by_device_id(conn, device_id)
    finally:
        conn.close()

    if device is None:
        print(f"error: device '{device_id}' not found in DB", file=sys.stderr)
        raise typer.Exit(code=1)

    current = os.environ.get("FOUNDRY_DEVICE_ID", "")
    if device["device_id"] == current:
        print(f"✓ {device_id}: local device — no SSH needed")
        return

    runner = SSHRunner(device)
    result = runner.run("echo ok")
    if result.returncode == 0 and "ok" in result.stdout:
        print(f"✓ {device_id}: SSH connection OK")
    else:
        err = result.stderr.strip() or result.stdout.strip() or "connection failed"
        print(f"✗ {device_id}: {err}", file=sys.stderr)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
