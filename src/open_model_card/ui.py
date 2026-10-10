"""Open-Model-Card v1.0 — single-page control panel.

The page is one screen with three regions:

  SYSTEM    — machine + detected engines, refresh on entry
  WHAT TO DO — mode picker (single default, multi-model advanced), model
              picker with engine context, resource check, Go button
  RESULTS   — live progress, cards stacked, copy buttons per card
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from open_model_card import bundle as bundle_mod
from open_model_card.brief import read_operator_notes
from open_model_card.client import EndpointError
from open_model_card.compare import (
    comparison_markdown,
    filter_same_machine,
    load_reports,
    plain_choice,
    recommend,
)
from open_model_card.discovery import scan_engines, scan_installed_apps
from open_model_card.predict import fits, predict
from open_model_card.report import plain_summary, to_markdown
from open_model_card.resource import collect as collect_resources
from open_model_card.retention import enforce as retention_enforce


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open Model Card</title>
<style>
  :root { color-scheme: dark; --bg: #10140f; --fg: #d7f5c8; --accent: #9dff8a; --warn: #e6c15a; --err: #ef4444; --border: #3d8f4a; --card: #0c120d; --muted: #b7d7ae; }
  body { margin: 0; min-height: 100vh; background: var(--bg); color: var(--fg); font: 16px/1.45 "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace; }
  main { max-width: 56rem; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
  header { display: flex; justify-content: space-between; gap: 1rem; align-items: center; border-bottom: 2px solid var(--border); padding-bottom: 0.8rem; }
  h1 { font-size: 1.4rem; letter-spacing: 0.08em; margin: 0; color: var(--accent); }
  h2 { font-size: 1.05rem; color: var(--warn); margin: 1.2rem 0 0.6rem; letter-spacing: 0.06em; }
  .step { color: var(--warn); font-size: 0.78rem; letter-spacing: 0.12em; }
  p.help { color: var(--muted); margin: 0 0 0.7rem; font-size: 0.9rem; }
  .panel { border: 1px solid var(--border); margin-top: 0.8rem; padding: 1rem 1.1rem; background: var(--card); border-radius: 4px; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 0.5rem; vertical-align: middle; background: #555; }
  .dot.green { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
  .dot.red { background: var(--err); }
  .dot.yellow { background: var(--warn); animation: pulse 1s steps(2) infinite; }
  @keyframes pulse { 50% { opacity: 0.3; } }
  .lamp { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 0.4rem; vertical-align: middle; }
  .lamp.green { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
  .lamp.yellow { background: var(--warn); box-shadow: 0 0 4px var(--warn); animation: pulse 1s steps(2) infinite; }
  .lamp.red { background: var(--err); box-shadow: 0 0 4px var(--err); }
  .row { display: flex; gap: 0.6rem; margin: 0.4rem 0; flex-wrap: wrap; align-items: center; }
  label { display: block; margin: 0.6rem 0 0.25rem; font-size: 0.85rem; }
  label.inline { display: flex; align-items: center; gap: 0.4rem; margin: 0; }
  label .lbl { display: block; font-size: 0.75rem; color: var(--muted); margin: 0.4rem 0 0.15rem; letter-spacing: 0.05em; text-transform: uppercase; }
  input, select { width: 100%; box-sizing: border-box; padding: 0.5rem; background: #071008; color: var(--fg); border: 1px solid var(--border); font: inherit; border-radius: 3px; }
  input[type=checkbox] { width: auto; margin-right: 0.4rem; }
  input[type=radio] { width: auto; margin-right: 0.3rem; }
  button { appearance: none; -webkit-appearance: none; background: var(--warn); color: #14180c; border: 2px solid var(--warn); padding: 0.55rem 0.9rem; cursor: pointer; font: inherit; font-weight: 700; border-radius: 3px; }
  button:hover, button:focus { background: #fff1b8; color: #14180c; outline: 2px solid var(--accent); }
  button.primary { background: var(--accent); border-color: var(--accent); }
  button.ghost { background: transparent; color: var(--accent); border-color: var(--accent); }
  button[disabled] { opacity: 0.4; cursor: not-allowed; }
  pre { white-space: pre-wrap; min-height: 6rem; margin: 0; background: #070d08; color: var(--fg); padding: 1rem; border: 1px solid var(--border); border-radius: 3px; font: inherit; font-size: 0.85rem; }
  .ok { color: var(--accent); }
  .warn-text { color: var(--warn); }
  .err-text { color: var(--err); }
  .small { font-size: 0.82rem; color: var(--muted); }
  .step-list { list-style: none; padding-left: 0; margin: 0.4rem 0; }
  .step-list li { padding: 0.2rem 0; }
  .engine-row { padding: 0.2rem 0; }
  .res-bar { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  .res-bar .pill { background: #071008; border: 1px solid var(--border); padding: 0.2rem 0.5rem; border-radius: 3px; font-size: 0.85rem; }
  .res-bar .pill.warn { border-color: var(--warn); color: var(--warn); }
  .res-bar .pill.err { border-color: var(--err); color: var(--err); }
  .res-bar .pill.ok { border-color: var(--accent); color: var(--accent); }
  .card { background: #0a0f0b; border: 1px solid var(--border); border-radius: 4px; padding: 0.9rem 1rem; margin: 0.7rem 0; }
  .card .head { display: flex; justify-content: space-between; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
  .card .head strong { color: var(--accent); }
  .hidden { display: none !important; }
  .modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; z-index: 100; }
  .modal { background: var(--card); border: 1px solid var(--warn); padding: 1.2rem; border-radius: 6px; max-width: 32rem; }
  .modal h3 { margin: 0 0 0.6rem; color: var(--warn); }
  .modal .actions { display: flex; gap: 0.5rem; margin-top: 0.8rem; justify-content: flex-end; flex-wrap: wrap; }
  .resume { background: #14201a; border: 1px solid var(--warn); padding: 0.7rem 1rem; border-radius: 4px; margin: 0.8rem 0; display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
</style>
</head>
<body>
<main>
  <header>
    <h1>OPEN MODEL CARD</h1>
    <span><span class="lamp" id="topLamp"></span> <span id="topStatus">Idle</span></span>
  </header>

  <div id="resume" class="resume hidden">
    <span><span class="lamp yellow"></span> <strong id="resumeText">Run in progress…</strong></span>
    <span class="row">
      <button id="resumeWatch" class="primary">Watch live</button>
      <button id="resumeDiscard" class="ghost">Discard</button>
    </span>
  </div>

  <section class="panel" id="systemPanel">
    <div class="step">SYSTEM</div>
    <h2>What is on this machine</h2>
    <p class="help" id="machineSummary">Detecting…</p>
    <div class="res-bar" id="resBar"></div>
    <p class="help" style="margin-top:0.7rem;">Engines detected</p>
    <div id="engineList"><span class="small">Probing ports…</span></div>
    <p class="small" id="installedApps"></p>
    <div class="row" style="margin-top: 0.6rem;">
      <button class="ghost" id="refreshBtn">Refresh detection</button>
      <button class="ghost" id="addEngineBtn">Add custom engine</button>
    </div>
  </section>

  <section class="panel" id="actionPanel">
    <div class="step">WHAT TO DO</div>
    <h2>Pick a model and run</h2>
    <p class="help">Default is one model. Multi-model is opt-in and takes longer.</p>

    <div class="row" style="margin-top: 0.4rem;">
      <label class="inline" style="background: #071008; padding: 0.3rem 0.6rem; border-radius: 3px; border: 1px solid var(--border);">
        <input type="radio" name="mode" value="single" checked> <strong>Test one model</strong>
      </label>
      <label class="inline" style="background: #071008; padding: 0.3rem 0.6rem; border-radius: 3px; border: 1px solid var(--border);">
        <input type="radio" name="mode" value="multi"> <strong>Test all detected models</strong>
        <span class="small" id="multiEstimate"></span>
      </label>
    </div>

    <label class="lbl" for="modelPick">Model</label>
    <select id="modelPick"><option value="">No models detected yet</option></select>
    <p class="small" id="modelMeta">Pick an engine in SYSTEM and refresh.</p>
    <p class="small" id="fitsLine"></p>

    <label class="inline" style="margin-top: 0.7rem;">
      <input type="checkbox" id="thinkingBox"> This model prints a reasoning trace before each final answer (thinking model).
    </label>

    <div class="row" style="margin-top: 0.8rem;">
      <button class="primary" id="goBtn" disabled>Pick a model first</button>
      <button class="ghost" id="compareBtn">Compare saved cards</button>
    </div>
  </section>

  <section class="panel" id="resultsPanel">
    <div class="step">RESULTS</div>
    <h2>Progress and cards</h2>
    <p id="status"><span class="lamp" id="lamp"></span> <span id="statusText">Idle. Start with step 1.</span></p>
    <ul class="step-list" id="stepList"></ul>
    <div id="cardArea"></div>
    <pre id="out" class="hidden">The plain summary will appear here. The technical record follows it.</pre>
  </section>

  <p class="small" style="margin-top: 1.5rem; text-align: center;">
    Schema v1.0 · Local-only on this Mac · <a href="javascript:void(0)" id="settingsBtn" style="color: var(--accent);">Settings</a>
  </p>
</main>

<div id="modalBg" class="modal-bg hidden">
  <div class="modal" id="modalInner"></div>
</div>

<script>
const $ = (id) => document.getElementById(id);
const out = $("out");

function plain(err) {
  const msg = String((err && err.message) || err || "");
  if (msg.indexOf("401") >= 0 || msg.indexOf("API Key") >= 0) {
    return "That server wants a password. Click 'Add custom engine' to provide one.";
  }
  if (msg.indexOf("could not reach") >= 0) {
    return "That server is not running. Start it, then press Refresh detection.";
  }
  return msg;
}

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function getJson(path) {
  const res = await fetch(path);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

let systemState = null;
let selectedEngine = null;
let selectedModel = null;

async function refreshSystem() {
  $("engineList").innerHTML = '<span class="small">Probing ports…</span>';
  try {
    const data = await getJson("/api/state");
    systemState = data;
    renderSystem(data);
    renderModelPicker(data);
  } catch (err) {
    $("engineList").innerHTML = '<span class="err-text">Detection failed: ' + plain(err) + '</span>';
  }
}

function renderSystem(data) {
  const m = data.machine || {};
  $("machineSummary").textContent = (m.os || "unknown") + " · " + (m.total_ram_mb ? Math.round(m.total_ram_mb / 1024) + " GB RAM" : "RAM unknown");
  const pressure = m.pressure || "unknown";
  const freeGB = m.free_ram_mb ? (m.free_ram_mb / 1024).toFixed(1) : "?";
  const presPill = pressure === "normal" ? "ok" : (pressure === "warn" ? "warn" : (pressure === "critical" ? "err" : ""));
  const freePill = (m.free_ram_mb && m.free_ram_mb < 8192) ? "warn" : "ok";
  $("resBar").innerHTML = [
    '<span class="pill ' + presPill + '">memory pressure: ' + pressure + '</span>',
    '<span class="pill ' + freePill + '">free: ' + freeGB + ' GB</span>',
    '<span class="pill">' + (m.swap_used_mb != null ? ('swap: ' + Math.round(m.swap_used_mb) + ' MB') : 'swap: n/a') + '</span>',
  ].join("");
  const engines = data.engines || [];
  if (!engines.length) {
    $("engineList").innerHTML = '<span class="err-text">No engines detected.</span>';
  } else {
    $("engineList").innerHTML = engines.map(e => {
      const dot = e.reachable ? (e.needs_auth ? "yellow" : "green") : "red";
      const state = e.reachable ? (e.needs_auth ? "needs key" : "idle") : "not reachable";
      return '<div class="engine-row"><span class="dot ' + dot + '"></span><strong>' + e.name + '</strong> (' + e.url + ') — ' + state + (e.version ? ' · v' + e.version : '') + '</div>';
    }).join("");
  }
  let totalModels = 0;
  for (const e of engines) if (e.reachable && !e.needs_auth) totalModels += e.models.length;
  $("multiEstimate").textContent = totalModels > 1 ? "(~" + (totalModels * 5) + " min, " + totalModels + " models)" : "(no models available)";
  const apps = data.installed_apps || [];
  if (apps.length) {
    $("installedApps").innerHTML = 'Installed: ' + apps.map(a => '<span class="pill">' + a.name + (a.version ? ' v' + a.version : '') + ' (' + a.kind + ')</span>').join(" ");
  } else {
    $("installedApps").innerHTML = '';
  }
}

function renderModelPicker(data) {
  const sel = $("modelPick");
  sel.innerHTML = "";
  let count = 0;
  for (const e of data.engines || []) {
    if (!e.reachable || e.needs_auth) continue;
    for (const m of e.models || []) {
      const opt = document.createElement("option");
      opt.value = JSON.stringify({family: e.family, url: e.url, name: e.name, model: m});
      opt.textContent = m.id + " on " + e.name;
      sel.appendChild(opt);
      count++;
    }
  }
  if (count === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No models — start an engine and refresh";
    sel.appendChild(opt);
  } else {
    // Auto-select the first model so the user doesn't have to click to
    // populate the resource check. (Page would otherwise show
    // "Pick an engine in SYSTEM and refresh" until the user picks one.)
    sel.selectedIndex = 0;
  }
  sel.onchange = onModelPicked;
  onModelPicked();
}

async function onModelPicked() {
  const v = $("modelPick").value;
  if (!v) {
    selectedEngine = null;
    selectedModel = null;
    $("modelMeta").textContent = "Pick an engine in SYSTEM and refresh.";
    $("fitsLine").textContent = "";
    $("goBtn").disabled = true;
    $("goBtn").textContent = "Pick a model first";
    return;
  }
  const obj = JSON.parse(v);
  selectedEngine = {family: obj.family, name: obj.name, url: obj.url};
  selectedModel = {id: obj.model.id, size_bytes: obj.model.size_bytes, state: obj.model.state};
  $("modelMeta").textContent = "Engine: " + obj.name + " · " + obj.url;
  try {
    const data = await post("/api/predict", {url: obj.url, family: obj.family, model_id: obj.model.id});
    if (data.fits && data.fits.ok) {
      const v = data.fits;
      const verdict = v.reason === "ok" ? "Fits with headroom." : "Fits, but tight. Close other apps first?";
      $("fitsLine").innerHTML = '<span class="ok">Will use: ~' + v.predicted_mb + ' MB · ' + verdict + '</span>';
      $("goBtn").disabled = false;
      $("goBtn").textContent = "Go";
      $("goBtn").dataset.override = "";
    } else {
      const reason = (data.fits && data.fits.reason) || "unknown";
      $("fitsLine").innerHTML = '<span class="err-text">Will not fit: ' + reason + '. Close other apps and refresh, or click Go anyway to override.</span>';
      $("goBtn").disabled = false;
      $("goBtn").textContent = "Go anyway";
      $("goBtn").dataset.override = "1";
    }
  } catch (err) {
    $("fitsLine").textContent = "Could not predict size: " + plain(err);
    $("goBtn").disabled = false;
    $("goBtn").textContent = "Go anyway";
    $("goBtn").dataset.override = "1";
  }
}

$("refreshBtn").onclick = refreshSystem;
$("addEngineBtn").onclick = () => showAddEngineModal();
$("goBtn").onclick = () => runTests();
$("compareBtn").onclick = () => compareCards();
$("settingsBtn").onclick = () => alert("Settings UI is not implemented in this build. Edit reports/operator.md for now.");

function showModal(html) {
  $("modalInner").innerHTML = html;
  $("modalBg").classList.remove("hidden");
}
function hideModal() { $("modalBg").classList.add("hidden"); }

function showAddEngineModal() {
  showModal(`
    <h3>Add custom engine</h3>
    <p class="small">Use this for engines on non-default ports or future engines.</p>
    <label class="lbl" for="addUrl">Base URL (with /v1)</label>
    <input id="addUrl" placeholder="http://127.0.0.1:9999/v1">
    <label class="lbl" for="addFamily">Engine family</label>
    <select id="addFamily">
      <option value="llamacpp">llama.cpp</option>
      <option value="ollama">Ollama</option>
      <option value="omlx">oMLX</option>
      <option value="lmstudio">LM Studio</option>
    </select>
    <label class="lbl" for="addKey">API key (optional)</label>
    <input id="addKey" type="password" placeholder="leave empty for Ollama, etc.">
    <div class="actions">
      <button class="ghost" id="addCancel">Cancel</button>
      <button class="primary" id="addSave">Add and probe</button>
    </div>
  `);
  $("addCancel").onclick = hideModal;
  $("addSave").onclick = async () => {
    const url = $("addUrl").value;
    const family = $("addFamily").value;
    const key = $("addKey").value;
    try {
      await post("/api/engines/add", {url, family, api_key: key});
      hideModal();
      await refreshSystem();
    } catch (err) {
      alert("Could not add engine: " + plain(err));
    }
  };
}

async function runTests() {
  if (!selectedEngine || !selectedModel) return;
  let unloadFirst = false;
  try {
    const loaded = await post("/api/loaded", {family: selectedEngine.family, url: selectedEngine.url, model: selectedModel.id});
    if (loaded.loaded && loaded.loaded !== selectedModel.id) {
      const ok = await confirmUnload(loaded.loaded, selectedEngine.name, false);
      if (!ok) return;
      unloadFirst = true;
    }
  } catch (e) { /* ignore */ }

  const mode = document.querySelector('input[name=mode]:checked').value;
  const thinking = $("thinkingBox").checked;
  $("stepList").innerHTML = "";
  $("cardArea").innerHTML = "";
  out.textContent = "";
  $("out").classList.add("hidden");
  $("topLamp").className = "lamp yellow";
  $("topStatus").textContent = "Running…";
  $("lamp").className = "lamp yellow";
  $("statusText").textContent = "Starting.";
  try {
    await post("/api/run", {
      mode: mode,
      engine: selectedEngine,
      model: selectedModel,
      thinking_aware: thinking,
      unload_first: unloadFirst,
    });
    await pollStatus();
  } catch (err) {
    showError(plain(err));
  }
}

function confirmUnload(otherModel, engineName, weStarted) {
  return new Promise((resolve) => {
    showModal(`
      <h3>Another model is loaded</h3>
      <p><code>${otherModel}</code> is loaded on ${engineName}.</p>
      <p>Unload it and continue?</p>
      <p class="small">Default: <strong>${weStarted ? "Yes (we started it)" : "No (we did not start it)"}</strong></p>
      <div class="actions">
        <button class="ghost" id="unloadNo">No, keep it loaded</button>
        <button class="primary" id="unloadYes">Yes, unload and continue</button>
      </div>
    `);
    $("unloadNo").onclick = () => { hideModal(); resolve(false); };
    $("unloadYes").onclick = () => { hideModal(); resolve(true); };
  });
}

async function pollStatus() {
  while (true) {
    const status = await fetch("/api/status").then(r => r.json());
    renderStatus(status);
    if (status.state === "done") { onRunDone(status); return; }
    if (status.state === "error") { showError(status.error || "unknown error"); return; }
    await new Promise(r => setTimeout(r, 1000));
  }
}

function renderStatus(s) {
  const elapsed = s.elapsed_s == null ? "" : " (" + s.elapsed_s + "s)";
  $("statusText").textContent = (s.step || "Working") + elapsed;
  $("topStatus").textContent = (s.step || "Working") + elapsed;
  if (s.steps) {
    $("stepList").innerHTML = s.steps.map(st => {
      const icon = st.done ? '<span class="ok">✓</span>' : (st.active ? '<span class="lamp yellow"></span>' : '<span class="pending">·</span>');
      return '<li>' + icon + ' ' + st.text + (st.elapsed ? ' (' + st.elapsed + 's)' : '') + '</li>';
    }).join("");
  }
}

function onRunDone(status) {
  $("topLamp").className = "lamp green";
  $("topStatus").textContent = "Finished.";
  $("lamp").className = "lamp green";
  $("statusText").textContent = "Finished.";
  out.textContent = status.plain + "\\n\\n--- Technical record ---\\n\\n" + status.markdown;
  $("out").classList.remove("hidden");
  if (status.card) appendCard(status.card);
}

function showError(msg) {
  $("topLamp").className = "lamp red";
  $("topStatus").textContent = "Stopped.";
  $("lamp").className = "lamp red";
  $("statusText").textContent = "Stopped.";
  out.textContent = msg;
  $("out").classList.remove("hidden");
}

function appendCard(card) {
  const div = document.createElement("div");
  div.className = "card";
  const machine = card.machine || {};
  const engine = card.engine || {};
  const model = card.model || {};
  const tasks = card.tasks || [];
  const passed = tasks.filter(t => t.pass).length;
  const speed = card.speed || {};
  const memory = card.memory || {};
  div.innerHTML = `
    <div class="head">
      <strong>${escapeHtml(model.id || "?")}</strong> on ${escapeHtml(engine.name || "?")} <span class="small">${escapeHtml(engine.url || "")}</span>
      <span class="small">${passed} of ${tasks.length} passed · ${escapeHtml(machine.os || "")}</span>
    </div>
    <div class="small">
      Speed: ${speed.ttft_s != null ? speed.ttft_s + "s ttft" : "n/a"} ·
      ${speed.tok_per_s != null ? speed.tok_per_s + " tok/s" : "n/a"} ·
      ${memory.rss_mb != null ? memory.rss_mb + " MB resident" : "memory n/a"}
    </div>
    <div class="small">Created: ${escapeHtml(card.created || "")} · Schema v${escapeHtml(card.schema_version || "?")}</div>
    <div class="row" style="margin-top: 0.5rem;">
      <button class="ghost" data-copy="agent">Copy for my agent</button>
      <button class="ghost" data-copy="chat">Copy for a chatbot</button>
      <button class="ghost" data-copy="clean">Copy clean</button>
      <button class="ghost" data-redo>Run again</button>
    </div>
    <pre class="small" style="margin-top: 0.5rem;">${(card.tasks || []).map(t => (t.pass ? "[pass] " : "[fail] ") + escapeHtml(t.id) + " (" + escapeHtml(t.area) + "): " + escapeHtml(t.detail)).join("\\n")}</pre>
  `;
  div.querySelector("[data-copy='agent']").onclick = () => copyBrief("agent", card);
  div.querySelector("[data-copy='chat']").onclick = () => copyBrief("chat", card);
  div.querySelector("[data-copy='clean']").onclick = () => copyBrief("clean", card);
  div.querySelector("[data-redo]").onclick = () => { if (selectedEngine && selectedModel) runTests(); };
  $("cardArea").prepend(div);
}

async function copyBrief(format, card) {
  try {
    const data = await post("/api/copy/" + format, {card: card});
    await navigator.clipboard.writeText(data.text);
  } catch (err) {
    alert("Could not copy: " + plain(err));
  }
}

async function compareCards() {
  try {
    const data = await post("/api/compare", {machine_scope: "same"});
    showModal(`
      <h3>Compare saved cards</h3>
      <pre style="font-size: 0.78rem; max-height: 22rem; overflow: auto;">${escapeHtml(data.table || "")}</pre>
      <p class="small">${escapeHtml(data.plain || "")}</p>
      <p class="small">Bundle: ${data.bundle_written ? "written" : "not written"} (${data.card_count || 0} cards)</p>
      <div class="actions">
        <button class="ghost" id="cmpClose">Close</button>
        <button class="primary" id="cmpCopy">Copy recommendation</button>
      </div>
    `);
    $("cmpClose").onclick = hideModal;
    $("cmpCopy").onclick = async () => {
      try {
        const d = await post("/api/copy/agent", {card: null});
        await navigator.clipboard.writeText(d.text);
      } catch (err) { alert("Copy failed: " + plain(err)); }
    };
  } catch (err) {
    alert("Could not compare: " + plain(err));
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function checkResume() {
  try {
    const data = await getJson("/api/status");
    if (data.state === "running") {
      $("resumeText").textContent = `Run in progress: ${(data.target || {}).model || "model"} on ${(data.target || {}).engine || "engine"} — ${data.elapsed_s || 0}s`;
      $("resume").classList.remove("hidden");
    } else {
      // State is idle / done / error — hide the banner.
      $("resume").classList.add("hidden");
    }
  } catch (e) { /* ignore */ }
}

// Poll status every 3 seconds. Hides the resume banner automatically
// when the run ends. Also keeps the top lamp in sync with the server.
setInterval(() => {
  getJson("/api/status").then(data => {
    if (data.state === "running") {
      $("topLamp").className = "lamp yellow";
      $("topStatus").textContent = (data.step || "Running") + (data.elapsed_s != null ? " (" + data.elapsed_s + "s)" : "");
      const t = $("resume");
      if (t.classList.contains("hidden")) {
        $("resumeText").textContent = `Run in progress: ${(data.target || {}).model || "model"} on ${(data.target || {}).engine || "engine"} — ${data.elapsed_s || 0}s`;
        t.classList.remove("hidden");
      }
    } else if (data.state === "done" || data.state === "error") {
      $("resume").classList.add("hidden");
      if (data.state === "done") {
        $("topLamp").className = "lamp green";
        $("topStatus").textContent = "Finished.";
      } else {
        $("topLamp").className = "lamp red";
        $("topStatus").textContent = "Stopped.";
      }
    } else {
      $("resume").classList.add("hidden");
      $("topLamp").className = "lamp";
      $("topStatus").textContent = "Idle";
    }
  }).catch(() => {});
}, 3000);

$("resumeWatch").onclick = () => { $("resume").classList.add("hidden"); pollStatus(); };
$("resumeDiscard").onclick = async () => {
  await post("/api/discard", {});
  $("resume").classList.add("hidden");
  $("topStatus").textContent = "Idle";
};

refreshSystem();
checkResume();
</script>
</body>
</html>
"""


