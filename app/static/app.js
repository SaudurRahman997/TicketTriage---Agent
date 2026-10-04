let sid = null;
const $ = id => document.getElementById(id);

function timestamp() {
  return new Intl.DateTimeFormat([], { hour: 'numeric', minute: '2-digit' }).format(new Date());
}

function setStatus(label, kind = '') {
  const status = $('status');
  status.textContent = label || 'Ready';
  status.className = `badge ${kind}`.trim();
}

function addMessage(who, text) {
  $('welcome')?.remove();
  const win = $('chat');
  const row = document.createElement('div');
  row.className = `msg ${who}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = String(text ?? '');
  const time = document.createElement('time');
  time.className = 'meta';
  time.textContent = timestamp();
  if (who === 'user') row.append(time, bubble);
  else row.append(bubble, time);
  win.append(row);
  win.scrollTop = win.scrollHeight;
}

function renderRun(data) {
  const events = Array.isArray(data.events) ? data.events : [];
  const calls = Array.isArray(data.tool_calls) ? data.tool_calls : [];
  const timeline = $('timeline');
  timeline.replaceChildren();
  $('event-count').textContent = `${events.length} event${events.length === 1 ? '' : 's'}`;
  if (!events.length) {
    const empty = document.createElement('li');
    empty.className = 'empty-state';
    empty.textContent = 'No agent actions were needed for this reply.';
    timeline.append(empty);
  }
  events.forEach(event => {
    const item = document.createElement('li');
    const step = event.step == null ? '' : `Step ${event.step} · `;
    const details = [event.type, event.action || event.tool, event.detail]
      .filter(value => value != null && value !== '')
      .join(' · ');
    const problems = Array.isArray(event.problems) ? event.problems.join('; ') : '';
    item.textContent = `${step}${details}${event.valid === false && problems ? ` · ${problems}` : ''}`;
    if (event.valid === false || String(event.type || '').includes('error')) item.classList.add('bad');
    timeline.append(item);
  });

  const observations = calls.map(call => {
    const args = JSON.stringify(call.arguments ?? {});
    const result = JSON.stringify(call.result ?? call.error ?? 'No result returned');
    return `${call.name || 'tool'}(${args})\n→ ${result}`;
  }).join('\n\n');
  $('obs').textContent = observations || 'No tool observations for this reply.';
}

async function init() {
  try {
    const response = await fetch('/models');
    if (!response.ok) throw new Error(`Model list returned ${response.status}`);
    const data = await response.json();
    const select = $('model');
    select.replaceChildren();
    (data.models || []).forEach(model => {
      const option = new Option(`${model.id}${model.configured ? '' : ' · key not set'}`, model.id);
      option.disabled = !model.configured;
      select.add(option);
    });
    if (data.default) select.value = data.default;
  } catch (error) {
    setStatus('Models unavailable', 'error');
    $('meta').textContent = 'Could not load the model list';
  }
}

async function send(event) {
  event?.preventDefault();
  const message = $('msg').value.trim();
  if (!message) return;
  $('msg').value = '';
  addMessage('user', message);
  setStatus('Working…', 'running');
  $('meta').textContent = 'The agent is checking your request';
  $('send').disabled = true;

  const context = $('ctx').value.trim();
  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sid,
        message,
        model: $('model').value || null,
        external_context: context ? [{ source: 'note', content: context, trust: 'untrusted' }] : []
      })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
    sid = data.session_id || sid;
    addMessage('agent', data.final_response || 'The agent returned no message.');
    const status = data.status || 'unknown';
    setStatus(status.replaceAll('_', ' '), status === 'failed' || status === 'tool_error' ? 'error' : '');
    const metrics = data.metrics || {};
    $('meta').textContent = `Step ${data.steps ?? '—'} · ${metrics.latency_ms ?? '—'} ms · tokens ${metrics.input_tokens ?? '?'} in / ${metrics.output_tokens ?? '?'} out · cost ${metrics.estimated_cost_usd ?? 'n/a'}`;
    renderRun(data);
  } catch (error) {
    addMessage('agent', `I couldn’t reach the agent service. ${error.message}`);
    setStatus('Connection error', 'error');
    $('meta').textContent = 'Check the deployment and try again';
  } finally {
    $('send').disabled = false;
    $('msg').focus();
  }
}

async function resetChat() {
  if (sid) {
    try {
      await fetch('/chat/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid })
      });
    } catch (_) { /* Starting a fresh local view still works if reset is offline. */ }
  }
  sid = null;
  $('chat').replaceChildren();
  const welcome = document.createElement('div');
  welcome.id = 'welcome';
  welcome.className = 'welcome';
  welcome.innerHTML = '<div class="welcome-mark">✦</div><strong>What can I help you triage?</strong><span>Try “Triage ticket T-1002 and draft a reply.” I can read, classify, draft, or route sandbox tickets.</span>';
  $('chat').append(welcome);
  $('timeline').innerHTML = '<li class="empty-state">Your agent’s decisions will appear here.</li>';
  $('event-count').textContent = '0 events';
  $('obs').textContent = 'Ticket reads and tool results will appear here.';
  $('ctx').value = '';
  $('meta').textContent = 'Your sandbox queue is ready';
  setStatus('Ready');
}

$('composer').addEventListener('submit', send);
$('newchat').addEventListener('click', resetChat);
init();
