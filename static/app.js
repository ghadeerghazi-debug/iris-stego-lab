// Iris-Stego Lab — front-end controller
const $ = (s) => document.querySelector(s);
const state = { runId: null, keys: [] };

// ————————————————————————————— PWA: service worker + install
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
// ————————————————————————————— sidebar + page navigation
function showPage(name) {
  document.querySelectorAll(".page").forEach((p) => p.classList.toggle("active", p.dataset.page === name));
  document.querySelectorAll(".nav-item[data-page]").forEach((n) => n.classList.toggle("active", n.dataset.page === name));
  document.body.classList.remove("nav-open");
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".nav-item[data-page]").forEach((n) =>
    n.addEventListener("click", (e) => { e.preventDefault(); showPage(n.dataset.page); }));
  const toggle = document.querySelector("#nav-toggle");
  const scrim = document.querySelector("#scrim");
  if (toggle) toggle.addEventListener("click", () => document.body.classList.toggle("nav-open"));
  if (scrim) scrim.addEventListener("click", () => document.body.classList.remove("nav-open"));
  document.querySelectorAll(".link-how").forEach((l) =>
    l.addEventListener("click", (e) => { e.preventDefault(); showPage("how"); }));
  const start = (location.hash || "").replace("#", "");
  if (start && document.querySelector(`.page[data-page="${start}"]`)) showPage(start);
});

let deferredInstall = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstall = e;
  const b = document.querySelector("#btn-install");
  if (b) b.hidden = false;
});
window.addEventListener("appinstalled", () => {
  const b = document.querySelector("#btn-install");
  if (b) b.hidden = true;
  deferredInstall = null;
});
document.addEventListener("DOMContentLoaded", () => {
  const b = document.querySelector("#btn-install");
  if (!b) return;
  b.addEventListener("click", async () => {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall = null;
    b.hidden = true;
  });
});

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

// mode toggle visual state
document.querySelectorAll('#mode-toggle input[name="mode"]').forEach((r) =>
  r.addEventListener("change", () => {
    document.querySelectorAll("#mode-toggle .mode-opt").forEach((o) =>
      o.classList.toggle("selected", o.querySelector("input").checked));
  }));

// ————————————————————————————— Step V: encrypt + send
$("#btn-enc").addEventListener("click", async () => {
  const mode = document.querySelector('#mode-toggle input[name="mode"]:checked').value;
  const fd = new FormData();
  fd.append("key_index", $("#key-select").value);
  fd.append("aes_secret", $("#aes-secret").value || "123");
  fd.append("mode", mode);
  try {
    const r = await api(`/api/runs/${state.runId}/encrypt`, { method: "POST", body: fd });
    $("#fig-cipher").src = png(r.cipher_noise_png);
    drawHist($("#hist-cipher"), r.hist_cipher, r.authenticated ? "#1d5f58" : "#a32330");
    $("#wrapped-key").textContent = r.wrapped_key;
    metricRows($("#enc-metrics"), [
      ["cipher mode", r.mode.toUpperCase() + (r.authenticated ? " · authenticated ✓" : " · unauthenticated")],
      ["key derivation", r.key_repr],
      ["ciphertext size", r.cipher_size.toLocaleString() + " B"],
      ["entropy plain → cipher", `${fmt(r.entropy_plain, 4)} → ${fmt(r.entropy_cipher, 4)}`],
      ["encrypt time", fmt(r.rc4_encrypt_ms, 2) + " ms"],
    ]);
    $("#enc-results").hidden = false;
    $("#btn-send").disabled = false;
    toast(`Encrypted (${r.mode.toUpperCase()}) · entropy ${fmt(r.entropy_cipher, 3)}`);
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
      ["cipher mode", r.mode.toUpperCase() + (r.authenticated ? " · authenticated ✓" : "")],
      ["message length", r.message_length + " B"],
      ["decrypt time", fmt(r.rc4_decrypt_ms, 2) + " ms"],
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

// ————————————————————————————— Step 0: iris recognition
$("#iris-input").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  $("#fig-iris").src = URL.createObjectURL(file);
  const fd = new FormData(); fd.append("iris", file);
  try {
    const r = await api("/api/identify", { method: "POST", body: fd });
    const conf = Math.round(r.confidence * 100);
    $("#iris-verdict").innerHTML =
      `<span class="vc-label">Identified sender</span>
       <span class="vc-big">Subject #${r.subject}</span>
       <span class="vc-conf">${conf}% confidence · 1-of-${r.n_subjects}</span>`;
    metricRows($("#iris-metrics"),
      [["method", "Fisherfaces (PCA→LDA→SVM)"]].concat(
        r.top3.map((t, i) => [`rank ${i + 1}`, `subject #${t.subject} · ${(t.confidence * 100).toFixed(1)}%`])));
    $("#iris-results").hidden = false;
    toast(`Iris → subject #${r.subject} (${conf}%)`);
  } catch (err) { toast(err.message, true); }
});
const idrop = $("#irisdrop");
["dragover", "dragenter"].forEach((ev) => idrop.addEventListener(ev, (e) => { e.preventDefault(); idrop.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => idrop.addEventListener(ev, () => idrop.classList.remove("drag")));
idrop.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files[0]) { $("#iris-input").files = e.dataTransfer.files; $("#iris-input").dispatchEvent(new Event("change")); }
});

