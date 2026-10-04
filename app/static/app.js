let sid = null;
const $ = id => document.getElementById(id);
const say = (cls, t) => { const d = document.createElement("div"); d.className = cls; d.textContent = (cls === "u" ? "You: " : "Agent: ") + t; $("chat").append(d); $("chat").scrollTop = 1e9; };
async function init() {
  const m = await (await fetch("/models")).json();
  m.models.forEach(o => { const e = new Option(o.id + (o.configured ? "" : " (no key)"), o.id); e.disabled = !o.configured; $("model").add(e); });
  if (m.default) $("model").value = m.default;
}
async function send() {
  const message = $("msg").value.trim(); if (!message) return;
  $("msg").value = ""; say("u", message); $("status").textContent = "running...";
  const ctx = $("ctx").value.trim();
  const r = await fetch("/chat", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sid, message, model: $("model").value || null,
      external_context: ctx ? [{ source: "note", content: ctx, trust: "untrusted" }] : [] }) });
  if (!r.ok) { $("status").textContent = "error " + r.status; return; }
  const d = await r.json(); sid = d.session_id;
  say("a", d.final_response || "(no message)");
  $("status").textContent = d.status + " (" + d.stop_reason + ")";
  const mt = d.metrics || {};
  $("meta").textContent = `steps ${d.steps} | ${mt.latency_ms} ms | tokens in/out ${mt.input_tokens ?? "?"}/${mt.output_tokens ?? "?"} | cost ${mt.estimated_cost_usd ?? "n/a"}`;
  $("timeline").innerHTML = ""; $("obs").textContent = "";
  d.events.forEach(e => { const li = document.createElement("li"); li.textContent = `step ${e.step}: ${e.type} ${e.action || e.tool || ""} ${e.valid === false ? "INVALID " + e.problems.join("; ") : ""} ${e.detail || ""}`; if (e.valid === false || e.type.includes("error")) li.className = "bad"; $("timeline").append(li); });
  $("obs").textContent = d.tool_calls.map(c => `${c.name}(${JSON.stringify(c.arguments)}) -> ${JSON.stringify(c.result ?? c.error)}`).join("\n");
}
$("send").onclick = send; $("msg").onkeydown = e => { if (e.key === "Enter") send(); };
$("newchat").onclick = async () => { if (sid) await fetch("/chat/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session_id: sid }) }); sid = null; $("chat").innerHTML = ""; $("timeline").innerHTML = ""; $("obs").textContent = ""; $("status").textContent = "idle"; };
init();
