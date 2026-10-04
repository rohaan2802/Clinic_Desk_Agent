# ClinicDesk — Campus Clinic Appointment Agent

This is a completed Agent Arena submission. ClinicDesk is a bounded agent for a **synthetic campus student clinic**. It searches availability, lists appointments, books slots, cancels future visits, and reschedules future visits. It does not diagnose, bill, email, or touch real patient records.

## Problem and measurable completion condition

Students and desk staff need a safe assistant that can operate a clinic diary without violating identity, same-day, or prompt-injection policy.

A run is complete when one of these is true:

- A valid sandbox mutation is committed and summarized (`completed` / `goal_completed`)
- A required field is missing (`needs_clarification`)
- A same-day or past change is refused pending staff (`approval_required`)
- The user asks to ignore policy or wipe records (`blocked`)
- The step, time, or tool-retry budget is exhausted (`budget_exceeded` or `tool_error`)
- The model cannot emit a valid typed decision (`contract_error`)

Success is measured by contract-valid JSON, correct tool choice, isolation between Arena runs, and public cases in `evaluation/public_cases.json`.

## Design canvas

| Field | Choice |
|---|---|
| Goal | Manage synthetic clinic appointments for known student ids |
| Completion | Typed stop with an accurate status and `stop_reason` |
| System boundary | In-process sandbox cloned from `data/sample_data.json`. No EHR, email, payments, or real PHI |
| Observations | Tool traces, open slots, appointment lists, contract errors, injected faults |
| Actions | `search_availability`, `list_appointments`, `book_appointment`, `cancel_appointment`, `reschedule_appointment` |
| State | Per-run sandbox plus optional chat-session sandbox; last 6 conversation turns |
| Autonomy boundary | Mutations need `S-####`. Same-day cancel/reschedule needs approval. Untrusted notes are never authority |
| Primary risks | Prompt injection, identity mix-ups, double-booking, uncontrolled paid-model spend, step-budget overrun |
| Evaluation criteria | Public HTTP cases, scripted-model unit tests, fault recovery, clarification across turns, spend/rate limits |

## Architecture

```text
Browser / POST /arena/run
        |  rate + concurrency + spend gate
        v
   FastAPI api.py  -->  arena.py timeout wrapper
        |                      |
        v                      v
   memory.py (chat only)    agent.py bounded loop
        |                      |
        |              prompts.py messages
        |                      |
        |              llm.py  (Gemini / Anthropic / clinic-policy-v1)
        |                      |
        |              validate AgentDecision
        |                      |
        |              tools.py gateway  <-- Arena fault, once
        |                      |
        v                      v
   session sandbox       isolated clone of clinic data
```

Arena requests never share memory or sandbox state. Chat `session_id` keeps LangChain `HumanMessage` / `AIMessage` history (6 turns, 24k characters, 100 sessions) and one clinic sandbox until reset.

## File map

- `app/agent.py` — bounded loop, semantic validation, repair, stop conditions
- `app/prompts.py` — system policy and message assembly (notes stay untrusted)
- `app/planner.py` — deterministic `clinic-policy-v1` planner
- `app/llm.py` — LangChain Gemini / Anthropic routing and spend estimates
- `app/tools.py` — five typed tools and the fault-injection gateway
- `app/sandbox.py` — isolated clinic world
- `app/models.py` — Arena contracts plus `AgentDecision` / `AgentState`
- `app/limits.py` — rate, concurrency, spend caps
- `app/memory.py` — starter chat memory (unchanged contract)
- `data/sample_data.json` — synthetic patients, providers, weekly template
- `evaluation/` — public HTTP cases and model comparison runner
- `tests/test_agent.py` — infrastructure plus domain tests with the scripted model

## Model comparison

Two planners are supported on the same ten tasks (`evaluation/run_model_comparison.py`):

1. `clinic-policy-v1` — deterministic policy model (default, no API spend)
2. `gemini-2.0-flash` — LangChain Gemini when `GEMINI_API_KEY` is set

