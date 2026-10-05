"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

// Normalised point layout (horse facing left, bounding box 0..1) for manual placement
const TEMPLATE = {
  muzzle: [0.0, 0.207], poll: [0.207, 0.0], throatlatch: [0.19, 0.207], neck_base_low: [0.259, 0.373],
  withers: [0.512, 0.182], back_low: [0.621, 0.228], loin: [0.781, 0.184], croup_high: [0.848, 0.184],
  tail_base: [0.983, 0.249], scapula_top: [0.485, 0.231], shoulder_point: [0.3, 0.423], elbow: [0.397, 0.539],
  girth_low: [0.464, 0.578], front_knee: [0.431, 0.767], front_fetlock: [0.418, 0.922],
  front_coronet: [0.392, 0.968], front_toe: [0.371, 1.0], hip_point: [0.781, 0.281],
  buttock_point: [0.996, 0.362], stifle: [0.873, 0.481], hock: [1.0, 0.705], hind_fetlock: [1.0, 0.907],
  hind_coronet: [0.978, 0.968], hind_toe: [0.957, 1.0],
};

const STATUS_LABEL = { ideal: "Ihanteellinen", acceptable: "Hyväksyttävä", deviation: "Poikkeama" };

const $ = (id) => document.getElementById(id);
const state = {
  schema: null,     // {keypoints: [{id, label, group, hint}], skeleton: [[a, b]]}
  points: {},       // id -> {x, y, source}
  findings: [],
  activeFinding: null,
  selected: null,   // point id moved by arrow keys
  hover: null,      // point id under the cursor
  drag: null,       // {id, dx, dy} while dragging
  file: null,       // the uploaded File, sent along when saving to the dataset
  sampleId: null,   // dataset id once saved; later saves update it
  fileName: "",
  width: 0,
  height: 0,
};

init();

async function init() {
  initUserBar();
  state.schema = await apiJson("/api/schema");

  $("file").addEventListener("change", (e) => e.target.files[0] && loadFile(e.target.files[0]));
  const drop = $("drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
  });
  $("manual").addEventListener("click", placeTemplate);
  $("new").addEventListener("click", reset);
  $("horse-form").addEventListener("submit", saveSample);
  $("show-labels").addEventListener("change", render);

  // Pointer handling lives on the persistent <svg>: render() rebuilds the points,
  // so listeners or pointer capture on the circles would be lost mid-drag.
  const svg = $("overlay");
  svg.addEventListener("pointerdown", onPointerDown);
  svg.addEventListener("pointermove", onPointerMove);
  svg.addEventListener("pointerup", endDrag);
  svg.addEventListener("pointercancel", endDrag);
  svg.addEventListener("pointerleave", () => { if (!state.drag) setHover(null); });
  document.addEventListener("keydown", onKeyDown);
}

function setStatus(text, error = false) {
  $("status").textContent = text;
  $("status").classList.toggle("error", error);
}

async function loadFile(file) {
  state.file = file;
  state.fileName = file.name;
  $("manual").hidden = true;
  setStatus("Ladataan kuvaa…");

  const url = URL.createObjectURL(file);
  const img = $("photo");
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = url;
  }).catch(() => setStatus("Kuvaa ei voitu avata.", true));
  state.width = img.naturalWidth;
  state.height = img.naturalHeight;
  $("canvas").style.setProperty("--aspect", state.width / state.height);

  setStatus("Tunnistetaan hevosen rakennetta…");
  const body = new FormData();
  body.append("file", file);
  const res = await api("/api/detect", { method: "POST", body });
  if (!res.ok) {
    const msg = (await res.json().catch(() => ({}))).detail || "Tunnistus epäonnistui.";
    setStatus(`${msg} Voit asettaa pisteet käsin.`, true);
    $("manual").hidden = false;
    return;
  }
  const { keypoints } = await res.json();
  state.points = {};
  for (const [id, p] of Object.entries(keypoints)) state.points[id] = { x: p.x, y: p.y, source: p.source };
  showWorkspace();
}

function placeTemplate() {
  // Centre the template in the photo, horse facing left
  const w = state.width * 0.8, h = state.height * 0.8;
  const x0 = state.width * 0.1, y0 = state.height * 0.1;
  state.points = {};
  for (const [id, [nx, ny]] of Object.entries(TEMPLATE)) {
    state.points[id] = { x: x0 + nx * w, y: y0 + ny * h, source: "estimated" };
  }
  showWorkspace();
}

function showWorkspace() {
  setStatus("");
  $("upload").hidden = true;
  $("workspace").hidden = false;
  state.activeFinding = null;
  state.selected = state.hover = state.drag = null;
  state.sampleId = null;
  $("horse-form").reset();
  setSaveStatus("");
  $("save").textContent = "Tallenna aineistoon";
  const svg = $("overlay");
  svg.setAttribute("viewBox", `0 0 ${state.width} ${state.height}`);
  render();
  analyze();
}

