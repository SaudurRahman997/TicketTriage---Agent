# Submission summary
Copy these details into i230540_submission.pdf (same values, clickable URLs).

- Full name: Saud  (TODO: add full name as on university records)
- Roll number: i230540
- Class / section: TODO
- University email: TODO
- GitHub username: TODO
- Agent name and domain: TicketTriage Sentinel — Support-Ticket Triage
- Private GitHub repository URL: TODO
- Final source commit hash: TODO (run `git rev-parse HEAD`)
- Working public agent interface URL: TODO (https://YOUR-APP.onrender.com/)
- GET /health URL: TODO (…/health)
- POST /arena/run URL: TODO (…/arena/run)
- GET /arena/manifest URL: TODO (…/arena/manifest)
- API documentation URL: TODO (…/docs)
- Hosting provider: Render (free web service)
- Default model and provider: TODO (set after model comparison)
- Other available models: anthropic:claude-haiku-4-5-20251001, gemini:gemini-2.5-flash (via AVAILABLE_MODELS)
- Example input and expected behavior: "Triage ticket T-1002 and draft a reply" -> reads ticket, classifies technical/high, saves an unsent draft, status completed. "Close my ticket" -> needs_clarification (no id invented).
- Cold-start / restart limitations: Free instance sleeps; first request can take ~1 min; in-memory chat history is lost on restart; single worker.
- Instructor repository invitation status: TODO (pending / accepted)
- Public test result file: evaluation/public_results.md

Submit i230540.zip and i230540_submission.pdf in Google Classroom, then click Turn in.
The ZIP must contain one i230540/ project folder including this file. See assignment Section 19.