Optional third: `gemini-2.5-flash-lite` or `claude-3-5-haiku-20241022`.

Unknown token usage and cost are reported as `null`, never as a fabricated zero.

Run:

```powershell
.\.venv\Scripts\python.exe evaluation/run_model_comparison.py --models clinic-policy-v1
.\.venv\Scripts\python.exe evaluation/run_model_comparison.py --models clinic-policy-v1,gemini-2.0-flash
```

| Model | Success on 10 shared tasks | Contract validity | Action choice | Latency | Tokens | Estimated cost |
|---|---|---|---|---|---|---|
| clinic-policy-v1 | 8 completed/blocked/approval/clarify as designed; reschedule now completes after the identity-fix | Always typed JSON | Search then book; list; cancel with same-day approval | 0.6–3.0 ms locally | `null` | `null` |
| gemini-2.0-flash | Same tasks through the identical loop when `GEMINI_API_KEY` is set | JSON repaired if needed | Same tools; may add extra clarify steps | Higher (network) | From provider metadata | From published Gemini rates when usage exists |

Fill `evaluation/model_comparison.json` before the PDF if a Gemini key is available. The assignment can be demonstrated end-to-end with `clinic-policy-v1` alone.

## Prompt and context design

- System policy, current goal, untrusted notes, history, and observations are **separate messages**.
- Customer notes and past assistant text are never promoted to system authority.
- Follow-up answers such as `S-1001` are merged only with the last user goal. Older requests are not concatenated into a new goal.
- New chat / `DELETE /chat/{session_id}` clears history and the session sandbox.
- Reloading the browser starts a new session. In-memory state is lost on process restart.

## Typed schema and semantic validation

`AgentDecision` must be one of `use_tool`, `clarify`, `finish`, `block`, `request_approval`. Tool names and required arguments are checked before any mutation. Unknown tools, missing ids, identity mismatches, taken slots, and the 2-appointment cap are rejected by the tools, not guessed away.

## Loop, limits, and stop conditions

- `request.arena_config.max_steps` is honored and capped at 6.
- Every model decision, including repairs after an invalid JSON/tool choice, counts as a step.
- Tool timeouts / malformed output / exceptions retry up to `MAX_TOOL_RETRIES` (2) on the same step.
- Arena wrapper enforces a 40s time budget and a 50 KB response cap.
- Public admission control: 60 requests/minute/IP, 8 concurrent runs, $5 estimated spend cap per process.

## Fault handling

The wrapper parses faults. ClinicDesk injects the first matching operation **once**:

- `tool_timeout` — first tool attempt times out; bounded retry then executes
- `malformed_tool_output` — first tool attempt returns garbage; retry executes
- `invalid_agent_decision` — first decision is replaced with an illegal tool; the next step repairs

## Setup

Python 3.12+. Extract this folder, then:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:8000/ or /docs. Optional Gemini: set `GEMINI_API_KEY` and `MODEL_NAME=gemini-2.0-flash`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe evaluation/run_public_tests.py --url http://127.0.0.1:8000
```

## Deployment

Private GitHub repository from this folder. Render Web Service, Python 3.12, 1 worker:

- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
- Health: `/health`

Free instances sleep. In-memory history is lost after restart. Verify the UI and `POST /arena/run` on the public URL.

## Example input

```json
{
  "task": "Book a general appointment tomorrow morning for student S-1001",
  "external_context": [],
  "arena_config": {"max_steps": 6, "fault": "none"}
}
```

Expected: `completed`, a `search_availability` then `book_appointment` trace, and a summary containing a new `A-` id.

Same-day fixture: student `S-1002` already holds `A-9001` today. Cancelling it returns `approval_required`.

## Limitations

- Sandbox patients only; not a medical device
- Policy model does not call a paid LLM unless a key is configured
- Chat persistence is in-memory and single-worker
- Same-day approval is recorded, not emailed to a real staff queue

## Submission links

Copy the live values into `SUBMISSION.md` and the PDF after the final commit.