// ————————————————————————————— Step IV-a: message vetting
$("#btn-vet").addEventListener("click", async () => {
  const message = $("#message").value;
  if (!message.trim()) return toast("Enter a message first", true);
  const fd = new FormData();
  fd.append("message", message); fd.append("lang", $("#vet-lang").value);
  try {
    const r = await api("/api/classify", { method: "POST", body: fd });
    const badge = $("#vet-badge");
    const fake = r.verdict === "fake";
    badge.textContent = `${fake ? "⚠ FAKE" : "✓ AUTHENTIC"} · ${Math.round(r.confidence * 100)}% (${r.language})`;
    badge.className = "vet-badge " + (fake ? "bad" : "ok");
    badge.hidden = false;
    toast(`Message vetted: ${r.verdict} (${Math.round(r.confidence * 100)}%)`);
  } catch (e) { toast(e.message, true); }
});

// ————————————————————————————— model accuracy footnotes
async function loadModelMeta() {
  try {
    const m = await api("/api/models");
    if (m.iris) $("#step-iris .step-head p").insertAdjacentHTML("beforeend",
      ` <span class="acc-chip">test acc ${(m.iris.test_accuracy * 100).toFixed(1)}% · ${m.iris.subjects} subjects</span>`);
    if (m.text_en) $("#step-hide .step-head p").insertAdjacentHTML("beforeend",
      ` <span class="acc-chip">EN ${(m.text_en.test_accuracy * 100).toFixed(1)}% · AR ${(m.text_ar.test_accuracy * 100).toFixed(1)}%</span>`);
  } catch {}
}
loadModelMeta();

