# Submission Summary

Complete the `TODO` fields before submitting. Copy the same information and clickable URLs into `i230540_submission.pdf`.

- Full name: TODO — enter full name as shown in university records
- Roll number: i230540
- Class / section: TODO
- University email: TODO
- GitHub username: SaudurRahman997
- Agent name: TicketTriage Sentinel
- Domain: Support-Ticket Triage

## Repository and deployment

- GitHub repository URL: https://github.com/SaudurRahman997/TicketTriage---Agent
- Final source commit hash: TODO — update after the final commit and deployment
- Working public agent interface: https://tickettriageagent.vercel.app/
- Health endpoint (GET): https://tickettriageagent.vercel.app/health
- Arena endpoint (POST): https://tickettriageagent.vercel.app/arena/run
- Manifest endpoint (GET): https://tickettriageagent.vercel.app/arena/manifest
- API documentation: https://tickettriageagent.vercel.app/docs
- Hosting provider: Vercel

## Agent details

- Default model / provider: TODO — verify the production value at `/models` before submission
- Other available models: TODO — copy the configured model list from `/models`
- Example input: `Triage ticket T-1002 and draft a short reply.`
- Expected result: Reads the named ticket, classifies it, saves an unsent draft reply in the sandbox, and reports only confirmed actions.
- Cold-start / restart limitations: The app keeps conversation history in memory. Vercel may start separate or fresh function instances, so session history may not persist across requests or restarts. Verify multi-turn clarification behavior on the deployed app.

## Evaluation and access

- Instructor repository access: TODO — record pending or accepted after inviting the instructor
- Public test results: `evaluation/public_results.md` (rerun after the final code and production model are in place)
- Model comparison: TODO — add results for at least two models and a short selection rationale to `README.md`

## Classroom submission

Create `i230540.zip` containing one top-level `i230540/` project folder and upload it together with `i230540_submission.pdf`. Exclude `.env`, `.venv/`, `.git/`, `__pycache__/`, compiled files, and API keys. Confirm Google Classroom shows **Turned in**.
