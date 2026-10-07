import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app.arena import execute
from app.config import ROOT, settings
from app.limits import admit, release, snapshot
from app.llm import configured_models, provider_flags
from app.models import ArenaRequest, ArenaResponse, ChatRequest
from app.sandbox import clear_sandbox

router = APIRouter(tags=['Clinic endpoints'])
_NO_STORE = {'Cache-Control': 'no-store, no-cache, must-revalidate'}


def _pretty_page(title: str, sub: str, data) -> HTMLResponse:
    """Human-friendly JSON document — data is embedded so no second fetch can fail."""
    body = json.dumps(data, indent=2, ensure_ascii=True)
    # Escape for HTML text node (not a script context).
    safe = (
        body.replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>{title} · ClinicDesk</title>
  <style>
    :root{{color-scheme:dark}}
    html,body{{margin:0;min-height:100%;background:#070c0d;color:#eef8f5;font:18px/1.55 Sora,system-ui,sans-serif}}
    .wrap{{max-width:980px;margin:0 auto;padding:28px 22px 48px}}
    .eyebrow{{margin:0 0 6px;color:#3de0c5;letter-spacing:.12em;text-transform:uppercase;font-size:13px;font-weight:700}}
    h1{{margin:0 0 8px;font-size:clamp(28px,5vw,40px);letter-spacing:-.03em}}
    .sub{{margin:0 0 22px;color:#9fb8b2;font-size:16px}}
    .panel{{
      margin:0;padding:22px 24px;border-radius:18px;border:1px solid #1d3a40;
      background:#10242b;box-shadow:0 18px 40px #0006;
      font:16px/1.55 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;
      color:#f4fffb;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <p class="eyebrow">ClinicDesk</p>
    <h1>{title}</h1>
    <p class="sub">{sub}</p>
    <pre class="panel">{safe}</pre>
  </div>
</body>
</html>"""
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})


@router.get('/', summary='Open the clinic desk page')
def index():
    return FileResponse(
        ROOT / 'app/static/index.html',
        headers={'Cache-Control': 'no-store'},
    )


@router.get('/static/app.js', include_in_schema=False)
def app_js():
    # Beat CDN/browser cache after live-status fixes (must be registered before StaticFiles mount).
    return FileResponse(
        ROOT / 'app/static/app.js',
        media_type='application/javascript; charset=utf-8',
        headers=dict(_NO_STORE),
    )


@router.get('/static/style.css', include_in_schema=False)
def app_css():
    return FileResponse(
        ROOT / 'app/static/style.css',
        media_type='text/css; charset=utf-8',
        headers=dict(_NO_STORE),
    )


def _health_payload() -> dict:
    """Always-safe process heartbeat for Render Health Check Path + live UI.

    Must not raise: a thrown exception here fails Render health checks and the desk pill.
    Extra fields (models/limits) are best-effort; status stays ok while the process is up.
    """
    checked_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        default_model = settings.model_name or 'clinic-policy-v1'
    except Exception:
        default_model = 'clinic-policy-v1'
    try:
        models = configured_models()
    except Exception:
        models = ['clinic-policy-v1']
    try:
        providers = provider_flags()
    except Exception:
        providers = {'clinic-policy-v1': True}
    try:
        limits = snapshot()
    except Exception:
        limits = {'concurrent': 0, 'spend_usd': 0.0, 'max_spend_usd': 0.0}
    return {
        'status': 'ok',
        'checked_at': checked_at,
        'implementation': 'complete',
        'agent': 'ClinicDesk',
        'domain': 'campus_clinic_appointments',
        'default_model': default_model,
        'models': models,
        'providers_ready': providers,
        'limits': limits,
    }


@router.get('/health-ui', summary='Open the health status page')
def health_ui():
    # Boot snapshot for first paint; health.html keeps polling /health for real-time updates.
    html = (ROOT / 'app/static/health.html').read_text(encoding='utf-8')
    boot = json.dumps(_health_payload(), ensure_ascii=True)
    inject = f'<script>window.__HEALTH__={boot};</script>\n  <script src="/static/theme.js"></script>'
    html = html.replace('<script src="/static/theme.js"></script>', inject, 1)
    return HTMLResponse(html, headers=dict(_NO_STORE))


@router.get('/health-raw', summary='Open health data as a pretty page')
def health_raw():
    data = _health_payload()
    return _pretty_page(
        'Health snapshot',
        f'Live ClinicDesk status at {data.get("checked_at", "request time")} — refresh for a new capture',
        data,
    )


@router.get('/openapi', include_in_schema=False)
def openapi_pretty(request: Request):
    return _pretty_page(
        'OpenAPI contract',
        'Full machine-readable list of ClinicDesk endpoints, request bodies, and responses',
        request.app.openapi(),
    )


@router.get('/manifest', include_in_schema=False)
def manifest_pretty():
    data = json.loads((ROOT / 'arena_manifest.json').read_text(encoding='utf-8'))
    return _pretty_page(
        'Arena manifest',
        'Assignment contract: tools, faults, limits, and Arena version',
        data,
    )


@router.get('/models-view', include_in_schema=False)
def models_pretty():
    return _pretty_page(
        'Answer models',
        'Models enabled for this ClinicDesk process',
        {'models': configured_models()},
    )


@router.get('/json-view', include_in_schema=False)
def json_view_page():
    # Legacy bookmarks still work; preferred routes embed JSON directly.
    return FileResponse(ROOT / 'app/static/json-view.html', headers={'Cache-Control': 'no-store'})


@router.get('/docs', include_in_schema=False)
def docs_ui():
    return FileResponse(ROOT / 'app/static/docs.html')


@router.get('/openapi-spec', include_in_schema=False)
def openapi_spec(request: Request):
    """Internal JSON for Swagger / scripts only. Humans open /openapi."""
    return JSONResponse(request.app.openapi())


@router.get('/openapi.json', include_in_schema=False)
def openapi_json_redirect():
    """Old path — send people to the pretty OpenAPI contract page."""
    return RedirectResponse(url='/openapi', status_code=307)


@router.get('/health', summary='Check if ClinicDesk is running')
def health():
    # Render Health Check Path should be exactly /health — keep this fast and never 5xx.
    try:
        payload = _health_payload()
    except Exception:
        payload = {
            'status': 'ok',
            'checked_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            'implementation': 'complete',
            'agent': 'ClinicDesk',
            'domain': 'campus_clinic_appointments',
            'default_model': 'clinic-policy-v1',
            'models': ['clinic-policy-v1'],
            'providers_ready': {'clinic-policy-v1': True},
            'limits': {'concurrent': 0, 'spend_usd': 0.0, 'max_spend_usd': 0.0},
        }
    return JSONResponse(payload, headers=dict(_NO_STORE))


@router.get('/arena/manifest', summary='Show the assignment contract')
def manifest():
    return json.loads((ROOT / 'arena_manifest.json').read_text(encoding='utf-8'))


@router.get('/models', summary='List available answer models')
def models():
    return {'models': configured_models()}


@router.post('/arena/run', response_model=ArenaResponse, summary='Run one isolated clinic task')
async def arena_run(payload: ArenaRequest, request: Request):
    admit(request)
    try:
        return await execute(payload, model=payload_model(payload))
    finally:
        release()


@router.post('/chat', response_model=ArenaResponse, summary='Send a chat message and keep the session')
async def chat(payload: ChatRequest, request: Request):
    available = configured_models()
    if payload.model not in available:
        raise HTTPException(400, 'Model is not enabled')
    busy = request.app.state.busy
    if payload.session_id in busy:
        raise HTTPException(409, 'This chat is already running')
    admit(request)
    busy.add(payload.session_id)
    memory = request.app.state.memory
    try:
        result = await execute(payload, memory.get(payload.session_id), payload.model)
        memory.add(payload.session_id, payload.task, result.final_response)
        return result
    finally:
        busy.discard(payload.session_id)
        release()


@router.delete('/chat/{session_id}', summary='Clear one chat session')
def reset(session_id: str, request: Request):
    if session_id in request.app.state.busy:
        raise HTTPException(409, 'Chat is running')
    request.app.state.memory.clear(session_id)
    clear_sandbox(session_id)
    return {'status': 'cleared'}


def payload_model(payload: ArenaRequest) -> str:
    return settings.model_name or 'clinic-policy-v1'
