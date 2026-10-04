"""Deterministic ClinicDesk planner used as clinic-policy-v1 and as LLM fallback."""
from __future__ import annotations

from datetime import date, timedelta

from app.prompts import (
    APPT_RE, SLOT_RE, STUDENT_RE, detect_injection, looks_like_followup, resolve_goal,
)
from app.tools import SPECIALTIES


def _history_text(history: list) -> str:
    parts = []
    for message in history or []:
        parts.append(str(getattr(message, 'content', '')))
    return '\n'.join(parts)


def _extract_student(text: str) -> str | None:
    match = STUDENT_RE.search(text or '')
    return match.group(0).upper() if match else None


def _extract_appt(text: str) -> str | None:
    match = APPT_RE.search(text or '')
    return match.group(0).upper() if match else None


def _extract_slot(text: str) -> str | None:
    match = SLOT_RE.search(text or '')
    return match.group(0).upper() if match else None


def _extract_specialty(text: str) -> str | None:
    lowered = (text or '').lower()
    for spec in SPECIALTIES:
        if spec in lowered:
            return spec
    if 'skin' in lowered:
        return 'dermatology'
    if 'tooth' in lowered or 'teeth' in lowered:
        return 'dental'
    if 'physio' in lowered or 'back pain' in lowered:
        return 'physiotherapy'
    if 'checkup' in lowered or 'check-up' in lowered or 'gp' in lowered:
        return 'general'
    return None


def _extract_date(text: str) -> str | None:
    lowered = (text or '').lower()
    today = date.today()
    if 'today' in lowered:
        return today.isoformat()
    if 'tomorrow' in lowered:
        return (today + timedelta(days=1)).isoformat()
    match = __import__('re').search(r'20\d{2}-\d{2}-\d{2}', text or '')
    return match.group(0) if match else None


def _intent(text: str) -> str:
    lowered = (text or '').lower()
    if detect_injection(lowered):
        return 'inject'
    if any(word in lowered for word in ('reschedule', 'move my', 'change the slot', 'change appointment')):
        return 'reschedule'
    if any(word in lowered for word in ('cancel', 'drop the appointment', 'call off')):
        return 'cancel'
    if any(word in lowered for word in ('list', 'show my', 'what appointments', 'upcoming')):
        return 'list'
    if any(word in lowered for word in ('book', 'schedule', 'make an appointment', 'reserve')):
        return 'book'
    if any(word in lowered for word in ('available', 'availability', 'open slot', 'free slot', 'what slots')):
        return 'search'
    return 'unknown'


def _prefers_morning(text: str) -> bool:
    return 'morning' in (text or '').lower()


def _prefers_afternoon(text: str) -> bool:
    return any(word in (text or '').lower() for word in ('afternoon', 'evening'))


def _parse_open_slots(observations: list[str]) -> list[str]:
    slots = []
    for obs in observations:
        if 'OPEN_SLOTS' not in obs:
            continue
        for line in obs.splitlines():
            if line.startswith('SLOT-'):
                slots.append(line.split('|')[0].strip())
    return slots


def _pick_slot(observations: list[str], goal: str) -> str | None:
    slots = _parse_open_slots(observations)
    if not slots:
        return None
    if _prefers_morning(goal):
        morning = [s for s in slots if any(token in s for token in ('-09', '-10', '-11'))]
        if morning:
            return morning[0]
    if _prefers_afternoon(goal):
        afternoon = [s for s in slots if any(token in s for token in ('-13', '-14', '-15', '-16'))]
        if afternoon:
            return afternoon[0]
    return slots[0]


def _from_list_observation(observations: list[str], want_today: bool) -> str | None:
    today = date.today().isoformat().replace('-', '')
    for obs in reversed(observations):
        if 'APPOINTMENTS:' not in obs:
            continue
        for line in obs.splitlines():
            if not line.startswith('A-'):
                continue
            if 'booked' not in line:
                continue
            if want_today and today not in line.replace('-', ''):
                continue
            return line.split('|')[0].strip()
    return None


def _humanize_slots(obs: str) -> str:
    lines = []
    for line in (obs or '').splitlines():
        if not line.startswith('SLOT-'):
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) < 4:
            continue
        slot, when, specialty, provider = parts[0], parts[1], parts[2], parts[3]
        lines.append(f'• {when} — {specialty} with {provider} (ref {slot})')
    if not lines:
        return 'No open times matched that visit type and day. Try another day or another kind of visit.'
    return 'Here are the open times I found:\n' + '\n'.join(lines)


