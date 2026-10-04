# Submission summary

Copy these details into `i222327_submission.pdf`.

- Full name: Mohammad Rohaan
- Roll number: 22I-2327 (`i222327`)
- Class / section: A
- University email: i222327@nu.edu.pk
- GitHub username: rohaan2802
- Agent name and domain: ClinicDesk — campus clinic appointment operations
- Private GitHub repository URL: PENDING_PUSH
- Final source commit hash: PENDING_COMMIT
- Working public agent interface URL: PENDING_DEPLOY
- GET /health URL: PENDING_DEPLOY/health
- POST /arena/run URL: PENDING_DEPLOY/arena/run
- GET /arena/manifest URL: PENDING_DEPLOY/arena/manifest
- API documentation URL: PENDING_DEPLOY/docs
- Hosting provider: Render (Free web service)
- Default model and provider: clinic-policy-v1 (deterministic clinic policy; no paid API key required)
- Other available models: gemini-2.0-flash and gemini-2.5-flash-lite if GEMINI_API_KEY is set; claude-3-5-haiku-20241022 if ANTHROPIC_API_KEY is set; unconfigured aliases the policy model
- Example input and expected behavior: `Book a general appointment tomorrow morning for student S-1001` → `completed` / `goal_completed` after search + book. `Cancel appointment A-9001 for student S-1002` → `approval_required`.
- Cold-start / restart limitations: Render free instances may sleep after idle time and take about a minute to wake. In-memory chat history and session sandboxes reset on restart. Arena runs are always isolated.
- Instructor repository invitation status: PENDING — Classroom note did not include the instructor GitHub username. Invite them as a collaborator as soon as it is posted.
- Public test result file: evaluation/public_test_results.txt (20/20 unit tests, 9/9 public HTTP cases)

Submit i222327.zip and i222327_submission.pdf in Google Classroom, then click Turn in.
The ZIP must contain one i222327/ project folder including this file. See assignment Section 19.