function reset() {
  $("workspace").hidden = true;
  $("upload").hidden = false;
  $("file").value = "";
  state.points = {};
  state.findings = [];
}

// ---------------------------------------------------------------- overlay

function el(name, attrs, parent) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  parent?.appendChild(node);
  return node;
}

function render() {
  updateUncheckedNote();
  const svg = $("overlay");
  svg.replaceChildren();
  const unit = Math.max(state.width, state.height) / 200;
  const P = state.points;

  const bones = el("g", {}, svg);
  for (const [a, b] of state.schema.skeleton) {
    if (!P[a] || !P[b]) continue;
    el("line", { class: "bone", x1: P[a].x, y1: P[a].y, x2: P[b].x, y2: P[b].y, "stroke-width": unit * 0.35 }, bones);
  }

  const finding = state.findings.find((f) => f.id === state.activeFinding);
  if (finding) {
    const g = el("g", {}, svg);
    for (const line of finding.overlay) {
      el("polyline", {
        class: "measure",
        points: line.map(([x, y]) => `${x},${y}`).join(" "),
        "stroke-width": unit * 0.8,
      }, g);
    }
  }

  const showLabels = $("show-labels").checked;
  const labels = Object.fromEntries(state.schema.keypoints.map((k) => [k.id, k]));
  const focus = state.drag?.id ?? state.hover ?? state.selected;
  for (const [id, p] of Object.entries(P)) {
    const classes = ["kp", p.source];
    if (id === state.selected) classes.push("active");
    if (id === state.hover) classes.push("hover");
    const big = id === state.selected || id === state.hover;
    el("circle", {
      class: classes.join(" "), cx: p.x, cy: p.y, r: unit * (big ? 1.6 : 1.1), "stroke-width": unit * 0.3,
    }, svg);
    if (showLabels || id === focus) {
      const t = el("text", {
        class: "label", x: p.x + unit * 2, y: p.y + unit * 0.8,
        "font-size": unit * 2.6, "stroke-width": unit * 0.5,
      }, svg);
      t.textContent = labels[id]?.label ?? id;
    }
  }
}

function toSvg(evt) {
  const svg = $("overlay");
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

// Image pixels per screen pixel
function screenScale() {
  return state.width / $("overlay").getBoundingClientRect().width;
}

// Nearest point within GRAB_RADIUS screen pixels, so points need not be hit exactly
const GRAB_RADIUS = 20;
function nearestPoint(pos) {
  let best = null;
  let bestDist = GRAB_RADIUS * screenScale();
  for (const [id, p] of Object.entries(state.points)) {
    const d = Math.hypot(p.x - pos.x, p.y - pos.y);
    if (d < bestDist) { best = id; bestDist = d; }
  }
  return best;
}

let analyzeTimer = null;
function scheduleAnalyze() {
  clearTimeout(analyzeTimer);
  analyzeTimer = setTimeout(analyze, 120);
}

function movePoint(id, x, y) {
  state.points[id] = {
    x: Math.min(Math.max(x, 0), state.width),
    y: Math.min(Math.max(y, 0), state.height),
    source: "user",
  };
}

function setHover(id) {
  if (id === state.hover) return;
  state.hover = id;
  $("overlay").style.cursor = id ? "grab" : "default";
  render();
}

function onPointerDown(e) {
  const pos = toSvg(e);
  const id = nearestPoint(pos);
  if (!id) return;
  e.preventDefault();
  $("overlay").setPointerCapture(e.pointerId);
  $("overlay").style.cursor = "grabbing";
  const p = state.points[id];
  // Keep the grab offset so the point does not jump under the cursor
  state.drag = { id, dx: p.x - pos.x, dy: p.y - pos.y };
  state.selected = id;
  showPointInfo(id);
  render();
}

function onPointerMove(e) {
  const pos = toSvg(e);
  if (!state.drag) {
    setHover(nearestPoint(pos));
    return;
  }
  const { id, dx, dy } = state.drag;
  movePoint(id, pos.x + dx, pos.y + dy);
  render();
  scheduleAnalyze();
}

function endDrag(e) {
  if (!state.drag) return;
  state.drag = null;
  if ($("overlay").hasPointerCapture(e.pointerId)) $("overlay").releasePointerCapture(e.pointerId);
  $("overlay").style.cursor = "grab";
  render();
  analyze();
}

function onKeyDown(e) {
  const id = state.selected;
  const step = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (!id || !step || $("workspace").hidden) return;
  e.preventDefault();
  const amount = (e.shiftKey ? 10 : 1) * screenScale();
  movePoint(id, state.points[id].x + step[0] * amount, state.points[id].y + step[1] * amount);
  render();
  scheduleAnalyze();
}

function showPointInfo(id) {
  const k = state.schema.keypoints.find((k) => k.id === id);
  if (k) $("point-info").innerHTML = `<strong>${k.label}</strong> (${k.group}): ${k.hint}. Hienosäädä nuolinäppäimillä (Shift = isompi askel).`;
}

// ---------------------------------------------------------------- report

let analyzeSeq = 0;
async function analyze() {
  const seq = ++analyzeSeq;
  const keypoints = Object.fromEntries(Object.entries(state.points).map(([id, p]) => [id, [p.x, p.y]]));
  const res = await api("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keypoints }),
  });
  const data = await res.json();
  if (seq !== analyzeSeq) return; // a newer request is on its way
  if (!res.ok) {
    $("warnings").innerHTML = `<div class="warning">${data.detail}</div>`;
    $("findings").replaceChildren();
    return;
  }
  state.findings = data.findings;
  renderReport(data);
  render();
}