def _humanize_appointments(obs: str) -> str:
    student = ''
    if 'student=' in (obs or ''):
        student = obs.split('student=', 1)[-1].split()[0]
    lines = []
    for line in (obs or '').splitlines():
        if not line.startswith('A-'):
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) < 4:
            continue
        appt, when, specialty, status = parts[0], parts[1], parts[2], parts[3]
        lines.append(f'• {appt}: {when} — {specialty} ({status})')
    who = f' for student {student}' if student else ''
    if not lines:
        return f'No appointments on file{who}.'
    return f'Appointments{who}:\n' + '\n'.join(lines)


def _humanize_terminal(obs: str) -> str:
    text = obs.replace('TERMINAL=1', '').strip()
    parts = text.split()
    try:
        tool = parts[1]
        appt_id, student_id, day, start, specialty, status = parts[4:10]
    except (IndexError, ValueError):
        return 'The clinic update finished, but I could not turn the result into a short summary.'
    if tool == 'book_appointment':
        return f'Done. Booked visit {appt_id} for student {student_id} on {day} at {start} ({specialty}). It is {status}.'
    if tool == 'cancel_appointment':
        return f'Done. Cancelled visit {appt_id} for student {student_id} on {day} at {start} ({specialty}).'
    if tool == 'reschedule_appointment':
        return f'Done. Moved visit {appt_id} for student {student_id} to {day} at {start} ({specialty}).'
    return f'Done. Updated visit {appt_id} for student {student_id} on {day} at {start} ({specialty}).'


def _last_obs(observations: list[str]) -> str:
    return observations[-1] if observations else ''


def _decision(action: str, message: str, thought: str, tool: str | None = None, arguments: dict | None = None) -> dict:
    return {
        'action': action,
        'thought': thought,
        'user_message': message[:2000],
        'tool': tool,
        'arguments': arguments or {},
    }


def _reject_message(obs: str) -> str:
    if 'message=' in (obs or ''):
        return obs.split('message=', 1)[-1].strip()
    return 'That clinic update was rejected. Please check the visit id and try again.'


