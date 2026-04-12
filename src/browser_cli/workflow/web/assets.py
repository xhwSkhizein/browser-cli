"""Static HTML assets for the local workflow UI."""

from __future__ import annotations


def render_index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Browser CLI Workflows</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --line: #d6cdc0;
      --text: #1e1d1a;
      --muted: #6e675d;
      --accent: #0f766e;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--text);
      background:
        radial-gradient(circle at top right, rgba(15,118,110,0.08), transparent 28%),
        linear-gradient(180deg, #f7f2e8, var(--bg));
    }
    header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(255,255,255,0.75);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    header h1 { margin: 0 0 8px; font-size: 28px; }
    header p { margin: 0; color: var(--muted); }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(320px, 1fr) minmax(280px, 360px);
      gap: 16px;
      padding: 16px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      min-height: 320px;
      box-shadow: 0 12px 32px rgba(30,29,26,0.06);
    }
    h2 { margin-top: 0; font-size: 20px; }
    .workflow-item {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 10px;
      cursor: pointer;
      background: #fff;
    }
    .workflow-item.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .row { display: grid; gap: 8px; margin-bottom: 12px; }
    label { font-size: 13px; color: var(--muted); display: grid; gap: 6px; }
    input, textarea, select, button {
      font: inherit;
      border-radius: 10px;
      border: 1px solid var(--line);
      padding: 10px 12px;
      background: #fff;
      color: var(--text);
    }
    textarea { min-height: 92px; resize: vertical; }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    button.secondary {
      background: #fff;
      color: var(--text);
      border-color: var(--line);
    }
    button.danger {
      background: var(--danger);
      border-color: var(--danger);
    }
    .button-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .status-line { color: var(--muted); font-size: 13px; margin-bottom: 12px; }
    .run-item {
      border-bottom: 1px solid var(--line);
      padding: 10px 0;
      cursor: pointer;
    }
    .run-item:last-child { border-bottom: 0; }
    .mono { font-family: "SFMono-Regular", "Menlo", monospace; font-size: 12px; white-space: pre-wrap; }
    .pill {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      background: rgba(15,118,110,0.12);
      color: var(--accent);
      font-size: 12px;
    }
    .error { color: var(--danger); }
    @media (max-width: 1100px) {
      main { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Browser CLI Workflows</h1>
    <p>Persistent local workflow service for published tasks.</p>
  </header>
  <main>
    <section>
      <h2>Workflows</h2>
      <div class="button-row">
        <button id="refresh-list" class="secondary">Refresh</button>
        <button id="new-workflow" class="secondary">New</button>
      </div>
      <div id="service-status" class="status-line"></div>
      <div id="workflow-list"></div>
    </section>
    <section>
      <h2>Workflow Detail</h2>
      <div class="button-row">
        <button id="save-workflow">Save</button>
        <button id="toggle-workflow" class="secondary">Enable/Disable</button>
        <button id="run-now" class="secondary">Run Now</button>
      </div>
      <div class="row">
        <label>ID<input id="wf-id"></label>
        <label>Name<input id="wf-name"></label>
        <label>Description<textarea id="wf-description"></textarea></label>
        <label>Task Path<input id="wf-task-path"></label>
        <label>Task Meta Path<input id="wf-task-meta-path"></label>
        <label>Entrypoint<input id="wf-entrypoint" value="run"></label>
        <label>Timezone<input id="wf-timezone" value="UTC"></label>
        <label>Schedule Mode
          <select id="wf-schedule-kind">
            <option value="manual">manual</option>
            <option value="interval">interval</option>
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
          </select>
        </label>
        <label>Schedule Payload JSON<textarea id="wf-schedule-payload">{}</textarea></label>
        <label>Input Overrides JSON<textarea id="wf-input-overrides">{}</textarea></label>
        <label>Output Directory<input id="wf-output-dir"></label>
        <label>Result JSON Path<input id="wf-result-json-path"></label>
        <label>Retry Attempts<input id="wf-retry-attempts" type="number" value="0"></label>
        <label>Retry Backoff Seconds<input id="wf-retry-backoff" type="number" value="0"></label>
        <label>Timeout Seconds<input id="wf-timeout-seconds" type="number" step="0.1"></label>
      </div>
      <div id="detail-status" class="status-line"></div>
    </section>
    <section>
      <h2>Runs</h2>
      <div id="run-list"></div>
      <h2>Run Detail</h2>
      <div class="button-row">
        <button id="retry-run" class="secondary">Retry Selected Run</button>
      </div>
      <div id="run-detail" class="mono"></div>
    </section>
  </main>
  <script>
    let workflows = [];
    let selectedWorkflowId = null;
    let selectedRunId = null;

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error_message || "Request failed");
      }
      return payload.data;
    }

    function parseJson(text, fallback) {
      if (!text.trim()) return fallback;
      return JSON.parse(text);
    }

    function workflowPayload() {
      return {
        id: document.getElementById("wf-id").value.trim(),
        name: document.getElementById("wf-name").value.trim(),
        description: document.getElementById("wf-description").value.trim(),
        task_path: document.getElementById("wf-task-path").value.trim(),
        task_meta_path: document.getElementById("wf-task-meta-path").value.trim(),
        entrypoint: document.getElementById("wf-entrypoint").value.trim() || "run",
        timezone: document.getElementById("wf-timezone").value.trim() || "UTC",
        schedule_kind: document.getElementById("wf-schedule-kind").value,
        schedule_payload: parseJson(document.getElementById("wf-schedule-payload").value, {}),
        input_overrides: parseJson(document.getElementById("wf-input-overrides").value, {}),
        output_dir: document.getElementById("wf-output-dir").value.trim(),
        result_json_path: document.getElementById("wf-result-json-path").value.trim(),
        retry_attempts: Number(document.getElementById("wf-retry-attempts").value || 0),
        retry_backoff_seconds: Number(document.getElementById("wf-retry-backoff").value || 0),
        timeout_seconds: document.getElementById("wf-timeout-seconds").value
          ? Number(document.getElementById("wf-timeout-seconds").value)
          : null,
      };
    }

    function fillWorkflow(workflow) {
      selectedWorkflowId = workflow ? workflow.id : null;
      document.getElementById("wf-id").value = workflow?.id || "";
      document.getElementById("wf-name").value = workflow?.name || "";
      document.getElementById("wf-description").value = workflow?.description || "";
      document.getElementById("wf-task-path").value = workflow?.task_path || "";
      document.getElementById("wf-task-meta-path").value = workflow?.task_meta_path || "";
      document.getElementById("wf-entrypoint").value = workflow?.entrypoint || "run";
      document.getElementById("wf-timezone").value = workflow?.timezone || "UTC";
      document.getElementById("wf-schedule-kind").value = workflow?.schedule_kind || "manual";
      document.getElementById("wf-schedule-payload").value = JSON.stringify(workflow?.schedule_payload || {}, null, 2);
      document.getElementById("wf-input-overrides").value = JSON.stringify(workflow?.input_overrides || {}, null, 2);
      document.getElementById("wf-output-dir").value = workflow?.output_dir || "";
      document.getElementById("wf-result-json-path").value = workflow?.result_json_path || "";
      document.getElementById("wf-retry-attempts").value = workflow?.retry_attempts ?? 0;
      document.getElementById("wf-retry-backoff").value = workflow?.retry_backoff_seconds ?? 0;
      document.getElementById("wf-timeout-seconds").value = workflow?.timeout_seconds ?? "";
      document.getElementById("detail-status").textContent = workflow
        ? `status=${workflow.definition_status} enabled=${workflow.enabled} next=${workflow.next_run_at || "manual"}`
        : "Create a new workflow or select an existing one.";
    }

    function renderWorkflowList() {
      const root = document.getElementById("workflow-list");
      root.innerHTML = "";
      workflows.forEach((workflow) => {
        const item = document.createElement("div");
        item.className = "workflow-item" + (workflow.id === selectedWorkflowId ? " active" : "");
        item.innerHTML = `
          <div><strong>${workflow.name || workflow.id}</strong></div>
          <div class="status-line">${workflow.id}</div>
          <div><span class="pill">${workflow.enabled ? "enabled" : "disabled"}</span> <span class="pill">${workflow.definition_status}</span></div>
          <div class="status-line">next: ${workflow.next_run_at || "manual"}</div>
          <div class="status-line">latest: ${workflow.latest_run?.status || "none"}</div>
        `;
        item.onclick = async () => {
          await selectWorkflow(workflow.id);
        };
        root.appendChild(item);
      });
    }

    function renderRunList(runs) {
      const root = document.getElementById("run-list");
      root.innerHTML = "";
      runs.forEach((run) => {
        const item = document.createElement("div");
        item.className = "run-item";
        item.innerHTML = `
          <div><strong>${run.status}</strong> <span class="pill">${run.trigger_type}</span></div>
          <div class="status-line">${run.run_id}</div>
          <div class="status-line">${run.queued_at || ""}</div>
          <div class="status-line ${run.error_message ? "error" : ""}">${run.error_message || ""}</div>
        `;
        item.onclick = async () => {
          selectedRunId = run.run_id;
          await refreshRunDetail();
        };
        root.appendChild(item);
      });
    }

    async function refreshStatus() {
      const status = await api("/api/service/status");
      document.getElementById("service-status").textContent =
        `service healthy=${status.service.healthy} workflows=${status.metrics.workflow_count} queued=${status.metrics.queued_runs} running=${status.metrics.running_runs}`;
    }

    async function refreshWorkflows() {
      workflows = await api("/api/workflows");
      renderWorkflowList();
      await refreshStatus();
      if (selectedWorkflowId) {
        await selectWorkflow(selectedWorkflowId);
      }
    }

    async function selectWorkflow(workflowId) {
      const workflow = await api(`/api/workflows/${workflowId}`);
      fillWorkflow(workflow);
      renderWorkflowList();
      renderRunList(await api(`/api/workflows/${workflowId}/runs`));
      selectedRunId = null;
      document.getElementById("run-detail").textContent = "";
    }

    async function refreshRunDetail() {
      if (!selectedRunId) return;
      const run = await api(`/api/runs/${selectedRunId}`);
      document.getElementById("run-detail").textContent = JSON.stringify(run, null, 2);
    }

    document.getElementById("refresh-list").onclick = refreshWorkflows;
    document.getElementById("new-workflow").onclick = () => fillWorkflow(null);
    document.getElementById("save-workflow").onclick = async () => {
      const payload = workflowPayload();
      const method = selectedWorkflowId ? "PUT" : "POST";
      const path = selectedWorkflowId ? `/api/workflows/${selectedWorkflowId}` : "/api/workflows";
      const workflow = await api(path, { method, body: JSON.stringify(payload) });
      fillWorkflow(workflow);
      await refreshWorkflows();
    };
    document.getElementById("toggle-workflow").onclick = async () => {
      if (!selectedWorkflowId) return;
      const workflow = await api(`/api/workflows/${selectedWorkflowId}`);
      const endpoint = workflow.enabled ? "disable" : "enable";
      await api(`/api/workflows/${selectedWorkflowId}/${endpoint}`, { method: "POST" });
      await refreshWorkflows();
    };
    document.getElementById("run-now").onclick = async () => {
      if (!selectedWorkflowId) return;
      await api(`/api/workflows/${selectedWorkflowId}/run`, { method: "POST" });
      await selectWorkflow(selectedWorkflowId);
    };
    document.getElementById("retry-run").onclick = async () => {
      if (!selectedRunId) return;
      await api(`/api/runs/${selectedRunId}/retry`, { method: "POST" });
      if (selectedWorkflowId) await selectWorkflow(selectedWorkflowId);
    };
    refreshWorkflows().catch((error) => {
      document.getElementById("service-status").textContent = error.message;
    });
  </script>
</body>
</html>"""
