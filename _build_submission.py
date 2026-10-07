"""Build final Classroom PDF + ZIP for roll i222327."""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from fpdf import FPDF

ROOT = Path(r'c:\Users\CodeTech\Desktop\Agentic AI Assignment# 01')
SRC = ROOT / 'Agent_Arena_Student_Starter' / 'student-agent'
OUT = ROOT / 'FINAL_SUBMISSION'
OUT.mkdir(exist_ok=True)

for old in list(OUT.glob('i222327*')) + list(ROOT.glob('i222327*')):
    if old.is_file():
        old.unlink()
    elif old.is_dir():
        shutil.rmtree(old)

pdf_path = OUT / 'i222327_submission.pdf'
zip_path = OUT / 'i222327.zip'


class PDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')


pdf = PDF(format='A4')
pdf.set_margins(18, 18, 18)
pdf.set_auto_page_break(auto=True, margin=18)
pdf.add_page()
pdf.set_font('Helvetica', 'B', 18)
pdf.multi_cell(0, 10, 'Agent Arena Submission')
pdf.set_font('Helvetica', '', 12)
pdf.ln(2)
pdf.multi_cell(0, 7, 'ClinicDesk - Campus Clinic Appointment Agent')
pdf.ln(4)

lines = [
    ('Full name', 'Mohammad Rohaan'),
    ('Roll number', '22I-2327 (i222327)'),
    ('Class / section', 'A'),
    ('University email', 'i222327@nu.edu.pk'),
    ('GitHub username', 'rohaan2802'),
    ('Agent name and domain', 'ClinicDesk - campus clinic appointment operations'),
    ('Private GitHub repository URL', 'https://github.com/rohaan2802/Clinic_Desk_Agent'),
    ('Final source commit hash', '1a990b8'),
    ('Working public agent interface URL', 'https://clinic-desk-agent.onrender.com/'),
    ('GET /health URL', 'https://clinic-desk-agent.onrender.com/health'),
    ('POST /arena/run URL', 'https://clinic-desk-agent.onrender.com/arena/run'),
    ('GET /arena/manifest URL', 'https://clinic-desk-agent.onrender.com/arena/manifest'),
    ('API documentation URL', 'https://clinic-desk-agent.onrender.com/docs'),
    ('Hosting provider', 'Render (Free web service - no card required)'),
    ('Default model and provider', 'clinic-policy-v1 (deterministic clinic policy; no Gemini key required)'),
    (
        'Other available models',
        'Gemini flash models and OpenRouter GPT-4o mini when API keys are set; '
        'unconfigured aliases the policy model',
    ),
    (
        'Example input and expected behavior',
        'Book a general appointment tomorrow morning for student S-1001 -> completed / goal_completed '
        'after search + book. Cancel appointment A-9001 for student S-1002 -> approval_required.',
    ),
    (
        'Cold-start / restart limitations',
        'Render free instances may sleep after idle time and take about a minute to wake. '
        'In-memory chat history and session sandboxes reset on restart. Arena runs are always isolated.',
    ),
    (
        'Instructor repository invitation status',
        'PENDING - Classroom note does not include the instructor GitHub username. '
        'Invite them under Settings -> Collaborators as soon as it is posted.',
    ),
    (
        'Public test result file',
        'evaluation/public_test_results.txt (full unittest battery including 9/9 public cases + break-attempt battery)',
    ),
]

usable = pdf.w - pdf.l_margin - pdf.r_margin

pdf.set_font('Helvetica', 'B', 13)
pdf.multi_cell(usable, 8, 'Submission details')
pdf.ln(2)

for label, value in lines:
    pdf.set_x(pdf.l_margin)
    pdf.set_font('Helvetica', 'B', 11)
    pdf.multi_cell(usable, 6, label)
    pdf.set_x(pdf.l_margin)
    pdf.set_font('Helvetica', '', 11)
    safe = (
        value.replace('\u2014', '-')
        .replace('\u2013', '-')
        .replace('\u2192', '->')
    )
    pdf.multi_cell(usable, 6, safe)
    pdf.ln(2)

pdf.set_x(pdf.l_margin)
pdf.ln(2)
pdf.set_font('Helvetica', 'B', 13)
pdf.multi_cell(usable, 8, 'What /arena/manifest is')
pdf.set_x(pdf.l_margin)
pdf.set_font('Helvetica', '', 11)
pdf.multi_cell(
    usable,
    6,
    'The Arena manifest is a short machine-readable contract for graders. '
    'It declares the agent name, domain, tools, fault types, step/time limits, '
    'and autonomy rules (clarify / approval / block). Live URL: '
    'https://clinic-desk-agent.onrender.com/arena/manifest',
)

pdf.set_x(pdf.l_margin)
pdf.ln(4)
pdf.set_font('Helvetica', 'B', 13)
pdf.multi_cell(usable, 8, 'Turn-in note')
pdf.set_x(pdf.l_margin)
pdf.set_font('Helvetica', '', 11)
pdf.multi_cell(
    usable,
    6,
    'Submit i222327.zip and i222327_submission.pdf in Google Classroom, then click Turn in. '
    'The ZIP contains one i222327/ project folder including SUBMISSION.md.',
)

pdf.output(str(pdf_path))
print('PDF:', pdf_path)

staging = OUT / '_stage'
if staging.exists():
    shutil.rmtree(staging)
proj = staging / 'i222327'
proj.mkdir(parents=True)

skip_dirs = {'.venv', '__pycache__', '.git', '.pytest_cache', '.mypy_cache', 'node_modules', '_stage'}
skip_files = {'.env', '_build_submission.py'}
skip_suffix = {'.pyc', '.pyo'}


def should_skip(path: Path) -> bool:
    if set(path.parts) & skip_dirs:
        return True
    if path.name in skip_files:
        return True
    if path.suffix in skip_suffix:
        return True
    return False


for item in SRC.rglob('*'):
    rel = item.relative_to(SRC)
    if should_skip(rel):
        continue
    dest = proj / rel
    if item.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)

# Keep SUBMISSION.md in sync with source (already copied); ensure hash present
shutil.copy2(SRC / 'SUBMISSION.md', proj / 'SUBMISSION.md')

if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for file in proj.rglob('*'):
        if file.is_file():
            zf.write(file, arcname=str(Path('i222327') / file.relative_to(proj)))

shutil.rmtree(staging)
print('ZIP:', zip_path)
print('entries:', len(zipfile.ZipFile(zip_path).namelist()))
