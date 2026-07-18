// Iris-Stego Lab — front-end controller
const $ = (s) => document.querySelector(s);
const state = { runId: null, keys: [] };

// ————————————————————————————— helpers
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.headers.get("content-type")?.includes("json") ? res.json() : res;
}
function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (isError ? " error" : ""); t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
}
function unlock(id) { $(id).classList.remove("locked"); }
function metricRows(el, rows) {
  el.innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
}
function png(b64) { return "data:image/png;base64," + b64; }
function fmt(n, d = 3) { return typeof n === "number" ? n.toFixed(d) : n; }

// ————————————————————————————— histogram plotter
function drawHist(canvas, data, color = "#a32330") {
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, n = data.length;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#efe7d5"; ctx.fillRect(0, 0, W, H);
  const max = Math.max(...data) || 1, bw = W / n;
  ctx.fillStyle = color;
  data.forEach((v, i) => {
    const h = (v / max) * (H - 8);
    ctx.fillRect(i * bw, H - h, Math.max(bw - 0.3, 0.6), h);
  });
  ctx.strokeStyle = "#1c1712"; ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
}

// ————————————————————————————— init
async function init() {
  $("#meta-date").textContent = new Date().toISOString().slice(0, 10);
  try {
    state.keys = await api("/api/keys");
    $("#meta-keys").textContent = state.keys.length + " keys loaded";
    $("#key-select").innerHTML = state.keys
      .map((k) => `<option value="${k.index}">#${k.index} · ${k.dims}-D · ${k.preview}</option>`)
      .join("");
  } catch (e) { toast("Could not load keys: " + e.message, true); }
  refreshInbox();
  refreshLog();
}

// ————————————————————————————— Step I: cover
$("#cover-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("cover", file);
  try {
    const r = await api("/api/runs", { method: "POST", body: fd });
    state.runId = r.id;
    $("#meta-run").textContent = "run " + r.id;
    $("#fig-cover").src = png(r.cover_png);
    metricRows($("#cover-metrics"), [
      ["run id", r.id], ["file", r.cover_name],
      ["dimensions", `${r.width} × ${r.height}`],
      ["capacity", r.capacity_bytes.toLocaleString() + " B"],
    ]);
    $("#cover-results").hidden = false;
    ["#step-pre", "#step-feat", "#step-hide", "#step-enc"].forEach(unlock);
    toast("Run " + r.id + " created");
    refreshLog();
  } catch (err) { toast(err.message, true); }
});
// drag styling
const drop = $("#filedrop");
["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("drag")));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files[0]) { $("#cover-input").files = e.dataTransfer.files; $("#cover-input").dispatchEvent(new Event("change")); }
});

// ————————————————————————————— Step II: preprocess
$("#btn-pre").addEventListener("click", async () => {
  try {
    const r = await api(`/api/runs/${state.runId}/preprocess`, { method: "POST" });
    $("#fig-gray").src = png(r.gray_png);
    $("#fig-eq").src = png(r.equalized_png);
    drawHist($("#hist-gray"), r.hist_gray, "#4c443a");
    drawHist($("#hist-eq"), r.hist_equalized, "#a32330");
    metricRows($("#pre-metrics"), [
      ["entropy — grayscale", fmt(r.entropy_gray, 4) + " bits/px"],
      ["entropy — equalized", fmt(r.entropy_equalized, 4) + " bits/px"],
    ]);
    $("#pre-results").hidden = false;
    toast("Preprocessing complete");
  } catch (e) { toast(e.message, true); }
});

// ————————————————————————————— Step III: features
$("#btn-feat").addEventListener("click", async () => {
  try {
    const r = await api(`/api/runs/${state.runId}/features`, { method: "POST" });
    $("#fig-feat").src = png(r.features_png);
    $("#cap-feat").textContent = `Fig. 3 — ${r.count} ${r.detector} keypoints.`;
    metricRows($("#feat-metrics"), [
      ["detector", r.detector],
      ["keypoints", r.count.toLocaleString()],
      ["mean response", fmt(r.mean_response, 5)],
    ]);
    $("#feat-results").hidden = false;
    toast(r.count + " " + r.detector + " keypoints");
  } catch (e) { toast(e.message, true); }
});

// ————————————————————————————— Step IV: hide
$("#btn-hide").addEventListener("click", async () => {
  const message = $("#message").value;
  if (!message.trim()) return toast("Enter a message first", true);
  const fd = new FormData(); fd.append("message", message);
  try {
    const r = await api(`/api/runs/${state.runId}/hide`, { method: "POST", body: fd });
    $("#fig-stego").src = png(r.stego_png);
    metricRows($("#hide-metrics"), [
      ["payload", r.payload_bytes + " B of " + r.capacity_bytes.toLocaleString() + " B"],
      ["carrier bytes written", r.bits_written.toLocaleString()],
      ["pixel bytes changed", r.bits_flipped.toLocaleString()],
      ["MSE", fmt(r.mse, 6)],
      ["PSNR", (r.psnr_db === null ? "∞" : fmt(r.psnr_db, 2)) + " dB"],
      ["embed time", fmt(r.embed_ms, 2) + " ms"],
      ["entropy cover → stego", `${fmt(r.entropy_cover, 4)} → ${fmt(r.entropy_stego, 4)}`],
    ]);
    $("#hide-results").hidden = false;
    toast("Message embedded · PSNR " + fmt(r.psnr_db, 1) + " dB");
  } catch (e) { toast(e.message, true); }
});

