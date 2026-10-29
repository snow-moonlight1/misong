"use strict";
/* MISONG desktop front end. Talks to the Python Api via window.pywebview.api. */
(function () {
const ICONS = window.ICONS || {};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (name) => `<i data-icon="${name}">${ICONS[name] || ""}</i>`;
const DISK_COLORS = { quark: "#4B7BF5", feimao: "#F0803C", baidu: "#3A8DF5", xunlei: "#2A7CF0", uc: "#F5A623", "123pan": "#18B88E" };
const fmtSize = (n) => {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(n < 10 ? 2 : 1)) + " " + u[i];
};
const fmtTime = (iso) => { if (!iso) return ""; const d = new Date(iso); if (isNaN(d)) return iso;
  const p = (x) => String(x).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`; };
const diskColor = (k) => DISK_COLORS[k] || "#8A8784";
const DISK_LOGOS = { quark: "svg", baidu: "svg", xunlei: "svg", uc: "svg", "123pan": "svg", feimao: "png" };
const avatar = (k, label, cls = "") => {
  const letter = esc((label || k || "?").slice(0, 1));
  const logo = DISK_LOGOS[k] ? `<img src="disks/${k}.${DISK_LOGOS[k]}" alt="" draggable="false" onerror="this.remove()">` : "";
  return `<span class="avatar ${logo ? "has-logo" : ""} ${cls}" style="background:${diskColor(k)}">${letter}${logo}</span>`;
};
const STATE_LABEL = { prepared: "待开始", running: "进行中", uploading: "上传中", uploaded: "待分享", shared: "已分享", complete: "已完成", paused: "已暂停", blocked: "需处理", pending: "待上传" };
const STATE_CLASS = { complete: "ok", shared: "ok", uploaded: "run", uploading: "run", running: "run", prepared: "", pending: "", paused: "warn", blocked: "bad" };

/* ---------- backend bridge ---------- */
let API = null;
const ready = new Promise((res) => {
  if (window.pywebview && window.pywebview.api) return res(window.pywebview.api);
  window.addEventListener("pywebviewready", () => res(window.pywebview.api), { once: true });
  setTimeout(() => { if (!window.pywebview || !window.pywebview.api) res(window.__MISONG_MOCK__ || null); }, 1500);
});
async function call(method, ...args) {
  if (!API) { API = await ready; }
  if (!API || typeof API[method] !== "function") throw new Error("后端未就绪：" + method);
  const r = await API[method](...args);
  if (r && typeof r === "object" && "ok" in r) { if (!r.ok) throw new Error(r.error || "操作失败"); return r.data; }
  return r;
}

/* ---------- global state ---------- */
const S = {
  meta: null, settings: {}, page: "pipeline", job: null, logs: [], logSeen: 0,
  pipeline: { task_name: "", folder_name: "", cleanup_after_upload: false, inputs: [], layers_version: 2, checksum: false, layers: [], video: "", disguise: "", size: "1900M", raw_merge: false, disks: [], form: "direct", hop: "feimao", hopPw: "", pwdHint: "请向分享者获取解压密码。", expiry: "default", access: "default", schemes: ["beast", "mojibake", "hajimi"], key: "", result: null },
  pack: { inputs: [], layers_version: 2, checksum: false, layers: [], video: "", disguise: "", split: false, size: "1900M", raw_merge: false, result: null },
  upload: { task_name: "", folder_name: "", files: [], checksum: false, disks: [], expiry: "default", access: "default", schemes: ["beast", "mojibake", "hajimi"], key: "", result: null },
  restore: { inputs: [], keyFile: null, out: "", result: null },
  // 文案还原：密钥只在内存中保存，不进入 saveSettings
  textrestore: { kind: "text", text: "", video: "", keyFile: "", manual: false, recipeJson: "", secrets: {}, out: "", result: null },
  codec: { mode: "encode", schemes: ["beast"], key: "", input: "", output: null, outScheme: null },
  tasks: { items: [], sel: null, detail: null, filter: "all", query: "", loadError: "", reloadDetail: false },
  accounts: [],
};
const DEFAULT_LAYERS = () => [{ type: "archive", fmt: "lz4", password: "", header_enc: true }, { type: "archive", fmt: "7z", password: "", header_enc: true }];

/* ---------- toast / log / modal ---------- */
function toast(text, level = "") {
  const el = document.createElement("div");
  el.className = "toast " + (level || "");
  el.innerHTML = icon(level === "err" ? "warn" : level === "ok" ? "check" : level === "warn" ? "warn" : "info") + `<span>${esc(text)}</span>`;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(12px)"; el.style.transition = "all .2s"; setTimeout(() => el.remove(), 220); }, 3600);
}
function pushLog(text, kind = "") {
  S.logs.push({ t: new Date(), text, kind });
  if (S.logs.length > 500) S.logs.splice(0, S.logs.length - 500);
  renderLogs();
}
function renderLogs() {
  const open = !$("#logDrawer").hidden;
  $("#logCount").textContent = S.logs.length ? String(S.logs.length) : "";
  if (!open) return;
  const list = $("#logList");
  list.innerHTML = S.logs.map((l) => {
    const p = (x) => String(x).padStart(2, "0");
    const time = `${p(l.t.getHours())}:${p(l.t.getMinutes())}:${p(l.t.getSeconds())}`;
    return `<li class="${l.kind}"><time>${time}</time><span>${esc(l.text)}</span></li>`;
  }).join("");
  list.scrollTop = list.scrollHeight;
}
function modal(html) {
  const box = $("#modal .modal-box"); box.innerHTML = html; $("#modal").hidden = false; return box;
}
function closeModal() { $("#modal").hidden = true; $("#modal .modal-box").innerHTML = ""; }
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); }
  catch (_) { const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
  if (btn) { const old = btn.innerHTML; btn.innerHTML = icon("check") + "已复制"; setTimeout(() => (btn.innerHTML = old), 1400); }
  else toast("已复制到剪贴板", "ok");
}

/* paint inline SVG into any <i data-icon> that is still empty */
function paintIcons(root = document) {
  $$("i[data-icon]", root).forEach((el) => { if (!el.firstChild) el.innerHTML = ICONS[el.dataset.icon] || ""; });
}

/* expose for drag-drop from Python */
window.misongDrop = (paths) => { if (window.__onDrop) window.__onDrop(paths); };

/* ---------- reusable widgets ---------- */
function fileList(items, onRemove) {
  if (!items.length) return "";
  const rows = items.map((f, i) => `
    <div class="file">
      <span class="file-ic ${f.dir ? "dir" : ""}">${icon(f.dir ? "folder" : "file")}</span>
      <div class="file-main"><div class="file-name">${esc(f.name)}</div><div class="file-path">${esc(f.path)}</div></div>
      <span class="file-meta">${f.dir ? ((f.count || 0) + " 项 · ") : ""}${fmtSize(f.size)}</span>
      <button class="btn btn-ghost icon-only" data-rm="${i}" aria-label="移除">${icon("x")}</button>
    </div>`).join("");
  const total = items.reduce((a, f) => a + (f.size || 0), 0);
  return `<div class="files">${rows}<div class="files-foot"><span>共 ${items.length} 项</span><span>${fmtSize(total)}</span></div></div>`;
}
function dropzone(id, title, sub, compact) {
  return `<div class="drop ${compact ? "compact" : ""}" data-drop="${id}">
    <span class="drop-icon">${icon("inbox")}</span>
    <div class="drop-text"><b>${esc(title)}</b><small>${esc(sub)}</small></div>
    <div class="btn-row"><button class="btn" data-act="paste-paths">${icon("clipboard")}粘贴路径</button><button class="btn" data-act="pick-files">${icon("file")}选择文件</button><button class="btn" data-act="pick-folder">${icon("folder")}文件夹</button></div>
  </div>`;
}
function pwField(label, value, key, placeholder) {
  return `<label class="field"><span>${esc(label)}</span><div class="pw">
    <input class="input" type="password" value="${esc(value || "")}" placeholder="${esc(placeholder || "")}" autocomplete="off" data-model="${key}">
    <button type="button" data-pwtoggle>${icon("eye")}</button></div></label>`;
}
function selectField(label, value, options, key, hint) {
  const opts = options.map((o) => `<option value="${esc(o.key)}" ${o.key === value ? "selected" : ""}>${esc(o.label)}</option>`).join("");
  return `<label class="field"><span>${esc(label)}</span><select class="select" data-model="${key}">${opts}</select>${hint ? `<small>${esc(hint)}</small>` : ""}</label>`;
}

/* bind data-model inputs within a root to a target object + rerender hook */
function bindModels(root, target, after) {
  $$("[data-model]", root).forEach((el) => {
    const key = el.dataset.model;
    const handler = () => {
      target[key] = el.type === "checkbox" ? el.checked : el.value;
      if (after) after(key, el);
    };
    el.addEventListener(el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "input", handler);
  });
  $$("[data-pwtoggle]", root).forEach((btn) => btn.addEventListener("click", () => {
    const input = btn.previousElementSibling;
    const show = input.type === "password"; input.type = show ? "text" : "password";
    btn.innerHTML = ICONS[show ? "eyeoff" : "eye"] || "";
  }));
}

/* ---------- layer editor ---------- */
const canLock = (fmt) => !!(S.meta.formats.find((f) => f.key === fmt) || {}).password;
const hasPassword = (st) => (st.layers || []).some((l) => l.password && canLock(l.fmt));
const missingLocked = (st) => (st.layers || []).filter((l) => l._lock && canLock(l.fmt) && !l.password).length;
const LAYER_NAMES = { archive: "压缩 / 加密", cover: "门面视频", split: "分卷", rename: "改后缀" };
const layerLabel = (l) => l.type === "cover" ? "门面视频" : l.type === "split" ? "分卷 " + l.size : l.type === "rename" ? "后缀 " + l.ext : l.fmt;
function outExt(state) {
  let ext = "";
  (state.layers || []).forEach((l) => {
    if (l.type === "cover") ext = ".mp4";
    else if (l.type === "rename") ext = "." + String(l.ext || "").replace(/^\./, "");
    else if (!l.type || l.type === "archive") ext = ((S.meta.formats.find((f) => f.key === l.fmt) || {}).ext || "");
  });
  return ext;
}
function tplDesc(t) { return (t.layers || []).map((l) => layerLabel(l) + (l.locked ? "🔒" : "")).join(" → ") + (t.disguise ? " · 后缀 " + t.disguise : "") + (t.size ? " · 每卷 " + t.size : ""); }
function applyLayers(state, layers, opts = {}) {
  state.layers = layers.map((p) => ({ ...p, type: p.type || "archive", password: "", header_enc: p.header_enc !== false,
    _lock: !!(p.lock || p.locked) && canLock(p.fmt) }));
  if (opts.layers_version !== 2 && state.layers.every((l) => l.type === "archive")) {
    if (opts.disguise) state.layers.push({ type: "rename", ext: "." + opts.disguise.replace(/^\./, "") });
    if (opts.video) state.layers.push({ type: "cover", video: opts.video });
    if (opts.size && opts.split !== false) state.layers.push({ type: "split", size: opts.size });
  }
  state.layers_version = 2;
  state.video = state.disguise = ""; state.split = false;
  state._pwAck = state._lockAck = false;
  if (opts.options) { state.raw_merge = !!opts.options.raw_merge; state.checksum = !!opts.options.checksum; }
  if (Array.isArray(opts.text_recipes)) {
    ensureText(state); state.recipes = opts.text_recipes.map(recipeFromPublic);
    state.textMode = state.recipes.length ? "recipes" : "legacy";
    state.textSecrets = {}; state.textVideos = {}; state.exportKeys = [];
  }
}
function layerProblems(st) {
  const problems = []; let single = st.inputs.length === 1 && !st.inputs[0].dir, archive = null;
  st.layers.forEach((l, i) => {
    const prefix = `第 ${i + 1} 层：`;
    if (l.type === "archive") { single = true; archive = l.fmt; return; }
    if (!single) problems.push(prefix + "只接受单文件，请先添加压缩层");
    if (l.type === "cover") {
      if (!["7z", "zip"].includes(archive)) problems.push(prefix + "门面视频前需要 7z / zip 归档");
      if (!l.video) problems.push(prefix + "选择 MP4 门面视频");
      archive = null;
    } else if (l.type === "split") { if (!/^\s*\d+(\.\d+)?\s*([kKmMgGtT]?[iI]?[bB]?)?\s*$/.test(l.size || "") || parseFloat(l.size) <= 0) problems.push(prefix + "填写有效每卷大小"); single = false; archive = null; }
    else if (l.type === "rename" && !/^\.?[^/\\:*?"<>|]+$/.test(l.ext || "")) problems.push(prefix + "填写有效后缀");
  });
  return problems;
}
function enterSubmits(box, fn) {
  box.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); fn(); } });
}
function confirmModal(title, text, backLabel, okLabel, onOk, onBack) {
  const box = modal(`<h3>${esc(title)}</h3><p>${text}</p>
    <div class="modal-actions"><button class="btn" data-x>${esc(backLabel)}</button><button class="btn btn-primary" data-ok>${esc(okLabel)}</button></div>`);
  $("[data-x]", box).addEventListener("click", () => { closeModal(); if (onBack) onBack(); });
  $("[data-ok]", box).addEventListener("click", () => { closeModal(); onOk(); });
  $("[data-ok]", box).focus();
}
function focusMissingPw(page) {
  const root = $(`.page[data-page="${page}"]`); if (!root) return;
  const el = $(".layer.need [data-lpw]", root) || $("[data-lpw]:not([disabled])", root);
  if (el) { el.focus(); el.scrollIntoView({ block: "center" }); }
}
/* templates never carry passwords: ask once (per layer setup) before running with no / missing passwords */
function checkPasswords(page, cont, onBack) {
  const st = S[page];
  if (!hasPassword(st) && !st._pwAck) {
    confirmModal("没有设置任何密码", "当前所有层都没有密码，产物只是普通压缩，任何拿到文件的人都能直接解开。确定按“仅压缩”继续吗？",
      "返回填写密码", "仍然继续", () => { st._pwAck = st._lockAck = true; cont(); }, onBack);
    return;
  }
  const miss = missingLocked(st);
  if (hasPassword(st) && miss && !st._lockAck) {
    confirmModal("还有加密层没填密码", `模板要求加密的层里有 ${miss} 层还没有填写密码，这些层将只压缩、不加密。`,
      "返回填写", "这些层不加密，继续", () => { st._lockAck = true; cont(); }, onBack);
    return;
  }
  cont();
}
function layerEditor(state, mountSel, root) {
  const fmts = S.meta.formats;
  const page = root && root.dataset ? root.dataset.page : S.page;
  function chainView() {
    const nodes = [`<span class="node src">${icon("file")}资源</span>`];
    state.layers.forEach((l) => {
      const locked = l.password && canLock(l.fmt);
      nodes.push('<span class="arr">→</span>');
      nodes.push(`<span class="node ${locked ? "locked" : ""}">${locked ? icon("lock") : ""}${esc(layerLabel(l))}</span>`);
    });

    if (state.layers.length) nodes.push('<span class="arr">→</span>', `<span class="node out">${icon("download")}${esc(outExt(state) || "产物")}</span>`);
    return `<div class="chain">${nodes.join("")}</div>`;
  }
  function warnView() {
    if (!state.layers.length) return "";
    if (!hasPassword(state)) return `<div class="callout warn" data-pwwarn>${icon("warn")}<span><b>当前仅压缩，未启用密码加密。</b>任何拿到文件的人都能直接解开；需要加密请给 7z / zip 层填写密码。</span></div>`;
    const miss = missingLocked(state);
    return miss ? `<div class="callout warn" data-pwwarn>${icon("warn")}<span>模板标记为加密的层还有 ${miss} 个未填写密码，这些层将不加密。</span></div>` : "";
  }
  function row(l, i) {
    const kind = l.type || "archive";
    const types = Object.entries(LAYER_NAMES).map(([k,v]) => `<option value="${k}" ${kind === k ? "selected" : ""}>${v}</option>`).join("");
    let fields = "";
    if (kind === "archive") {
      const opts = fmts.map((f) => `<option value="${f.key}" ${f.key === l.fmt ? "selected" : ""}>${esc(f.key)}${f.password ? "" : " · 无密码"}</option>`).join("");
      const lockable = canLock(l.fmt);
      fields = `<div class="layer-archive"><label class="field"><span>归档格式</span><select class="select" data-lfmt>${opts}</select></label>
        <label class="field"><span>密码 · 可空</span><div class="pw"><input class="input" type="password" placeholder="${lockable ? (l._lock ? "模板要求密码" : "不填写则仅压缩") : "该格式不支持密码"}" value="${esc(l.password || "")}" autocomplete="off" ${lockable ? "" : "disabled"} data-lpw><button type="button" data-pwtoggle>${icon("eye")}</button></div></label>
        <label class="field"><span>压缩等级</span><select class="select" data-level><option value="" ${l.level == null ? "selected" : ""}>自动（${i ? "仅存储" : "标准压缩"}）</option>${[0,1,3,5,7,9].map((v) => `<option value="${v}" ${l.level === v ? "selected" : ""}>${v === 0 ? "0 · 仅存储" : v}</option>`).join("")}</select></label>
        <label class="check layer-header" ${l.fmt === "7z" ? "" : "hidden"}><input type="checkbox" data-lhe ${l.header_enc !== false ? "checked" : ""}>加密文件名（有密码时）</label></div>`;
    } else if (kind === "cover") fields = videoField(l, i);
    else if (kind === "split") {
      const m = String(l.size || "1900MB").match(/^([\d.]+)\s*([a-zA-Z]*)$/) || ["", "1900", "MB"];
      const unit = /^g/i.test(m[2]) ? "GB" : "MB";
      fields = `<label class="field"><span>每卷大小</span><div class="input-group"><input class="input" type="number" min="0.001" step="any" value="${esc(m[1])}" data-lsize><select class="select size-unit" data-lunit><option ${unit === "MB" ? "selected" : ""}>MB</option><option ${unit === "GB" ? "selected" : ""}>GB</option></select></div><small>上一层产物不超过每卷大小时，将保留单文件，不生成分卷。</small><small>后续压缩层会把所有卷重新打包；要最终输出 .001 / .002…，请把分卷放在最后一层。</small></label>`;
    } else fields = `<label class="field"><span>产物后缀</span><input class="input" value="${esc(l.ext || "")}" placeholder="例如 .mp4" data-lext><small>只改文件名；还原时自动恢复原名</small></label>`;
    return `<div class="layer ${l._lock && canLock(l.fmt) && !l.password ? "need" : ""}" data-i="${i}">
      <div class="layer-top"><span class="layer-idx"><b>第 ${i + 1} 层</b>${i === 0 ? "最内" : ""}</span><select class="select layer-type" data-ltype>${types}</select>
      <div class="layer-tools"><button class="btn btn-ghost icon-only" data-lup ${i === 0 ? "disabled" : ""} title="上移">↑</button><button class="btn btn-ghost icon-only" data-ldown ${i === state.layers.length - 1 ? "disabled" : ""} title="下移">↓</button><button class="btn btn-ghost icon-only" data-ldel aria-label="删除" ${state.layers.length <= 1 ? "disabled" : ""}>${icon("trash")}</button></div></div>
      <div class="layer-fields">${fields}</div></div>`;
  }
  function presetsView() {
    const list = S.meta.templates || [];
    const chips = list.map((t, i) => `<span class="chip mine" title="${esc(tplDesc(t))}"><button data-tpl="${i}">${esc(t.name)}</button><button class="chip-x" data-tplren="${i}" title="重命名" aria-label="重命名">${icon("edit")}</button><button class="chip-x" data-tpldel="${i}" title="删除" aria-label="删除">${icon("x")}</button></span>`).join("");
    const names = list.map((t) => t.name);
    const lost = (S.meta.default_templates || []).some((n) => !names.includes(n));
    return `<div class="presets"><span>快速模板</span>${chips}<button class="chip ghost" data-tplsave title="把当前层设置存为模板（不含密码）">${icon("plus")}存为模板</button>${lost ? `<button class="chip ghost" data-tplreset title="找回删除过的内置模板，不影响自己的模板">${icon("refresh")}恢复默认</button>` : ""}</div>`;
  }
  function render() {
    const mount = $(mountSel, root);
    mount.innerHTML = chainView() + `<div class="layers">${state.layers.map(row).join("")}</div>` + warnView() +
      `<div class="layer-foot">${presetsView()}<div class="input-group add-layer"><select class="select" data-addtype><option value="archive">压缩 / 加密</option><option value="cover">门面视频</option><option value="split">分卷</option><option value="rename">改后缀</option></select><button class="btn btn-sm" data-addlayer>${icon("plus")}添加层</button></div></div>`;
    paintIcons(mount);
    const live = (el, i) => {
      $(".chain", mount).replaceWith(elFromHTML(chainView()));
      const old = $("[data-pwwarn]", mount); const html = warnView();
      if (old && html) old.replaceWith(elFromHTML(html)); else if (old) old.remove(); else if (html) $(".layers", mount).insertAdjacentElement("afterend", elFromHTML(html));
      const l = state.layers[i]; el.classList.toggle("need", !!(l._lock && canLock(l.fmt) && !l.password));
    };
    $$(".layer", mount).forEach((el) => {
      const i = +el.dataset.i, l = state.layers[i];
      const on = (sel, event, fn) => { const e = $(sel, el); if (e) e.addEventListener(event, fn); };
      on("[data-ltype]", "change", (e) => { state.layers[i] = { type: e.target.value, fmt: "7z", password: "", header_enc: true, video: "", size: "1900MB", ext: ".mp4" }; render(); sync(); });
      on("[data-lfmt]", "change", (e) => { l.fmt = e.target.value; if (!canLock(l.fmt)) l.password = ""; render(); sync(); });
      on("[data-lpw]", "input", (e) => { l.password = e.target.value; live(el, i); sync(); });
      on("[data-lhe]", "change", (e) => { l.header_enc = e.target.checked; sync(); });
      on("[data-level]", "change", (e) => { l.level = e.target.value === "" ? null : Number(e.target.value); sync(); });
      on("[data-lext]", "input", (e) => { l.ext = e.target.value; live(el, i); sync(); });
      const sizeChange = () => { l.size = $("[data-lsize]", el).value + $("[data-lunit]", el).value; live(el, i); sync(); };
      on("[data-lsize]", "input", sizeChange); on("[data-lunit]", "change", sizeChange);
      on("[data-ldel]", "click", () => { state.layers.splice(i, 1); render(); sync(); });
      on("[data-lup]", "click", () => { [state.layers[i-1], state.layers[i]] = [state.layers[i], state.layers[i-1]]; render(); sync(); });
      on("[data-ldown]", "click", () => { [state.layers[i+1], state.layers[i]] = [state.layers[i], state.layers[i+1]]; render(); sync(); });
      on("[data-pwtoggle]", "click", () => { const inp = $("[data-lpw]", el); inp.type = inp.type === "password" ? "text" : "password"; });
      on("[data-dropkind='video']", "click", async (e) => {
        if (e.target.closest("[data-clearvideo]")) { l.video = ""; render(); sync(); return; }
        try { const paths = await call("pick_files", false, true); if (paths[0]) { l.video = paths[0]; render(); sync(); } } catch (err) { toast(err.message, "err"); }
      });
    });
    $("[data-addlayer]", mount).addEventListener("click", () => { state.layers.push({ type: $("[data-addtype]", mount).value, fmt: "7z", password: "", header_enc: true, video: "", size: "1900MB", ext: ".mp4" }); render(); sync(); });
    $$("[data-tpl]", mount).forEach((b) => b.addEventListener("click", () => {
      const t = S.meta.templates[+b.dataset.tpl]; if (!t) return;
      applyLayers(state, t.layers || [], { ...t });
      rerender(page);
      const need = missingLocked(state);
      toast(`已套用「${t.name}」` + (need ? `，请在标出的 ${need} 个加密层填写密码` : "，可继续调整"), "ok");
    }));
    const rs = $("[data-tplreset]", mount);
    if (rs) rs.addEventListener("click", async () => { try { templatesChanged(await call("reset_templates"), page, "已恢复内置模板"); } catch (e) { toast(e.message, "err"); } });
    $$("[data-tplren]", mount).forEach((b) => b.addEventListener("click", () => renameTemplateModal(+b.dataset.tplren, page)));
    $$("[data-tpldel]", mount).forEach((b) => b.addEventListener("click", () => deleteTemplateModal(+b.dataset.tpldel, page)));
    $("[data-tplsave]", mount).addEventListener("click", () => saveTemplateModal(state, page));
  }
  function elFromHTML(html) { const d = document.createElement("div"); d.innerHTML = html; const el = d.firstElementChild; paintIcons(el); return el; }
  function sync() { if (state._onchange) state._onchange(); }
  render();
}
function templatesChanged(list, page, msg) { S.meta.templates = list || []; if (msg) toast(msg, "ok"); if (page) rerender(page); }
function saveTemplateModal(state, page) {
  const withSize = false;
  const layers = layerPayload(state).map((l,i) => ({ ...l, password: undefined, locked: !!(state.layers[i].password || state.layers[i]._lock) && canLock(l.fmt) }));
  const draft = { name: "", extras: true };
  const box = modal(`<h3>保存为快速模板</h3><p>记录公开层序和“哪些层需要密码”。密码与源视频路径不保存，套用后重新选择和填写。</p>
    <div class="chain-text">${esc(tplDesc({ layers }))}</div>
    <label class="field"><span>模板名称</span><input class="input" maxlength="24" placeholder="例如：发群用 lz4+7z" data-model="name"></label>
    <label class="check"><input type="checkbox" checked data-model="extras">记住公开打包选项与文案配方</label>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-primary" data-ok>保存模板</button></div>`);
  bindModels(box, draft);
  const ok = async () => {
    const name = (draft.name || "").trim(); if (!name) { toast("请填写模板名称", "warn"); return; }
    const exists = (S.meta.templates || []).some((t) => t.name === name);
    try {
      const list = await call("save_template", name, layers, draft.extras ? (state.disguise || "") : "", draft.extras && withSize ? (state.size || "") : "", null,
        draft.extras ? {raw_merge:!!state.raw_merge, checksum:!!state.checksum} : null,
        draft.extras && page === "pipeline" ? (isRecipeMode(state) ? state.recipes.map(recipeToPublic) : []) : null);
      closeModal(); templatesChanged(list, page, exists ? `已更新模板「${name}」` : `已保存模板「${name}」`);
    } catch (e) { toast(e.message, "err"); }
  };
  $("[data-x]", box).addEventListener("click", closeModal);
  $("[data-ok]", box).addEventListener("click", ok);
  enterSubmits(box, ok);
  $("input.input", box).focus();
}
function renameTemplateModal(i, page) {
  const t = (S.meta.templates || [])[i]; if (!t) return;
  const draft = { name: t.name };
  const box = modal(`<h3>重命名模板</h3><div class="chain-text">${esc(tplDesc(t))}</div>
    <label class="field"><span>新名称</span><input class="input" maxlength="24" value="${esc(t.name)}" data-model="name"></label>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-primary" data-ok>保存</button></div>`);
  bindModels(box, draft);
  const ok = async () => {
    const name = (draft.name || "").trim(); if (!name) { toast("请填写模板名称", "warn"); return; }
    if (name === t.name) { closeModal(); return; }
    try { const list = await call("save_template", name, t.layers, t.disguise || "", t.size || "", t.name); closeModal(); templatesChanged(list, page, "已重命名为「" + name + "」"); }
    catch (e) { toast(e.message, "err"); }
  };
  $("[data-x]", box).addEventListener("click", closeModal);
  $("[data-ok]", box).addEventListener("click", ok);
  enterSubmits(box, ok);
  const input = $("input.input", box); input.focus(); input.select();
}
function deleteTemplateModal(i, page) {
  const t = (S.meta.templates || [])[i]; if (!t) return;
  const builtin = (S.meta.default_templates || []).includes(t.name);
  const box = modal(`<h3>删除模板</h3><p>确定删除模板「${esc(t.name)}」？只删除这个快捷方式，不影响已有任务和当前设置。${builtin ? "内置模板删除后可用“恢复默认”找回。" : ""}</p>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-danger-solid" data-ok>删除</button></div>`);
  $("[data-x]", box).addEventListener("click", closeModal);
  $("[data-ok]", box).addEventListener("click", async () => {
    try { const list = await call("delete_template", t.name); closeModal(); templatesChanged(list, page, "已删除模板"); } catch (e) { toast(e.message, "err"); }
  });
}

/* ---------- account status: one owner-facing state per disk ---------- */
const fmtShort = (iso) => { const t = fmtTime(iso); return t ? t.slice(5) : ""; };
const ACCT_STATE = {
  verification: {cls:"warn", text:"需要人工验证", tip:"请由账号所有者完成验证码或绑定后重新检查"},
  unknown: {cls:"warn", text:"检查未能确认", tip:"超时或检查环境故障，不能据此判断登录失效"},
  none: { cls: "", text: "未登录", tip: "还没有在本机登录该网盘" },
  loggedin: { cls: "run", text: "已登录 · 未测试", tip: "已登录，但本机还没有用该盘完整跑通一次上传 + 分享" },
  tested: { cls: "ok", text: "已通过测试", tip: "本机已用该盘完整跑通上传 + 分享；检测登录不会改变这一状态" },
  expired: { cls: "bad", text: "登录失效", tip: "上次打开网盘时未能确认已登录，请重新登录" },
  neterr: { cls: "warn", text: "检测失败 · 网络", tip: "上次检测时网盘页面打不开（网络问题），登录未必失效，网络恢复后再检测一次" },
};
function statusInfo(a) {
  const base = ACCT_STATE[a.state] || ACCT_STATE[a.session ? "loggedin" : "none"];
  let when = "";
  if (a.state === "tested" && a.verified_at) when = "测试通过 " + fmtShort(a.verified_at);
  else if (a.state === "loggedin" && (a.session_at || a.session_saved)) when = (a.session_at ? "登录确认 " : "登录保存 ") + fmtShort(a.session_at || a.session_saved);
  else if ((a.state === "expired" || a.state === "neterr") && a.last_error_at) when = "检测于 " + fmtShort(a.last_error_at);
  return Object.assign({ when }, base);
}
function diskPicker(selected, onToggle, opts = {}) {
  const items = S.meta.providers.map((p) => {
    const on = selected.includes(p.key);
    const acc = S.accounts.find((a) => a.key === p.key);
    let dot = "", label = p.auto ? "支持自动上传" : "仅手动回填", tip = "";
    if (p.auto && acc) {
      const s = statusInfo(acc);
      dot = { ok: "ok", bad: "bad", warn: "warn", run: "run" }[s.cls] || "";
      label = s.text; tip = s.tip + (s.when ? "（" + s.when + "）" : "");
    }
    const disabled = opts.autoOnly && !p.auto;
    return `<button class="disk ${on ? "on" : ""}" data-disk="${p.key}" ${disabled ? "disabled title='暂无自动驱动'" : `title="${esc(tip)}"`}>
      ${avatar(p.key, p.label)}
      <div class="disk-main"><span class="disk-name">${esc(p.label)}</span><span class="disk-state"><i class="dot ${dot}"></i>${esc(label)}</span></div>
      <span class="disk-check">${icon("check")}</span></button>`;
  }).join("");
  return `<div class="disks">${items}</div>`;
}
function bindDiskPicker(root, selected, onChange, opts = {}) {
  $$("[data-disk]", root).forEach((b) => b.addEventListener("click", () => {
    if (b.disabled) return;
    const k = b.dataset.disk; const i = selected.indexOf(k);
    if (i >= 0) selected.splice(i, 1); else selected.push(k);
    onChange();
  }));
}

/* ---------- scheme picker ---------- */
function schemePicker(selected) {
  const primary = S.meta.schemes.filter((s) => ["beast", "mojibake", "hajimi"].includes(s.key));
  const extra = S.meta.schemes.filter((s) => !primary.includes(s));
  const descs = { beast: "兽音冕冕风格", mojibake: "文言文密文", hajimi: "哈基米梵文" };
  const cards = primary.map((s) => `<button class="scheme ${selected.includes(s.key) ? "on" : ""}" data-scheme="${s.key}"><b>${esc(s.label)}</b><small>${esc(descs[s.key] || "")}</small><span class="disk-check">${icon("check")}</span></button>`).join("");
  const tags = extra.map((s) => `<button class="tag-toggle ${selected.includes(s.key) ? "on" : ""}" data-scheme="${s.key}">${esc(s.label)}</button>`).join("");
  return `<div class="schemes">${cards}</div>
    <details class="more" ${extra.some((s) => selected.includes(s.key)) ? "open" : ""}><summary>${icon("chevron")}更多通用编码</summary><div class="more-body"><div class="extra-schemes">${tags}</div></div></details>`;
}
function bindSchemePicker(root, selected, onChange) {
  $$("[data-scheme]", root).forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.scheme; const i = selected.indexOf(k);
    if (i >= 0) selected.splice(i, 1); else selected.push(k);
    onChange();
  }));
}

