"use strict";

const COUNTRIES = ["DE", "FR", "ES", "IT", "NL", "PL", "GB", "US", "CA", "AU", "BR", "MX", "PE",
  "AR", "CL", "CO", "IN", "ID", "TR", "UA", "KZ", "RU", "JP", "KR", "TH", "VN", "PH", "ZA", "NG"];
const COLORS = ["#3f9e4d", "#2563eb", "#d97706", "#9333ea", "#db2777", "#0891b2", "#65a30d", "#dc2626"];

const $ = (sel, root = document) => root.querySelector(sel);
const state = { offers: [], campaigns: [], campaign: null };

// ---------------------------------------------------------------- helpers
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function errorText(body, status) {
  if (!body) return `Ошибка ${status}`;
  const d = body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(e => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ");
  if (d && typeof d === "object") return Object.entries(d).map(([k, v]) => `${k}: ${v}`).join("; ");
  return `Ошибка ${status}`;
}

async function api(method, url, body) {
  const resp = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => null);
  if (!resp.ok) throw new Error(errorText(data, resp.status));
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const el = $("#toast");
  el.textContent = message;
  el.className = isError ? "error" : "";
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 6000 : 3000);
}

function fillSelect(select, items, selected, placeholder) {
  select.innerHTML = (placeholder ? `<option value="">${esc(placeholder)}</option>` : "") +
    items.map(i => `<option value="${i.id}">${esc(i.name)} (#${i.id})</option>`).join("");
  if (selected != null) select.value = String(selected);
}

function offerName(id) {
  const o = state.offers.find(x => x.id === id);
  return o ? o.name : `Оффер #${id}`;
}

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach(btn => btn.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b === btn));
  document.querySelectorAll(".panel").forEach(p => { p.hidden = p.id !== `tab-${btn.dataset.tab}`; });
  if (btn.dataset.tab === "editor" && !state.campaigns.length) loadCampaigns();
}));

// ---------------------------------------------------------------- part 1
async function loadMeta() {
  const form = $("#create-form");
  try {
    const meta = await api("GET", "/api/meta");
    state.offers = meta.offers;
    const d = meta.defaults;
    // Pre-select the configured default, or the only option when there is just one.
    const pick = (items, def) => def ?? (items.length === 1 ? items[0].id : null);
    fillSelect(form.offer_id, meta.offers, pick(meta.offers, null), "— выберите оффер —");
    fillSelect(form.group_id, meta.groups, pick(meta.groups, d.group_id), "— группа —");
    fillSelect(form.domain_id, meta.domains, pick(meta.domains, d.domain_id), "— домен —");
    fillSelect(form.traffic_source_id, meta.traffic_sources, pick(meta.traffic_sources, d.traffic_source_id), "— источник —");
    fillSelect($("#filter-group"), meta.groups, d.group_id ?? "", "Все группы");
  } catch (e) {
    toast(`Не удалось загрузить справочники Keitaro: ${e.message}`, true);
  }
}

$("#countries").innerHTML = COUNTRIES.map(c => `<option value="${c}">`).join("");

$("#create-form").addEventListener("submit", async ev => {
  ev.preventDefault();
  const form = ev.target;
  const button = form.querySelector("button[type=submit]");
  const result = $("#create-result");
  const payload = {
    name: form.name.value.trim(),
    country: form.country.value.trim().toUpperCase(),
    offer_id: Number(form.offer_id.value),
    group_id: Number(form.group_id.value),
    domain_id: Number(form.domain_id.value),
    traffic_source_id: Number(form.traffic_source_id.value),
  };
  button.disabled = true;
  button.textContent = "Создаём…";
  try {
    const c = await api("POST", "/api/campaigns", payload);
    result.className = "result";
    result.innerHTML = `Кампания <b>${esc(c.name)}</b> создана (ID ${c.keitaro_campaign_id}).<br>` +
      `Поток 1: ${esc(c.country)} → Google, поток 2: → ${esc(offerName(c.offer_id))}.<br>` +
      (c.url ? `Ссылка: <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a><br>` : "") +
      `<a href="#" data-open="${c.keitaro_campaign_id}">Открыть в редакторе</a>`;
    result.hidden = false;
    form.name.value = "";
    loadCreated();
    state.campaigns = [];
  } catch (e) {
    result.className = "result error";
    result.textContent = e.message;
    result.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Создать";
  }
});