// ————————————————————————————— bilingual step notes (Arabic beside English)
const AR_NOTES = [
  // 0 · iris
  `<span class="ex-q">ماذا يفعل</span>
   <p>ترفعين صورة لقزحية عين شخص ما (الحلقة الملوّنة في العين)، فيخمّن الحاسوب <strong>هوية صاحبها</strong> — تمامًا مثل التعرّف على الوجه، لكن باستخدام العين.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>في هذا النظام يُعرَّف المُرسِل من خلال جسده — قزحيته — بدلاً من اسم مستخدم، وهذه الهوية هي ما يربط الشخص بمفتاح التشفير الخاص به. هذا هو جزء <strong>«مَن الذي يُرسِل؟»</strong>.</p>
   <span class="ex-q">كيف تعلّم ذلك</span>
   <p>دُرِّب النموذج مرة واحدة على قاعدة بيانات القزحيات <strong>MMU</strong> (مئات الصور لأعين 45 شخصًا) بطريقة <strong>Fisherfaces</strong> الكلاسيكية — نفس فكرة نظام FisherFace في البرنامج الأصلي.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>يعرض <strong>الشخص المتوقّع</strong> ونسبة <strong>الثقة</strong> وأفضل ثلاثة احتمالات. النموذج مصيب في نحو <strong>62%</strong> من الحالات (من بين 45 شخصًا — التخمين العشوائي نحو 2%)، لذا يُخطئ أحيانًا؛ ورقم الثقة يبيّن مدى تأكّده.</p>`,
  // 1 · cover
  `<span class="ex-q">ماذا يفعل</span>
   <p>تختارين صورة عادية. هذه هي <strong>«الغطاء»</strong> — الصورة البريئة الظاهر التي ستحمل الرسالة المخفية بداخلها.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>إخفاء المعلومات يهدف إلى إخفاء الرسالة <strong>بحيث لا يشكّ أحد بوجودها أصلاً</strong>. تبدو صورة الغطاء طبيعية تمامًا لمن يراها — والسرّ مدفون في وحدات البكسل.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>يعرض حجم الصورة و<strong>سعتها</strong> — أقصى عدد من الحروف يمكن إخفاؤه داخل هذه الصورة. الصور الأكبر تتّسع لرسائل أطول.</p>`,
  // 2 · preprocess
  `<span class="ex-q">ماذا يفعل</span>
   <p>يحوّل الصورة إلى <strong>تدرّج رمادي (أبيض وأسود)</strong> ثم <strong>يوازن سطوعها</strong> (معادلة الرسم البياني) لتكون المناطق الداكنة والفاتحة أكثر توازنًا.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>هذا بالضبط ما كان يفعله البرنامج الأصلي بلغة C++‎ قبل التعرّف على القزحية. توحيد معالجة كل صورة بالطريقة نفسها يجعل التحليل اللاحق عادلاً وقابلاً للتكرار.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>الرسمان البيانيان يوضّحان عدد وحدات البكسل الداكنة مقابل الفاتحة؛ بعد المعادلة تتوزّع الأعمدة بشكل أكثر تساويًا. و<strong>الإنتروبيا</strong> تقيس كمية المعلومات البصرية في الصورة (كلما زادت زادت التفاصيل).</p>`,
  // 3 · features
  `<span class="ex-q">ماذا يفعل</span>
   <p>يجد <strong>أكثر النقاط تميّزًا</strong> في الصورة — الزوايا والحواف والمناطق ذات الملمس — ويعلّمها بدوائر صغيرة تُسمّى <strong>النقاط المفتاحية</strong>.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>استخدم البرنامج الأصلي طريقة تُسمّى <strong>SURF</strong> لوصف الصورة عبر نقاطها المميّزة. (SURF محمية ببراءة اختراع وغير متاحة هنا، لذا يستخدم المختبر <strong>SIFT</strong> — قريبتها المعروفة — ويخبرك أيّهما عمل.)</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>سترين الصورة مغطّاة بالدوائر و<strong>عددًا</strong> للنقاط المفتاحية المكتشفة. كثرة النقاط تعني صورة أغنى بالتفاصيل الفريدة.</p>`,
  // 4 · hide + vet
  `<span class="ex-q">أولاً — التحقّق من الرسالة (اختياري)</span>
   <p>قبل الإخفاء، يمكنك سؤال الحاسوب إن كانت الرسالة تبدو <strong>حقيقية أم مزيّفة</strong>. نموذج دُرِّب على أخبار حقيقية ومزيّفة (بالإنجليزية أو العربية) يعطي حكمه. هذا هو جزء <strong>«هل الرسالة موثوقة؟»</strong>.</p>
   <span class="ex-q">ثم — إخفاء الرسالة</span>
   <p>يُحوَّل نصّك إلى <strong>أصفار وآحاد</strong> ويُدسّ في <strong>البِت الأقل أهمية</strong> من قيمة لون كل بكسل. تغيير هذا البِت الأخير يزيح اللون بقدر ضئيل جدًا لا تراه العين — لكن الرسالة أصبحت داخل الصورة.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>يقيس <strong>PSNR</strong> و<strong>MSE</strong> مقدار الفرق بين الصورة الجديدة والأصلية. قيمة <strong>PSNR عالية</strong> (70+ ديسيبل) تعني أن التغيير غير مرئي عمليًا — وهو تمامًا ما يريده الإخفاء الجيّد.</p>`,
  // 5 · encrypt
  `<span class="ex-q">ماذا يفعل</span>
   <p>يشفّر الصورة كاملة فتصبح <strong>ضجيجًا بلا معنى</strong> لأي شخص يعترضها. يأتي المفتاح من <strong>متجه سمات القزحية</strong> — أرقام مشتقّة من عين الشخص — فتصبح السمة الحيوية هي المفتاح نفسه. ثم يُقفَل هذا المفتاح داخل طبقة أخرى (AES) للنقل.</p>
   <span class="ex-q">الوضعان (لماذا يوجد خيار)</span>
   <p><strong>RC4 · الأمين</strong> يعيد إنتاج الأطروحة الأصلية تمامًا لتبقى النتائج قابلة للمقارنة — لكنه قديم ولم يعد آمنًا. <strong>AES-256-GCM · الآمن</strong> هو الترقية الحديثة: يكشف أيضًا <strong>العبث بالبيانات</strong> ويشتقّ مفتاحًا قويًا بطريقة سليمة (PBKDF2). استخدمي RC4 لمطابقة الأرقام القديمة، وAES-GCM لعرض النسخة المحسّنة.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>تظهر الصورة المشفّرة كـ<strong>ضجيج عشوائي</strong>، ويجب أن يبدو رسمها البياني <strong>مسطّحًا</strong>. <strong>إنتروبيا قريبة من 8.0</strong> تعني أن الناتج شبه عشوائي تمامًا — علامة التشفير القوي.</p>`,
  // 6 · receiver
  `<span class="ex-q">ماذا يفعل</span>
   <p>هذا <strong>جانب المُستقبِل</strong>. يأخذ الحزمة المشفّرة المُرسَلة <strong>ويعكس كل خطوة</strong> — يفتح المفتاح، يفكّ تشفير الصورة، ويستخرج الرسالة المخفية.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>يثبت أن <strong>الرحلة كاملة تعمل من الطرف إلى الطرف</strong>: السرّ الذي أُخفي وشُفِّر في جهة يخرج سليمًا في الجهة الأخرى. في الأطروحة الحقيقية حدث ذلك بين حاسوبين عبر الشبكة؛ وهنا محاكاة في مكان واحد.</p>
   <span class="ex-q">كيف تقرئين النتيجة</span>
   <p>تعرض الرسالة المستعادة و<strong>حكم الرحلة الكاملة</strong>: <strong>PASS</strong> يعني أن الرسالة عادت مطابقة تمامًا لما أُرسل (نجاح!). ومع الوضع الآمن يؤكّد أيضًا أن الحزمة <strong>لم يُعبَث بها</strong>.</p>`,
  // 7 · log
  `<span class="ex-q">ماذا يفعل</span>
   <p>تُسجَّل كل تجربة تجرينها <strong>كصفّ واحد</strong> مع جميع أرقامها المقيسة — جودة الصورة (PSNR/MSE)، والعشوائية (الإنتروبيا)، والأزمنة، وما إذا نجحت الرحلة الكاملة.</p>
   <span class="ex-q">لماذا يهمّ البحث</span>
   <p>هذا <strong>جدول نتائجك للأطروحة</strong>. بدلاً من تدوين الأرقام يدويًا، شغّلي عدة تجارب فتتجمّع الأدلة تلقائيًا. زر <strong>«تصدير CSV»</strong> ينزّل كل شيء إلى جدول بيانات يمكن وضعه مباشرة في الأطروحة أو في الرسوم البيانية.</p>`,
];
document.querySelectorAll(".explain").forEach((det, i) => {
  const body = det.querySelector(".explain-body");
  if (body && AR_NOTES[i]) {
    const div = document.createElement("div");
    div.className = "ex-ar"; div.setAttribute("dir", "rtl"); div.lang = "ar";
    div.innerHTML = AR_NOTES[i];
    body.appendChild(div);
  }
  const sum = det.querySelector("summary");
  if (sum && !sum.dataset.bi) {
    sum.dataset.bi = "1";
    const en = sum.textContent.trim();
    sum.innerHTML = `<span class="sum-en">${en}</span><span class="sum-ar" dir="rtl">  ·  ما الذي يحدث في هذه الخطوة؟</span>`;
  }
});

init();
