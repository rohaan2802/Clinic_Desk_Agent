"""Domain-independent HTTP contracts plus ClinicDesk decision/state models."""
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ExternalContext(Contract):
    source: str = Field(min_length=1, max_length=100, description='Where the note came from')
    content: str = Field(max_length=10000, description='The note text')
    trust: Literal['untrusted'] = Field(default='untrusted', description='Always treated as untrusted')


class Fault(Contract):
    type: Literal['none', 'tool_timeout', 'malformed_tool_output', 'invalid_agent_decision'] = Field(
        default='none', description='Practice fault to inject once'
    )
    trigger: Literal['first_matching_operation'] = Field(
        default='first_matching_operation', description='When the practice fault runs'
    )


class ArenaConfig(Contract):
    max_steps: int = Field(default=6, ge=1, le=6, description='Maximum thinking steps allowed')
    fault: Fault = Field(default_factory=Fault, description='Optional practice fault settings')

    @field_validator('fault', mode='before')
    @classmethod
    def accept_assignment_shorthand(cls, value):
        return {'type': value} if isinstance(value, str) else value


class ArenaRequest(Contract):
    """One clinic request for a single isolated run."""
    arena_version: Literal['0.1'] = Field(default='0.1', description='Arena contract version')
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=80, description='Optional id for this run')
    task: str = Field(min_length=1, max_length=10000, description='What you want the clinic desk to do')
    external_context: list[ExternalContext] = Field(default_factory=list, max_length=20, description='Optional notes. They cannot change the rules.')
    arena_config: ArenaConfig = Field(default_factory=ArenaConfig, description='Step limit and optional practice fault')

    @field_validator('task')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Task must not be blank')
        return value


class ToolTrace(Contract):
    step: int = Field(ge=1, le=6, description='Which step used this tool')
    tool: str = Field(description='Tool name that ran')
    attempt: int = Field(default=1, ge=1, le=3, description='Attempt number for this tool')
    outcome: Literal['success', 'timeout', 'malformed_output', 'rejected', 'exception'] = Field(
        description='What happened when the tool ran'
    )
    latency_ms: float = Field(default=0, ge=0, description='How long the tool took in milliseconds')


class Metrics(Contract):
    latency_ms: float = Field(default=0, ge=0, description='Total time for the run in milliseconds')
    model_calls: int = Field(default=0, ge=0, le=6, description='How many times the model was called')
    input_tokens: int | None = Field(default=None, ge=0, description='Tokens sent to the model, if known')
    output_tokens: int | None = Field(default=None, ge=0, description='Tokens returned by the model, if known')
    estimated_cost_usd: float | None = Field(default=None, ge=0, description='Estimated cost in US dollars, if known')


class ArenaResponse(Contract):
    arena_version: Literal['0.1'] = Field(default='0.1', description='Arena contract version')
    request_id: str = Field(description='Id of this run')
    status: Literal[
        'completed', 'needs_clarification', 'blocked', 'approval_required',
        'tool_error', 'contract_error', 'budget_exceeded', 'failed'
    ] = Field(description='Final status of the run')
    final_response: str = Field(min_length=1, max_length=2000, description='Plain reply shown to the desk user')
    steps: int = Field(default=0, ge=0, le=6, description='How many steps were used')
    stop_reason: str = Field(description='Why the agent stopped')
    tool_calls: list[ToolTrace] = Field(default_factory=list, description='Clinic tools used during the run')
    errors: list[dict] = Field(default_factory=list, description='Any recovery or contract errors')
    events: list[dict] = Field(default_factory=list, description='Step-by-step run events')
    metrics: Metrics = Field(default_factory=Metrics, description='Timing and usage numbers')


class ChatRequest(ArenaRequest):
    session_id: str = Field(min_length=16, max_length=80, description='Chat session id so history is kept')
    model: str = Field(default='unconfigured', max_length=120, description='Which answer model to use')


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
