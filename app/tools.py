"""ClinicDesk sandbox tools. All mutations go through execute_tool so faults apply once."""
from __future__ import annotations

from datetime import date
from time import perf_counter

from app.models import ToolTrace
from app.sandbox import next_appointment_id

SPECIALTIES = ('general', 'dental', 'dermatology', 'physiotherapy')
TERMINAL_TOOLS = {'book_appointment', 'cancel_appointment', 'reschedule_appointment'}


def _patient(sandbox: dict, student_id: str) -> dict | None:
    return next((p for p in sandbox['patients'] if p['student_id'] == student_id), None)


def _slot(sandbox: dict, slot_id: str) -> dict | None:
    return next((s for s in sandbox['slots'] if s['slot_id'] == slot_id), None)


def _appointment(sandbox: dict, appointment_id: str) -> dict | None:
    return next((a for a in sandbox['appointments'] if a['appointment_id'] == appointment_id), None)


def _active_count(sandbox: dict, student_id: str) -> int:
    return sum(
        1 for a in sandbox['appointments']
        if a['student_id'] == student_id and a['status'] == 'booked'
    )


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lower()
    today = date.today()
    if text == 'today':
        return today.isoformat()
    if text == 'tomorrow':
        from datetime import timedelta
        return (today + timedelta(days=1)).isoformat()
    if len(text) == 10 and text[4] == '-' and text[7] == '-':
        return text
    return None


def search_availability(sandbox: dict, specialty: str | None = None, date_value: str | None = None) -> dict:
    wanted_date = _normalize_date(date_value)
    wanted_spec = (specialty or '').strip().lower() or None
    if wanted_spec and wanted_spec not in SPECIALTIES:
        return {
            'ok': False,
            'code': 'unknown_specialty',
            'message': f'Unknown specialty. Use one of: {", ".join(SPECIALTIES)}',
        }
    matches = []
    for slot in sandbox['slots']:
        if slot['status'] != 'open':
            continue
        if wanted_spec and slot['specialty'] != wanted_spec:
            continue
        if wanted_date and slot['date'] != wanted_date:
            continue
        matches.append(slot)
    matches.sort(key=lambda s: (s['date'], s['start']))
    return {
        'ok': True,
        'code': 'ok',
        'count': len(matches),
        'slots': matches[:8],
        'filter': {'specialty': wanted_spec, 'date': wanted_date},
    }


def list_appointments(sandbox: dict, student_id: str) -> dict:
    if not _patient(sandbox, student_id):
        return {'ok': False, 'code': 'unknown_student', 'message': f'No patient record for {student_id}'}
    items = [a for a in sandbox['appointments'] if a['student_id'] == student_id]
    items.sort(key=lambda a: (a['date'], a.get('start', '')))
    return {'ok': True, 'code': 'ok', 'student_id': student_id, 'appointments': items}


def book_appointment(sandbox: dict, student_id: str, slot_id: str, reason: str = 'clinic visit') -> dict:
    if not _patient(sandbox, student_id):
        return {'ok': False, 'code': 'unknown_student', 'message': f'No patient record for {student_id}'}
    slot = _slot(sandbox, slot_id)
    if not slot:
        return {'ok': False, 'code': 'unknown_slot', 'message': f'Slot {slot_id} does not exist'}
    if slot['status'] != 'open':
        return {'ok': False, 'code': 'slot_taken', 'message': f'Slot {slot_id} is no longer open'}
    if _active_count(sandbox, student_id) >= sandbox['policies']['max_active_appointments']:
        return {
            'ok': False,
            'code': 'limit_reached',
            'message': 'This student already has the maximum of 2 active appointments',
        }
    appointment = {
        'appointment_id': next_appointment_id(sandbox),
        'student_id': student_id,
        'slot_id': slot_id,
        'date': slot['date'],
        'start': slot['start'],
        'end': slot['end'],
        'provider_name': slot['provider_name'],
        'specialty': slot['specialty'],
        'status': 'booked',
        'reason': (reason or 'clinic visit')[:120],
    }
    slot['status'] = 'booked'
    sandbox['appointments'].append(appointment)
    return {'ok': True, 'code': 'booked', 'appointment': appointment, 'terminal': True}