// ————————————————————————————— Step V: encrypt + send
$("#btn-enc").addEventListener("click", async () => {
  const fd = new FormData();
  fd.append("key_index", $("#key-select").value);
  fd.append("aes_secret", $("#aes-secret").value || "123");
  try {
    const r = await api(`/api/runs/${state.runId}/encrypt`, { method: "POST", body: fd });
    $("#fig-cipher").src = png(r.cipher_noise_png);
    drawHist($("#hist-cipher"), r.hist_cipher, "#1d5f58");
    $("#wrapped-key").textContent = r.wrapped_key;
    metricRows($("#enc-metrics"), [
      ["RC4 key (hex)", r.rc4_key_hex.slice(0, 32) + "…"],
      ["ciphertext size", r.cipher_size.toLocaleString() + " B"],
      ["entropy plain → cipher", `${fmt(r.entropy_plain, 4)} → ${fmt(r.entropy_cipher, 4)}`],
      ["RC4 encrypt time", fmt(r.rc4_encrypt_ms, 2) + " ms"],
    ]);
    $("#enc-results").hidden = false;
    $("#btn-send").disabled = false;
    toast("Encrypted · cipher entropy " + fmt(r.entropy_cipher, 3));
  } catch (e) { toast(e.message, true); }
});

$("#btn-send").addEventListener("click", async () => {
  try {
    await api(`/api/runs/${state.runId}/send`, { method: "POST" });
    toast("Dispatched to receiver inbox ⇥");
    $("#btn-send").disabled = true;
    refreshInbox(); refreshLog();
    document.querySelector("#ch-receiver").scrollIntoView({ behavior: "smooth" });
  } catch (e) { toast(e.message, true); }
});

// ————————————————————————————— Step VI: inbox / receive
async function refreshInbox() {
  const inbox = await api("/api/inbox");
  const el = $("#inbox-list");
  if (!inbox.length) { el.innerHTML = `<p class="inbox-empty">Inbox empty — dispatch a package from §1.</p>`; return; }
  el.innerHTML = inbox.map((it) => `
    <div class="inbox-item">
      <span class="tag ${it.received ? "" : "new"}">${it.received ? "opened" : "new"}</span>
      <span class="mono">${it.run_id}</span>
      <span class="mono">${it.cipher_size.toLocaleString()} B</span>
      <span class="mono">${it.sent.replace("T", " ")}</span>
      <button class="btn btn-small" data-run="${it.run_id}">Decrypt &amp; reveal</button>
    </div>`).join("");
  el.querySelectorAll("button[data-run]").forEach((b) =>
    b.addEventListener("click", () => receive(b.dataset.run)));
}

async function receive(runId) {
  const fd = new FormData(); fd.append("aes_secret", $("#rx-secret").value || "123");
  try {
    const r = await api(`/api/inbox/${runId}/receive`, { method: "POST", body: fd });
    $("#fig-decrypted").src = png(r.decrypted_png);
    $("#rx-message").textContent = r.message;
    const v = $("#rx-verdict");
    v.textContent = r.roundtrip_ok ? "✓ INTEGRITY VERIFIED — recovered payload matches source"
                                   : "✗ MISMATCH — recovered payload differs from source";
    v.className = "verdict " + (r.roundtrip_ok ? "ok" : "bad");
    metricRows($("#rx-metrics"), [
      ["message length", r.message_length + " B"],
      ["RC4 decrypt time", fmt(r.rc4_decrypt_ms, 2) + " ms"],
      ["LSB reveal time", fmt(r.reveal_ms, 2) + " ms"],
      ["round-trip", r.roundtrip_ok ? "PASS" : "FAIL"],
    ]);
    $("#rx-results").hidden = false;
    toast(r.roundtrip_ok ? "Round-trip verified ✓" : "Round-trip mismatch ✗", !r.roundtrip_ok);
    refreshInbox(); refreshLog();
  } catch (e) { toast(e.message, true); }
}

// ————————————————————————————— Experiment log
async function refreshLog() {
  const runs = await api("/api/runs");
  const body = $("#runs-table tbody");
  body.innerHTML = runs.map((r) => {
    const rt = r.roundtrip_ok === true ? `<span class="ok-mark">PASS</span>`
             : r.roundtrip_ok === false ? `<span class="bad-mark">FAIL</span>` : "—";
    const g = (v, d = 2) => (v === undefined || v === null ? "—" : (typeof v === "number" ? v.toFixed(d) : v));
    return `<tr>
      <td>${r.id}</td><td>${r.cover_name ?? "—"}</td><td>${r.width}×${r.height}</td>
      <td>${g(r.payload_bytes, 0)}</td><td>${g(r.psnr_db)}</td><td>${g(r.mse, 5)}</td>
      <td>${g(r.bits_flipped, 0)}</td><td>${g(r.entropy_cover, 3)}</td>
      <td>${g(r.entropy_stego, 3)}</td><td>${g(r.entropy_cipher, 3)}</td>
      <td>${g(r.embed_ms)}</td><td>${g(r.rc4_encrypt_ms)}</td><td>${g(r.rc4_decrypt_ms)}</td>
      <td>${rt}</td><td>${r.status}</td>
    </tr>`;
  }).join("");
}

init();
