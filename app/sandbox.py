"""Isolated clinic sandbox per Arena run; chat sessions keep one copy until reset."""
from __future__ import annotations

import copy
import json
from collections import OrderedDict
from datetime import date, timedelta

from app.config import ROOT

_BASE = json.loads((ROOT / 'data/sample_data.json').read_text(encoding='utf-8'))
_SESSIONS: OrderedDict[str, dict] = OrderedDict()
_SESSION_CAP = 100


def _providers_by_id(data: dict) -> dict:
    return {p['provider_id']: p for p in data['providers']}


def materialize_slots(data: dict) -> None:
    providers = _providers_by_id(data)
    today = date.today()
    slots = []
    for offset in range(0, 14):
        day = today + timedelta(days=offset)
        template_weekday = day.weekday() if day.weekday() < 5 else 0
        for tmpl in data.get('weekly_template', []):
            if tmpl['weekday'] != template_weekday:
                continue
            provider = providers[tmpl['provider_id']]
            slot_id = f"SLOT-{day.strftime('%Y%m%d')}-{tmpl['provider_id']}-{tmpl['start'].replace(':', '')}"
            slots.append({
                'slot_id': slot_id,
                'date': day.isoformat(),
                'start': tmpl['start'],
                'end': tmpl['end'],
                'provider_id': tmpl['provider_id'],
                'provider_name': provider['name'],
                'specialty': provider['specialty'],
                'status': 'open',
            })
    data['slots'] = slots
    data.setdefault('appointments', [])


def seed_demo_appointments(data: dict) -> None:
    """Always seed one same-day and one future appointment for policy tests."""
    today = date.today()
    future = today + timedelta(days=3)
    if future.weekday() >= 5:
        future = today + timedelta(days=5)

    def ensure_slot(day: date, provider_id: str, start: str, end: str) -> dict:
        providers = _providers_by_id(data)
        provider = providers[provider_id]
        slot_id = f"SLOT-{day.strftime('%Y%m%d')}-{provider_id}-{start.replace(':', '')}"
        existing = next((s for s in data['slots'] if s['slot_id'] == slot_id), None)
        if existing:
            existing['status'] = 'booked'
            return existing
        slot = {
            'slot_id': slot_id,
            'date': day.isoformat(),
            'start': start,
            'end': end,
            'provider_id': provider_id,
            'provider_name': provider['name'],
            'specialty': provider['specialty'],
            'status': 'booked',
        }
        data['slots'].append(slot)
        return slot

    today_slot = ensure_slot(today, 'D-10', '14:00', '14:30')
    future_slot = ensure_slot(future, 'D-11', '11:00', '11:30')
    data['appointments'] = [
        {
            'appointment_id': 'A-9001',
            'student_id': 'S-1002',
            'slot_id': today_slot['slot_id'],
            'date': today.isoformat(),
            'start': '14:00',
            'end': '14:30',
            'provider_name': today_slot['provider_name'],
            'specialty': today_slot['specialty'],
            'status': 'booked',
            'reason': 'follow-up',
        },
        {
            'appointment_id': 'A-9002',
            'student_id': 'S-1001',
            'slot_id': future_slot['slot_id'],
            'date': future.isoformat(),
            'start': '11:00',
            'end': '11:30',
            'provider_name': future_slot['provider_name'],
            'specialty': future_slot['specialty'],
            'status': 'booked',
            'reason': 'dental checkup',
        },
    ]


def clone_base() -> dict:
    data = copy.deepcopy(_BASE)
    materialize_slots(data)
    seed_demo_appointments(data)
    data['seq'] = 9100
    return data


def get_sandbox(session_id: str | None = None) -> dict:
    if not session_id:
        return clone_base()
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = clone_base()
        _SESSIONS.move_to_end(session_id)
        while len(_SESSIONS) > _SESSION_CAP:
            _SESSIONS.popitem(last=False)
    return _SESSIONS[session_id]


def clear_sandbox(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def next_appointment_id(sandbox: dict) -> str:
    sandbox['seq'] = int(sandbox.get('seq', 9100)) + 1
    return f"A-{sandbox['seq']}"