def cancel_appointment(sandbox: dict, appointment_id: str, student_id: str | None = None) -> dict:
    appt = _appointment(sandbox, appointment_id)
    if not appt:
        return {'ok': False, 'code': 'unknown_appointment', 'message': f'No appointment {appointment_id}'}
    if appt['status'] != 'booked':
        return {'ok': False, 'code': 'not_active', 'message': f'{appointment_id} is already {appt["status"]}'}
    if student_id and appt['student_id'] != student_id:
        return {
            'ok': False,
            'code': 'identity_mismatch',
            'message': 'Student id does not match this appointment',
        }
    appt_day = date.fromisoformat(appt['date'])
    if appt_day <= date.today():
        return {
            'ok': False,
            'code': 'approval_required',
            'message': 'Same-day or past cancellations need staff approval. I will not cancel this in the sandbox.',
            'appointment': appt,
        }
    appt['status'] = 'cancelled'
    slot = _slot(sandbox, appt['slot_id'])
    if slot:
        slot['status'] = 'open'
    return {'ok': True, 'code': 'cancelled', 'appointment': appt, 'terminal': True}


def reschedule_appointment(sandbox: dict, appointment_id: str, new_slot_id: str, student_id: str | None = None) -> dict:
    appt = _appointment(sandbox, appointment_id)
    if not appt:
        return {'ok': False, 'code': 'unknown_appointment', 'message': f'No appointment {appointment_id}'}
    if appt['status'] != 'booked':
        return {'ok': False, 'code': 'not_active', 'message': f'{appointment_id} is already {appt["status"]}'}
    if student_id and appt['student_id'] != student_id:
        return {
            'ok': False,
            'code': 'identity_mismatch',
            'message': 'Student id does not match this appointment',
        }
    appt_day = date.fromisoformat(appt['date'])
    if appt_day <= date.today():
        return {
            'ok': False,
            'code': 'approval_required',
            'message': 'Same-day appointments cannot be rescheduled without staff approval.',
            'appointment': appt,
        }
    new_slot = _slot(sandbox, new_slot_id)
    if not new_slot:
        return {'ok': False, 'code': 'unknown_slot', 'message': f'Slot {new_slot_id} does not exist'}
    if new_slot['status'] != 'open':
        return {'ok': False, 'code': 'slot_taken', 'message': f'Slot {new_slot_id} is no longer open'}
    old = _slot(sandbox, appt['slot_id'])
    if old:
        old['status'] = 'open'
    new_slot['status'] = 'booked'
    appt['slot_id'] = new_slot_id
    appt['date'] = new_slot['date']
    appt['start'] = new_slot['start']
    appt['end'] = new_slot['end']
    appt['provider_name'] = new_slot['provider_name']
    appt['specialty'] = new_slot['specialty']
    return {'ok': True, 'code': 'rescheduled', 'appointment': appt, 'terminal': True}


TOOL_IMPL = {
    'search_availability': lambda sandbox, arguments: search_availability(
        sandbox,
        specialty=arguments.get('specialty'),
        date_value=arguments.get('date') or arguments.get('date_value'),
    ),
    'list_appointments': lambda sandbox, arguments: list_appointments(
        sandbox, student_id=str(arguments.get('student_id', '')).strip(),
    ),
    'book_appointment': lambda sandbox, arguments: book_appointment(
        sandbox,
        student_id=str(arguments.get('student_id', '')).strip(),
        slot_id=str(arguments.get('slot_id', '')).strip(),
        reason=str(arguments.get('reason') or 'clinic visit'),
    ),
    'cancel_appointment': lambda sandbox, arguments: cancel_appointment(
        sandbox,
        appointment_id=str(arguments.get('appointment_id', '')).strip(),
        student_id=(str(arguments['student_id']).strip() if arguments.get('student_id') else None),
    ),
    'reschedule_appointment': lambda sandbox, arguments: reschedule_appointment(
        sandbox,
        appointment_id=str(arguments.get('appointment_id', '')).strip(),
        new_slot_id=str(arguments.get('new_slot_id') or arguments.get('slot_id') or '').strip(),
        student_id=(str(arguments['student_id']).strip() if arguments.get('student_id') else None),
    ),
}

TOOLS = {name: True for name in TOOL_IMPL}

TOOL_SCHEMAS = {
    'search_availability': {
        'specialty': 'optional general|dental|dermatology|physiotherapy',
        'date': 'optional YYYY-MM-DD or today|tomorrow',
    },
    'list_appointments': {'student_id': 'required S-####'},
    'book_appointment': {
        'student_id': 'required S-####',
        'slot_id': 'required SLOT-...',
        'reason': 'optional short reason',
    },
    'cancel_appointment': {
        'appointment_id': 'required A-####',
        'student_id': 'optional S-#### to confirm identity',
    },
    'reschedule_appointment': {
        'appointment_id': 'required A-####',
        'new_slot_id': 'required SLOT-...',
        'student_id': 'optional S-####',
    },
}