JOB = {"id": None, "state": "idle", "step": "Idle", "started": 0.0, "error": "", "plain": "", "markdown": "", "steps": [], "target": None, "card": None}
JOB_LOCK = threading.RLock()


def _status_dict() -> dict:
    with JOB_LOCK:
        elapsed = None
        if JOB["state"] == "running" and JOB["started"]:
            elapsed = round(time.time() - JOB["started"], 1)
        return {
            "id": JOB["id"],
            "state": JOB["state"],
            "step": JOB["step"],
            "started": JOB["started"],
            "elapsed_s": elapsed,
            "error": JOB["error"],
            "target": JOB["target"],
            "steps": list(JOB["steps"]),
        }


def _job_step(text: str, done: bool = False, active: bool = False) -> None:
    with JOB_LOCK:
        if active:
            for s in JOB["steps"]:
                if s.get("active"):
                    s["active"] = False
                    s["done"] = True
        JOB["steps"].append({"text": text, "done": done, "active": active, "elapsed": None})


def _start_run(data: dict, out_dir: Path) -> str:
    job_id = time.strftime("%Y%m%dT%H%M%S")
    with JOB_LOCK:
        JOB.update(id=job_id, state="running", step="Starting", started=time.time(), error="", plain="", markdown="", steps=[], target=data.get("target"), card=None, thread=None)
    _job_step("Starting test run", active=True)
    thread = threading.Thread(target=_run_worker, args=(data, out_dir, job_id), daemon=True)
    with JOB_LOCK:
        JOB["thread"] = thread
    thread.start()
    return job_id


