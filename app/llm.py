"""Model routing: clinic-policy-v1 is the authority; LLMs may only polish soft clarify wording."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from app.config import settings
from app.planner import plan_decision

POLICY_MODELS = {'clinic-policy-v1', 'unconfigured', '', 'clinic-policy'}
GEMINI_MODELS = {'gemini-3.8-flash', 'gemini-3.5-flash-lite'}
ANTHROPIC_MODELS = {'claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'}
OPENROUTER_MODELS = {'openai/gpt-4o-mini'}
# Soft wording only — never rewrite tool/finish/approval facts.
POLISHABLE_ACTIONS = {'clarify', 'block'}
LLM_TIMEOUT_SECONDS = 4.0

PRICES = {
    'gemini-3.8-flash': (0.10 / 1_000_000, 0.40 / 1_000_000),
    'gemini-3.5-flash-lite': (0.10 / 1_000_000, 0.40 / 1_000_000),
    'openai/gpt-4o-mini': (0.15 / 1_000_000, 0.60 / 1_000_000),
    'claude-3-5-haiku-20241022': (0.80 / 1_000_000, 4.00 / 1_000_000),
}


@dataclass
class ModelResult:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    used_fallback: bool = False


def gemini_key() -> str:
    return (settings.gemini_api_key or settings.google_api_key or '').strip()


def openrouter_key() -> str:
    return settings.openrouter_api_key.strip()


def configured_models() -> list[str]:
    names = ['clinic-policy-v1']
    if gemini_key():
        names.extend(sorted(GEMINI_MODELS))
    if openrouter_key():
        names.extend(sorted(OPENROUTER_MODELS))
    if settings.anthropic_api_key.strip():
        names.append('claude-3-5-haiku-20241022')
    names.append('unconfigured')
    return names


def provider_flags() -> dict:
    return {
        'clinic-policy-v1': True,
        'gemini': bool(gemini_key()),
        'openrouter': bool(openrouter_key()),
        'anthropic': bool(settings.anthropic_api_key.strip()),
    }


def resolve_model_name(name: str | None) -> str:
    requested = (name or '').strip()
    if requested in {'', 'unconfigured'}:
        return settings.model_name.strip() or 'clinic-policy-v1'
    return requested


def estimate_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    prices = PRICES.get(model)
    if not prices:
        return None
    return round(input_tokens * prices[0] + output_tokens * prices[1], 8)


def _usage_from_response(response) -> tuple[int | None, int | None]:
    meta = getattr(response, 'usage_metadata', None) or {}
    if not meta:
        return None, None
    if isinstance(meta, dict):
        inp = meta.get('input_tokens') or meta.get('prompt_token_count')
        out = meta.get('output_tokens') or meta.get('candidates_token_count')
        return inp, out
    inp = getattr(meta, 'input_tokens', None)
    out = getattr(meta, 'output_tokens', None)
    return inp, out


def _parse_json_object(raw: str) -> dict | None:
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _safe_user_message(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    message = text.strip()
    if not message or len(message) > 2000:
        return None
    lowered = message.lower()
    if 'tool ' in lowered or 'terminal=1' in lowered or lowered.startswith('{'):
        return None
    if '```' in message:
        return None
    return message


def _authoritative_decision(context: dict) -> dict:
    return plan_decision(
        task=context['task'],
        history=context.get('history') or [],
        observations=context.get('observations') or [],
        notes=context.get('notes') or [],
    )


def _merge_with_authority(authority: dict, llm_payload: dict | None) -> dict:
    """Clinic policy owns action/tool/arguments. LLM may only polish the user-facing line."""
    locked = {
        'action': authority['action'],
        'thought': authority.get('thought', ''),
        'user_message': authority.get('user_message', ''),
        'tool': authority.get('tool'),
        'arguments': authority.get('arguments') or {},
    }
    if not llm_payload:
        return locked
    if llm_payload.get('action') != authority.get('action'):
        return locked
    if authority.get('action') == 'use_tool' and llm_payload.get('tool') != authority.get('tool'):
        return locked
    polished = _safe_user_message(llm_payload.get('user_message'))
    if polished:
        locked['user_message'] = polished
    return locked


async def _llm_complete(model_name: str, messages: list) -> ModelResult:
    if model_name in GEMINI_MODELS:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key(),
            temperature=0,
            max_output_tokens=min(settings.max_output_tokens, 180),
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,
        )
    elif model_name in OPENROUTER_MODELS:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model_name,
            api_key=openrouter_key(),
            base_url='https://openrouter.ai/api/v1',
            temperature=0,
            max_tokens=min(settings.max_output_tokens, 180),
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,
            default_headers={
                'HTTP-Referer': 'http://127.0.0.1:8000',
                'X-Title': 'ClinicDesk Agent Arena',
            },
        )
    elif model_name in ANTHROPIC_MODELS:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=min(settings.max_output_tokens, 180),
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,
        )
    else:
        raise ValueError(f'Unknown LLM {model_name}')
    response = await llm.ainvoke(messages)
    content = response.content if isinstance(response.content, str) else json.dumps(response.content)
    inp, out = _usage_from_response(response)
    return ModelResult(
        content=content,
        input_tokens=inp,
        output_tokens=out,
        estimated_cost_usd=estimate_cost(model_name, inp, out),
    )


async def complete(model_name: str, messages: list, context: dict) -> ModelResult:
    """Always decide with clinic-policy-v1. LLMs may soft-polish clarify/block only."""
    authority = _authoritative_decision(context)
    resolved = resolve_model_name(model_name)
    llm_models = GEMINI_MODELS | ANTHROPIC_MODELS | OPENROUTER_MODELS
    if resolved in POLICY_MODELS or resolved not in llm_models:
        return ModelResult(content=json.dumps(authority))
    # Tool / finish / approval answers stay 100% policy text — no LLM rewrite, no slow calls.
    if authority.get('action') not in POLISHABLE_ACTIONS:
        return ModelResult(content=json.dumps(authority), used_fallback=True)
    try:
        llm_result = await asyncio.wait_for(_llm_complete(resolved, messages), timeout=LLM_TIMEOUT_SECONDS)
        locked = _merge_with_authority(authority, _parse_json_object(llm_result.content))
        return ModelResult(
            content=json.dumps(locked),
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            estimated_cost_usd=llm_result.estimated_cost_usd,
            used_fallback=locked.get('user_message') == authority.get('user_message'),
        )
    except Exception:
        return ModelResult(content=json.dumps(authority), used_fallback=True)