REQUIRED_ARGS = {
    'search_availability': (),
    'list_appointments': ('student_id',),
    'book_appointment': ('student_id', 'slot_id'),
    'cancel_appointment': ('appointment_id',),
    'reschedule_appointment': ('appointment_id', 'new_slot_id'),
}


def format_observation(tool: str, result: dict) -> str:
    if not result.get('ok'):
        return f'TOOL {tool} REJECTED code={result.get("code")} message={result.get("message")}'
    if tool == 'search_availability':
        lines = [f'TOOL {tool} OK count={result["count"]} OPEN_SLOTS:']
        if not result['slots']:
            lines.append('none')
        for slot in result['slots']:
            lines.append(
                f"{slot['slot_id']} | {slot['date']} {slot['start']}-{slot['end']} | "
                f"{slot['specialty']} | {slot['provider_name']} | {slot['status']}"
            )
        return '\n'.join(lines)
    if tool == 'list_appointments':
        lines = [f'TOOL {tool} OK student={result["student_id"]} APPOINTMENTS:']
        if not result['appointments']:
            lines.append('none')
        for appt in result['appointments']:
            lines.append(
                f"{appt['appointment_id']} | {appt['date']} {appt.get('start', '')} | "
                f"{appt['specialty']} | {appt['status']} | {appt['slot_id']}"
            )
        return '\n'.join(lines)
    appt = result.get('appointment') or {}
    return (
        f"TOOL {tool} OK code={result.get('code')} TERMINAL=1 "
        f"{appt.get('appointment_id')} {appt.get('student_id')} {appt.get('date')} "
        f"{appt.get('start')} {appt.get('specialty')} {appt.get('status')}"
    )


def execute_tool(name: str, arguments: dict, sandbox: dict) -> dict:
    if name not in TOOL_IMPL:
        return {'ok': False, 'code': 'unknown_tool', 'message': f'Unsupported tool {name}'}
    if name == 'reschedule_appointment' and not arguments.get('new_slot_id') and arguments.get('slot_id'):
        arguments = {**arguments, 'new_slot_id': arguments.get('slot_id')}
    missing = [key for key in REQUIRED_ARGS[name] if not str(arguments.get(key) or '').strip()]
    if missing:
        return {'ok': False, 'code': 'missing_args', 'message': f'Missing arguments: {", ".join(missing)}'}
    return TOOL_IMPL[name](sandbox, arguments)


def run_tool_with_faults(name: str, arguments: dict, sandbox: dict, fault, fault_used: bool, step: int, max_retries: int):
    """First matching tool operation can receive the requested Arena fault once."""
    traces: list[ToolTrace] = []
    result = None
    observation = ''
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        started = perf_counter()
        if not fault_used and fault.type == 'tool_timeout':
            fault_used = True
            traces.append(ToolTrace(
                step=step, tool=name, attempt=attempt, outcome='timeout',
                latency_ms=(perf_counter() - started) * 1000,
            ))
            observation = 'TOOL timeout: the clinic system did not respond. Retrying if attempts remain.'
            continue
        if not fault_used and fault.type == 'malformed_tool_output':
            fault_used = True
            traces.append(ToolTrace(
                step=step, tool=name, attempt=attempt, outcome='malformed_output',
                latency_ms=(perf_counter() - started) * 1000,
            ))
            observation = 'TOOL malformed_output: received <<<not-json>>> instead of a typed result. Retrying.'
            continue
        try:
            result = execute_tool(name, arguments, sandbox)
            outcome = 'success' if result.get('ok') else 'rejected'
            traces.append(ToolTrace(
                step=step, tool=name, attempt=attempt, outcome=outcome,
                latency_ms=(perf_counter() - started) * 1000,
            ))
            observation = format_observation(name, result)
            return traces, result, observation, fault_used
        except Exception as exc:
            traces.append(ToolTrace(
                step=step, tool=name, attempt=attempt, outcome='exception',
                latency_ms=(perf_counter() - started) * 1000,
            ))
            observation = f'TOOL exception: {type(exc).__name__}'
            result = {'ok': False, 'code': 'exception', 'message': type(exc).__name__}
    return traces, result, observation, fault_used
