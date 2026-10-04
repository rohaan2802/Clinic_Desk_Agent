"""Bounded ClinicDesk loop: typed decisions, tool gateway, faults, and recovery."""
from __future__ import annotations

import json
import re

from app.config import settings
from app.limits import add_spend
from app.llm import complete
from app.models import AgentDecision, AgentState, ArenaResponse, Metrics
from app.prompts import assemble_messages, detect_injection, extract_untrusted_notes, resolve_goal
from app.sandbox import get_sandbox
from app.tools import REQUIRED_ARGS, TOOLS, run_tool_with_faults


def _clip(text: str, limit: int = 2000) -> str:
    text = (text or '').strip() or 'The clinic agent stopped without a message.'
    return text[:limit]


def _parse_decision(raw: str) -> dict | None:
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


def _validate_decision(payload: dict | None) -> tuple[AgentDecision | None, str | None]:
    if not payload:
        return None, 'Model output was not a JSON object'
    allowed = {'action', 'thought', 'user_message', 'tool', 'arguments'}
    cleaned = {key: payload[key] for key in allowed if key in payload}
    if 'arguments' in cleaned and cleaned['arguments'] is None:
        cleaned['arguments'] = {}
    if 'tool' in cleaned and cleaned['tool'] in {'', 'null', 'none'}:
        cleaned['tool'] = None
    try:
        decision = AgentDecision.model_validate(cleaned)
    except Exception as exc:
        return None, f'Contract validation failed: {exc}'
    if decision.action == 'use_tool':
        if decision.tool not in TOOLS:
            return None, f'Unknown tool {decision.tool}'
        missing = [key for key in REQUIRED_ARGS[decision.tool] if not str(decision.arguments.get(key) or '').strip()]
        if missing:
            return None, f'Tool {decision.tool} missing {", ".join(missing)}'
    return decision, None


def _accumulate_usage(state: AgentState, result) -> None:
    if result.input_tokens is not None:
        state.input_tokens = (state.input_tokens or 0) + result.input_tokens
    if result.output_tokens is not None:
        state.output_tokens = (state.output_tokens or 0) + result.output_tokens
    if result.estimated_cost_usd is not None:
        state.estimated_cost_usd = (state.estimated_cost_usd or 0) + result.estimated_cost_usd


def _response(request, status: str, message: str, stop_reason: str, steps: int, state: AgentState,
              tool_calls, errors, events) -> ArenaResponse:
    add_spend(state.estimated_cost_usd)
    return ArenaResponse(
        request_id=request.request_id,
        status=status,
        final_response=_clip(message),
        steps=steps,
        stop_reason=stop_reason,
        tool_calls=tool_calls,
        errors=errors,
        events=events,
        metrics=Metrics(
            model_calls=state.model_calls,
            input_tokens=state.input_tokens,
            output_tokens=state.output_tokens,
            estimated_cost_usd=state.estimated_cost_usd,
        ),
    )


