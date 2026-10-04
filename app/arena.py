"""Common boundary; ordinary Arena requests have no chat memory."""
import asyncio
import logging
from time import perf_counter
from app.agent import run_agent
from app.config import settings
from app.models import ArenaResponse
log = logging.getLogger('arena')
async def execute(request, history=None, model='unconfigured'):
    started = perf_counter()
    request = request.model_copy(deep=True)
    request.arena_config.max_steps = min(request.arena_config.max_steps, settings.max_steps)
    try:
        async with asyncio.timeout(settings.run_timeout_seconds):
            result = await run_agent(request, history or [], model)
            result = ArenaResponse.model_validate(result)
    except TimeoutError:
        result = ArenaResponse(request_id=request.request_id, status='budget_exceeded',
            final_response='That request took too long, so I stopped. Please try again.', stop_reason='time_budget_reached')
    except Exception:
        result = ArenaResponse(request_id=request.request_id, status='failed',
            final_response='Something went wrong on my side. Please try that clinic request again.', stop_reason='internal_error')
    result.metrics.latency_ms = (perf_counter() - started) * 1000
    if len(result.model_dump_json().encode()) > 50000:
        result = ArenaResponse(request_id=request.request_id, status='failed',
            final_response='The reply was too long to send. Please ask for a shorter clinic request.', stop_reason='response_too_large')
    log.info('request=%s status=%s steps=%s', request.request_id, result.status, result.steps)
    return result
