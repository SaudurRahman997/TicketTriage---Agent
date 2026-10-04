"""Section 6 experiment: run the SAME public cases on two+ models, in-process.
Needs real keys in .env. Usage:
  python evaluation/model_comparison.py --models anthropic:claude-haiku-4-5-20251001,gemini:gemini-2.5-flash
Writes evaluation/model_comparison.md (paste the table into the README)."""
import argparse, json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
from app import api
from app.models import ExternalItem
from run_public_tests import check

HERE = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--models", required=True); a = ap.parse_args()
    cases = json.loads((HERE / "public_cases.json").read_text())
    head = ["| model | task success | contract-valid (no unexpected repair) | correct final status | avg latency s | avg in tokens | avg out tokens | est. cost / case (USD) |", "|---|---|---|---|---|---|---|---|"]
    rows = []
    for mid in a.models.split(","):
        succ = valid = act = 0; lat, tin, tout, cost = [], 0, 0, 0.0; known = True
        for c in cases:
            r = api._execute(c["task"], [ExternalItem(**e) for e in c.get("external_context", [])], c.get("max_steps", 6),
                             c.get("fault", "none"), [], mid, None).model_dump()
            why = check(c, r); succ += not why
            valid += r["status"] != "contract_error" and r.get("metrics", {}).get("repair_attempts", 0) == (1 if c.get("expect_repair") else 0)
            act += r["status"] in c["expect_status"]
            m = r.get("metrics", {}); lat.append(m.get("latency_ms", 0) / 1000)
            if m.get("input_tokens") is None: known = False
            else: tin += m["input_tokens"]; tout += m["output_tokens"]; cost += m.get("estimated_cost_usd") or 0
            print(mid, c["id"], "PASS" if not why else why)
        n = len(cases)
        tok = f"{tin // n} | {tout // n} | {cost / n:.5f}" if known else "n/a | n/a | n/a"
        rows.append(f"| {mid} | {succ}/{n} | {valid}/{n} | {act}/{n} | {statistics.mean(lat):.1f} | {tok} |")
    out = "\n".join(head + rows) + "\n"
    (HERE / "model_comparison.md").write_text(out); print(out)


if __name__ == "__main__":
    main()