def plan_decision(task: str, history: list, observations: list[str], notes: list[str]) -> dict:
    if detect_injection(task):
        return _decision(
            'block',
            'I cannot ignore clinic rules, show hidden instructions, or cancel every visit at once.',
            'Task contains an injection or out-of-policy override.',
        )

    ignored = [note for note in notes if detect_injection(note)]
    _ = ignored
    goal = resolve_goal(task, history)
    # Current task/goal only. Never dig old chat for ids — that caused wrong cancels and step loops.
    student_id = _extract_student(goal)
    appt_id = _extract_appt(goal)
    # Optional confirm-id for cancel/reschedule: only if typed in THIS user message.
    task_student_id = _extract_student(task)
    slot_id = _extract_slot(goal)
    specialty = _extract_specialty(goal)
    wanted_date = _extract_date(goal)
    intent = _intent(goal)
    last = _last_obs(observations)

    if 'code=approval_required' in last:
        return _decision(
            'request_approval',
            _reject_message(last) or (
                'This visit is today or already passed, so a staff member must approve the change. I left it as it is.'
            ),
            'Tool required human approval.',
        )
    if 'TERMINAL=1' in last:
        return _decision('finish', _humanize_terminal(last), 'Mutation succeeded.')
    if any(code in last for code in (
        'code=not_active',
        'code=identity_mismatch',
        'code=unknown_appointment',
        'code=limit_reached',
        'code=missing_args',
    )):
        return _decision('finish', _reject_message(last), 'Hard tool rejection; stop looping.')
    if 'OPEN_SLOTS' in last and last.strip().endswith('none'):
        return _decision(
            'finish',
            'No open times matched that visit type and day. Try another day or another kind of visit.',
            'Search returned no slots',
        )
    if 'OPEN_SLOTS' in last and intent in {'search', 'unknown'}:
        return _decision('finish', _humanize_slots(last), 'Availability search completed.')
    if 'APPOINTMENTS:' in last and intent == 'list':
        return _decision('finish', _humanize_appointments(last), 'Appointment list completed.')
    if 'code=unknown_student' in last:
        return _decision('clarify', 'I could not find that student. Please send an id like S-1001.', 'Unknown student')
    if 'code=slot_taken' in last or 'code=unknown_slot' in last:
        # Avoid infinite search↔book loops: only retry search once per run.
        prior_searches = sum(1 for obs in observations if 'OPEN_SLOTS' in obs)
        if prior_searches >= 2:
            return _decision(
                'clarify',
                'I could not lock an open time. Please name a free slot ref (SLOT-...) or try another day.',
                'Slot search already retried.',
            )
        return _decision(
            'use_tool',
            'That time is no longer free. I will look for another open time.',
            'Need a fresh slot list',
            'search_availability',
            {'specialty': specialty or 'general', 'date': wanted_date},
        )

    if intent in {'book', 'list'} and not student_id:
        return _decision(
            'clarify',
            'I can help with that. Please send the student id, like S-1001.',
            'Missing identity for a mutation or lookup.',
        )
    if intent == 'cancel' and not appt_id and not student_id:
        return _decision(
            'clarify',
            'Which visit should I cancel? Send the visit id (A-9001) or the student id (S-1002).',
            'Cancel is ambiguous.',
        )

    if intent == 'list':
        if not student_id:
            return _decision('clarify', 'Please send the student id, like S-1001, so I can show their visits.', 'Need id')
        return _decision('use_tool', 'Looking up that student now.', 'List appointments', 'list_appointments', {'student_id': student_id})

    if intent == 'search' or (intent == 'unknown' and (specialty or 'slot' in goal.lower() or 'available' in goal.lower())):
        return _decision(
            'use_tool',
            'Checking which clinic times are still open.',
            'Search availability',
            'search_availability',
            {'specialty': specialty, 'date': wanted_date},
        )

    if intent == 'book':
        if not student_id:
            return _decision('clarify', 'Please send the student id, like S-1001, so I can book the visit.', 'Need id to book')
        picked = slot_id or _pick_slot(observations, goal)
        if not picked:
            return _decision(
                'use_tool',
                'I will first find an open time, then book it.',
                'Search before book',
                'search_availability',
                {'specialty': specialty or 'general', 'date': wanted_date},
            )
        return _decision(
            'use_tool',
            f'Booking that time for student {student_id}.',
            'Book selected slot',
            'book_appointment',
            {'student_id': student_id, 'slot_id': picked, 'reason': 'student request'},
        )

    if intent == 'cancel':
        if not appt_id:
            if student_id and 'APPOINTMENTS:' not in ''.join(observations):
                return _decision(
                    'use_tool',
                    'I will show this student\'s visits so we can cancel the right one.',
                    'Need appointment id',
                    'list_appointments',
                    {'student_id': student_id},
                )
            listed = _from_list_observation(observations, want_today='today' in goal.lower())
            if listed:
                appt_id = listed
            else:
                return _decision('clarify', 'Which visit should I cancel? Send an id like A-9001.', 'Still missing id')
        args = {'appointment_id': appt_id}
        if task_student_id:
            args['student_id'] = task_student_id
        return _decision('use_tool', f'Checking whether {appt_id} can be cancelled.', 'Cancel', 'cancel_appointment', args)

    if intent == 'reschedule':
        if not appt_id:
            return _decision('clarify', 'Please send the visit id to move, like A-9002.', 'Need appointment id')
        picked = slot_id or _pick_slot(observations, goal)
        if not picked:
            return _decision(
                'use_tool',
                'Looking up a new open time so I can move the visit.',
                'Search before reschedule',
                'search_availability',
                {'specialty': specialty or 'general', 'date': wanted_date},
            )
        args = {'appointment_id': appt_id, 'new_slot_id': picked}
        if task_student_id:
            args['student_id'] = task_student_id
        return _decision('use_tool', f'Moving visit {appt_id} to a new time.', 'Reschedule', 'reschedule_appointment', args)

    if looks_like_followup(task) and student_id:
        return _decision(
            'use_tool',
            'Thanks. I will check open times and continue.',
            'Follow-up supplied identity; search then book if the prior goal was a booking.',
            'search_availability',
            {'specialty': specialty or 'general', 'date': wanted_date},
        )

    if intent == 'unknown':
        return _decision(
            'clarify',
            'I can find open times, show visits, book, cancel, or move a visit. '
            'Tell me the student id (like S-1001) and what you want done.',
            'Goal is underspecified.',
        )
    return _decision('clarify', 'Please say what you need — book, list, cancel, or move — and include a student id like S-1001.', 'Fallback clarify')
