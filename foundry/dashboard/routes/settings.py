"""LLM settings — Providers, Models, Roles (3-level)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from foundry.dashboard import db

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter()


@router.get("/settings")
async def settings_redirect():
    return RedirectResponse(url="/settings/models", status_code=302)


@router.get("/settings/models", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    conn = db.get_conn()
    try:
        providers = db.llm_providers_list(conn)
        models = db.llm_models_list(conn)
        roles = db.llm_roles_list(conn)
        app_settings = db.settings_all(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "settings_models.html",
        {"providers": providers, "models": models, "roles": roles,
         "app_settings": app_settings, "saved": False, "error": None},
    )


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

@router.post("/settings/general", response_class=HTMLResponse)
async def save_general_settings(
    request: Request,
    run_command: str = Form("claude --dangerously-skip-permissions"),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.setting_set(conn, "run_command", run_command.strip())
        app_settings = db.settings_all(conn)
        providers = db.llm_providers_list(conn)
        models = db.llm_models_list(conn)
        roles = db.llm_roles_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "settings_models.html",
        {"providers": providers, "models": models, "roles": roles,
         "app_settings": app_settings, "saved": True, "error": None},
    )



@router.post("/settings/providers/new", response_class=HTMLResponse)
async def create_provider(
    request: Request,
    name: str = Form(...),
    type: str = Form("anthropic"),
    base_url: str = Form(""),
    api_key_env_var: str = Form(""),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.llm_provider_create(conn, name=name, type=type, base_url=base_url, api_key_env_var=api_key_env_var)
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/providers_list.html", {"providers": providers}
    )


@router.post("/settings/providers/{provider_id}/delete", response_class=HTMLResponse)
async def delete_provider(request: Request, provider_id: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.llm_provider_delete(conn, provider_id)
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/providers_list.html", {"providers": providers}
    )


@router.post("/settings/providers/{provider_id}/test", response_class=HTMLResponse)
async def test_provider(request: Request, provider_id: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        provider = db.llm_provider_get(conn, provider_id)
        models = db.llm_models_list(conn, provider_id)
    finally:
        conn.close()

    if provider is None:
        return HTMLResponse('<span class="text-red-400 text-sm">Provider not found</span>')
    if not models:
        return HTMLResponse('<span class="text-yellow-400 text-sm">No models configured for this provider</span>')

    import os
    import litellm

    model = models[0]
    model_str = model["model_id"] if provider["type"] == "anthropic" else f"openai/{model['model_id']}"
    kwargs: dict = {
        "model": model_str,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    if provider.get("base_url"):
        kwargs["api_base"] = provider["base_url"]
    api_key_env = provider.get("api_key_env_var", "")
    if api_key_env:
        api_key = os.environ.get(api_key_env, "")
        if api_key:
            kwargs["api_key"] = api_key

    try:
        litellm.completion(**kwargs)
        return HTMLResponse(f'<span class="text-green-400 text-sm">✓ {provider["name"]}: connection OK</span>')
    except Exception as exc:
        short = str(exc)[:120]
        return HTMLResponse(f'<span class="text-red-400 text-sm">✗ {short}</span>')


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@router.post("/settings/models/new", response_class=HTMLResponse)
async def create_model(
    request: Request,
    provider_id: int = Form(...),
    model_id: str = Form(...),
    display_name: str = Form(""),
    context_window: int = Form(200000),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.llm_model_create(conn, provider_id=provider_id, model_id=model_id,
                            display_name=display_name, context_window=context_window)
        models = db.llm_models_list(conn)
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/models_list.html", {"models": models, "providers": providers}
    )


@router.post("/settings/models/{model_pk}/delete", response_class=HTMLResponse)
async def delete_model(request: Request, model_pk: int) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.llm_model_delete(conn, model_pk)
        models = db.llm_models_list(conn)
        providers = db.llm_providers_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/models_list.html", {"models": models, "providers": providers}
    )


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

@router.post("/settings/roles/{role_name}/assign", response_class=HTMLResponse)
async def assign_role(
    request: Request,
    role_name: str,
    model_pk: int = Form(...),
) -> HTMLResponse:
    conn = db.get_conn()
    try:
        db.llm_role_assign(conn, role_name, model_pk if model_pk > 0 else None)
        roles = db.llm_roles_list(conn)
        models = db.llm_models_list(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request, "partials/roles_list.html", {"roles": roles, "models": models}
    )