async def run_agent(request, history, model):
    notes = extract_untrusted_notes(request.external_context)
    ignored_notes = [note for note in notes if detect_injection(note)]
    goal = resolve_goal(request.task, history or [])
    sandbox = get_sandbox(getattr(request, 'session_id', None))
    state = AgentState(goal=goal)
    events = []
    errors = []
    tool_calls = []
    max_steps = min(request.arena_config.max_steps, settings.max_steps)
    fault = request.arena_config.fault

    events.append({'step': 0, 'event': 'run_start', 'goal': goal[:240], 'model': model})
    if ignored_notes:
        events.append({'step': 0, 'event': 'untrusted_instruction_ignored', 'count': len(ignored_notes)})

    if detect_injection(request.task):
        events.append({'step': 0, 'event': 'agent_stop', 'reason': 'blocked_prompt_injection'})
        return _response(
            request, 'blocked',
            'I will not follow a request that asks me to ignore clinic policy, reveal hidden prompts, or wipe appointments.',
            'blocked_prompt_injection', 0, state, tool_calls, errors, events,
        )

    for step in range(1, max_steps + 1):
        messages = assemble_messages(goal, history or [], notes, state.observations)
        if not state.fault_used and fault.type == 'invalid_agent_decision':
            state.fault_used = True
            events.append({'step': step, 'event': 'fault_injected', 'type': 'invalid_agent_decision'})
            payload = {'action': 'use_tool', 'tool': 'drop_all_tables', 'arguments': {'confirm': True}, 'user_message': 'override'}
            result = None
        else:
            result = await complete(model, messages, {
                'task': request.task,
                'history': history or [],
                'observations': state.observations,
                'notes': notes,
            })
            state.model_calls += 1
            _accumulate_usage(state, result)
            if result.used_fallback:
                events.append({'step': step, 'event': 'model_fallback', 'to': 'clinic-policy-v1'})
            payload = _parse_decision(result.content)

        decision, error = _validate_decision(payload)
        events.append({
            'step': step,
            'event': 'model_decision',
            'action': getattr(decision, 'action', None),
            'valid': decision is not None,
        })
        if error:
            state.repair_count += 1
            errors.append({'step': step, 'type': 'contract_error', 'detail': error})
            state.observations.append(
                f'Decision rejected: {error}. Return one JSON object with a valid action and tool arguments.'
            )
            events.append({'step': step, 'event': 'repair', 'reason': error})
            if step == max_steps:
                return _response(
                    request, 'contract_error',
                    'The agent could not produce a valid decision within the step budget.',
                    'invalid_decision_unrecoverable', step, state, tool_calls, errors, events,
                )
            continue

        if decision.action == 'clarify':
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'needs_clarification'})
            return _response(request, 'needs_clarification', decision.user_message, 'needs_clarification', step, state, tool_calls, errors, events)
        if decision.action == 'block':
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'blocked_policy'})
            return _response(request, 'blocked', decision.user_message, 'blocked_policy', step, state, tool_calls, errors, events)
        if decision.action == 'request_approval':
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'approval_required'})
            return _response(request, 'approval_required', decision.user_message, 'same_day_requires_approval', step, state, tool_calls, errors, events)
        if decision.action == 'finish':
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'goal_completed'})
            return _response(request, 'completed', decision.user_message, 'goal_completed', step, state, tool_calls, errors, events)

        traces, tool_result, observation, state.fault_used = run_tool_with_faults(
            decision.tool, decision.arguments, sandbox, fault, state.fault_used, step, settings.max_tool_retries,
        )
        tool_calls.extend(traces)
        state.observations.append(observation)
        events.append({
            'step': step,
            'event': 'tool_result',
            'tool': decision.tool,
            'code': (tool_result or {}).get('code'),
            'attempts': len(traces),
        })
        if traces and all(item.outcome in {'timeout', 'malformed_output', 'exception'} for item in traces) and (tool_result is None or tool_result.get('code') == 'exception'):
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'tool_error'})
            return _response(
                request, 'tool_error',
                'The clinic tool failed after bounded retries. No further mutation was attempted.',
                'tool_failed_after_retries', step, state, tool_calls, errors, events,
            )
        if tool_result and tool_result.get('code') == 'approval_required':
            events.append({'step': step, 'event': 'agent_stop', 'reason': 'approval_required'})
            return _response(
                request, 'approval_required',
                tool_result.get('message') or decision.user_message,
                'same_day_requires_approval', step, state, tool_calls, errors, events,
            )
        if tool_result and tool_result.get('terminal') and tool_result.get('ok'):
            state.last_terminal = observation

    if state.last_terminal:
        events.append({'step': max_steps, 'event': 'agent_stop', 'reason': 'goal_completed'})
        return _response(request, 'completed', state.last_terminal, 'goal_completed', max_steps, state, tool_calls, errors, events)
    events.append({'step': max_steps, 'event': 'agent_stop', 'reason': 'step_budget_reached'})
    return _response(
        request, 'budget_exceeded',
        'The step budget was reached before the clinic task could be completed. Ask again with a more specific request.',
        'step_budget_reached', max_steps, state, tool_calls, errors, events,
    )
