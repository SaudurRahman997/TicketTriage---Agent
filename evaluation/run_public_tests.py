"""Run public cases against a running server (costs money once a model is configured).
Usage: python evaluation/run_public_tests.py --url http://127.0.0.1:8000 [--only A1,B1]
Writes evaluation/public_results.json and public_results.md"""
import argparse, json, sys, time
from pathlib import Path
import httpx

HERE = Path(__file__).parent


def check(case, r):
    names = [c["name"] for c in r.get("tool_calls", [])]
    why = []
    if r["status"] not in case["expect_status"]:
        why.append(f"status {r['status']} not in {case['expect_status']}")
    if case.get("expect_no_tools") and names:
        why.append(f"unexpected tools {names}")
    for t in case.get("expect_tools", []):
        if t not in names:
            why.append(f"missing tool {t}")
    for t in case.get("forbid_tools", []):
        if t in names:
            why.append(f"forbidden tool {t}")
    for c in r.get("tool_calls", []):
        if c["name"] == "classify_ticket" and c["arguments"].get("ticket_id") in case.get("expect_no_label_on", []):
            why.append("classified a ticket the task did not mention")
    if case.get("expect_repair") and r.get("metrics", {}).get("repair_attempts", 0) < 1:
        why.append("expected a repair attempt")
    if case.get("expect_retry") and not any(c.get("attempts", 1) > 1 for c in r.get("tool_calls", [])):
        why.append("expected a tool retry")
    return why


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8000"); ap.add_argument("--only", default="")
    a = ap.parse_args()
    cases = json.loads((HERE / "public_cases.json").read_text())
    if a.only:
        cases = [c for c in cases if c["id"] in a.only.split(",")]
    rows, ok = [], 0
    for c in cases:
        body = {"task": c["task"], "external_context": c.get("external_context", []),
                "arena_config": {"max_steps": c.get("max_steps", 6), "fault": c.get("fault", "none")}}
        t = time.time()
        try:
            r = httpx.post(a.url.rstrip("/") + "/arena/run", json=body, timeout=60).json()
        except Exception as e:
            r = {"status": "failed", "stop_reason": f"client_error:{type(e).__name__}", "tool_calls": [], "steps": 0}
        why = check(c, r); ok += not why
        rows.append({"id": c["id"], "category": c["category"], "pass": not why, "why": why, "status": r["status"],
                     "stop_reason": r.get("stop_reason"), "steps": r.get("steps"), "seconds": round(time.time() - t, 1)})
        print(("PASS" if not why else "FAIL"), c["id"], r["status"], r.get("stop_reason"), why or "")
    (HERE / "public_results.json").write_text(json.dumps(rows, indent=2))
    md = ["| id | category | result | status | stop_reason | steps | s |", "|---|---|---|---|---|---|---|"]
    md += [f"| {x['id']} | {x['category']} | {'PASS' if x['pass'] else 'FAIL: ' + '; '.join(x['why'])} | {x['status']} | {x['stop_reason']} | {x['steps']} | {x['seconds']} |" for x in rows]
    (HERE / "public_results.md").write_text("\n".join(md) + f"\n\n{ok}/{len(rows)} passed\n")
    print(f"{ok}/{len(rows)} passed"); sys.exit(0 if ok == len(rows) else 1)


if __name__ == "__main__":
    main()
