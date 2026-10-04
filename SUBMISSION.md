# Submission summary

Copy these details into `i222327_submission.pdf`.

- Full name: Mohammad Rohaan
- Roll number: 22I-2327 (`i222327`)
- Class / section: A
- University email: i222327@nu.edu.pk
- GitHub username: rohaan2802
- Agent name and domain: ClinicDesk — campus clinic appointment operations
- Private GitHub repository URL: https://github.com/rohaan2802/i222327-clinicdesk
- Final source commit hash: 746cdb4
- Working public agent interface URL: PENDING_RENDER_FREE_DEPLOY
- GET /health URL: PENDING_RENDER_FREE_DEPLOY/health
- POST /arena/run URL: PENDING_RENDER_FREE_DEPLOY/arena/run
- GET /arena/manifest URL: PENDING_RENDER_FREE_DEPLOY/arena/manifest
- API documentation URL: PENDING_RENDER_FREE_DEPLOY/docs
- Hosting provider: Render (Free web service — no card required)
- Default model and provider: clinic-policy-v1 (deterministic clinic policy; no Gemini key required)
- Other available models: Gemini flash models and OpenRouter GPT-4o mini when API keys are set; unconfigured aliases the policy model
- Example input and expected behavior: `Book a general appointment tomorrow morning for student S-1001` → `completed` / `goal_completed` after search + book. `Cancel appointment A-9001 for student S-1002` → `approval_required`.
- Cold-start / restart limitations: Render free instances may sleep after idle time and take about a minute to wake. In-memory chat history and session sandboxes reset on restart. Arena runs are always isolated.
- Instructor repository invitation status: PENDING — Classroom note does not include the instructor GitHub username. Invite them under Settings → Collaborators as soon as it is posted.
- Public test result file: evaluation/public_test_results.txt (full unittest battery including 9/9 public cases + break-attempt battery)

Submit i222327.zip and i222327_submission.pdf in Google Classroom, then click Turn in.
The ZIP must contain one i222327/ project folder including this file. See assignment Section 19.
