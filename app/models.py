"""Domain-independent HTTP contracts plus ClinicDesk decision/state models."""
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ExternalContext(Contract):
    source: str = Field(min_length=1, max_length=100)
    content: str = Field(max_length=10000)
    trust: Literal['untrusted'] = 'untrusted'


class Fault(Contract):
    type: Literal['none', 'tool_timeout', 'malformed_tool_output', 'invalid_agent_decision'] = 'none'
    trigger: Literal['first_matching_operation'] = 'first_matching_operation'


class ArenaConfig(Contract):
    max_steps: int = Field(default=6, ge=1, le=6)
    fault: Fault = Field(default_factory=Fault)

    @field_validator('fault', mode='before')
    @classmethod
    def accept_assignment_shorthand(cls, value):
        return {'type': value} if isinstance(value, str) else value


class ArenaRequest(Contract):
    arena_version: Literal['0.1'] = '0.1'
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=80)
    task: str = Field(min_length=1, max_length=10000)
    external_context: list[ExternalContext] = Field(default_factory=list, max_length=20)
    arena_config: ArenaConfig = Field(default_factory=ArenaConfig)

    @field_validator('task')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Task must not be blank')
        return value


class ToolTrace(Contract):
    step: int = Field(ge=1, le=6)
    tool: str
    attempt: int = Field(default=1, ge=1, le=3)
    outcome: Literal['success', 'timeout', 'malformed_output', 'rejected', 'exception']
    latency_ms: float = Field(default=0, ge=0)


class Metrics(Contract):
    latency_ms: float = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0, le=6)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class ArenaResponse(Contract):
    arena_version: Literal['0.1'] = '0.1'
    request_id: str
    status: Literal[
        'completed', 'needs_clarification', 'blocked', 'approval_required',
        'tool_error', 'contract_error', 'budget_exceeded', 'failed'
    ]
    final_response: str = Field(min_length=1, max_length=2000)
    steps: int = Field(default=0, ge=0, le=6)
    stop_reason: str
    tool_calls: list[ToolTrace] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    events: list[dict] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)


class ChatRequest(ArenaRequest):
    session_id: str = Field(min_length=16, max_length=80)
    model: str = Field(default='unconfigured', max_length=120)


class AgentDecision(Contract):
    """One typed model output. Invalid payloads are rejected, not executed."""
    action: Literal['use_tool', 'clarify', 'finish', 'block', 'request_approval']
    thought: str = Field(default='', max_length=800)
    user_message: str = Field(default='I could not complete that clinic request.', max_length=2000)
    tool: str | None = Field(default=None, max_length=80)
    arguments: dict = Field(default_factory=dict)


class AgentState(Contract):
    """Per-run working memory. Isolated from other arena requests."""
    goal: str
    observations: list[str] = Field(default_factory=list)
    last_terminal: str | None = None
    fault_used: bool = False
    model_calls: int = Field(default=0, ge=0, le=6)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    repair_count: int = Field(default=0, ge=0)