/* ---------- file helpers shared by pages ---------- */
async function addPaths(target, paths, filesOnly) {
  if (!paths || !paths.length) return;
  let described = await call("describe_paths", paths);
  if (filesOnly) {
    const expanded = [];
    for (const d of described) {
      if (d.dir) { try { const inner = await call("folder_files", d.path); (await call("describe_paths", inner)).forEach((x) => expanded.push(x)); } catch (_) {} }
      else expanded.push(d);
    }
    described = expanded;
  }
  const seen = new Set(target.map((f) => f.path));
  described.forEach((d) => { if (!seen.has(d.path)) { target.push(d); seen.add(d.path); } });
}

window.__MISONG_APP__ = { S, call, toast, rerender, recipeToPublic };

/* ======================================================================
   PAGE: pipeline / pack / upload share a files+config+run layout
   ====================================================================== */
function mount(page, name) { return $(`.page[data-page="${page}"] [data-mount="${name}"]`); }

function namingMount(page, state) {
  const el = mount(page, "names"); if (!el) return;
  el.innerHTML = `<div class="grid2"><label class="field"><span>任务名称 · 可选</span><input class="input" data-model="task_name" maxlength="120" value="${esc(state.task_name || "")}" placeholder="留空使用资源名称"></label>
    <label class="field"><span>网盘目录名 · 可选</span><input class="input" data-model="folder_name" maxlength="100" value="${esc(state.folder_name || "")}" placeholder="留空自动生成独立目录"></label></div>
    <p class="hint">多盘使用同名目录；中转第一跳加 -hop。自定义目录已存在时会停止，请使用新名称。</p>`;
  bindModels(el, state);
}
function renderFilesMount(page, state, key, filesOnly) {
  const el = mount(page, "files"); if (!el) return;
  el.innerHTML = dropzone(page + "-" + key, filesOnly ? "拖入文件，或点击选择" : "拖入文件 / 文件夹，或点击选择",
    filesOnly ? "文件夹会展开为其中的文件" : "支持多选，名称不能重复", items(state, key).length > 0) + fileList(items(state, key), true) + (page === "upload" ? `<div class="sub"><label class="check"><input type="checkbox" data-uploadchecksum ${state.checksum ? "checked" : ""}>附带校验文件（SHA-256）</label><p class="hint">清单与还原说明会自动排除。</p></div>` : "");
  paintIcons(el);
  const uc = $("[data-uploadchecksum]", el); if (uc) uc.addEventListener("change", () => { state.checksum = uc.checked; runPanel(page); });
  const dz = $("[data-drop]", el);
  $("[data-act='paste-paths']", el).addEventListener("click", async () => {
    try {
      const paths = await call("clipboard_paths");
      if (!paths.length) { toast("剪贴板里没有路径，请先复制文件的完整路径", "warn"); return; }
      const before = items(state, key).length;
      await addPaths(items(state, key), paths, filesOnly);
      if (items(state, key).length === before) toast("没有新增文件，请检查路径是否存在或已经添加", "warn");
      rerender(page);
    } catch (_) { toast("无法读取剪贴板，请使用选择文件或拖放", "warn"); }
  });
  $("[data-act='pick-files']", el).addEventListener("click", async () => {
    try { await addPaths(items(state, key), await call("pick_files", true, false), filesOnly); rerender(page); } catch (e) { toast(e.message, "err"); }
  });
  const pf = $("[data-act='pick-folder']", el);
  pf.addEventListener("click", async () => {
    try { await addPaths(items(state, key), await call("pick_folder"), filesOnly); rerender(page); } catch (e) { toast(e.message, "err"); }
  });
  $$("[data-rm]", el).forEach((b) => b.addEventListener("click", () => { items(state, key).splice(+b.dataset.rm, 1); rerender(page); }));
  if (dz) {
    dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("over"); });
  }
}
function items(state, key) { return state[key]; }

