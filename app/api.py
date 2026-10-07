import json
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from app.arena import execute
from app.config import ROOT, settings
from app.limits import admit, release, snapshot
from app.llm import configured_models, provider_flags
from app.models import ArenaRequest, ArenaResponse, ChatRequest
from app.sandbox import clear_sandbox

router = APIRouter(tags=['Clinic endpoints'])


def _pretty_page(src: str, title: str, sub: str) -> RedirectResponse:
    """Human-friendly JSON document page (opens as structured blank view)."""
    query = f'src={quote(src, safe="")}&title={quote(title)}&sub={quote(sub)}'
    return RedirectResponse(url=f'/json-view?{query}', status_code=307)


@router.get('/', summary='Open the clinic desk page')
def index():
    return FileResponse(ROOT / 'app/static/index.html')


def _health_payload() -> dict:
    return {
        'status': 'ok',
        'implementation': 'complete',
        'agent': 'ClinicDesk',
        'domain': 'campus_clinic_appointments',
        'default_model': settings.model_name or 'clinic-policy-v1',
        'models': configured_models(),
        'providers_ready': provider_flags(),
        'limits': snapshot(),
    }


@router.get('/health-ui', summary='Open the health status page')
def health_ui():
    # Embed live status in the HTML so Render Free cold-starts don't flash "offline"
    # when the second /health fetch is slow or briefly fails.
    html = (ROOT / 'app/static/health.html').read_text(encoding='utf-8')
    boot = json.dumps(_health_payload(), ensure_ascii=True)
    inject = f'<script>window.__HEALTH__={boot};</script>\n  <script src="/static/theme.js"></script>'
    html = html.replace('<script src="/static/theme.js"></script>', inject, 1)
    return HTMLResponse(html, headers={'Cache-Control': 'no-store'})


@router.get('/health-raw', summary='Open health data as a pretty page')
def health_raw():
    return _pretty_page('/health', 'Health snapshot', 'Live ClinicDesk status as structured JSON')


@router.get('/openapi', include_in_schema=False)
def openapi_pretty():
    return _pretty_page(
        '/openapi-spec',
        'OpenAPI contract',
        'Full machine-readable list of ClinicDesk endpoints, request bodies, and responses',
    )


@router.get('/manifest', include_in_schema=False)
def manifest_pretty():
    return _pretty_page(
        '/arena/manifest',
        'Arena manifest',
        'Assignment contract: tools, faults, limits, and Arena version',
    )


@router.get('/models-view', include_in_schema=False)
def models_pretty():
    return _pretty_page('/models', 'Answer models', 'Models enabled for this ClinicDesk process')


@router.get('/json-view', include_in_schema=False)
def json_view_page():
    return FileResponse(ROOT / 'app/static/json-view.html')


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
    return _health_payload()


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
