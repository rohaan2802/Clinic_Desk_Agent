import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from app.config import ROOT, settings
from app.llm import configured_models
from app.limits import admit, release, snapshot
from app.models import ArenaRequest, ArenaResponse, ChatRequest
from app.arena import execute
from app.sandbox import clear_sandbox

router = APIRouter()


@router.get('/')
def index():
    return FileResponse(ROOT / 'app/static/index.html')


@router.get('/health')
def health():
    return {
        'status': 'ok',
        'implementation': 'complete',
        'agent': 'ClinicDesk',
        'domain': 'campus_clinic_appointments',
        'default_model': settings.model_name or 'clinic-policy-v1',
        'limits': snapshot(),
    }


@router.get('/arena/manifest')
def manifest():
    return json.loads((ROOT / 'arena_manifest.json').read_text(encoding='utf-8'))


@router.get('/models')
def models():
    return {'models': configured_models()}


@router.post('/arena/run', response_model=ArenaResponse)
async def arena_run(payload: ArenaRequest, request: Request):
    admit(request)
    try:
        return await execute(payload, model=payload_model(payload))
    finally:
        release()


@router.post('/chat', response_model=ArenaResponse)
async def chat(payload: ChatRequest, request: Request):
    if payload.model not in models()['models']:
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


@router.delete('/chat/{session_id}')
def reset(session_id: str, request: Request):
    if session_id in request.app.state.busy:
        raise HTTPException(409, 'Chat is running')
    request.app.state.memory.clear(session_id)
    clear_sandbox(session_id)
    return {'status': 'cleared'}


def payload_model(payload: ArenaRequest) -> str:
    return settings.model_name or 'clinic-policy-v1'