const VIDEO_EXTS = [".mp4", ".mov", ".m4v"];
const isVideo = (p) => VIDEO_EXTS.some((x) => String(p || "").toLowerCase().endsWith(x));
const baseName = (p) => String(p || "").split(/[\\/]/).pop();
function setVideo(page, path, index) {
  const layer = S[page].layers[index];
  if (!layer || layer.type !== "cover" || !isVideo(path)) { toast("请把普通 MP4 文件拖到门面视频层", "warn"); return; }
  layer.video = path; rerender(page);
}
function videoField(layer, index) {
  return `<div class="field"><span>MP4 门面视频</span><div class="vdrop ${layer.video ? "has" : ""}" data-dropkind="video" data-layer="${index}" role="button" tabindex="0"><span class="vdrop-ic">${icon("video")}</span><div class="vdrop-text">${layer.video ? `<b>${esc(baseName(layer.video))}</b><small>${esc(layer.video)}</small>` : "<b>拖入 MP4，或点击选择</b>"}</div>${layer.video ? `<button class="btn btn-ghost icon-only" data-clearvideo>${icon("x")}</button>` : ""}</div><small>归档嵌入视频开头，自动修正偏移；产物为可播放的 .mp4</small></div>`;
}
function packOptionsMount(page, state) {
  const el = mount(page, "packopts"); if (!el) return;
  el.innerHTML = `<label class="check"><input type="checkbox" data-model="checksum" ${state.checksum ? "checked" : ""}>附带校验文件（SHA-256）</label><p class="hint">仅上传最后一层的文件 / 分卷；清单与还原说明保留在本地。</p>`;
  if (page === "pack") el.innerHTML += `<div class="sub"><label class="check"><input type="checkbox" data-model="export_key" ${state.export_key ? "checked" : ""}>导出 .mskey 还原钥匙</label><p class="hint">接收方拖入产物和钥匙即可还原。钥匙包含解密凭据，请交给有权接收资源的人。</p></div>`;
  if (page === "pipeline") el.innerHTML += selectField("还原钥匙 · .mskey", state.restore_key_location || "none", [{key:"none", label:"不导出"}, {key:"local", label:"仅保留本地"}, {key:"body", label:"随本体上传分享"}, {key:"hop", label:"随第一跳指引分享（需中转）"}], "restore_key_location", "选择导出后，接收方无需逐层填写密码；本地钥匙会保留。");
  if (page === "pipeline") el.innerHTML += `<div class="sub"><label class="check"><input type="checkbox" data-model="cleanup_after_upload" ${state.cleanup_after_upload ? "checked" : ""}>上传完成后删除本地加工产物</label><p class="hint">全部目标网盘上传并分享成功后，删除本任务生成的压缩包、门面视频、分卷、校验文件和中转文件。保留源文件、原始视频、任务记录及还原说明；仅生成本地产物、暂停或失败时不删除。</p></div>`;
  bindModels(el, state, () => runPanel(page));
}
function requestPreflight(page) {
  const st = S[page]; if (!st || !st.layers || !st.inputs.length || !st.layers.length) return;
  const cfg = { inputs: st.inputs.map((x) => x.path), layers: layerPayload(st), layers_version: 2 };
  const key = JSON.stringify({ ...cfg, output: S.meta.runs });
  if (st._preflightKey === key) return;
  st._preflightKey = key; st._preflight = null; clearTimeout(st._preflightTimer);
  st._preflightTimer = setTimeout(async () => {
    let data;
    try { data = await call("preflight_pack", cfg, page); } catch (e) { data = { ok: false, message: e.message }; }
    if (st._preflightKey !== key) return;
    st._preflight = data; runPanel(page);
  }, 250);
}
function preflightNote(st) { return st.inputs.length ? `<div class="callout ${st._preflight && !st._preflight.ok ? "warn" : ""}">${icon("info")}<span>${esc(st._preflight ? st._preflight.message : "正在估算中间空间和耗时…")}</span></div>` : ""; }
function updateChain(page) {
  const st = S[page];
  if (st.layers && mount(page, "layers")) layerEditor(st, '[data-mount="layers"]', $(`.page[data-page="${page}"]`));
}

function disksMount(page, state) {
  const el = mount(page, "disks"); if (!el) return;
  const isPipeline = page === "pipeline";
  const ch = state._choices;
  const expiry = (ch && ch.expiry) || [{ key: "default", label: S.meta.expiry.default }];
  const access = (ch && ch.access) || [{ key: "default", label: S.meta.access.default }];
  el.innerHTML = diskPicker(state.disks, null, { autoOnly: true }) +
    (isPipeline ? relayBlock(state) : "") +
    `<div class="sub"><div class="sub-title">${icon("link")}分享设置</div><div class="grid2">
      ${selectField("有效期 · 全部网盘", state.expiry, expiry, "expiry", "仅显示所选网盘共同支持的选项")}
      ${selectField("提取码", state.access, access, "access")}
    </div></div>`;
  paintIcons(el);
  bindDiskPicker(el, state.disks, () => { refreshShareChoices(page); });
  bindModels(el, state, (k) => {
    if (k === "hopPw") { runPanel(page); return; }
    if (!isPipeline) return;
    if (k === "form") { rerender(page); refreshShareChoices(page); }
    else if (k === "hop") refreshShareChoices(page);
  });
}
function relayBlock(state) {
  const forms = Object.entries(S.meta.forms).map(([k, v]) => ({ key: k, label: v }));
  const hopDisks = S.meta.providers.filter((p) => p.auto).map((p) => ({ key: p.key, label: p.label }));
  const needHop = state.form !== "direct";
  return `<div class="relay-box"><div class="sub-title">${icon("flow")}中转方式</div>
    <p class="relay-desc">直接分享：本体链接即最终文案。中转：先把下载指引传到第一跳网盘，再对外发布第一跳链接；加密中转会把指引打包为 7z。</p>
    <div class="grid3">
      ${selectField("中转模式", state.form, forms, "form")}
      ${needHop ? selectField("第一跳网盘", state.hop, hopDisks, "hop") : ""}
      ${state.form === "complex" ? pwField("第一跳包密码", state.hopPw, "hopPw", "加密中转必填") : ""}
    </div>
    <label class="field" style="margin-top:12px"><span>给接收方的密码提示</span><input class="input" value="${esc(state.pwdHint)}" data-model="pwdHint"></label></div>`;
}
async function refreshShareChoices(page) {
  const st = S[page];
  const disks = st.disks.slice();
  if (page === "pipeline" && st.form !== "direct" && st.hop) disks.push(st.hop);
  try { st._choices = await call("share_choices", disks); } catch (_) { st._choices = null; }
  const ch = st._choices;
  if (ch && !ch.expiry.some((o) => o.key === st.expiry)) st.expiry = "default";
  if (ch && !ch.access.some((o) => o.key === st.access)) st.access = "default";
  disksMount(page, st); runPanel(page);
}

function schemesMount(page, state) {
  const el = mount(page, "schemes"); if (!el) return;
  if (page === "pipeline") { textStepMount(el, state); return; }
  el.innerHTML = schemePicker(state.schemes) + `<div class="sub">${pwField("魔曰密钥 · 生成魔曰文案时使用", state.key, "key", "默认 ABRACADABRA")}</div>`;
  paintIcons(el);
  bindSchemePicker(el, state.schemes, () => { schemesMount(page, state); runPanel(page); });
  bindModels(el, state);
}

/* ---- pipeline wizard: one step at a time, each confirmed with 下一步 ---- */
const STEPS = ["选择资源", "加密打包", "上传与分享", "链接文案"];
const plainDisks = (keys) => keys.map((k) => (S.meta.providers.find((p) => p.key === k) || {}).label || k).join("、");
const plainSchemes = (keys) => keys.map((k) => (S.meta.schemes.find((x) => x.key === k) || {}).label || k).join("、");
function stepSummary(n) {
  const st = S.pipeline;
  if (n === 1) return st.inputs.length ? st.inputs.length + " 项资源" : "未添加";
  if (n === 2) return st.layers.length ? st.layers.map((l) => layerLabel(l) + (l.password && canLock(l.fmt) ? "🔒" : "")).join(" → ") : "未设置";
  if (n === 3) return st.disks.length ? plainDisks(st.disks) + (st.form !== "direct" ? " · 中转" : "") : "未选网盘";
  if (isRecipeMode(st)) return recipeSummary(st);
  return st.schemes.length ? plainSchemes(st.schemes) : "未选文案";
}
function stepProblem(n) {
  const st = S.pipeline;
  if (n === 1 && !st.inputs.length) return "请先添加要发布的资源";
  if (n === 2 && !st.layers.length) return "请至少设置一层格式";
  if (n === 2 && layerProblems(st).length) return layerProblems(st)[0];
  if (n === 3 && !st.disks.length) return "请至少选择一个本体网盘";
  if (n === 3 && st.form === "complex" && !st.hopPw) return "加密中转需要填写第一跳包密码";
  if (n === 4 && isRecipeMode(st)) return recipeProblems(st)[0] || "";
  if (n === 4 && !st.schemes.length) return "请至少选择一种链接文案";
  return "";
}
function goStep(target) {
  const st = S.pipeline; const cur = st._step || 1;
  target = Math.max(1, Math.min(4, target));
  const show = (n) => { const moved = n !== (st._step || 1); st._step = n; runPanel("pipeline"); if (moved) $(".main").scrollTop = 0; };
  if (target <= cur) { show(target); return; }
  const advance = (n) => {
    if (n >= target) { show(target); return; }
    const bad = stepProblem(n);
    if (bad) { show(n); toast(bad, "warn"); return; }
    if (n === 2) { checkPasswords("pipeline", () => advance(n + 1), () => { show(2); focusMissingPw("pipeline"); }); return; }
    advance(n + 1);
  };
  advance(cur);
}
function renderWizard() {
  const root = $('.page[data-page="pipeline"]'); if (!root) return;
  const st = S.pipeline; const cur = st._step || 1;
  $$("article[data-step]", root).forEach((a) => { a.hidden = +a.dataset.step !== cur; });
  const wz = mount("pipeline", "wizard");
  if (wz) {
    wz.innerHTML = `<ol>${STEPS.map((name, i) => {
      const n = i + 1; const cls = n === cur ? "on" : n < cur ? "done" : "";
      return `<li class="${cls}"><button data-goto="${n}" ${n === cur ? 'aria-current="step"' : ""} title="${esc(name)}：${esc(stepSummary(n))}"><b>${n < cur ? icon("check") : n}</b><span><em>${esc(name)}</em><small>${esc(stepSummary(n))}</small></span></button></li>`;
    }).join("")}</ol>`;
    paintIcons(wz);
    $$("[data-goto]", wz).forEach((b) => b.addEventListener("click", () => goStep(+b.dataset.goto)));
  }
  const nav = mount("pipeline", "stepnav");
  if (nav) {
    nav.innerHTML = (cur > 1 ? `<button class="btn" data-stepprev>${icon("chevron")}上一步</button>` : "") + `<span class="grow">第 ${cur} / 4 步</span>` +
      (cur < 4 ? `<button class="btn btn-primary" data-stepnext>确认，下一步：${esc(STEPS[cur])}${icon("chevron")}</button>`
        : `<span class="step-ready">${icon("check")}设置完成，请在右侧核对后开始发布</span>`);
    paintIcons(nav);
    const pv = $("[data-stepprev]", nav); if (pv) pv.addEventListener("click", () => goStep(cur - 1));
    const nx = $("[data-stepnext]", nav); if (nx) nx.addEventListener("click", () => goStep(cur + 1));
  }
}

