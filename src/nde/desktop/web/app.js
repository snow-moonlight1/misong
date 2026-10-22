"use strict";
/* NDE desktop front end. Talks to the Python Api via window.pywebview.api. */
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
  setTimeout(() => { if (!window.pywebview || !window.pywebview.api) res(window.__NDE_MOCK__ || null); }, 1500);
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
  pipeline: { inputs: [], layers_version: 2, checksum: false, layers: [], video: "", disguise: "", size: "1900M", raw_merge: false, disks: [], form: "direct", hop: "feimao", hopPw: "", pwdHint: "请向分享者获取解压密码。", expiry: "default", access: "default", schemes: ["beast", "mojibake", "hajimi"], key: "", result: null },
  pack: { inputs: [], layers_version: 2, checksum: false, layers: [], video: "", disguise: "", split: false, size: "1900M", raw_merge: false, result: null },
  upload: { files: [], checksum: false, disks: [], expiry: "default", access: "default", schemes: ["beast", "mojibake", "hajimi"], key: "", result: null },
  codec: { mode: "encode", schemes: ["beast"], key: "", input: "", output: null, outScheme: null },
  tasks: { items: [], sel: null, detail: null, filter: "all", query: "", loadError: "" },
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
window.ndeDrop = (paths) => { if (window.__onDrop) window.__onDrop(paths); };

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
    <div class="btn-row"><button class="btn" data-act="pick-files">${icon("file")}选择文件</button><button class="btn" data-act="pick-folder">${icon("folder")}文件夹</button></div>
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
  const box = modal(`<h3>保存为快速模板</h3><p>记录层顺序、各层参数、门面视频路径和“哪些层需要密码”，不会保存任何密码。套用后需要密码的层会标出来，直接在层里填写即可。</p>
    <div class="chain-text">${esc(tplDesc({ layers }))}</div>
    <label class="field"><span>模板名称</span><input class="input" maxlength="24" placeholder="例如：发群用 lz4+7z" data-model="name"></label>
    <label class="check"><input type="checkbox" checked data-model="extras">记住各层参数与门面视频路径</label>
    <div class="modal-actions"><button class="btn" data-x>取消</button><button class="btn btn-primary" data-ok>保存模板</button></div>`);
  bindModels(box, draft);
  const ok = async () => {
    const name = (draft.name || "").trim(); if (!name) { toast("请填写模板名称", "warn"); return; }
    const exists = (S.meta.templates || []).some((t) => t.name === name);
    try {
      const list = await call("save_template", name, layers, draft.extras ? (state.disguise || "") : "", draft.extras && withSize ? (state.size || "") : "");
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

window.__NDE_APP__ = { S, call, toast };

/* ======================================================================
   PAGE: pipeline / pack / upload share a files+config+run layout
   ====================================================================== */
function mount(page, name) { return $(`.page[data-page="${page}"] [data-mount="${name}"]`); }

function renderFilesMount(page, state, key, filesOnly) {
  const el = mount(page, "files"); if (!el) return;
  el.innerHTML = dropzone(page + "-" + key, filesOnly ? "拖入文件，或点击选择" : "拖入文件 / 文件夹，或点击选择",
    filesOnly ? "文件夹会展开为其中的文件" : "支持多选，名称不能重复", items(state, key).length > 0) + fileList(items(state, key), true) + (page === "upload" ? `<div class="sub"><label class="check"><input type="checkbox" data-uploadchecksum ${state.checksum ? "checked" : ""}>附带校验文件（SHA-256）</label><p class="hint">清单与还原说明会自动排除。</p></div>` : "");
  paintIcons(el);
  const uc = $("[data-uploadchecksum]", el); if (uc) uc.addEventListener("change", () => { state.checksum = uc.checked; runPanel(page); });
  const dz = $("[data-drop]", el);
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
  return st.schemes.length ? plainSchemes(st.schemes) : "未选文案";
}
function stepProblem(n) {
  const st = S.pipeline;
  if (n === 1 && !st.inputs.length) return "请先添加要发布的资源";
  if (n === 2 && !st.layers.length) return "请至少设置一层格式";
  if (n === 2 && layerProblems(st).length) return layerProblems(st)[0];
  if (n === 3 && !st.disks.length) return "请至少选择一个本体网盘";
  if (n === 3 && st.form === "complex" && !st.hopPw) return "加密中转需要填写第一跳包密码";
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
  if (page === "upload") { if (!st.files.length) m.push("添加要上传的文件"); if (!st.disks.length) m.push("选择至少一个网盘"); return m; }
  if (!st.inputs.length) m.push("添加资源");
  if (!st.layers.length) m.push("设置至少一层格式");
  m.push(...layerProblems(st));
  if (st.inputs.length && st.layers.length) { if (!st._preflight) m.push("等待空间预检"); else if (!st._preflight.ok) m.push(st._preflight.message); }
  if (page === "pipeline") {
    if (!st.disks.length) m.push("选择本体网盘");
    if (!st.schemes.length) m.push("选择至少一种链接文案");
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
  const notes = missingNote(miss) + busyNote(busy) + (page === "upload" ? "" : preflightNote(st));
  if (page === "pack") {
    push("资源", st.inputs.length ? st.inputs.length + " 项" : "<span class='muted'>未选择</span>", !st.inputs.length);
    push("加密层", chainText(st));
    const pw = pwRow(st); push("密码", esc(pw[0]), pw[1]);
    push("产物", esc(outExt(st) || "—"));
    push("校验文件", st.checksum ? "附带 SHA-256" : "不附带");
    return `<div class="run"><h3>生成本地产物</h3><dl class="summary">${rows.join("")}</dl>${notes}
      <div class="run-actions"><button class="btn btn-primary btn-lg btn-block" data-run="go" ${dis}>${icon("lock")}开始打包</button></div>
      <p class="run-note">产物目录：${esc(S.meta.runs)}。密码仅用于本次打包，不会写入磁盘。</p></div>`;
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
  push("文案", st.schemes.length ? schemeNames(st.schemes) : "<span class='muted'>未选</span>", !st.schemes.length);
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

function resultCard(page, result) {
  if (result.error) {
    const paused = result.paused;
    return `<div class="result-card"><div class="result-title ${paused ? "paused" : "error"}"><span class="ok-ic">${icon(paused ? "pause" : "warn")}</span>${paused ? "任务已暂停" : "任务未完成"}</div>
      <p class="result-msg">${esc(result.error)}</p>
      <div class="run-actions">${result.plan ? `<button class="btn btn-primary btn-block" data-resume="${esc(result.plan)}">${icon("play")}继续任务</button>` : ""}
      <button class="btn btn-block" data-newrun>${icon("refresh")}重新开始</button></div></div>`;
  }
  if (page === "pack") {
    const files = (result.files || []).concat(result.parts || []);
    return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>打包完成</div>
      <p class="result-msg">格式链：${esc(result.chain || "")}</p>
      <div class="mini-files">${files.map((f) => `<div class="mini-file"><span>${esc(f.name)}</span><span>${fmtSize(f.size)}</span></div>`).join("")}</div>
      <div class="run-actions"><button class="btn btn-primary btn-block" data-open="${esc(result.out)}">${icon("folder")}打开产物目录</button><button class="btn btn-block" data-newrun>${icon("plus")}新建打包</button></div></div>`;
  }
  // publish / upload success with copies
  const copies = result.copies || {};
  const keys = Object.keys(copies);
  const tabs = keys.map((k, i) => `<button class="${i === 0 ? "on" : ""}" data-tab="${esc(k)}">${esc(schemeNames([k]))}</button>`).join("");
  const first = keys[0];
  return `<div class="result-card success"><div class="result-title"><span class="ok-ic">${icon("check")}</span>发布完成</div>
    <p class="result-msg">分享链接已生成以下加密文案，点击标签切换。</p>
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
  const nr = $("[data-newrun]", el); if (nr) nr.addEventListener("click", () => { S[page].result = null; if (page === "pipeline") S.pipeline._step = 1; rerender(page); });
  const rs = $("[data-resume]", el); if (rs) rs.addEventListener("click", () => resumeTask(rs.dataset.resume, page));
}

/* ---- job lifecycle ---- */
async function startJob(page, mode, confirmed) {
  const st = S[page];
  if (!confirmed && page !== "upload") {
    checkPasswords(page, () => startJob(page, mode, true), () => { if (page === "pipeline") goStep(2); focusMissingPw(page); });
    return;
  }
  try {
    let data;
    if (page === "pack") {
      data = await call("start_pack", { inputs: st.inputs.map((f) => f.path), layers: layerPayload(st), layers_version: 2, checksum: st.checksum });
    } else if (page === "upload") {
      data = await call("start_upload", { files: st.files.map((f) => f.path), checksum: st.checksum, body_disks: st.disks, expiry: st.expiry, access: st.access, schemes: st.schemes, key: st.key });
    } else {
      data = await call("start_pipeline", { inputs: st.inputs.map((f) => f.path), layers: layerPayload(st), layers_version: 2, checksum: st.checksum, body_disks: st.disks, form: st.form, hop_disk: st.hop, hop_password: st.hopPw, pwd_hint: st.pwdHint, expiry: st.expiry, access: st.access, schemes: st.schemes, key: st.key, upload: mode === "publish" });
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
    const data = await call("resume_task", plan, st ? st.key : "", (st && st.hopPw) || "");
    S.job = data; S.job.task = null; if (st) st.result = null;
    renderJobCard(); renderAll();
    go("tasks");
  } catch (e) { toast(e.message, "err"); }
}
async function pauseJob() { try { await call("pause"); toast("正在暂停…", "warn"); } catch (e) { toast(e.message, "err"); } }
$("#jobPause").addEventListener("click", pauseJob);
$("#jobView").addEventListener("click", () => { if (S.job) go(S.job.kind === "account" ? "accounts" : S.job.kind === "pipeline" ? "pipeline" : S.job.kind === "pack" ? "pack" : S.job.kind === "upload" ? "upload" : "tasks"); });

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
  const page = kind === "pipeline" ? "pipeline" : kind;
  if (state === "running") { S.job = Object.assign(S.job || {}, job); renderJobCard(); return; }
  S.job = null; renderJobCard();
  if (kind === "account") {
    if (state === "done") toast("账号操作完成", "ok"); else toast(error || "账号操作未完成", "warn");
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
  if (page === "pipeline") { renderFilesMount("pipeline", st, "inputs", false); layerEditor(st, '[data-mount="layers"]', $('.page[data-page="pipeline"]')); packOptionsMount("pipeline", st); disksMount("pipeline", st); schemesMount("pipeline", st); runPanel("pipeline"); }
  else if (page === "pack") { renderFilesMount("pack", st, "inputs", false); layerEditor(st, '[data-mount="layers"]', $('.page[data-page="pack"]')); packOptionsMount("pack", st); runPanel("pack"); }
  else if (page === "upload") { renderFilesMount("upload", st, "files", true); disksMount("upload", st); schemesMount("upload", st); runPanel("upload"); }
  else if (page === "codec") renderCodec();
  else if (page === "tasks") renderTasks();
  else if (page === "accounts") renderAccounts();
}
function renderAll() { ["pipeline", "pack", "upload"].forEach((p) => { if (S.page === p) rerender(p); else runPanel(p); }); }

/* ---------- init per-page (one-time structure fill) ---------- */
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
async function loadTasks() { try { S.tasks.items = await call("list_tasks"); updateBadge(); if (S.page === "tasks") renderTasks(); } catch (_) {} }
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
      ${t.note ? `<div class="task-note">${esc(t.note)}</div>` : ""}
      <div class="task-meta"><span>${kindLabel}</span>${disks ? `<span class="task-disks">${disks}</span>` : ""}<span>${esc(fmtTime(t.updated || t.created))}</span>${err}</div></div>`;
  }).join("");
  paintIcons(list);
  $$("[data-task]", list).forEach((el) => {
    el.addEventListener("click", (e) => { if (!e.target.closest("[data-star]")) selectTask(el.dataset.task); });
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === el) selectTask(el.dataset.task); });
  });
  $$("[data-star]", list).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); toggleStar(b.dataset.star); }));
  if (!S.tasks.sel || !items.find((t) => taskId(t) === S.tasks.sel)) selectTask(taskId(items[0]));
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
  stats.push(["状态", STATE_LABEL[d.state] || d.state]);
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
    ${errHtml}${noteHtml}<div class="detail-grid">${statsHtml}</div>${stages}${copies}${filesHtml}</div>`;
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
    if (Array.isArray(s.body_disks)) st.disks = s.body_disks.filter((k) => S.meta.providers.some((p) => p.key === k && p.auto));
    if (s.expiry) st.expiry = s.expiry; if (s.access) st.access = s.access;
    if (Array.isArray(s.schemes)) st.schemes = s.schemes.slice();
    if (page === "upload") { st.files = []; st.checksum = !!s.checksum; }
  }
  if (page === "pipeline") { if (s.form) st.form = s.form; if (s.hop_disk) st.hop = s.hop_disk; if (s.pwd_hint) st.pwdHint = s.pwd_hint; st.hopPw = ""; }
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
      <button class="btn" data-op="probe" title="打开网盘确认是否仍处于登录状态，不上传文件；仍登录时保持“已通过测试”">${icon("refresh")}检测登录</button><button class="btn btn-primary" data-op="login">${icon("user")}登录</button></div>${hint}</div>`;
  }).join("");
  paintIcons(grid);
  $$("[data-acct]", grid).forEach((card) => {
    const disk = card.dataset.acct; const sel = $("select", card);
    $$("[data-op]", card).forEach((b) => b.addEventListener("click", async () => {
      if (S.job) { toast("已有任务运行中，请稍后", "warn"); return; }
      try { const data = await call("account_action", disk, b.dataset.op, sel.value); S.job = data; renderJobCard(); renderAll(); toast(b.dataset.op === "probe" ? "正在检测登录…" : "已在浏览器中打开，请完成登录", ""); }
      catch (e) { toast(e.message, "err"); }
    }));
  });
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
  $$("#taskFilter button").forEach((b) => b.addEventListener("click", () => { $$("#taskFilter button").forEach((x) => x.classList.toggle("on", x === b)); S.tasks.filter = b.dataset.v; renderTasks(); }));
  bindCodec();
  // global drag-drop to the active page
  window.__onDrop = (paths) => {
    const p = S.page; const d = S._drop; S._drop = null;
    if (!paths || !paths.length) return;
    if (d && d.kind === "video" && Date.now() - d.t < 8000 && (p === "pipeline" || p === "pack")) { setVideo(p, paths.find(isVideo) || paths[0], d.layer); return; }
    if (p === "pipeline" || p === "pack") {
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
  try { S.meta = await call("bootstrap"); }
  catch (e) { toast("后端连接失败：" + e.message, "err"); return; }
  applySettings(S.meta.settings);
  renderOutputDir();
  S.codec.schemes = ["beast"];
  if (S.meta.job) { S.job = S.meta.job; renderJobCard(); }
  await loadAccounts();
  await loadTasks();
  go("pipeline");
  poll();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
})();