async function loadCreated() {
  const tbody = $("#created-table tbody");
  const items = await api("GET", "/api/campaigns/created").catch(() => []);
  tbody.innerHTML = items.length ? items.map(c => `
    <tr>
      <td>${c.keitaro_campaign_id}</td>
      <td>${esc(c.name)}</td>
      <td>${esc(c.country)}</td>
      <td>${c.offer_id}</td>
      <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a>` : "—"}</td>
      <td>${new Date(c.created_at).toLocaleString("ru-RU")}</td>
      <td><a href="#" data-open="${c.keitaro_campaign_id}">Редактировать</a></td>
    </tr>`).join("") : `<tr><td colspan="7" class="empty">Пока ничего не создано</td></tr>`;
}

document.addEventListener("click", ev => {
  const link = ev.target.closest("[data-open]");
  if (!link) return;
  ev.preventDefault();
  openInEditor(Number(link.dataset.open));
});

async function openInEditor(campaignId) {
  document.querySelector('.tab[data-tab="editor"]').click();
  $("#filter-group").value = "";
  $("#filter-search").value = String(campaignId);
  await loadCampaigns();
  $("#campaign-select").value = String(campaignId);
  loadCampaign(campaignId);
}

// ---------------------------------------------------------------- part 2
let searchTimer;
$("#filter-group").addEventListener("change", loadCampaigns);
$("#filter-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadCampaigns, 300);
});
$("#campaign-select").addEventListener("change", ev => {
  if (ev.target.value) loadCampaign(Number(ev.target.value));
  else $("#campaign-view").innerHTML = "";
});

let campaignsRequest = 0;
async function loadCampaigns() {
  const requestId = ++campaignsRequest;
  const params = new URLSearchParams();
  if ($("#filter-group").value) params.set("group_id", $("#filter-group").value);
  if ($("#filter-search").value.trim()) params.set("search", $("#filter-search").value.trim());
  const select = $("#campaign-select");
  const current = select.value;
  try {
    const campaigns = await api("GET", `/api/campaigns?${params}`);
    // A slower, older request must not overwrite the result of a newer filter.
    if (requestId !== campaignsRequest) return;
    state.campaigns = campaigns;
    select.innerHTML = `<option value="">— выберите кампанию (${state.campaigns.length}) —</option>` +
      state.campaigns.map(c => `<option value="${c.id}">#${c.id} ${esc(c.name)}${c.state !== "active" ? ` [${esc(c.state)}]` : ""}</option>`).join("");
    if (state.campaigns.some(c => String(c.id) === current)) select.value = current;
    if (state.campaign && state.campaigns.some(c => c.id === state.campaign.id)) {
      select.value = String(state.campaign.id);
    }
  } catch (e) {
    if (requestId === campaignsRequest) toast(`Не удалось загрузить кампании: ${e.message}`, true);
  }
}

async function loadCampaign(id) {
  const view = $("#campaign-view");
  view.innerHTML = `<div class="card empty">Загрузка…</div>`;
  try {
    state.campaign = await api("GET", `/api/campaigns/${id}`);
    renderCampaign();
    loadHistory(id);
  } catch (e) {
    view.innerHTML = `<div class="card result error">${esc(e.message)}</div>`;
  }
}

function describeStream(s) {
  if (s.schema === "redirect") {
    const geo = s.filters.filter(f => f.name === "country")
      .map(f => `${f.mode === "accept" ? "" : "не "}${(f.payload || []).join(", ")}`).join("; ");
    return `Редирект${geo ? ` (страна: ${esc(geo)})` : ""} → ${esc(s.action_payload || "—")}`;
  }
  if (s.schema === "landings") return "Офферы";
  return esc(s.schema || "");
}

function renderCampaign() {
  const c = state.campaign;
  const streamsHtml = c.streams.map(renderStream).join("") ||
    `<div class="card empty">У кампании нет потоков</div>`;
  $("#campaign-view").innerHTML = `
    <div class="card">
      <div class="stream-head">
        <div>
          <h2 style="margin:0">#${c.id} ${esc(c.name)}</h2>
          <div class="meta">${esc(c.group || "без группы")} · ${esc(c.state || "")}
            ${c.url ? ` · <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.url)}</a>` : ""}</div>
        </div>
        <button class="secondary" data-reload>Обновить</button>
      </div>
    </div>
    ${streamsHtml}
    <div class="card">
      <h2>История изменений</h2>
      <ul class="history" id="history"><li class="empty">Загрузка…</li></ul>
    </div>`;
}