/* ---- run / summary panel ---- */
function runPanel(page) {
  if (page === "pipeline" || page === "pack") requestPreflight(page);
  if (page === "pipeline") renderWizard();
  const el = mount(page, "run"); if (!el) return;
  const st = S[page]; const busy = !!S.job;
  const pageEl = $(`.page[data-page="${page}"]`);
  if (pageEl) pageEl.dataset.busy = (!st.result && busy && S.job.kind === pageKind(page)) ? "1" : "";
  if (st.result) { el.innerHTML = resultCard(page, st.result); paintIcons(el); bindResult(el, page, st.result); return; }
  if (busy && S.job.kind === pageKind(page)) { el.innerHTML = progressCard(); paintIcons(el); const pb = $("#runPause", el); if (pb) pb.addEventListener("click", pauseJob); return; }
  el.innerHTML = summaryCard(page);
  paintIcons(el);
  $$("[data-run]", el).forEach((b) => b.addEventListener("click", () => startJob(page, b.dataset.run)));
}
function pageKind(page) { return page === "pipeline" ? "pipeline" : page; }
function missingFor(page) {
  const st = S[page]; const m = [];
  if (page === "restore") { if (!st.inputs.length) m.push("添加压缩包或下载文件夹"); if (!st.keyFile) m.push("添加 .mskey 还原钥匙"); return m; }
  if (page === "textrestore") return textRestoreProblems(st);
  if (page === "upload") { if (!st.files.length) m.push("添加要上传的文件"); if (!st.disks.length) m.push("选择至少一个网盘"); return m; }
  if (!st.inputs.length) m.push("添加资源");
  if (!st.layers.length) m.push("设置至少一层格式");
  m.push(...layerProblems(st));
  if (st.inputs.length && st.layers.length) { if (!st._preflight) m.push("等待空间预检"); else if (!st._preflight.ok) m.push(st._preflight.message); }
  if (page === "pipeline") {
    if (st.restore_key_location === "hop" && st.form === "direct") m.push("钥匙随第一跳交付时，请选择中转方式");
    if (!st.disks.length) m.push("选择本体网盘");
    if (isRecipeMode(st)) m.push(...recipeProblems(st));
    else if (!st.schemes.length) m.push("选择至少一种链接文案");
    if (st.form === "complex" && !st.hopPw) m.push("填写第一跳包密码");
    if ((st._step || 1) < 4 && !m.length) m.push(`按步骤确认设置（当前第 ${st._step || 1} / 4 步）`);
  }
  return m;
}
function missingNote(m) { return m.length ? `<div class="missing"><b>${icon("info")}还缺：</b><ul>${m.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""; }
function pwRow(st) {
  if (hasPassword(st)) { const miss = missingLocked(st); return [miss ? `已设置 · ${miss} 层未填` : "已设置", !!miss]; }
  return ["未设置 · 仅压缩", true];
}
function summaryCard(page) {
  const st = S[page]; const rows = [];
  const push = (k, v, warn) => rows.push(`<div><dt>${esc(k)}</dt><dd class="${warn ? "warn" : ""}">${v}</dd></div>`);
  const busy = !!S.job; const miss = missingFor(page);
  const dis = busy || miss.length ? "disabled" : "";
  if (page === "textrestore") return textRestoreSummary(st, miss, busy, dis);
  const notes = missingNote(miss) + busyNote(busy) + (page === "upload" ? "" : preflightNote(st));
  if (page === "restore") return `<div class="run"><h3>校验并还原</h3><p class="hint">根据钥匙自动完成全部处理层，校验不符或缺卷时停止。</p>${missingNote(miss)}${busyNote(busy)}<button class="btn btn-primary btn-lg btn-block" data-run="go" ${dis}>${icon("folder")}开始还原</button><p class="run-note">输出到空目录，全部层成功后交付还原结果。</p></div>`;
  if (page === "pack") {
    push("资源", st.inputs.length ? st.inputs.length + " 项" : "<span class='muted'>未选择</span>", !st.inputs.length);
    push("加密层", chainText(st));
    const pw = pwRow(st); push("密码", esc(pw[0]), pw[1]);
    push("产物", esc(outExt(st) || "—"));
    push("校验文件", st.checksum ? "附带 SHA-256" : "不附带");
    return `<div class="run"><h3>生成本地产物</h3><dl class="summary">${rows.join("")}</dl>${notes}
      <div class="run-actions"><button class="btn btn-primary btn-lg btn-block" data-run="go" ${dis}>${icon("lock")}开始打包</button></div>
      <p class="run-note">产物目录：${esc(S.meta.runs)}。${st.export_key ? "已选择导出还原钥匙；普通清单不包含密码。" : "密码仅用于本次打包；未选择导出钥匙。"}</p></div>`;
  }
  if (page === "upload") {
    push("文件", st.files.length ? st.files.length + " 个" : "<span class='muted'>未选择</span>", !st.files.length);
    push("网盘", diskNames(st.disks), !st.disks.length);
    push("文案", st.schemes.length ? schemeNames(st.schemes) : "仅原始链接");
    return `<div class="run"><h3>上传并分享</h3><dl class="summary">${rows.join("")}</dl>${notes}
      <div class="run-actions"><button class="btn btn-primary btn-lg btn-block" data-run="go" ${dis}>${icon("cloud")}上传并分享</button></div>
      <p class="run-note">每个文件上传成功后自动保存进度，中断可在任务中心继续。</p></div>`;
  }
  // pipeline
  push("资源", st.inputs.length ? st.inputs.length + " 项" : "<span class='muted'>未选择</span>", !st.inputs.length);
  push("加密层", chainText(st));
  const pw = pwRow(st); push("密码", esc(pw[0]), pw[1]);
  push("产物", esc(outExt(st) || "—"));
  push("本体网盘", diskNames(st.disks), !st.disks.length);
  push("分享方式", S.meta.forms[st.form] + (st.form !== "direct" ? " · " + diskNames([st.hop]) : ""), st.form === "complex" && !st.hopPw);
  if (isRecipeMode(st)) push("文案", esc(recipeSummary(st)) + (st.recipes.some((r) => r.carrier === "framewords") ? " · 需联网" : ""), !st.recipes.length);
  else push("文案", st.schemes.length ? schemeNames(st.schemes) : "<span class='muted'>未选</span>", !st.schemes.length);
  push("本地产物", st.cleanup_after_upload ? "分享完成后删除 · 保留源文件" : "保留");
  return `<div class="run"><h3>开始发布</h3><dl class="summary">${rows.join("")}</dl>${notes}
    <div class="run-actions">
      <button class="btn btn-primary btn-lg btn-block" data-run="publish" ${dis}>${icon("flow")}打包并上传分享</button>
      <button class="btn btn-block" data-run="prepare" ${dis}>${icon("lock")}仅生成本地产物</button>
    </div>
    <p class="run-note">全程逐文件校验并保存检查点，支持暂停和继续。密码不写入任务文件。</p></div>`;
}
function busyNote(busy) { return busy ? `<div class="busy-note">${icon("info")}<span>已有任务在运行，请等它完成或先暂停。</span></div>` : ""; }
function chainText(st) { if (!st.layers || !st.layers.length) return "<span class='muted'>未设置</span>"; return st.layers.map((l) => esc(layerLabel(l)) + (l.password ? "🔒" : "")).join(" → "); }
function diskNames(keys) { if (!keys.length) return "<span class='muted'>未选</span>"; return keys.map((k) => { const p = S.meta.providers.find((x) => x.key === k); return esc(p ? p.label : k); }).join("、"); }
function schemeNames(keys) { return keys.map((k) => { const s = S.meta.schemes.find((x) => x.key === k); return esc(s ? s.label : k); }).join("、"); }

function progressCard() {
  const job = S.job; const task = job.task;
  let stages = "";
  if (task && task.stages && task.stages.length) {
    stages = `<div class="stages">${task.stages.map((s) => {
      const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
      const done = s.state === "shared" || s.state === "complete";
      return `<div class="stage-row"><div class="stage-top">${avatar(s.disk, s.label)}<b>${esc(s.label)}</b><span class="grow"></span><em>${s.done}/${s.total}</em>${badge(s.state)}</div>
        <div class="bar ${done ? "done" : ""}"><span style="width:${done ? 100 : pct}%"></span></div></div>`;
    }).join("")}</div>`;
  } else {
    stages = `<div class="bar indeterminate"><span></span></div>`;
  }
  return `<div class="progress-card"><div class="progress-head"><h3><span class="spinner"></span> ${esc(job.title || "任务进行中")}</h3>${badge("running")}</div>
    <div class="progress-step">${esc(job.step || "处理中…")}</div>${stages}
    <div class="run-actions" style="margin-top:16px"><button class="btn btn-block" id="runPause">${icon("pause")}暂停任务</button></div></div>`;
}
function badge(state) { return `<span class="badge ${STATE_CLASS[state] || ""}">${esc(STATE_LABEL[state] || state)}</span>`; }
function cleanupNote(task) {
  const c = task && task.cleanup;
  if (!c || !c.enabled) return "";
  const done = c.state === "complete";
  const text = done ? `已删除 ${c.deleted} 个本地加工文件，源文件和任务记录保留。` : c.state === "pending" ? "上传分享完成后自动删除本地加工产物，源文件保留。" : `部分加工产物未清理，已保留文件；源文件保留。可用 CLI 继续该任务重试清理。`;
  return `<div class="callout ${done ? "" : "warn"}">${icon(done ? "check" : "info")}<span>${esc(text)}</span></div>`;
}

function resultCard(page, result) {
  if (result.error) {
    const paused = result.paused;
    return `<div class="result-card"><div class="result-title ${paused ? "paused" : "error"}"><span class="ok-ic">${icon(paused ? "pause" : "warn")}</span>${paused ? "任务已暂停" : "任务未完成"}</div>
      <p class="result-msg">${esc(result.error)}</p>
      <div class="run-actions">${result.plan ? `<button class="btn btn-primary btn-block" data-resume="${esc(result.plan)}">${icon("play")}继续任务</button>` : ""}
      <button class="btn btn-block" data-newrun>${icon("refresh")}重新开始</button></div></div>`;
  }
  if (page === "textrestore") return textRestoreResult(result);
  if (page === "restore") return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>还原完成</div><p class="result-msg">产物校验通过，已完成 ${esc(result.layers)} 层处理。</p><div class="mini-files">${(result.files || []).map(f => `<div class="mini-file">${esc(f.name)}</div>`).join("")}</div><div class="run-actions"><button class="btn btn-primary btn-block" data-open="${esc(result.out)}">${icon("folder")}打开还原目录</button><button class="btn btn-block" data-newrun>还原其他文件</button></div></div>`;
  if (page === "pack") {
    const files = (result.files || []).concat(result.parts || []);
    return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>打包完成</div>
      <p class="result-msg">格式链：${esc(result.chain || "")}</p>
      ${result.restore_key ? `<p class="callout">已导出还原钥匙：${esc(baseName(result.restore_key))}</p>` : ""}
      <div class="mini-files">${files.map((f) => `<div class="mini-file"><span>${esc(f.name)}</span><span>${fmtSize(f.size)}</span></div>`).join("")}</div>
      <div class="run-actions"><button class="btn btn-primary btn-block" data-open="${esc(result.out)}">${icon("folder")}打开产物目录</button><button class="btn btn-block" data-newrun>${icon("plus")}新建打包</button></div></div>`;
  }
  // publish / upload success with copies
  const copies = result.copies || {};
  const keys = Object.keys(copies);
  if (!keys.length && page === "pipeline" && isRecipeMode(S.pipeline)) return recipeResultCard(result);
  const tabs = keys.map((k, i) => `<button class="${i === 0 ? "on" : ""}" data-tab="${esc(k)}">${esc(schemeNames([k]))}</button>`).join("");
  const first = keys[0];
  return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>发布完成</div>
    <p class="result-msg">分享链接已生成以下加密文案，点击标签切换。</p>
    ${cleanupNote(result.task)}
    ${keys.length ? `<div class="tabs">${tabs}</div><div class="copybox"><pre id="copyPre">${esc(copies[first] || "")}</pre><button class="btn btn-sm btn-primary" id="copyBtn">${icon("copy")}复制</button></div>` : "<p class='muted'>未选文案方案。</p>"}
    <div class="run-actions" style="margin-top:14px"><button class="btn btn-block" data-open="${esc(result.plan || "")}">${icon("folder")}打开任务目录</button><button class="btn btn-block" data-newrun>${icon("plus")}新建任务</button></div></div>`;
}
function bindResult(el, page, result) {
  const copies = result.copies || {};
  $$("[data-tab]", el).forEach((b) => b.addEventListener("click", () => {
    $$("[data-tab]", el).forEach((x) => x.classList.toggle("on", x === b));
    $("#copyPre", el).textContent = copies[b.dataset.tab] || "";
  }));
  const cb = $("#copyBtn", el); if (cb) cb.addEventListener("click", () => copy($("#copyPre", el).textContent, cb));
  $$("[data-open]", el).forEach((b) => b.addEventListener("click", () => { if (b.dataset.open) call("open_path", b.dataset.open).catch((e) => toast(e.message, "err")); }));
  const nr = $("[data-newrun]", el); if (nr) nr.addEventListener("click", () => { S[page].result = null; if (page === "pipeline") { S.pipeline._step = 1; S.pipeline.cleanup_after_upload = false; } rerender(page); });
  const rs = $("[data-resume]", el); if (rs) rs.addEventListener("click", () => resumeTask(rs.dataset.resume, page));
}

/* ---- job lifecycle ---- */
async function startJob(page, mode, confirmed) {
  const st = S[page];
  if (!confirmed && page !== "upload" && page !== "restore" && page !== "textrestore") {
    checkPasswords(page, () => startJob(page, mode, true), () => { if (page === "pipeline") goStep(2); focusMissingPw(page); });
    return;
  }
  try {
    let data;
    if (page === "textrestore") {
      data = await call("start_text_restore", textRestorePayload(st));
    } else if (page === "restore") {
      data = await call("start_restore", { source: st.inputs[0].path, key_file: st.keyFile.path, out: st.out });
    } else if (page === "pack") {
      data = await call("start_pack", { inputs: st.inputs.map((f) => f.path), layers: layerPayload(st), layers_version: 2, checksum: st.checksum, export_key: !!st.export_key });
    } else if (page === "upload") {
      data = await call("start_upload", { task_name: st.task_name, folder_name: st.folder_name, files: st.files.map((f) => f.path), checksum: st.checksum, body_disks: st.disks, expiry: st.expiry, access: st.access, schemes: st.schemes, key: st.key });
    } else {
      const cfg = { task_name: st.task_name, folder_name: st.folder_name, cleanup_after_upload: st.cleanup_after_upload, restore_key_location: st.restore_key_location || "none", inputs: st.inputs.map((f) => f.path), layers: layerPayload(st), layers_version: 2, checksum: st.checksum, body_disks: st.disks, form: st.form, hop_disk: st.hop, hop_password: st.hopPw, pwd_hint: st.pwdHint, expiry: st.expiry, access: st.access, schemes: st.schemes, key: st.key, upload: mode === "publish" };
      if (isRecipeMode(st)) Object.assign(cfg, recipePipelinePayload(st));
      data = await call("start_pipeline", cfg);
    }
    S.job = data; S.job.task = null; st.result = null;
    saveSettings();
    renderJobCard(); renderAll();
  } catch (e) { toast(e.message, "err"); }
}
function layerPayload(st) { return st.layers.map((l) => {
  const type = l.type || "archive";
  if (type === "archive") return { type, fmt: l.fmt, password: l.password || "", header_enc: l.header_enc !== false, level: l.level == null ? null : l.level };
  const key = { cover: "video", split: "size", rename: "ext" }[type]; return { type, [key]: l[key] || "" };
}); }
async function resumeTask(plan, page) {
  try {
    const st = page ? S[page] : null;
    if (!st) {
      const detail = await call("task_detail", plan);
      const req = detail.resume_requirements || {};
      if ((req.recipes || []).length || req.legacy_key || req.hop_password) {
        resumeCredentials(plan, req); return;
      }
    }
    const args = [plan, st ? st.key : "", (st && st.hopPw) || ""];
    if (page === "pipeline" && isRecipeMode(st)) args.push(recipeResumePayload(st));
    const data = await call("resume_task", ...args);
    S.job = data; S.job.task = null; if (st) st.result = null;
    renderJobCard(); renderAll();
    go("tasks");
  } catch (e) { toast(e.message, "err"); }
}
function resumeCredentials(plan, req) {
  const recipes = req.recipes || [];
  const slots = recipes.flatMap(r => [...r.layers, r.carrier].filter(x => x.secret_slot).map(x => ({slot:x.secret_slot, name:r.name})));
  const videos = recipes.filter(r => r.carrier.format_id === "framewords");
  const box = modal(`<h2>继续交付</h2><p class="hint">只重试尚未完成的方案。密钥和视频源仅用于本次运行。</p>
    ${slots.map(x => `<label class="field"><span>${esc(x.name)} · ${esc(x.slot)}</span><input class="input" type="password" autocomplete="off" data-resume-secret="${esc(x.slot)}"></label>`).join("")}
    ${req.legacy_key ? '<label class="field"><span>魔曰密钥</span><input class="input" type="password" data-resume-legacy placeholder="默认 ABRACADABRA" autocomplete="off"></label>' : ""}
    ${req.hop_password ? '<label class="field"><span>第一跳压缩密码</span><input class="input" type="password" data-resume-hop autocomplete="off"></label>' : ""}
    ${videos.map(r => `<label class="field"><span>${esc(r.name)} · 源视频</span><div class="btn-row"><input class="input" readonly data-resume-video="${esc(r.id)}"><button class="btn" data-resume-pick="${esc(r.id)}">选择视频</button></div></label>`).join("")}
    ${recipes.map(r => `<label class="check"><input type="checkbox" data-resume-export="${esc(r.id)}">为 ${esc(r.name)} 导出 .tkey（敏感文件，默认本地）</label>`).join("")}
    <div class="modal-actions"><button class="btn" data-cancel>取消</button><button class="btn btn-primary" data-go>继续</button></div>`);
  $("[data-cancel]", box).onclick = closeModal;
  $$("[data-resume-pick]", box).forEach(b => b.onclick = async () => {
    try { const paths = await call("pick_files", false, true); const field = $$("[data-resume-video]", box).find(x => x.dataset.resumeVideo === b.dataset.resumePick); if (paths[0]) field.value = paths[0]; }
    catch(e) { toast(e.message, "err"); }
  });
  $("[data-go]", box).onclick = async () => {
    const fields = $$("[data-resume-secret]", box), sources = $$("[data-resume-video]", box);
    if (fields.some(x => !x.value) || sources.some(x => !x.value) || (req.hop_password && !$("[data-resume-hop]", box).value)) { toast("请补齐本次所需密钥和视频", "warn"); return; }
    const runtime = {secrets:Object.fromEntries(fields.map(x => [x.dataset.resumeSecret,x.value])), video_sources:Object.fromEntries(sources.map(x => [x.dataset.resumeVideo,x.value])), export_keys:$$("[data-resume-export]", box).filter(x => x.checked).map(x => x.dataset.resumeExport)};
    const legacy = $("[data-resume-legacy]", box)?.value || "", hop = $("[data-resume-hop]", box)?.value || "";
    const button = $("[data-go]", box); button.disabled = true;
    try { S.job = await call("resume_task", plan, legacy, hop, runtime); closeModal(); renderJobCard(); go("tasks"); }
    catch(e) { toast(e.message, "err"); button.disabled = false; }
    finally { runtime.secrets = {}; }
  };
}
async function pauseJob() { try { await call("pause"); toast("正在暂停…", "warn"); } catch (e) { toast(e.message, "err"); } }
$("#jobPause").addEventListener("click", pauseJob);
$("#jobView").addEventListener("click", () => { if (S.job) go(S.job.kind === "account" ? "accounts" : S.job.kind === "text-restore" ? "textrestore" : ["pipeline", "pack", "upload", "restore"].includes(S.job.kind) ? S.job.kind : "tasks"); });

function renderJobCard() {
  renderOutputDir();
  const card = $("#jobCard");
  if (!S.job) { card.hidden = true; return; }
  card.hidden = false;
  $("#jobTitle").textContent = S.job.title || "任务运行中";
  $("#jobStep").textContent = S.job.step || "";
}

/* handle a finished job event from the poller */
function onJobEvent(ev) {
  const { state, job, result, error } = ev;
  const kind = job.kind;
  const page = kind === "text-restore" ? "textrestore" : kind;
  if (state === "running") { S.job = Object.assign(S.job || {}, job); renderJobCard(); return; }
  S.job = null; renderJobCard();
  if (kind === "account") {
    if (state === "done") toast("账号操作完成", "ok"); else toast(error || "账号操作未完成", "warn");
    S.accountReport = result && (result.checks || (result.selfcheck ? [result.selfcheck] : null));
    loadAccounts();
  } else if (S[page]) {
    if (state === "done") { S[page].result = result || { ok: true }; toast("任务完成", "ok"); }
    else { S[page].result = Object.assign({ error: error || "任务中断", paused: state === "paused" }, result || {}); if (result && result.plan) S[page].result.plan = result.plan; toast(error || "任务中断", state === "paused" ? "warn" : "err"); }
  }
  loadTasks();
  renderAll();
}

/* ---------- page rerender dispatch ---------- */
function rerender(page) {
  const st = S[page];
  if (page === "pipeline") { namingMount(page, st); renderFilesMount("pipeline", st, "inputs", false); layerEditor(st, '[data-mount="layers"]', $('.page[data-page="pipeline"]')); packOptionsMount("pipeline", st); disksMount("pipeline", st); schemesMount("pipeline", st); runPanel("pipeline"); }
  else if (page === "pack") { renderFilesMount("pack", st, "inputs", false); layerEditor(st, '[data-mount="layers"]', $('.page[data-page="pack"]')); packOptionsMount("pack", st); runPanel("pack"); }
  else if (page === "upload") { namingMount(page, st); renderFilesMount("upload", st, "files", true); disksMount("upload", st); schemesMount("upload", st); runPanel("upload"); }
  else if (page === "restore") { renderRestore(); runPanel(page); }
  else if (page === "textrestore") { renderTextRestore(); runPanel(page); }
  else if (page === "codec") renderCodec();
  else if (page === "tasks") renderTasks();
  else if (page === "accounts") renderAccounts();
  else if (page === "settings") renderSettings();
}
function renderAll() { ["pipeline", "pack", "upload", "restore", "textrestore"].forEach((p) => { if (S.page === p) rerender(p); else runPanel(p); }); }

async function addRestorePaths(paths) {
  const st = S.restore;
  const values = await call("describe_paths", paths);
  const keys = values.filter(f => f.path.toLowerCase().endsWith(".mskey") && !f.dir);
  if (keys.length > 1) throw new Error("请一次添加一把对应的还原钥匙");
  if (keys.length) st.keyFile = keys[0];
  const inputs = values.filter(f => !f.path.toLowerCase().endsWith(".mskey"));
  if (inputs.length) {
    const folders = inputs.filter(f => f.dir);
    if (folders.length > 1 || (folders.length && inputs.length > 1)) throw new Error("请选择一个下载文件夹，或同目录中的分卷");
    st.inputs = inputs;
  }
  st.result = null; rerender("restore");
}
function renderRestore() {
  const st = S.restore, el = mount("restore", "restorefiles");
  el.innerHTML = `${dropzone("restore", "拖入压缩包、分卷文件夹和 .mskey", "两个文件也可以一起拖入", false)}
    <div class="row" style="gap:8px;margin:12px 0;flex-wrap:wrap"><button class="btn" data-restorepick="out">选择还原目录</button><button class="btn btn-ghost" data-restoreclear>清空</button></div>
    <dl class="summary"><div><dt>下载资源</dt><dd>${st.inputs.length ? st.inputs.map(f => esc(f.name)).join("、") : "未选择"}</dd></div><div><dt>还原钥匙</dt><dd>${st.keyFile ? esc(st.keyFile.name) : "未选择 .mskey"}</dd></div><div><dt>还原目录</dt><dd>${esc(st.out || "自动创建新的还原目录")}</dd></div></dl>`;
  paintIcons(el);
  $$("[data-act]", el).forEach(b => b.addEventListener("click", async () => {
    try { await addRestorePaths(await call({"paste-paths":"clipboard_paths", "pick-files":"pick_files", "pick-folder":"pick_folder"}[b.dataset.act])); } catch (e) { toast(e.message, "err"); }
  }));
  $$("[data-restorepick]", el).forEach(b => b.addEventListener("click", async () => {
    try { const mode = b.dataset.restorepick, paths = await call(mode === "file" ? "pick_files" : "pick_folder"); if (!paths.length) return; if (mode === "out") { st.out = paths[0]; rerender("restore"); } else await addRestorePaths(paths); } catch (e) { toast(e.message, "err"); }
  }));
  $("[data-restoreclear]", el).addEventListener("click", () => { st.inputs = []; st.keyFile = null; st.out = ""; st.result = null; rerender("restore"); });
}

/* ---------- init per-page (one-time structure fill) ---------- */
/* ---------- v0.2 第四步：文案交付方案 & 文案还原 ----------
 * 对接 desktop/api.py 已实现的 text_capabilities / start_pipeline(recipes) /
 * resume_task(text_cfg) / start_text_restore。配方是公开结构；密钥只在内存中，
 * 不进入 saveSettings、日志或任务。钥匙导出默认关闭。 */
const TEXT_LAYER_SCHEMES = ["beast", "mojibake", "hajimi", "base64", "base64url", "base32", "base85", "hex", "url", "reverse", "rot13"];
const TEXT_LAYER_KIND = { beast: "编码", hajimi: "编码", mojibake: "加密", base64: "编码", base64url: "编码", base32: "编码", base85: "编码", hex: "编码", url: "编码", reverse: "变换", rot13: "变换" };
// 仅为字符膨胀粗估；真实长度以生成结果为准（魔曰/兽曰含随机化）。
const TEXT_GROWTH = { base64: 4 / 3, base64url: 4 / 3, base32: 1.6, base85: 1.25, hex: 2, url: 3, reverse: 1, rot13: 1, beast: 4, hajimi: 4, mojibake: 1.5 };
const ESTIMATE_INPUT = 64; // 典型分享链接 + 提取码的字符数
function textLabel(k) { const s = (S.meta && S.meta.schemes || []).find((x) => x.key === k); return s ? s.label : k; }
function ensureText(st) {
  if (!st.textMode) st.textMode = "legacy";
  if (!Array.isArray(st.recipes)) st.recipes = [];
  if (!st.textSecrets) st.textSecrets = {};
  if (!st.textVideos) st.textVideos = {};
  if (!Array.isArray(st.exportKeys)) st.exportKeys = [];
  return st;
}
function isRecipeMode(st) { return ensureText(st).textMode === "recipes"; }
function videoCap() { return ((S.textCaps && S.textCaps.carriers) || []).find((c) => c.format_id === "framewords") || null; }
function newRecipeId(st) { let i = st.recipes.length + 1; while (st.recipes.some((r) => r.id === "r" + i)) i++; return "r" + i; }
function newRecipe(st, preset) {
  const id = newRecipeId(st);
  const r = { id, name: "方案 " + id.slice(1), layers: [], carrier: "text", videoPw: false };
  if (preset === "mojibake-video") { r.name = "魔曰 → 视频"; r.layers = [{ id: "l1", scheme: "mojibake", keyed: true }]; r.carrier = "framewords"; r.videoPw = true; }
  else if (preset === "base64") { r.name = "Base64 纯文本"; r.layers = [{ id: "l1", scheme: "base64", keyed: false }]; }
  return r;
}
function layerSlot(r, l) { return l.secretSlot || r.id + "/" + l.id; }
function videoSlot(r) { return r.secretSlot || r.id + "/video"; }
function recipeFromPublic(r) {
  return {id:r.id, name:r.name, layers:r.layers.map(l => ({id:l.id, scheme:l.scheme, params:l.params,
    keyed:!!l.secret_slot, secretSlot:l.secret_slot})), carrier:r.carrier.format_id,
    videoPw:!!r.carrier.secret_slot, secretSlot:r.carrier.secret_slot};
}
function recipeToPublic(r) {
  return { version: 1, id: r.id, name: r.name || r.id,
    layers: r.layers.map((l) => ({ id: l.id, scheme: l.scheme, version: 1, params: l.params || {}, secret_slot: l.scheme === "mojibake" && l.keyed ? layerSlot(r, l) : null })),
    carrier: r.carrier === "framewords"
      ? { format_id: "framewords", version: 1, mode: "standard", params: {}, secret_slot: r.videoPw ? videoSlot(r) : null }
      : { format_id: "text", version: 1, mode: "plain", params: {}, secret_slot: null } };
}
function recipeSecrets(st) {
  const out = {};
  st.recipes.forEach((r) => { const p = recipeToPublic(r); [...p.layers, p.carrier].forEach((x) => { if (x.secret_slot && st.textSecrets[x.secret_slot]) out[x.secret_slot] = st.textSecrets[x.secret_slot]; }); });
  return out;
}
function recipeVideos(st) { const out = {}; st.recipes.forEach((r) => { if (r.carrier === "framewords" && st.textVideos[r.id]) out[r.id] = st.textVideos[r.id]; }); return out; }
function recipeExports(st) { return st.exportKeys.filter((id) => st.recipes.some((r) => r.id === id)); }
function recipePipelinePayload(st) {
  return { schemes: [], recipes: st.recipes.map(recipeToPublic), text_secrets: recipeSecrets(st), text_video_sources: recipeVideos(st), export_text_keys: recipeExports(st) };
}
function recipeResumePayload(st) { return { secrets: recipeSecrets(st), video_sources: recipeVideos(st), export_keys: recipeExports(st) }; }
function recipeSummary(st) {
  if (!st.recipes.length) return "未添加方案";
  return st.recipes.map((r) => (r.layers.length ? r.layers.map((l) => textLabel(l.scheme)).join("→") : "裸链接") + "→" + (r.carrier === "framewords" ? "视频" : "文本")).join("；");
}
function recipeProblems(st) {
  const m = [];
  if (!st.recipes.length) { m.push("至少添加一个文案交付方案"); return m; }
  st.recipes.forEach((r) => {
    const name = r.name || r.id;
    if (r.layers.length > 32) m.push(`${name}：文字层最多 32 层`);
    r.layers.forEach((l) => { if (l.scheme === "mojibake" && l.keyed && !st.textSecrets[layerSlot(r, l)]) m.push(`${name}：填写魔曰密钥`); });
    if (r.carrier === "framewords") {
      const cap = videoCap();
      if (!cap || !cap.can_encode) m.push(`${name}：当前环境不支持帧语视频载体`);
      if (!st.textVideos[r.id]) m.push(`${name}：选择本地源视频`);
      if (r.videoPw && !st.textSecrets[videoSlot(r)]) m.push(`${name}：填写视频解锁密码`);
    }
  });
  if (st.recipes.length > 16) m.push("最多 16 个交付方案");
  return m;
}
function estimateChars(r) {
  let n = ESTIMATE_INPUT; const steps = [];
  r.layers.forEach((l) => { n = Math.ceil(n * (TEXT_GROWTH[l.scheme] || 1)); steps.push(n); });
  return steps;
}
function recipeCard(st, r, i) {
  const cap = videoCap();
  const steps = estimateChars(r);
  const opts = TEXT_LAYER_SCHEMES.map((k) => ({ key: k, label: textLabel(k) + " · " + TEXT_LAYER_KIND[k] }));
  const layers = r.layers.map((l, j) => `<div class="tlayer" data-tl="${j}"><span class="tl-idx">${j + 1}</span>
      <select class="select" data-tlscheme>${opts.map((o) => `<option value="${o.key}" ${o.key === l.scheme ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select>
      ${l.scheme === "mojibake" ? `<label class="chk"><input type="checkbox" data-tlkeyed ${l.keyed ? "checked" : ""}>使用密钥</label>${l.keyed ? `<input class="input" type="password" autocomplete="off" data-secret="${esc(layerSlot(r, l))}" placeholder="魔曰密钥（不保存）" value="${esc(st.textSecrets[layerSlot(r, l)] || "")}">` : "<small class='muted'>默认密钥 ABRACADABRA，仅混淆</small>"}` : `<small class="muted">${TEXT_LAYER_KIND[l.scheme] === "编码" ? "仅编码，不提供密码保护" : "可逆变换，不提供密码保护"}</small>`}
      <em class="tl-chars" title="按 ${ESTIMATE_INPUT} 字符链接粗估">≈${steps[j]} 字</em>
      <span class="grow"></span><button class="btn btn-sm btn-ghost" data-tlup ${j === 0 ? "disabled" : ""} title="上移">↑</button><button class="btn btn-sm btn-ghost" data-tldown ${j === r.layers.length - 1 ? "disabled" : ""} title="下移">↓</button><button class="btn btn-sm btn-ghost" data-tlrm title="删除">✕</button></div>`).join("");
  const video = r.carrier === "framewords";
  const exported = st.exportKeys.includes(r.id);
  return `<div class="recipe" data-recipe="${i}">
    <div class="recipe-head"><input class="input" data-rname maxlength="60" value="${esc(r.name)}" aria-label="方案名称"><span class="grow"></span><button class="btn btn-sm btn-ghost" data-rrm>${icon("trash")}删除方案</button></div>
    <div class="tl-chain"><div class="tlayer origin"><span class="tl-idx">0</span><b>分享文案原文</b><em class="tl-chars">≈${ESTIMATE_INPUT} 字</em></div>${layers || "<p class='hint'>未加文字层：直接交付裸链接。</p>"}</div>
    <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn btn-sm" data-tladd ${r.layers.length >= 32 ? "disabled" : ""}>${icon("plus")}添加文字层</button></div>
    <div class="carrier"><span class="carrier-label">末端载体</span>
      <label class="chk"><input type="radio" name="carrier-${esc(r.id)}" value="text" data-rcarrier ${video ? "" : "checked"}>纯文本（本机离线）</label>
      <label class="chk ${cap ? "" : "disabled"}"><input type="radio" name="carrier-${esc(r.id)}" value="framewords" data-rcarrier ${video ? "checked" : ""} ${cap ? "" : "disabled"}>帧语视频（官网网页模式）</label></div>
    ${video ? `<div class="callout warn">${icon("info")}<span>视频载体由密送自动操作帧语官网生成并独立回读校验，<b>需要联网并依赖官网可用</b>；不是离线编解码。仅开放已验证的标准画面模式，容量由官网决定，超出时会明确失败。B 站链接暂不支持自动读取。</span></div>
      <div class="grid2"><div class="field"><span>本地源视频</span><div class="row" style="gap:6px"><input class="input" readonly value="${esc(st.textVideos[r.id] || "")}" placeholder="未选择"><button class="btn btn-sm" data-rvideo>选择</button></div></div>
      <div class="field"><span><label class="chk"><input type="checkbox" data-rvideopw ${r.videoPw ? "checked" : ""}>视频解锁密码</label></span>${r.videoPw ? `<input class="input" type="password" autocomplete="off" data-secret="${esc(videoSlot(r))}" placeholder="仅交给官网页面，不保存" value="${esc(st.textSecrets[videoSlot(r)] || "")}">` : "<small class='muted'>不设密码时任何人可读取</small>"}</div></div>` : ""}
    <label class="chk key-export"><input type="checkbox" data-rexport ${exported ? "checked" : ""}>导出文案还原钥匙 .tkey（默认关闭；仅保存在本地，持有钥匙即可还原，请按解密凭据交付）</label>
  </div>`;
}
function textStepMount(el, st) {
  ensureText(st);
  if (!S.textCaps && !S._textCapsLoading) {
    S._textCapsLoading = true;
    call("text_capabilities").then((c) => { S.textCaps = c; }).catch(() => { S.textCaps = { carriers: [] }; }).finally(() => { S._textCapsLoading = false; if (S.page === "pipeline") schemesMount("pipeline", st); });
  }
  const legacy = st.textMode !== "recipes";
  const mode = `<div class="seg" role="tablist"><button class="${legacy ? "on" : ""}" data-tmode="legacy">并列文案（旧版）</button><button class="${legacy ? "" : "on"}" data-tmode="recipes">交付方案（文字链 + 载体）</button></div>`;
  if (legacy) {
    el.innerHTML = mode + schemePicker(st.schemes) + `<div class="sub">${pwField("魔曰密钥 · 生成魔曰文案时使用", st.key, "key", "默认 ABRACADABRA")}</div>`;
    paintIcons(el);
    bindSchemePicker(el, st.schemes, () => { schemesMount("pipeline", st); runPanel("pipeline"); });
    bindModels(el, st);
  } else {
    el.innerHTML = mode + `<p class="hint">每个方案独立生成一份结果：按顺序处理文字，再输出纯文本或视频。编码层（Base64、兽曰等）只改变写法，不是密码保护；只有带密钥的魔曰层和视频密码提供加密。密钥只用于本次，不写入任务或设置。</p>`
      + `<div class="recipes">${st.recipes.map((r, i) => recipeCard(st, r, i)).join("") || "<p class='muted'>尚未添加方案。</p>"}</div>`
      + `<div class="row" style="gap:8px;flex-wrap:wrap;margin-top:10px"><button class="btn" data-radd="plain">${icon("plus")}裸链接 → 文本</button><button class="btn" data-radd="base64">${icon("plus")}Base64 → 文本</button><button class="btn" data-radd="mojibake-video" ${videoCap() ? "" : "disabled"}>${icon("plus")}魔曰 → 视频</button></div>`
      + `<p class="hint">容量：纯文本上限 1 MB；“≈字”为按 ${ESTIMATE_INPUT} 字符链接的粗估，魔曰/兽曰含随机化，以生成结果为准，不会自动截断。</p>`;
    paintIcons(el);
    bindRecipeEditor(el, st);
  }
  $$("[data-tmode]", el).forEach((b) => b.addEventListener("click", () => { st.textMode = b.dataset.tmode; schemesMount("pipeline", st); runPanel("pipeline"); }));
}
function bindRecipeEditor(el, st) {
  const redraw = () => { schemesMount("pipeline", st); runPanel("pipeline"); };
  $$("[data-radd]", el).forEach((b) => b.addEventListener("click", () => { if (st.recipes.length >= 16) return toast("最多 16 个方案", "warn"); st.recipes.push(newRecipe(st, b.dataset.radd)); redraw(); }));
  $$("[data-recipe]", el).forEach((card) => {
    const r = st.recipes[+card.dataset.recipe]; if (!r) return;
    $("[data-rname]", card).addEventListener("input", (e) => { r.name = e.target.value; });
    $("[data-rname]", card).addEventListener("change", () => runPanel("pipeline"));
    $("[data-rrm]", card).addEventListener("click", () => {
      [...r.layers.map(l => layerSlot(r,l)), videoSlot(r)].forEach(k => delete st.textSecrets[k]);
      st.recipes.splice(+card.dataset.recipe, 1);
      st.exportKeys = st.exportKeys.filter((id) => id !== r.id); delete st.textVideos[r.id];
      Object.keys(st.textSecrets).forEach((k) => { if (k.startsWith(r.id + "/")) delete st.textSecrets[k]; });
      redraw();
    });
    $("[data-tladd]", card).addEventListener("click", () => { let n = r.layers.length + 1; while (r.layers.some((l) => l.id === "l" + n)) n++; r.layers.push({ id: "l" + n, scheme: "base64", keyed: false }); redraw(); });
    $$("[data-tl]", card).forEach((row) => {
      const j = +row.dataset.tl, l = r.layers[j];
      $("[data-tlscheme]", row).addEventListener("change", (e) => { delete st.textSecrets[layerSlot(r,l)]; l.scheme = e.target.value; l.params = {}; l.keyed = l.scheme === "mojibake"; redraw(); });
      const k = $("[data-tlkeyed]", row); if (k) k.addEventListener("change", () => { l.keyed = k.checked; if (!l.keyed) delete st.textSecrets[layerSlot(r, l)]; redraw(); });
      const up = $("[data-tlup]", row); up.addEventListener("click", () => { if (j > 0) { r.layers.splice(j - 1, 0, r.layers.splice(j, 1)[0]); redraw(); } });
      const dn = $("[data-tldown]", row); dn.addEventListener("click", () => { if (j < r.layers.length - 1) { r.layers.splice(j + 1, 0, r.layers.splice(j, 1)[0]); redraw(); } });
      $("[data-tlrm]", row).addEventListener("click", () => { delete st.textSecrets[layerSlot(r, l)]; r.layers.splice(j, 1); redraw(); });
    });
    $$("[data-rcarrier]", card).forEach((x) => x.addEventListener("change", () => { r.carrier = x.value; if (r.carrier !== "framewords") { delete st.textVideos[r.id]; delete st.textSecrets[videoSlot(r)]; } redraw(); }));
    const pw = $("[data-rvideopw]", card); if (pw) pw.addEventListener("change", () => { r.videoPw = pw.checked; if (!r.videoPw) delete st.textSecrets[videoSlot(r)]; redraw(); });
    const vb = $("[data-rvideo]", card); if (vb) vb.addEventListener("click", async () => { try { const p = await call("pick_files", false, true); if (p && p[0]) { st.textVideos[r.id] = p[0]; redraw(); } } catch (e) { toast(e.message, "err"); } });
    $("[data-rexport]", card).addEventListener("change", (e) => { st.exportKeys = st.exportKeys.filter((id) => id !== r.id); if (e.target.checked) st.exportKeys.push(r.id); runPanel("pipeline"); });
  });
  $$("[data-secret]", el).forEach((inp) => {
    inp.addEventListener("input", () => { if (inp.value) st.textSecrets[inp.dataset.secret] = inp.value; else delete st.textSecrets[inp.dataset.secret]; });
    inp.addEventListener("change", () => runPanel("pipeline"));
  });
}
const TEXT_STATUS = { pending: "待处理", running: "进行中", complete: "已完成", blocked: "失败 · 可重试", cancelled: "已取消 · 可继续" };
function recipeResultCard(result) {
  const dir = result.plan ? String(result.plan).replace(/[\\/][^\\/]*$/, "") : "";
  const st = S.pipeline;
  const rows = st.recipes.map((r) => `<div class="mini-file"><span>${esc(r.name || r.id)}</span><span>${r.carrier === "framewords" ? "视频 · 已独立回读校验" : "文本 · 已逐字校验"}${st.exportKeys.includes(r.id) ? " · 含 .tkey" : ""}</span></div>`).join("");
  return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>全部交付完成</div>
    <p class="result-msg">网盘已分享，各方案文案保存在任务目录 copy/ 下。钥匙（如导出）只在本地，请自行交付，不会自动上传。</p>
    ${cleanupNote(result.task)}<div class="mini-files">${rows}</div>
    <div class="run-actions" style="margin-top:14px"><button class="btn btn-primary btn-block" data-open="${esc(dir ? dir + "/copy" : "")}">${icon("folder")}打开文案目录</button><button class="btn btn-block" data-newrun>${icon("plus")}新建任务</button></div></div>`;
}
/* 文案还原页 */
function textRestoreProblems(st) {
  const m = [];
  if (st.kind === "text" && !st.text) m.push("粘贴文案或已提取的文字");
  if (st.kind === "video" && !st.video) m.push("选择本地视频");
  if (!st.manual && !st.keyFile) m.push("添加 .tkey 文案还原钥匙，或改用手动配方");
  if (st.manual) { try { const r = JSON.parse(st.recipeJson || ""); if (!r || typeof r !== "object" || Array.isArray(r)) throw 0; } catch (_) { m.push("手动配方须为一份 JSON 方案"); } }
  return m;
}
function manualSlots(st) {
  try { const r = JSON.parse(st.recipeJson || ""); return [...(r.layers || []), r.carrier || {}].map((x) => x.secret_slot).filter(Boolean); } catch (_) { return []; }
}
function textRestorePayload(st) {
  const cfg = { secrets: Object.assign({}, st.secrets) };
  if (st.kind === "video") cfg.video = st.video; else cfg.text = st.text;
  if (st.manual) cfg.recipe = JSON.parse(st.recipeJson); else cfg.key_file = st.keyFile;
  if (st.out) cfg.output_dir = st.out;
  return cfg;
}
function renderTextRestore() {
  const st = S.textrestore, el = mount("textrestore", "textrestore"); if (!el) return;
  const isVideo = st.kind === "video";
  const slots = st.manual ? manualSlots(st) : [];
  el.innerHTML = `<div class="seg" role="tablist"><button class="${isVideo ? "" : "on"}" data-trkind="text">文字 / 已提取文字</button><button class="${isVideo ? "on" : ""}" data-trkind="video">本地帧语视频</button></div>
    ${isVideo ? `<div class="callout warn">${icon("info")}<span>密送会自动操作帧语官网提取并解锁外层视频（<b>需联网</b>，只把视频密码交给官网），内层文字在本机解开。不支持离线视频解码；B 站链接请自行在官网打开后把文字粘贴到“文字”入口。</span></div>
      <div class="field"><span>视频文件</span><div class="row" style="gap:6px"><input class="input" readonly value="${esc(st.video)}" placeholder="未选择"><button class="btn btn-sm" data-trpick="video">选择</button></div></div>`
      : `<label class="field"><span>文案（逐字保留，不自动去空格）</span><textarea class="input" rows="6" data-trtext spellcheck="false">${esc(st.text)}</textarea></label><p class="hint">纯文字还原在本机离线完成。</p>`}
    <div class="seg" role="tablist" style="margin-top:12px"><button class="${st.manual ? "" : "on"}" data-trmanual="0">使用 .tkey 钥匙</button><button class="${st.manual ? "on" : ""}" data-trmanual="1">手动配方</button></div>
    ${st.manual ? `<label class="field"><span>方案 JSON（公开配方，不含密码）</span><textarea class="input mono" rows="5" data-trrecipe spellcheck="false">${esc(st.recipeJson)}</textarea><small>手动还原没有原文摘要保证。</small></label>
      ${slots.map((s) => `<label class="field"><span>密钥 · ${esc(s)}</span><input class="input" type="password" autocomplete="off" data-trsecret="${esc(s)}" value="${esc(st.secrets[s] || "")}"></label>`).join("")}`
      : `<div class="field"><span>文案还原钥匙</span><div class="row" style="gap:6px"><input class="input" readonly value="${esc(st.keyFile)}" placeholder="选择 .tkey"><button class="btn btn-sm" data-trpick="key">选择</button></div><small>钥匙已包含所需密钥，持有钥匙即可还原。</small></div>`}
    <div class="row" style="gap:8px;margin:12px 0;flex-wrap:wrap"><button class="btn" data-trpick="out">选择输出目录</button><span class="muted">${esc(st.out || "默认：产物目录")}</span><span class="grow"></span><button class="btn btn-ghost" data-trclear>清空</button></div>`;
  paintIcons(el);
  const redraw = () => { renderTextRestore(); runPanel("textrestore"); };
  $$("[data-trkind]", el).forEach((b) => b.addEventListener("click", () => { st.kind = b.dataset.trkind; st.result = null; redraw(); }));
  $$("[data-trmanual]", el).forEach((b) => b.addEventListener("click", () => { st.manual = b.dataset.trmanual === "1"; st.secrets = {}; redraw(); }));
  const ta = $("[data-trtext]", el); if (ta) { ta.addEventListener("input", () => { st.text = ta.value; }); ta.addEventListener("change", () => runPanel("textrestore")); }
  const rj = $("[data-trrecipe]", el); if (rj) rj.addEventListener("change", () => { st.recipeJson = rj.value; redraw(); });
  $$("[data-trsecret]", el).forEach((i) => i.addEventListener("input", () => { if (i.value) st.secrets[i.dataset.trsecret] = i.value; else delete st.secrets[i.dataset.trsecret]; }));
  $$("[data-trpick]", el).forEach((b) => b.addEventListener("click", async () => {
    try {
      const kind = b.dataset.trpick;
      const paths = kind === "out" ? await call("pick_folder") : await call("pick_files", false, kind === "video");
      if (!paths || !paths.length) return;
      if (kind === "out") st.out = paths[0];
      else if (kind === "video") st.video = paths[0];
      else { if (!/\.tkey$/i.test(paths[0])) return toast("请选择 .tkey 文案还原钥匙", "warn"); st.keyFile = paths[0]; }
      redraw();
    } catch (e) { toast(e.message, "err"); }
  }));
  $("[data-trclear]", el).addEventListener("click", () => { Object.assign(st, { text: "", video: "", keyFile: "", recipeJson: "", secrets: {}, out: "", result: null }); redraw(); });
}
function textRestoreSummary(st, miss, busy, dis) {
  return `<div class="run"><h3>还原文案</h3><p class="hint">${st.kind === "video" ? "视频外层经官网联网提取，内层在本机解开。" : "纯文字在本机离线还原。"}摘要不符时停止，不交付部分结果。</p>${missingNote(miss)}${busyNote(busy)}<button class="btn btn-primary btn-lg btn-block" data-run="go" ${dis}>${icon("wand")}开始还原</button><p class="run-note">原文写入新的 .txt 文件，不覆盖已有文件；密钥不保存。</p></div>`;
}
function textRestoreResult(result) {
  const dir = String(result.out || "").replace(/[\\/][^\\/]*$/, "");
  return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>文案还原完成</div>
    <p class="result-msg">${result.verified ? "已与钥匙中的原文摘要核对一致。" : "手动配方还原，没有原文摘要可核对。"}</p>
    <div class="mini-files"><div class="mini-file"><span>${esc(baseName(result.out || ""))}</span></div></div>
    <div class="run-actions"><button class="btn btn-primary btn-block" data-open="${esc(dir)}">${icon("folder")}打开所在目录</button><button class="btn btn-block" data-newrun>还原其他文案</button></div></div>`;
}

function initPage(page) {
  const st = S[page];
  if ((page === "pipeline" || page === "pack") && !st.layers.length) st.layers = DEFAULT_LAYERS();
  if (page === "pipeline" || page === "pack") st._onchange = () => { st._pwAck = st._lockAck = false; runPanel(page); };
  if (page === "pipeline" && !st._init) { st._init = true; refreshShareChoices("pipeline"); }
  if (page === "upload" && !st._init) { st._init = true; refreshShareChoices("upload"); }
  rerender(page);
}

/* ======================================================================
   CODEC PAGE
   ====================================================================== */
function renderCodecBar() {
  const box = $("#codecSchemes");
  const multi = S.codec.mode === "encode";
  box.innerHTML = S.meta.schemes.map((s) => `<button class="tag-toggle ${S.codec.schemes.includes(s.key) ? "on" : ""}" data-cs="${s.key}">${esc(s.label)}</button>`).join("");
  $$("[data-cs]", box).forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.cs;
    if (multi) { const i = S.codec.schemes.indexOf(k); if (i >= 0) { if (S.codec.schemes.length > 1) S.codec.schemes.splice(i, 1); } else S.codec.schemes.push(k); }
    else S.codec.schemes = [k];
    renderCodecBar();
  }));
  $("#codecInLabel").textContent = multi ? "原文 / 分享链接" : "密文";
  $("#codecRun").querySelector("span").textContent = multi ? "生成文案" : "解回原文";
}
function renderCodecOut() {
  const out = $("#codecOut"); const r = S.codec.output;
  if (!r) { out.innerHTML = `<div class="pane-head"><b>结果</b></div><div class="pane-empty">${icon("wand")}<div style="margin-top:8px">输入左侧内容后点击中间按钮</div></div>`; paintIcons(out); return; }
  if (S.codec.mode === "decode") {
    out.innerHTML = `<div class="pane-head"><b>原文</b><div class="pane-actions"><button class="btn btn-sm btn-ghost" id="outCopy">${icon("copy")}复制</button></div></div><div class="pane-body"><div class="out-text">${esc(r.text)}</div></div>`;
    paintIcons(out); $("#outCopy").addEventListener("click", (e) => copy(r.text, e.currentTarget));
    return;
  }
  const blocks = Object.entries(r).map(([k, v]) => `<div class="out-block"><div class="out-head"><span>${esc(schemeNames([k]))}</span><button class="btn btn-sm btn-ghost" data-oc="${esc(k)}">${icon("copy")}复制</button></div><div class="out-text">${esc(v)}</div></div>`).join("");
  out.innerHTML = `<div class="pane-head"><b>结果</b><div class="pane-actions"><button class="btn btn-sm btn-ghost" id="outCopyAll">${icon("copy")}全部</button></div></div><div class="pane-body">${blocks}</div>`;
  paintIcons(out);
  $$("[data-oc]", out).forEach((b) => b.addEventListener("click", (e) => copy(r[b.dataset.oc], e.currentTarget)));
  $("#outCopyAll").addEventListener("click", (e) => copy(Object.values(r).join("\n\n"), e.currentTarget));
}
function renderCodec() { renderCodecBar(); renderCodecOut(); $("#codecInput").value = S.codec.input; $("#codecKey").value = S.codec.key; }
function bindCodec() {
  $$("#codecMode button").forEach((b) => b.addEventListener("click", () => {
    $$("#codecMode button").forEach((x) => x.classList.toggle("on", x === b));
    S.codec.mode = b.dataset.v;
    if (S.codec.mode === "decode" && S.codec.schemes.length > 1) S.codec.schemes = [S.codec.schemes[0]];
    S.codec.output = null; renderCodec();
  }));
  $("#codecInput").addEventListener("input", (e) => (S.codec.input = e.target.value));
  $("#codecKey").addEventListener("input", (e) => (S.codec.key = e.target.value));
  $("#codecClear").addEventListener("click", () => { S.codec.input = ""; S.codec.output = null; renderCodec(); });
  $("#codecPaste").addEventListener("click", async () => { try { const t = await navigator.clipboard.readText(); S.codec.input = t; renderCodec(); } catch (_) { toast("无法读取剪贴板", "warn"); } });
  $("#codecSwap").addEventListener("click", () => {
    const r = S.codec.output; if (!r) return;
    const text = S.codec.mode === "decode" ? r.text : Object.values(r)[0];
    S.codec.input = text; S.codec.output = null;
    S.codec.mode = S.codec.mode === "encode" ? "decode" : "encode";
    $$("#codecMode button").forEach((x) => x.classList.toggle("on", x.dataset.v === S.codec.mode));
    renderCodec();
  });
  $("#codecRun").addEventListener("click", runCodec);
}
async function runCodec() {
  const c = S.codec; if (!c.input.trim()) { toast("请先输入内容", "warn"); return; }
  try {
    if (c.mode === "encode") c.output = await call("encode", c.input, c.schemes, c.key);
    else c.output = { text: await call("decode", c.input, c.schemes[0], c.key) };
    renderCodecOut();
  } catch (e) { toast(e.message, "err"); }
}

/* ======================================================================
   TASKS PAGE
   ====================================================================== */
async function loadTasks() {
  try {
    S.tasks.items = await call("list_tasks");
    updateBadge();
    // The list comes from this fetch. The open detail is a separate, older
    // task_detail response, so a finished resume would leave the right pane
    // stale until another card is opened.
    if (S.page === "tasks") { S.tasks.reloadDetail = true; renderTasks(); }
  } catch (_) {}
}
function updateBadge() {
  const active = S.tasks.items.filter((t) => t.state && t.state !== "complete" && t.kind !== "pack").length;
  const b = $("#taskBadge"); b.hidden = !active; b.textContent = active || "";
}
function filteredTasks() {
  const f = S.tasks.filter; const q = (S.tasks.query || "").trim().toLowerCase();
  return S.tasks.items
    .filter((t) => f === "all" ? true : f === "star" ? t.starred : f === "pack" ? t.kind === "pack" : f === "complete" ? t.state === "complete" : (t.state !== "complete" && t.kind !== "pack"))
    .filter((t) => !q || [t.title, t.note, t.dir, t.chain, ...(t.stages || []).map((s) => s.label)].some((x) => String(x || "").toLowerCase().includes(q)));
}
const taskId = (t) => t.plan || t.dir;
function renderTasks() {
  const list = $("#taskList"); const items = filteredTasks();
  if (!items.length) {
    const narrowed = (S.tasks.query || "").trim() || S.tasks.filter !== "all";
    list.innerHTML = `<div class="empty">${icon("inbox")}<b>${narrowed ? "没有匹配的任务" : "暂无任务"}</b><span>${narrowed ? "换个关键词或筛选条件试试" : "完成一次打包或发布后会出现在这里，也可以导入已有的任务文件夹"}</span></div>`;
    $("#taskDetail").innerHTML = ""; paintIcons(list); return;
  }
  list.innerHTML = items.map((t) => {
    const disks = (t.stages || []).map((s) => avatar(s.disk, s.label)).join("");
    const kindLabel = (t.kind === "pack" ? "打包" : t.kind === "upload" ? "上传" : "发布") + (t.imported ? " · 导入" : "");
    const err = t.error && t.state !== "complete" ? `<span class="task-err" title="${esc(t.error)}">${icon("warn")}${esc(t.error)}</span>` : "";
    return `<div class="task ${S.tasks.sel === taskId(t) ? "on" : ""}" data-task="${esc(taskId(t))}" role="button" tabindex="0">
      <div class="task-top"><button class="star ${t.starred ? "on" : ""}" data-star="${esc(t.dir)}" title="${t.starred ? "取消收藏" : "收藏"}" aria-label="收藏">${icon(t.starred ? "starfill" : "star")}</button><b>${esc(t.title)}</b>${badge(t.state)}</div>
      ${t.delivery ? `<div class="task-note">${esc(t.delivery.label)}</div>` : ""}${t.note ? `<div class="task-note">${esc(t.note)}</div>` : ""}
      <div class="task-meta"><span>${kindLabel}</span>${disks ? `<span class="task-disks">${disks}</span>` : ""}<span>${esc(fmtTime(t.updated || t.created))}</span>${err}</div></div>`;
  }).join("");
  paintIcons(list);
  $$("[data-task]", list).forEach((el) => {
    el.addEventListener("click", (e) => { if (!e.target.closest("[data-star]")) selectTask(el.dataset.task); });
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === el) selectTask(el.dataset.task); });
  });
  $$("[data-star]", list).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); toggleStar(b.dataset.star); }));
  const keep = S.tasks.sel && items.find((t) => taskId(t) === S.tasks.sel);
  if (!keep) selectTask(taskId(items[0]));
  else if (S.tasks.reloadDetail) { S.tasks.reloadDetail = false; selectTask(S.tasks.sel); }
  else renderTaskDetail();
}
async function selectTask(idpath) {
  S.tasks.sel = idpath; S.tasks.loadError = "";
  $$("[data-task]").forEach((b) => b.classList.toggle("on", b.dataset.task === idpath));
  const item = S.tasks.items.find((t) => taskId(t) === idpath);
  try { S.tasks.detail = item && item.kind === "pack" ? await call("task_detail", null, item.dir) : await call("task_detail", idpath); }
  catch (e) { S.tasks.detail = null; S.tasks.loadError = e.message || "读取失败"; }
  renderTaskDetail();
}
async function toggleStar(dir) {
  const t = S.tasks.items.find((x) => x.dir === dir); if (!t) return;
  try {
    const u = await call("update_task", dir, { starred: !t.starred });
    t.starred = u.starred; if (S.tasks.detail && S.tasks.detail.dir === dir) S.tasks.detail.starred = u.starred;
    toast(u.starred ? "已收藏" : "已取消收藏", "ok"); renderTasks();
  } catch (e) { toast(e.message, "err"); }
}
function renderTaskDetail() {
  const host = $("#taskDetail");
  if (S.tasks.loadError) { host.innerHTML = `<div class="empty">${icon("warn")}<b>无法读取该任务</b><span>${esc(S.tasks.loadError)}</span></div>`; paintIcons(host); return; }
  const d = S.tasks.detail; if (!d) { host.innerHTML = ""; return; }
  const isPack = d.kind === "pack";
  const stats = [];
  stats.push(["类型", isPack ? "加密打包" : d.kind === "upload" ? "上传分享" : "一条龙发布"]);
  stats.push(["状态", d.delivery?.label || STATE_LABEL[d.state] || d.state]);
  if (d.chain) stats.push(["格式链", d.chain]);
  if (d.kind === "pipeline") stats.push(["分享方式", S.meta.forms[d.form] || d.form]);
  stats.push(["创建时间", fmtTime(d.created)]);
  const statsHtml = stats.map((s) => `<div class="stat"><span>${esc(s[0])}</span><b>${esc(s[1])}</b></div>`).join("");
  let stages = "";
  if (!isPack && d.stages && d.stages.length) {
    stages = `<div class="card"><div class="sub-title">${icon("cloud")}上传阶段</div><div class="stages">${d.stages.map((s) => {
      const pct = s.total ? Math.round(s.done / s.total * 100) : 0; const done = s.state === "shared" || s.state === "complete";
      const act = (s.state !== "shared" && s.state !== "complete") ? `<button class="btn btn-sm" data-fill="${esc(s.id)}">${icon("clipboard")}回填分享</button>` : "";
      return `<div class="stage-row"><div class="stage-top">${avatar(s.disk, s.label)}<b>${esc(s.label)}</b>${s.role === "hop" ? '<span class="badge">第一跳</span>' : ""}<span class="grow"></span><em>${s.done}/${s.total}</em>${badge(s.state)}${act}</div><div class="bar ${done ? "done" : ""}"><span style="width:${done ? 100 : pct}%"></span></div></div>`;
    }).join("")}</div></div>`;
  }
  let copies = "";
  if (d.copies && Object.keys(d.copies).length) {
    const keys = Object.keys(d.copies);
    copies = `<div class="card"><div class="sub-title">${icon("wand")}加密文案</div><div class="tabs">${keys.map((k, i) => `<button class="${i ? "" : "on"}" data-dtab="${esc(k)}">${esc(schemeNames([k]))}</button>`).join("")}</div><div class="copybox"><pre id="dCopyPre">${esc(d.copies[keys[0]])}</pre><button class="btn btn-sm btn-primary" id="dCopyBtn">${icon("copy")}复制</button></div></div>`;
  }
  const files = (d.files || []);
  const filesHtml = files.length ? `<div class="card"><div class="sub-title">${icon("file")}文件 · ${files.length}</div><div class="mini-files">${files.map((f) => `<div class="mini-file"><span>${esc(f.name)}</span><span>${fmtSize(f.size)}</span></div>`).join("")}</div></div>` : "";
  const canResume = !isPack && d.state !== "complete";
  const running = !!(S.job && S.job.plan && S.job.plan === d.plan);
  const errHtml = d.error && d.state !== "complete" ? `<div class="callout warn">${icon("warn")}<span><b>上次中断原因：</b>${esc(d.error)}。可点“继续”从检查点接着跑；如果已在网盘里手动分享，也可以“回填分享”。</span></div>` : "";
  const noteHtml = d.note ? `<div class="callout">${icon("info")}<span>${esc(d.note)}</span></div>` : "";
  host.innerHTML = `<div class="detail"><div class="detail-head"><div class="detail-title"><button class="star big ${d.starred ? "on" : ""}" data-dstar title="${d.starred ? "取消收藏" : "收藏"}" aria-label="收藏">${icon(d.starred ? "starfill" : "star")}</button><div><h2>${esc(d.title)}</h2><p>${esc(d.dir)}</p></div></div>
    <div class="btn-row">${canResume ? `<button class="btn btn-primary" data-resume="${esc(d.plan)}" ${running ? "disabled" : ""}>${icon("play")}继续</button>` : ""}<button class="btn" data-reuse title="把这个任务的打包、网盘和文案设置填到新建页面（不含密码和资源）">${icon("refresh")}复用设置</button><button class="btn" data-open="${esc(d.dir)}" title="打开当前选中任务的文件夹">${icon("folder")}打开当前任务目录</button>
    <button class="btn btn-ghost icon-only" data-edit title="重命名 / 备注" aria-label="编辑">${icon("edit")}</button><button class="btn btn-ghost icon-only btn-danger" data-del title="${d.imported ? "从列表移除（保留文件）" : "删除（移到回收站）"}" aria-label="删除" ${running ? "disabled" : ""}>${icon("trash")}</button></div></div>
    ${errHtml}${noteHtml}${cleanupNote(d)}<div class="detail-grid">${statsHtml}</div>${stages}${d.delivery?.recipes?.length ? `<div class="card"><h3>交付方案</h3>${d.delivery.recipes.map(r => `<p>${esc(r.name)} · ${esc(STATE_LABEL[r.status] || r.status)} ${esc(r.error_code || "")}</p>`).join("")}</div>` : ""}${copies}${filesHtml}</div>`;
  paintIcons(host);
  $$("[data-open]", host).forEach((b) => b.addEventListener("click", () => call("open_path", b.dataset.open).catch((e) => toast(e.message, "err"))));
  const rb = $("[data-resume]", host); if (rb) rb.addEventListener("click", () => resumeTask(rb.dataset.resume));
  $$("[data-dtab]", host).forEach((b) => b.addEventListener("click", () => { $$("[data-dtab]", host).forEach((x) => x.classList.toggle("on", x === b)); $("#dCopyPre", host).textContent = d.copies[b.dataset.dtab]; }));
  const dc = $("#dCopyBtn", host); if (dc) dc.addEventListener("click", () => copy($("#dCopyPre", host).textContent, dc));
  $$("[data-fill]", host).forEach((b) => b.addEventListener("click", () => fillShare(d.plan, b.dataset.fill)));
  $("[data-dstar]", host).addEventListener("click", () => toggleStar(d.dir));
  $("[data-edit]", host).addEventListener("click", () => editTaskModal(d));
  $("[data-del]", host).addEventListener("click", () => deleteTaskModal(d));
  $("[data-reuse]", host).addEventListener("click", () => reuseSettings(d));
}
function editTaskModal(d) {
  const draft = { title: d.title, note: d.note || "" };
  const box = modal(`<h3>编辑任务</h3>
    <label class="field"><span>名称</span><input class="input" maxlength="120" value="${esc(d.title)}" data-model="title"></label>
    <label class="field"><span>备注 · 可选</span><textarea class="input" maxlength="500" data-model="note" placeholder="例如：发到哪个群、对应哪一期资源">${esc(d.note || "")}</textarea></label>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-primary" data-ok>保存</button></div>`);
  bindModels(box, draft);
  const ok = async () => {
    if (!(draft.title || "").trim()) { toast("名称不能为空", "warn"); return; }
    try { await call("update_task", d.dir, { title: draft.title, note: draft.note }); closeModal(); toast("已保存", "ok"); await loadTasks(); await selectTask(S.tasks.sel); }
    catch (e) { toast(e.message, "err"); }
  };
  $("[data-x]", box).addEventListener("click", closeModal);
  $("[data-ok]", box).addEventListener("click", ok);
  enterSubmits(box, ok);
  const input = $("input.input", box); input.focus(); input.select();
}
function deleteTaskModal(d) {
  const imported = !!d.imported;
  const box = modal(`<h3>${imported ? "从任务中心移除" : "删除任务"}</h3>
    <p>${imported ? `「${esc(d.title)}」是导入的文件夹：只从列表中移除，文件夹和其中的文件都保留在原处。` : `将把「${esc(d.title)}」整个任务文件夹（本地产物、上传进度、文案）移到回收站，需要时可从回收站还原。已经上传到网盘的文件和分享链接不受影响。`}</p>
    <div class="path">${esc(d.dir)}</div>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-danger-solid" data-ok>${imported ? "移出列表" : "移到回收站"}</button></div>`);
  $("[data-x]", box).addEventListener("click", closeModal);
  $("[data-ok]", box).addEventListener("click", async () => {
    try { const r = await call("delete_task", d.dir); closeModal(); toast(r.trashed ? "已移到回收站" : "已从列表移除", "ok"); S.tasks.sel = null; S.tasks.detail = null; await loadTasks(); }
    catch (e) { toast(e.message, "err"); }
  });
}
async function importTask() {
  try {
    const picked = await call("pick_folder"); const folder = Array.isArray(picked) ? picked[0] : picked; if (!folder) return;
    const t = await call("import_task", folder);
    toast("已导入：" + t.title, "ok"); S.tasks.filter = "all"; $$("#taskFilter button").forEach((x) => x.classList.toggle("on", x.dataset.v === "all"));
    await loadTasks(); selectTask(taskId(t));
  } catch (e) { toast(e.message, "err"); }
}
/* fill a create page with the settings saved for a task (never passwords or input paths) */
function reuseSettings(d) {
  const s = d.settings || {}; const page = d.kind === "pack" ? "pack" : d.kind === "upload" ? "upload" : "pipeline";
  const st = S[page];
  if (page !== "upload") {
    if (Array.isArray(s.layers) && s.layers.length) applyLayers(st, s.layers, { ...s, split: page === "pipeline" ? true : s.split });
    st.checksum = !!s.checksum;
    st.inputs = [];
  }
  if (page !== "pack") {
    st.task_name = ""; st.folder_name = "";
    if (Array.isArray(s.body_disks)) st.disks = s.body_disks.filter((k) => S.meta.providers.some((p) => p.key === k && p.auto));
    if (s.expiry) st.expiry = s.expiry; if (s.access) st.access = s.access;
    if (Array.isArray(s.schemes)) st.schemes = s.schemes.slice();
    if (page === "upload") { st.files = []; st.checksum = !!s.checksum; }
  }
  if (page === "pipeline") { if (s.form) st.form = s.form; if (s.hop_disk) st.hop = s.hop_disk; if (s.pwd_hint) st.pwdHint = s.pwd_hint; st.hopPw = ""; st.cleanup_after_upload = false; }
  st.result = null;
  if (page === "pipeline") st._step = 1;
  go(page);
  if (page !== "pack") refreshShareChoices(page);
  const needPw = page !== "upload" && st.layers.some((l) => l._lock);
  toast("已载入该任务的设置，请重新添加" + (page === "upload" ? "文件" : "资源") + (needPw ? "，并在加密层填写密码" : ""), "ok");
}
function fillShare(plan, stageId) {
  const box = modal(`<h3>回填分享链接</h3><p>粘贴该阶段已上传文件的完整分享文本（含提取码），系统会自动解析。</p>
    <textarea class="input" id="fillText" placeholder="https://pan.quark.cn/s/xxxx\n提取码：abcd"></textarea>
    <div class="modal-actions"><button class="btn" id="fillCancel">取消</button><button class="btn btn-primary" id="fillOk">回填</button></div>`);
  $("#fillCancel", box).addEventListener("click", closeModal);
  $("#fillOk", box).addEventListener("click", async () => {
    const text = $("#fillText", box).value.trim(); if (!text) { toast("请粘贴分享文本", "warn"); return; }
    try { await call("import_share", plan, stageId, text); closeModal(); toast("已回填", "ok"); await selectTask(plan); loadTasks(); }
    catch (e) { toast(e.message, "err"); }
  });
  $("#fillText", box).focus();
}

/* ======================================================================
   ACCOUNTS PAGE
   ====================================================================== */
async function loadAccounts() { try { S.accounts = await call("accounts"); if (S.page === "accounts") renderAccounts(); } catch (_) {} }
function browserSelect(a) {
  const order = ["chromium", "chrome", "msedge"].filter((b) => (S.meta.browsers || []).includes(b));
  const inst = S.meta.browsers_installed || {}; const labels = S.meta.browser_labels || {};
  const opts = order.map((b) => {
    const missing = inst[b] === false;
    const short = { chromium: "Chromium", chrome: "Chrome", msedge: "Edge" }[b] || b;
    return `<option value="${b}" title="${esc(labels[b] || b)}" ${b === a.browser ? "selected" : ""} ${missing && b !== a.browser ? "disabled" : ""}>${esc(short)}${missing ? "（未安装）" : ""}</option>`;
  }).join("");
  return `<label class="field" title="登录和自动上传使用的浏览器"><select class="select" data-browser>${opts}</select></label>`;
}
function renderAccounts() {
  const grid = $("#accountGrid");
  const labels = S.meta.browser_labels || {};
  grid.innerHTML = S.accounts.map((a) => {
    if (!a.auto) return `<div class="acct"><div class="acct-top">${avatar(a.key, a.label)}<div><b>${esc(a.label)}</b><div class="acct-badges"><span class="badge">仅手动回填</span></div></div></div><div class="acct-off">该网盘暂无自动驱动。可在其它网盘发布后，于任务中心手动回填分享链接。</div></div>`;
    const s = statusInfo(a);
    const latest = [a.session_at, a.verified_at].filter(Boolean).sort().pop() || "";
    const err = a.last_error && (!latest || (a.last_error_at || "") >= latest)
      ? `<div class="acct-err" title="${esc(a.last_error)}">${icon("warn")}<span>上次出错${a.last_error_at ? "（" + esc(fmtShort(a.last_error_at)) + "）" : ""}：${esc(a.last_error)}</span></div>` : "";
    const hint = a.browser && a.browser !== "chromium"
      ? `<div class="acct-hint">此盘已记住使用 ${esc(labels[a.browser] || a.browser)}；如遇问题可改回 Chromium 后重新登录。</div>` : "";
    return `<div class="acct" data-acct="${a.key}"><div class="acct-top">${avatar(a.key, a.label)}<div><b>${esc(a.label)}</b><div class="acct-badges"><span class="badge ${s.cls}" title="${esc(s.tip)}">${esc(s.text)}</span>${s.when ? `<small class="acct-when">${esc(s.when)}</small>` : ""}</div></div></div>
      ${err}<div class="acct-actions">${browserSelect(a)}
      <button class="btn" data-op="check">${icon("refresh")}检测登录</button><button class="btn" data-op="selfcheck">只读自检</button><button class="btn btn-primary" data-op="login">${icon("user")}登录</button></div>${hint}</div>`;
  }).join("");
  paintIcons(grid);
  $$("[data-acct]", grid).forEach((card) => {
    const disk = card.dataset.acct; const sel = $("select", card);
    $$("[data-op]", card).forEach((b) => b.addEventListener("click", async () => {
      if (S.job) { toast("已有任务运行中，请稍后", "warn"); return; }
      try { const data = b.dataset.op === "check" ? await call("check_accounts", disk, sel.value) : b.dataset.op === "selfcheck" ? await call("selfcheck", disk, sel.value, $("#selfcheckSnapshots").checked) : await call("account_action", disk, b.dataset.op, sel.value); S.job = data; renderJobCard(); renderAll(); toast(b.dataset.op === "login" ? "已在浏览器中打开，请完成登录" : "正在只读检查…", ""); }
      catch (e) { toast(e.message, "err"); }
    }));
  });
  const reports = S.accountReport || [];
  $("#accountReport").innerHTML = reports.length ? `<h3>本次检查结果</h3>${reports.map(r => `<p>${esc(r.disk)} · ${esc(r.status)} · ${esc(r.code)}${(r.selectors || []).map(s => `<br>${esc(s.item)}：${esc(s.status)}`).join("")}</p>`).join("")}` : "";
}

function renderSettings() {
  $("#settingsResult").textContent = S.settingsResult || "密送 " + (S.meta.version || "") + " · 密钥不保存到模板或设置";
}
async function settingsAction(kind) {
  try {
    if (S.job) throw new Error("请先暂停正在运行的任务");
    let result;
    if (kind === "import") {
      const paths = await call("pick_files", false); if (!paths[0]) return;
      result = await call("import_templates", paths[0]); templatesChanged(result.templates, null);
      S.settingsResult = `已导入 ${result.added.length} 个模板${result.renamed.length ? "，重名模板已自动改名" : ""}`;
    } else {
      const path = await call("pick_save_file", kind === "export" ? "templates" : "diagnostics"); if (!path) return;
      if (kind === "export") result = await call("export_templates", path);
      else {
        const selected = S.tasks.items.find(t => taskId(t) === S.tasks.sel);
        if ($("#diagTask").checked && !selected) throw new Error("请先在任务中心选中任务");
        const shots = $("#diagScreenshots").checked ? (S.settingsScreenshots || []) : [];
        if ($("#diagScreenshots").checked && !shots.length) throw new Error("请选择本次明确附加的截图");
        result = await call("export_diagnostics", path, $("#diagTask").checked ? [selected.dir] : [], shots, S.logs.map(x => x.text));
      }
      S.settingsResult = "已导出：" + result.path;
    }
    renderSettings(); toast("操作完成", "ok");
  } catch(e) { toast(e.message, "err"); }
}

/* ======================================================================
   NAV + BOOT + POLLING
   ====================================================================== */
function go(page) {
  S.page = page;
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("active", p.dataset.page === page));
  $(".main").scrollTop = 0;
  initPage(page);
}
function saveSettings() {
  const p = S.pipeline;
  const data = { layers: layerPayload(p), layers_version: 2, checksum: p.checksum, body_disks: p.disks, form: p.form, hop_disk: p.hop, pwd_hint: p.pwdHint, expiry: p.expiry, access: p.access, schemes: p.schemes };
  call("save_settings", data).catch(() => {});
}
function renderOutputDir() {
  const path = S.meta?.runs || "runs";
  $("#outputPath").textContent = path;
  $("#outputChoose").title = `新任务产物目录：${path}；点击更改`;
  $("#outputChoose").disabled = !!S.job;
}
function applySettings(s) {
  if (!s) return;
  const p = S.pipeline;
  if (Array.isArray(s.layers) && s.layers.length) applyLayers(p, s.layers, s);
  p.checksum = !!s.checksum;
  if (Array.isArray(s.body_disks)) p.disks = s.body_disks.slice();
  if (s.form) p.form = s.form; if (s.hop_disk) p.hop = s.hop_disk; if (s.pwd_hint) p.pwdHint = s.pwd_hint;
  if (s.expiry) p.expiry = s.expiry; if (s.access) p.access = s.access; if (Array.isArray(s.schemes) && s.schemes.length) p.schemes = s.schemes.slice();
}

let pollTimer = null;
async function poll() {
  try {
    const r = await call("poll");
    (r.events || []).forEach((ev) => {
      if (ev.type === "log") pushLog(ev.text, /失败|错误|异常|Error|error/.test(ev.text) ? "err" : /完成|成功|已分享/.test(ev.text) ? "ok" : "");
      else if (ev.type === "toast") toast(ev.text, ev.level === "warn" ? "warn" : ev.level === "error" ? "err" : "");
      else if (ev.type === "job") onJobEvent(ev);
    });
    if (r.job) { S.job = Object.assign(S.job || {}, r.job); renderJobCard(); if (["pipeline", "pack", "upload"].includes(S.page) && S.job.kind === pageKind(S.page)) runPanel(S.page); }
    else if (S.job) { S.job = null; renderJobCard(); }
  } catch (_) {}
  pollTimer = setTimeout(poll, S.job ? 900 : 2000);
}

function bindShell() {
  $("#outputChoose").addEventListener("click", async () => {
    try {
      const result = await call("choose_output_dir");
      if (!result.changed) return;
      S.meta.runs = result.runs;
      renderOutputDir();
      renderAll();
      await loadTasks();
      toast("已更改新任务产物目录，已有任务仍保留", "ok");
    } catch (e) { toast(e.message, "err"); }
  });
  $$(".nav-item").forEach((b) => b.addEventListener("click", () => go(b.dataset.page)));
  $("#logToggle").addEventListener("click", () => { const d = $("#logDrawer"); d.hidden = !d.hidden; renderLogs(); });
  $("#logClose").addEventListener("click", () => { $("#logDrawer").hidden = true; });
  $("#logClear").addEventListener("click", () => { S.logs = []; renderLogs(); });
  $("#tasksRefresh").addEventListener("click", loadTasks);
  $("#tasksImport").addEventListener("click", importTask);
  $("#taskSearch").addEventListener("input", (e) => { S.tasks.query = e.target.value; renderTasks(); });
  $("#accountsRefresh").addEventListener("click", loadAccounts);
  $("#accountsCheckAll").addEventListener("click", async () => { try { if (S.job) throw new Error("请先等待当前任务完成"); S.job = await call("check_accounts"); renderJobCard(); } catch(e) { toast(e.message,"err"); } });
  $$("[data-settings-action]").forEach(b => b.onclick = () => settingsAction(b.dataset.settingsAction));
  $("#diagScreenshots").onchange = e => { $("#diagShotOptions").hidden = !e.target.checked; if (!e.target.checked) { S.settingsScreenshots = []; $("#diagShotCount").textContent = "尚未选择"; } };
  $("#diagPickShots").onclick = async () => { try { const paths=await call("pick_files",true); S.settingsScreenshots=paths; $("#diagShotCount").textContent=`已选择 ${paths.length} 张（请自行检查内容）`; } catch(e) { toast(e.message,"err"); } };
  $$("#taskFilter button").forEach((b) => b.addEventListener("click", () => { $$("#taskFilter button").forEach((x) => x.classList.toggle("on", x === b)); S.tasks.filter = b.dataset.v; renderTasks(); }));
  bindCodec();
  // global drag-drop to the active page
  window.__onDrop = (paths) => {
    const p = S.page; const d = S._drop; S._drop = null;
    if (!paths || !paths.length) return;
    if (d && d.kind === "video" && Date.now() - d.t < 8000 && (p === "pipeline" || p === "pack")) { setVideo(p, paths.find(isVideo) || paths[0], d.layer); return; }
    if (p === "restore") { addRestorePaths(paths).catch(e => toast(e.message, "err")); }
    else if (p === "pipeline" || p === "pack") {
      addPaths(S[p].inputs, paths, false).then(() => { rerender(p); if (p === "pipeline" && (S.pipeline._step || 1) !== 1) toast("已添加到第 1 步「选择资源」", "ok"); });
    }
    else if (p === "upload") { addPaths(S.upload.files, paths, true).then(() => rerender("upload")); }
  };
  // remember which drop zone received the drop: Python delivers the real paths a moment later
  const zoneOf = (e) => (e.target && e.target.closest ? e.target.closest("[data-drop],[data-dropkind]") : null);
  let overEl = null;
  const setOver = (el) => { if (overEl && overEl !== el) overEl.classList.remove("over"); overEl = el; if (el) el.classList.add("over"); };
  window.addEventListener("dragover", (e) => { e.preventDefault(); setOver(zoneOf(e)); }, true);
  window.addEventListener("dragleave", (e) => { if (!e.relatedTarget) setOver(null); }, true);
  window.addEventListener("drop", (e) => { const z = zoneOf(e); S._drop = { kind: (z && z.dataset.dropkind) || "files", layer: z ? Number(z.dataset.layer) : null, t: Date.now() }; setOver(null); }, true);
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("drop", (e) => e.preventDefault());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });
}

async function boot() {
  paintIcons(document);
  bindShell();
  $$(".nav-item").forEach(b => { b.disabled = true; });
  try { S.meta = await call("bootstrap"); }
  catch (e) { toast("后端连接失败：" + e.message, "err"); return; }
  applySettings(S.meta.settings);
  renderOutputDir();
  S.codec.schemes = ["beast"];
  if (S.meta.job) { S.job = S.meta.job; renderJobCard(); }
  await loadAccounts();
  await loadTasks();
  go("pipeline");
  $$(".nav-item").forEach(b => { b.disabled = false; });
  poll();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
})();