def _run_worker(data: dict, out_dir: Path, job_id: str) -> None:
    from open_model_card.cli import run_card
    engine = data.get("engine") or {}
    model = data.get("model") or {}
    target = {"engine": engine.get("name", "?"), "model": model.get("id", "?")}
    with JOB_LOCK:
        JOB["target"] = target
    try:
        if data.get("unload_first"):
            from open_model_card.guard import find_loaded_model
            from open_model_card.engines import REGISTRY
            adapter = REGISTRY.get(engine.get("family"))
            if adapter:
                _job_step("Unloading previously loaded model", active=True)
                other = find_loaded_model(engine.get("family"), engine.get("url"), data.get("api_key", ""))
                if other:
                    u = adapter.unload(engine.get("url"), other, data.get("api_key", ""), 30)
                    _job_step(f"Unload {other}: {'ok' if u.unloaded else u.detail}", done=True)
        api_key = data.get("api_key", "")
        if engine.get("family") == "llamacpp" and not api_key:
            from open_model_card.engines.llamacpp import _hermes_key
            api_key = _hermes_key() or ""
        report = run_card(
            engine.get("url"),
            model.get("id"),
            api_key,
            180,
            out_dir,
            False,
            False,
            progress=lambda msg: _job_step(msg, active=True),
            thinking_aware=bool(data.get("thinking_aware")),
            engine_family=engine.get("family"),
        )
        _job_step("Writing report", active=True)
        moved = retention_enforce(out_dir, keep=int(data.get("retention_keep", 10)))
        _job_step(f"Retention: moved {moved} older files", done=True)
        with JOB_LOCK:
            JOB["plain"] = plain_summary(report)
            JOB["markdown"] = to_markdown(report)
            JOB["card"] = report
            JOB["step"] = "Finished"
            JOB["state"] = "done"
    except Exception as exc:
        with JOB_LOCK:
            JOB["error"] = str(exc)
            JOB["step"] = "Stopped"
            JOB["state"] = "error"