function renderStream(s) {
  const head = `
    <div class="stream-head">
      <div>
        <h3>Поток ${s.position ?? ""}: ${esc(s.name)}</h3>
        <div class="meta">${describeStream(s)} · ${esc(s.type)} · ${esc(s.state)}</div>
      </div>`;
  if (s.schema !== "landings") return `<div class="card">${head}</div></div>`;

  const inStream = new Set(s.offers.map(o => o.offer_id));
  const available = state.offers.filter(o => !inStream.has(o.id));
  const rows = s.offers.map((o, i) => `
    <tr>
      <td><span class="badge" style="background:${COLORS[i % COLORS.length]};color:#fff">&nbsp;</span>
        ${esc(o.name)} <span class="meta">#${o.offer_id}</span>
        ${o.state !== "active" ? `<span class="badge">${esc(o.state)}</span>` : ""}</td>
      <td class="num"><input class="share" type="number" min="0" max="100" step="1"
        value="${o.share}" data-share="${o.offer_id}"> %</td>
      <td class="num"><button class="danger" data-remove="${o.offer_id}">Удалить</button></td>
    </tr>`).join("");
  const bar = s.offers.map((o, i) =>
    `<span style="width:${Math.max(0, o.share)}%;background:${COLORS[i % COLORS.length]}" title="${esc(o.name)}: ${o.share}%"></span>`).join("");

  return `
    <div class="card" data-stream="${s.id}">
      ${head}
        <span class="badge ${s.shares_valid ? "ok" : "bad"}" data-total>Сумма: ${s.shares_total}%</span>
      </div>
      ${s.offers.length ? `
        <div class="bar">${bar}</div>
        <table>
          <thead><tr><th>Оффер</th><th class="num">Доля</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="add-row actions">
          <button class="primary" data-save disabled>Сохранить доли</button>
          <button class="secondary" data-equalize ${s.offers.length < 2 ? "disabled" : ""}>Распределить поровну</button>
        </div>` : `<p class="empty">В потоке нет офферов — весь трафик потока никуда не идёт.</p>`}
      <div class="add-row">
        <select data-add-select ${available.length ? "" : "disabled"}>
          ${available.length ? `<option value="">— добавить оффер —</option>` +
            available.map(o => `<option value="${o.id}">${esc(o.name)} (#${o.id})</option>`).join("")
            : `<option>Все доступные офферы уже в потоке</option>`}
        </select>
        <button class="secondary" data-add disabled>Добавить</button>
      </div>
    </div>`;
}

async function loadHistory(campaignId) {
  const items = await api("GET", `/api/campaigns/${campaignId}/history`).catch(() => []);
  const el = $("#history");
  if (!el) return;
  const names = { add: "добавлен оффер", remove: "удалён оффер", update: "изменены доли", equalize: "доли выровнены" };
  const fmt = m => Object.entries(m).map(([k, v]) => `#${k}: ${v}%`).join(", ") || "пусто";
  el.innerHTML = items.length ? items.map(h => `
    <li>${new Date(h.created_at).toLocaleString("ru-RU")} — поток ${h.stream_id}: ${names[h.action] || h.action}
      ${h.offer_id ? `#${h.offer_id}` : ""} · было [${esc(fmt(h.shares_before))}] → стало [${esc(fmt(h.shares_after))}]</li>`).join("")
    : `<li class="empty">Изменений через редактор ещё не было</li>`;
}

function replaceStream(updated) {
  const c = state.campaign;
  c.streams = c.streams.map(s => (s.id === updated.id ? updated : s));
  renderCampaign();
  loadHistory(c.id);
}

async function streamAction(card, fn, okMessage) {
  card.querySelectorAll("button, input, select").forEach(el => { el.disabled = true; });
  try {
    replaceStream(await fn());
    toast(okMessage);
  } catch (e) {
    toast(e.message, true);
    renderCampaign();
    loadHistory(state.campaign.id);
  }
}

const view = $("#campaign-view");

view.addEventListener("input", ev => {
  const card = ev.target.closest("[data-stream]");
  if (ev.target.matches("[data-share]") && card) {
    const values = [...card.querySelectorAll("[data-share]")].map(i => Number(i.value));
    const total = values.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
    const ok = total === 100 && values.every(v => Number.isInteger(v) && v >= 0 && v <= 100);
    const badge = card.querySelector("[data-total]");
    badge.textContent = `Сумма: ${total}%`;
    badge.className = `badge ${ok ? "ok" : "bad"}`;
    card.querySelector("[data-save]").disabled = !ok;
  }
});

view.addEventListener("change", ev => {
  if (ev.target.matches("[data-add-select]")) {
    ev.target.closest("[data-stream]").querySelector("[data-add]").disabled = !ev.target.value;
  }
});

view.addEventListener("click", ev => {
  if (ev.target.closest("[data-reload]")) return loadCampaign(state.campaign.id);
  const card = ev.target.closest("[data-stream]");
  if (!card) return;
  const streamId = Number(card.dataset.stream);

  const removeBtn = ev.target.closest("[data-remove]");
  if (removeBtn) {
    const offerId = Number(removeBtn.dataset.remove);
    if (!confirm(`Удалить «${offerName(offerId)}» из потока? Его доля будет распределена между остальными офферами.`)) return;
    return streamAction(card, () => api("DELETE", `/api/streams/${streamId}/offers/${offerId}`), "Оффер удалён");
  }
  if (ev.target.closest("[data-add]")) {
    const offerId = Number(card.querySelector("[data-add-select]").value);
    if (!offerId) return;
    return streamAction(card, () => api("POST", `/api/streams/${streamId}/offers`, { offer_id: offerId }), "Оффер добавлен");
  }
  if (ev.target.closest("[data-equalize]")) {
    return streamAction(card, () => api("POST", `/api/streams/${streamId}/equalize`), "Доли распределены поровну");
  }
  if (ev.target.closest("[data-save]")) {
    const offers = [...card.querySelectorAll("[data-share]")].map(i => ({
      offer_id: Number(i.dataset.share), share: Number(i.value),
    }));
    return streamAction(card, () => api("PUT", `/api/streams/${streamId}/offers`, { offers }), "Доли сохранены");
  }
});

// ---------------------------------------------------------------- init
loadMeta();
loadCreated();
