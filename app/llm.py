"""Model routing: clinic-policy-v1, Gemini, and Anthropic via LangChain messages."""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import settings
from app.planner import plan_decision

POLICY_MODELS = {'clinic-policy-v1', 'unconfigured', '', 'clinic-policy'}
GEMINI_MODELS = {'gemini-2.0-flash', 'gemini-2.5-flash-lite', 'gemini-2.5-flash'}
ANTHROPIC_MODELS = {'claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'}

PRICES = {
    'gemini-2.0-flash': (0.10 / 1_000_000, 0.40 / 1_000_000),
    'gemini-2.5-flash-lite': (0.10 / 1_000_000, 0.40 / 1_000_000),
    'gemini-2.5-flash': (0.30 / 1_000_000, 2.50 / 1_000_000),
    'claude-3-5-haiku-20241022': (0.80 / 1_000_000, 4.00 / 1_000_000),
    'claude-3-5-sonnet-20241022': (3.00 / 1_000_000, 15.00 / 1_000_000),
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


def configured_models() -> list[str]:
    names = ['clinic-policy-v1']
    if gemini_key():
        names.extend(['gemini-2.0-flash', 'gemini-2.5-flash-lite'])
    if settings.anthropic_api_key.strip():
        names.append('claude-3-5-haiku-20241022')
    names.append('unconfigured')
    return names


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


async def _llm_complete(model_name: str, messages: list) -> ModelResult:
    if model_name in GEMINI_MODELS:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=gemini_key(),
            temperature=0,
            max_output_tokens=settings.max_output_tokens,
        )
    elif model_name in ANTHROPIC_MODELS:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=0,
            max_tokens=settings.max_output_tokens,
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
    resolved = resolve_model_name(model_name)
    if resolved in POLICY_MODELS or resolved not in GEMINI_MODELS | ANTHROPIC_MODELS:
        decision = plan_decision(
            task=context['task'],
            history=context.get('history') or [],
            observations=context.get('observations') or [],
            notes=context.get('notes') or [],
        )
        return ModelResult(content=json.dumps(decision))
    try:
        return await _llm_complete(resolved, messages)
    except Exception:
        decision = plan_decision(
            task=context['task'],
            history=context.get('history') or [],
            observations=context.get('observations') or [],
            notes=context.get('notes') or [],
        )
        return ModelResult(content=json.dumps(decision), used_fallback=True)