def _state_snapshot() -> dict:
    machine = collect_resources()
    engines = [e.to_dict() for e in scan_engines()]
    apps = scan_installed_apps()
    return {
        "machine": {
            "os": machine.platform,
            "arch": None,
            "total_ram_mb": machine.total_ram_mb,
            "free_ram_mb": machine.free_ram_mb,
            "pressure": machine.pressure,
            "swap_used_mb": machine.swap_used_mb,
            "available": machine.available,
            "reason": machine.reason,
        },
        "engines": engines,
        "installed_apps": apps,
    }


class Handler(BaseHTTPRequestHandler):
    out_dir = Path("reports")

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _read(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            self._json(200, _state_snapshot())
            return
        if path == "/api/status":
            with JOB_LOCK:
                # If state is "running" but the worker thread is no longer
                # alive, the run was interrupted. Mark it errored so the
                # UI can clear the resume banner.
                if JOB["state"] == "running" and JOB.get("thread") and not JOB["thread"].is_alive():
                    JOB["state"] = "error"
                    JOB["error"] = JOB.get("error") or "run was interrupted"
                    JOB["step"] = "Stopped"
                d = _status_dict()
                if JOB.get("state") == "done":
                    d["plain"] = JOB["plain"]
                    d["markdown"] = JOB["markdown"]
                    d["card"] = JOB["card"]
            self._json(200, d)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self._read()
            if path == "/api/state":
                # Some clients POST; serve the same payload as GET.
                self._json(200, _state_snapshot())
                return
            if path == "/api/engines/add":
                self._json(200, {"ok": True, "url": data.get("url")})
                return
            if path == "/api/predict":
                pred = predict(data.get("model_id", ""), data.get("family", "llamacpp"), data.get("url", ""), data.get("api_key", ""))
                free = _state_snapshot()["machine"].get("free_ram_mb")
                f = fits(pred.bytes_predicted, free)
                self._json(200, {"prediction": {"bytes": pred.bytes_predicted, "source": pred.source, "detail": pred.detail}, "fits": f})
                return
            if path == "/api/loaded":
                from open_model_card.guard import find_loaded_model
                m = find_loaded_model(data.get("family", "llamacpp"), data.get("url", ""), data.get("api_key", ""))
                self._json(200, {"loaded": m})
                return
            if path == "/api/run":
                target = {"engine": (data.get("engine") or {}).get("name"), "model": (data.get("model") or {}).get("id")}
                job_data = {
                    "engine": data.get("engine"),
                    "model": data.get("model"),
                    "thinking_aware": data.get("thinking_aware", False),
                    "api_key": data.get("api_key", ""),
                    "unload_first": data.get("unload_first", False),
                    "retention_keep": data.get("retention_keep", 10),
                    "target": target,
                }
                job_id = _start_run(job_data, self.out_dir)
                self._json(200, {"job_id": job_id, "started": True})
                return
            if path == "/api/discard":
                with JOB_LOCK:
                    JOB.update(state="idle", step="Idle", error="", plain="", markdown="", steps=[], target=None, card=None, id=None)
                self._json(200, {"ok": True})
                return
            if path == "/api/compare":
                cards = load_reports(self.out_dir)
                if not cards:
                    self._json(400, {"error": "No saved cards yet. Run a test first."})
                    return
                scope = data.get("machine_scope", "same")
                if scope == "same":
                    cards = filter_same_machine(cards)
                advice = recommend(cards)
                table = comparison_markdown(cards, advice)
                notes_path = self.out_dir / "operator.md"
                notes, filled = read_operator_notes(notes_path if notes_path.is_file() else None)
                bundle_mod.write_bundle(cards, self.out_dir, notes, filled)
                self._json(200, {
                    "plain": plain_choice(advice),
                    "table": table,
                    "recommendation": advice,
                    "card_count": len(cards),
                    "bundle_written": True,
                })
                return
            if path.startswith("/api/copy/"):
                fmt = path.removeprefix("/api/copy/")
                card = data.get("card")
                if not card:
                    cards = load_reports(self.out_dir)
                    card = cards[0] if cards else {}
                if not card:
                    self._json(400, {"error": "no card to copy"})
                    return
                notes_path = self.out_dir / "operator.md"
                notes, filled = read_operator_notes(notes_path if notes_path.is_file() else None)
                bundle = {"card_count": 1, "machines": ["unknown"], "operator_notes_filled": filled, "operator_notes": notes, "cards": [card], "recommendation": {}}
                if fmt == "agent":
                    bundle_mod.write_short(bundle, self.out_dir)
                    text = (Path(self.out_dir) / "bundle.short.md").read_text()
                elif fmt == "chat":
                    bundle_mod.write_chat_brief(bundle, self.out_dir, strip_pii_flag=False)
                    text = (Path(self.out_dir) / "chat-brief.md").read_text()
                elif fmt == "clean":
                    bundle_mod.write_chat_brief(bundle, self.out_dir, strip_pii_flag=True)
                    text = (Path(self.out_dir) / "chat-brief.md").read_text()
                else:
                    self._json(400, {"error": f"unknown copy format: {fmt}"})
                    return
                self._json(200, {"text": text, "format": fmt})
                return
            self._json(404, {"error": "not found"})
        except EndpointError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": str(exc)})


def serve(out_dir: Path, port: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    Handler.out_dir = out_dir
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Open http://127.0.0.1:{port}")
    print("This panel is only on this machine. Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        server.server_close()