function fmtRange([lo, hi], unit) {
  if (lo !== null && hi !== null) return `${lo}–${hi} ${unit}`;
  if (lo !== null) return `≥ ${lo} ${unit}`;
  return `≤ ${hi} ${unit}`;
}

function renderReport({ findings, warnings }) {
  $("warnings").innerHTML = warnings.map((w) => `<div class="warning">${w}</div>`).join("");

  const counts = { ideal: 0, acceptable: 0, deviation: 0 };
  findings.forEach((f) => counts[f.status]++);
  const container = $("findings");
  container.replaceChildren();
  const summary = document.createElement("div");
  summary.className = "summary";
  summary.innerHTML = Object.entries(counts)
    .map(([s, n]) => `<span class="badge ${s}">${STATUS_LABEL[s]}: ${n}</span>`).join("");
  container.appendChild(summary);

  let group = null;
  for (const f of findings) {
    if (f.group !== group) {
      group = f.group;
      const h = document.createElement("div");
      h.className = "group-title";
      h.textContent = group;
      container.appendChild(h);
    }
    const card = document.createElement("div");
    card.className = "finding" + (f.id === state.activeFinding ? " active" : "");
    card.innerHTML = `
      <div class="row">
        <span class="title">${f.title}</span>
        <span class="value">${f.value} ${f.unit}<span class="badge ${f.status}">${STATUS_LABEL[f.status]}</span></span>
      </div>
      <div class="text">${f.interpretation}</div>
      <div class="range">Ihanne ${fmtRange(f.ideal, f.unit)} · hyväksyttävä ${fmtRange(f.acceptable, f.unit)}</div>`;
    card.addEventListener("click", () => {
      state.activeFinding = state.activeFinding === f.id ? null : f.id;
      container.querySelectorAll(".finding").forEach((n) => n.classList.remove("active"));
      if (state.activeFinding) card.classList.add("active");
      render();
    });
    container.appendChild(card);
  }
}

// ---------------------------------------------------------------- dataset

function updateUncheckedNote() {
  const n = Object.values(state.points).filter((p) => p.source === "estimated").length;
  $("unchecked-points").textContent = n
    ? `${n} arvioitua (oranssia) pistettä on vielä siirtämättä – tarkista ne ennen tallennusta.`
    : "";
}

function setSaveStatus(text, error = false) {
  $("save-status").textContent = text;
  $("save-status").classList.toggle("error", error);
}

function formPayload() {
  const f = new FormData($("horse-form"));
  const val = (name) => (f.get(name) ?? "").toString().trim() || null;
  const num = (name) => (val(name) === null ? null : Number(val(name)));
  return {
    horse: {
      breed: val("breed"),
      type: val("type"),
      sex: val("sex"),
      age_years: num("age_years"),
      irl: { award: val("irl_award") },
      url: { award: val("url_award") },
      link: val("link"),
      notes: val("notes"),
    },
    keypoints: state.points,
    verified: f.get("verified") === "on",
    original_filename: state.fileName,
  };
}

async function saveSample(e) {
  e.preventDefault();
  const payload = formPayload();
  $("save").disabled = true;
  setSaveStatus("Tallennetaan…");
  try {
    let res;
    if (state.sampleId) {
      res = await api(`/api/samples/${state.sampleId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      const body = new FormData();
      body.append("file", state.file);
      body.append("data", JSON.stringify(payload));
      res = await api("/api/samples", { method: "POST", body });
    }
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Tallennus epäonnistui.");
    state.sampleId = data.id;
    $("save").textContent = "Päivitä tallennus";
    setSaveStatus(`Tallennettu. Aineistossa on nyt ${data.count} hevosta.`);
  } catch (err) {
    setSaveStatus(err.message, true);
  } finally {
    $("save").disabled = false;
  }
}
