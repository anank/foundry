"""One-shot script to import projects from Obsidian vault into Foundry DB.

Run from the foundry project root:
    python scripts/import_vault_projects.py
"""

import os
import sys
from pathlib import Path

# Ensure foundry package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from foundry.dashboard import db

VAULT_PROJECTS = [
    {
        "name": "algocloudfx",
        "description": "Algorithmic trading system: MT5 EA + Python backtester/optimizer + PHP live dashboard.",
        "spec": "Stack: MQL5, Python 3.11+, FastAPI, Optuna, vectorbt, PHP, MySQL, Docker Compose\n\nRepos:\n- Monorepo: https://github.com/anank/algocloudfx-backtest\n- MT5 Robot: https://github.com/anank/algocloudfx-mt5\n- Dashboard: https://github.com/anank/algocloudfx-dashboard",
        "github_url": "https://github.com/anank/algocloudfx-backtest",
        "status": "active",
        "priority": "high",
    },
    {
        "name": "ccanalyzer",
        "description": "Automated bank statement pipeline: fetch from Gmail, unlock PDFs, analyze with Claude, generate HTML dashboard.",
        "spec": "Stack: Python 3.11+, Gmail API (OAuth2), pypdf, pdfplumber, anthropic SDK, Jinja2, Click\n\nKey rules:\n- Never commit passwords.txt, .env, credentials.json, token.json\n- Chunk statements > 50k characters before sending to Claude\n- Model: claude-sonnet-4-6",
        "github_url": "https://github.com/anank/ccanalyzer",
        "status": "active",
        "priority": "medium",
    },
    {
        "name": "foundry",
        "description": "Personal idea-to-deployment triage system — default behavior is to reject ideas, not build them.",
        "spec": "Stack: Python 3.11+, FastAPI, HTMX + Tailwind, Typer, LiteLLM, Pydantic v2, SQLite, FastMCP\n\nKey principle: The idea killer is the highest-stakes component. Default verdict: KILL. Kill rate target: 60-80%.",
        "github_url": "https://github.com/anank/foundry",
        "status": "active",
        "priority": "high",
    },
    {
        "name": "pipnesia-ea",
        "description": "MQL5 Expert Advisor for MT5.",
        "spec": "Stack: MQL5, MetaTrader 5\n\nKey rules:\n- After any .mq5 change, recompile in MetaEditor before testing\n- Never commit compiled .ex5 files",
        "github_url": "https://github.com/anank/Pipnesia-ea",
        "status": "active",
        "priority": "medium",
    },
    {
        "name": "social-media-engine",
        "description": "Social media content engine — pre-MVP discovery phase.",
        "spec": "Status: Discovery. Strategy skills not yet run. Stack TBD after MVP scope is defined.",
        "github_url": "",
        "status": "parked",
        "priority": "low",
    },
    {
        "name": "vibe-trading",
        "description": "Crypto, stock, and sentiment-based trading system.",
        "spec": "Stack: See repo trading-system/ for implementation details.\n\nKey rules:\n- Keep strategy logic separate from execution logic\n- Never commit API keys or secrets",
        "github_url": "https://github.com/anank/vibe-trading",
        "status": "active",
        "priority": "high",
    },
    {
        "name": "whg-ai",
        "description": "AI-based ticket replying system for hosting support.",
        "spec": "Structure:\n- extension/ — browser/client extension\n- middleware/ — backend middleware\n- docs/ — documentation\n- hosting-support-ai-spec.md — full spec\n\nKey rules:\n- Never commit API keys or .env files\n- Read hosting-support-ai-spec.md before architectural changes",
        "github_url": "https://github.com/anank/whg-ai",
        "status": "active",
        "priority": "medium",
    },
]

# Per-project per-device paths (Windows paths from vault rules.md)
DEVICE_PATHS = {
    "algocloudfx":        "D:\\project\\AlgoCloudFX",
    "ccanalyzer":         "D:\\project\\personal-finance",
    "foundry":            "D:\\project\\foundry",
    "pipnesia-ea":        "D:\\project\\Pipnesia-ea",
    "social-media-engine": "",
    "vibe-trading":       "D:\\project\\vibe-trading",
    "whg-ai":             "D:\\project\\whg-ai",
}


def main():
    db_path = Path(os.environ.get("FOUNDRY_DB_PATH", Path.home() / ".foundry" / "foundry.db"))
    print(f"DB: {db_path}")
    db.init_db(db_path)
    conn = db.get_conn()

    # Find or create the local Windows device
    current_device_id = os.environ.get("FOUNDRY_DEVICE_ID", "")
    device_pk = None
    if current_device_id:
        device = db.device_get_by_device_id(conn, current_device_id)
        if device:
            device_pk = device["id"]
            print(f"Using existing device: {current_device_id} (id={device_pk})")

    imported = 0
    skipped = 0

    for p in VAULT_PROJECTS:
        existing = db.project_get_by_name(conn, p["name"])
        if existing:
            print(f"  skip  {p['name']} (already exists)")
            skipped += 1
            continue

        pid = db.project_create(
            conn,
            name=p["name"],
            description=p["description"],
            spec=p["spec"],
            github_url=p["github_url"],
            status=p["status"],
            priority=p["priority"],
        )
        print(f"  import {p['name']} -> id={pid}")

        # Add device path if we have a local device and a known path
        local_path = DEVICE_PATHS.get(p["name"], "")
        if device_pk and local_path:
            db.path_upsert(conn, pid, device_pk, local_path)
            print(f"         path: {local_path}")

        imported += 1

    conn.close()
    print(f"\nDone. {imported} imported, {skipped} skipped.")


if __name__ == "__main__":
    main()
