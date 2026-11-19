"use strict";
// Interface do buscador. Todo texto vindo das páginas raspadas é escapado antes de ir para o HTML.

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
const brl = (v) => v == null ? "" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const fmtDate = (iso) => iso ? new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
const TIER = { premium: "Premium / Primeira linha", intermediaria: "Segunda linha / Intermediária", custo_beneficio: "Custo-benefício", sem_classificacao: "Sem classificação" };
const REP = { boa: "Reputação boa", regular: "Reputação regular", ruim: "Reputação ruim", sem_informacao: "Reputação: sem informações" };
const COND = { novo: "Novo", usado: "Usado", recondicionado: "Recondicionado" };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
  return data;
}

// ---------------- navegação ----------------
function show(view) {
  $$(".view").forEach((v) => (v.hidden = v.id !== `view-${view}`));
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === (view === "results" ? "home" : view)));
}
function route() {
  const h = location.hash || "#/";
  const m = h.match(/^#\/r\/(\d+)/);
  if (m) { loadSearch(+m[1]); return; }
  if (h.startsWith("#/config")) { show("config"); loadConfig(); return; }
  show("home"); loadHome();
}
window.addEventListener("hashchange", route);

// ---------------- início ----------------
async function loadHome() {
  try {
    const [hist, st] = await Promise.all([api("/api/history?limit=15"), api("/api/status")]);
    const list = $("#recent-list");
    const done = hist.filter((h) => h.status === "done");
    list.innerHTML = done.length ? done.map((h) => `<li><button data-id="${h.id}"><span class="mono">${esc(h.code)}</span><span class="muted small">${h.stats ? `${h.stats.listings} anúncios · ` : ""}${fmtDate(h.collected_at)}</span></button></li>`).join("")
      : '<li class="muted">Nenhuma pesquisa ainda.</li>';
    list.querySelectorAll("button").forEach((b) => b.onclick = () => (location.hash = `#/r/${b.dataset.id}`));
    const warn = $("#setup-warning");
    const msgs = [];
    if (!Object.values(st.providers).some(Boolean)) msgs.push("Nenhum mecanismo de pesquisa configurado: defina <b>SERPAPI_KEY</b> ou <b>GOOGLE_CSE_KEY</b> + <b>GOOGLE_CSE_CX</b> no arquivo .env.");
    if (!st.ai_available) msgs.push("IA não configurada (<b>ANTHROPIC_API_KEY</b>): a pesquisa de preços funciona, mas os fabricantes ficarão sem classificação.");
    warn.hidden = !msgs.length;
    warn.innerHTML = msgs.join("<br>");
  } catch (e) { /* tela continua utilizável */ }
}

$("#search-form").addEventListener("submit", (ev) => { ev.preventDefault(); startSearch($("#code").value, false); });

async function startSearch(code, refresh) {
  const err = $("#form-error");
  err.hidden = true;
  const btn = $("#search-form button");
  btn.disabled = true;
  try {
    const r = await api("/api/search", { method: "POST", body: JSON.stringify({ code, refresh }) });
    if (r.cached) { location.hash = `#/r/${r.search_id}`; return; }
    show("home");
    await poll(r.search_id);
  } catch (e) {
    show("home");
    err.textContent = e.message; err.hidden = false;
  } finally { btn.disabled = false; }
}

async function poll(id) {
  const box = $("#progress");
  box.hidden = false;
  try {
    for (;;) {
      const r = await api(`/api/search/${id}`);
      if (r.status === "running") {
        const p = r.job.progress || {};
        $("#progress-stage").textContent = r.job.stage + "…";
        const parts = [];
        if (p.google_results != null) parts.push(`${p.google_results} resultados do Google`);
        if (p.sites_accessed != null) parts.push(`${p.sites_accessed} sites lidos`);
        if (p.sites_failed) parts.push(`${p.sites_failed} sem acesso`);
        parts.push(`${Math.round(r.job.elapsed)} s`);
        $("#progress-detail").textContent = parts.join(" · ");
        await new Promise((res) => setTimeout(res, 1200));
        continue;
      }
      if (r.status === "error") throw new Error(r.error);
      box.hidden = true;
      if (location.hash === `#/r/${id}`) renderResult(r.result); else location.hash = `#/r/${id}`;
      return;
    }
  } catch (e) {
    box.hidden = true;
    const err = $("#form-error"); err.textContent = e.message; err.hidden = false;
  }
}

// ---------------- resultados ----------------
let RESULT = null;

async function loadSearch(id) {
  try {
    const r = await api(`/api/search/${id}`);
    if (r.status === "running") { show("home"); poll(id); return; }
    if (r.status === "error") throw new Error(r.error);
    renderResult(r.result);
  } catch (e) {
    show("home"); loadHome();
    const err = $("#form-error"); err.textContent = e.message; err.hidden = false;
  }
}

function renderResult(res) {
  RESULT = res;
  show("results");
  $("#r-code").textContent = res.code;
  const ageH = (Date.now() - new Date(res.collected_at)) / 36e5;
  $("#r-collected").innerHTML = `Preços coletados em <b>${fmtDate(res.collected_at)}</b>` +
    (res.from_cache ? ` <span class="${ageH > 6 ? "stale" : "muted"}">— resultado armazenado; os preços podem ter mudado.</span>` : "");
  $("#r-refresh").onclick = () => startSearch(res.code, true);
  const s = res.stats;
  const stat = (n, l) => `<div class="stat"><b>${n ?? 0}</b><span>${l}</span></div>`;
  $("#r-stats").innerHTML = stat(s.google_results, "resultados encontrados") + stat(s.sites_accessed, "sites acessados") +
    stat(s.sites_failed, "sites sem acesso") + stat(s.listings, "anúncios identificados") +
    stat(s.listings_incomplete, "com informações incompletas") + stat(s.crossrefs_confirmed + " / " + s.crossrefs, "referências confirmadas / total") +
    (s.ai_cost_usd ? stat("US$ " + s.ai_cost_usd.toFixed(4), "custo de IA nesta pesquisa") : "");
  $("#r-warnings").innerHTML = (res.warnings || []).map((w) => `<div class="notice">${esc(w)}</div>`).join("");
  renderCrossrefs(res);
  buildFilters(res);
  applyFilters();
}

function renderCrossrefs(res) {
  const rows = [`<tr><td>${esc(res.oem.brand || "Não identificado")}</td><td class="mono">${esc(res.oem.code)}</td><td class="status-original">Código original pesquisado</td><td></td></tr>`];
  for (const r of res.crossrefs) {
    const label = r.status === "confirmada" ? "Referência cruzada confirmada" : "A verificar";
    const srcs = r.sources.slice(0, 4).map((e, i) => `<a href="${esc(safeUrl(e.url))}" target="_blank" rel="noopener noreferrer" title="${esc(e.snippet)}">${esc(e.domain)}</a> <span class="muted">(${esc(e.kind)})</span>`).join("<br>");
    rows.push(`<tr><td>${esc(r.brand)}</td><td class="mono">${esc(r.code)}</td><td class="status-${r.status}">${label}<div class="muted small">${esc(r.reason)}${r.ai_note ? " IA: " + esc(r.ai_note) : ""}</div></td><td class="small">${srcs}${r.sources.length > 4 ? `<br><span class="muted">+${r.sources.length - 4} fontes</span>` : ""}</td></tr>`);
  }
  $("#r-crossrefs").innerHTML = `<div class="table-wrap"><table><thead><tr><th>Fabricante</th><th>Código</th><th>Identificação</th><th>Fontes</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>` +
    (res.crossrefs.length ? "" : '<p class="empty">Nenhuma referência cruzada encontrada nas páginas acessadas.</p>');
}

function allListings() { return Object.values(RESULT.sections).flat(); }

function buildFilters(res) {
  const items = allListings();
  const count = (key) => items.reduce((m, d) => (d[key] ? m.set(d[key], (m.get(d[key]) || 0) + 1) : m), new Map());
  const brandsMap = new Map();
  items.forEach((d) => { if (d.brand_key) brandsMap.set(d.brand_key, { name: d.brand, n: (brandsMap.get(d.brand_key)?.n || 0) + 1 }); });
  $("#f-brands").innerHTML = [...brandsMap].sort((a, b) => b[1].n - a[1].n).map(([k, v]) => `<label class="check"><input type="checkbox" value="${esc(k)}">${esc(v.name)} <span class="muted">(${v.n})</span></label>`).join("") || '<span class="muted small">Nenhum fabricante identificado</span>';
  $("#f-tiers").innerHTML = Object.entries(TIER).map(([k, v]) => `<label class="check"><input type="checkbox" value="${k}">${v}</label>`).join("");
  $("#f-stores").innerHTML = [...count("store")].sort((a, b) => b[1] - a[1]).map(([k, n]) => `<label class="check"><input type="checkbox" value="${esc(k)}">${esc(k)} <span class="muted">(${n})</span></label>`).join("");
  $$("#filters input, #filters select").forEach((el) => (el.oninput = applyFilters));
  $("#f-clear").onclick = () => { $$("#filters input[type=checkbox]").forEach((c) => (c.checked = false)); $$("#filters input[type=number]").forEach((c) => (c.value = "")); $("#f-origin").value = ""; $("#f-cond").value = ""; applyFilters(); };
  if (window.innerWidth < 820) $("#filters-box").open = false;
}

const checked = (sel) => $$(`${sel} input:checked`).map((c) => c.value);

function applyFilters() {
  if (!RESULT) return;
  const brandsSel = checked("#f-brands"), tiers = checked("#f-tiers"), stores = checked("#f-stores");
  const pmin = parseFloat($("#f-pmin").value), pmax = parseFloat($("#f-pmax").value);
  const origin = $("#f-origin").value, cond = $("#f-cond").value, onlyConfirmed = $("#f-confirmed").checked;
  const sort = $("#f-sort").value;
  const tierOf = (d) => RESULT.manufacturers[d.brand_key]?.tier || "sem_classificacao";
  const keep = (d) =>
    (!brandsSel.length || brandsSel.includes(d.brand_key)) &&
    (!tiers.length || tiers.includes(tierOf(d))) &&
    (!stores.length || stores.includes(d.store)) &&
    (isNaN(pmin) || (d.price != null && d.price >= pmin)) &&
    (isNaN(pmax) || (d.price != null && d.price <= pmax)) &&
    (!origin || d.origin === origin) && (!cond || d.condition === cond);
  const sorter = {
    price_asc: (a, b) => (a.price == null) - (b.price == null) || (a.price ?? 0) - (b.price ?? 0),
    price_desc: (a, b) => (a.price == null) - (b.price == null) || (b.price ?? 0) - (a.price ?? 0),
    relevance: (a, b) => a.position - b.position,
  }[sort];
  for (const sec of ["original", "confirmed", "to_verify"]) {
    let list = RESULT.sections[sec].filter(keep);
    if (onlyConfirmed && sec !== "confirmed") list = [];
    list.sort(sorter);
    $(`#c-${sec}`).textContent = `(${list.length}${list.length !== RESULT.sections[sec].length ? " de " + RESULT.sections[sec].length : ""})`;
    $(`#s-${sec}`).innerHTML = list.length ? list.map(card).join("") : '<p class="empty">Nenhum anúncio nesta categoria.</p>';
  }
  $$(".tier-btn").forEach((b) => (b.onclick = () => showManufacturer(b.dataset.key)));
  $$(".rep-btn").forEach((b) => (b.onclick = () => showReputation(b.dataset.key)));
}

function card(d) {
  const m = RESULT.manufacturers[d.brand_key];
  const tier = m?.tier || "sem_classificacao";
  const img = safeUrl(d.image) ? `<img src="${esc(d.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(document.createTextNode('sem foto'))">` : "sem foto";
  const chips = [];
  if (d.brand) chips.push(`<button class="chip tier-btn tier-${tier}" data-key="${esc(d.brand_key)}" title="${m?.pending ? "* análise ainda não realizada — clique para ver o motivo" : "Ver análise do fabricante"}">${esc(TIER[tier])}${m?.pending ? " *" : ""}</button>`);
  if (d.origin) chips.push(`<span class="chip">${d.origin === "original" ? "Original (montadora)" : "Paralelo"}</span>`);
  if (d.ref_status) chips.push(`<span class="chip status-${d.ref_status}" title="${esc(d.ref_reason || "")}">${d.ref_status === "confirmada" ? "Referência confirmada" : "Equivalência a verificar"}</span>`);
  if (d.same_product_stores > 1) chips.push(`<span class="chip">mesmo produto em ${d.same_product_stores} anúncios</span>`);
  if (RESULT.reputation_enabled) {
    const rep = RESULT.reputations[d.seller_key];
    if (rep) chips.push(`<button class="chip rep-btn rep-${rep.overall}" data-key="${esc(d.seller_key)}">${esc(REP[rep.overall] || REP.sem_informacao)}</button>`);
  }
  const seller = d.seller && d.seller !== d.store ? ` · vendedor ${esc(d.seller)}` : "";
  return `<article class="card">
    <div class="thumb">${img}</div>
    <div>
      <h3>${esc(d.title || "(nome não informado)")}</h3>
      <div class="meta">
        <span>Código: <b class="mono">${esc(d.announced_code || "não identificado")}</b></span>
        <span>Fabricante: <b>${esc(d.brand || "não informado")}</b></span>
        <span>Condição: <b>${esc(COND[d.condition] || "não informada")}</b></span>
        <span>Loja: <b>${esc(d.store)}</b>${seller}</span>
      </div>
      <div class="chips">${chips.join("")}</div>
      ${d.missing.length ? `<div class="incomplete">Não informado no anúncio: ${esc(d.missing.join(", "))}</div>` : ""}
    </div>
    <div class="price-col">
      ${d.price != null ? `<div class="price">${brl(d.price)}</div>` : '<div class="price na">preço não identificado</div>'}
      <a class="btn primary" style="font-size:.9rem;padding:.5rem .9rem" href="${esc(safeUrl(d.url))}" target="_blank" rel="noopener noreferrer">Ver anúncio</a>
    </div>
  </article>`;
}

function sourcesList(sources) {
  if (!sources?.length) return '<p class="muted">Nenhuma fonte verificável.</p>';
  return "<ul>" + sources.map((s) => `<li><a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a> <span class="muted small">(${esc(s.type)})</span></li>`).join("") + "</ul>";
}

function modal(html) { $("#modal-body").innerHTML = html; $("#modal").showModal(); }

function showManufacturer(key) {
  const m = RESULT.manufacturers[key];
  if (!m) return;
  modal(`<h2>${esc(m.brand)} — ${esc(TIER[m.tier])}</h2>
    <p class="muted small">Segmento: ${esc(m.category)}${m.analyzed_at ? " · analisado em " + fmtDate(m.analyzed_at) : ""}${m.cached ? " (análise armazenada)" : ""}</p>
    ${m.summary ? `<p>${esc(m.summary)}</p>` : ""}
    ${m.history ? `<p><b>Histórico:</b> ${esc(m.history)}</p>` : ""}
    ${m.specialization ? `<p><b>Especialização:</b> ${esc(m.specialization)}</p>` : ""}
    ${m.quality_evidence ? `<p><b>Evidências de qualidade:</b> ${esc(m.quality_evidence)}</p>` : ""}
    ${m.certifications?.length ? `<p><b>Certificações:</b> ${esc(m.certifications.join(", "))}</p>` : ""}
    <p><b>Justificativa:</b> ${esc(m.justification || "")}</p>
    <h3>Fontes</h3>${sourcesList(m.sources)}`);
}

function showReputation(key) {
  const r = RESULT.reputations[key];
  if (!r) return;
  modal(`<h2>${esc(r.seller)} — ${esc(REP[r.overall])}</h2>
    ${r.analyzed_at ? `<p class="muted small">Verificado em ${fmtDate(r.analyzed_at)}</p>` : ""}
    <p>${esc(r.summary || "")}</p>
    ${r.ratings?.length ? "<ul>" + r.ratings.map((x) => `<li>${esc(x.platform)}: nota ${esc(x.score || "?")}${x.review_count ? ` (${esc(x.review_count)} avaliações)` : ""}</li>`).join("") + "</ul>" : ""}
    ${r.complaints ? `<p><b>Reclamações:</b> ${esc(r.complaints)}</p>` : ""}
    ${r.resolution_rate ? `<p><b>Índice de solução:</b> ${esc(r.resolution_rate)}</p>` : ""}
    ${r.years_active ? `<p><b>Tempo de atuação:</b> ${esc(r.years_active)}</p>` : ""}
    <p class="muted small">A ausência de informações não indica má reputação.</p>
    <h3>Fontes</h3>${sourcesList(r.sources)}`);
}

// ---------------- configurações / administração ----------------
const SETTINGS_UI = [
  ["reputation_enabled", "bool", "Análise de reputação dos vendedores", "Consulta Reclame Aqui, Mercado Livre e avaliações públicas com IA. Desativada: nenhuma consulta e nenhum token gasto."],
  ["manufacturer_ai_enabled", "bool", "Classificação de fabricantes por IA", "Análises ficam armazenadas e são reutilizadas."],
  ["crossref_ai_enabled", "bool", "IA para referências cruzadas ambíguas", "Envia apenas trechos curtos das páginas."],
  ["respect_robots", "bool", "Respeitar robots.txt", "Sites que proíbem acesso automatizado não são lidos."],
  ["use_browser", "bool", "Navegador para páginas dinâmicas (Playwright)", "Mais lento; usado só quando a página não traz dados no HTML."],
  ["search_provider", "select:auto|serpapi|google_cse", "Mecanismo de pesquisa", "auto = o primeiro com chave configurada."],
  ["max_results", "int", "Resultados do Google por pesquisa", "Meta inicial: até 50."],
  ["crossref_search_count", "int", "Referências cruzadas pesquisadas em seguida", "0 desativa a pesquisa dos códigos equivalentes."],
  ["crossref_search_results", "int", "Resultados por referência cruzada", ""],
  ["crossref_min_sources", "int", "Sites independentes para confirmar equivalência", "Quando não há catálogo técnico do fabricante."],
  ["cache_hours", "int", "Validade dos resultados armazenados (horas)", "0 = sempre coletar de novo."],
  ["fetch_concurrency", "int", "Acessos simultâneos", ""],
  ["fetch_timeout", "int", "Tempo limite por página (s)", ""],
  ["max_brands_analyzed", "int", "Fabricantes analisados por pesquisa", ""],
  ["max_sellers_analyzed", "int", "Vendedores analisados por pesquisa", ""],
  ["manufacturer_cache_days", "int", "Validade da análise de fabricante (dias)", ""],
  ["reputation_cache_days", "int", "Validade da análise de reputação (dias)", ""],
  ["blocked_domains", "text", "Sites ignorados", "Um domínio por linha."],
  ["catalog_domains", "text", "Catálogos técnicos adicionais", "Domínios tratados como fonte técnica para confirmar referências."],
];

$$(".tab").forEach((t) => (t.onclick = () => {
  $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
  $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== t.dataset.tab));
  loadTab(t.dataset.tab);
}));

async function loadConfig() {
  const [s, st] = await Promise.all([api("/api/settings"), api("/api/status")]);
  $("#status-box").innerHTML = `Mecanismos de pesquisa: ${Object.entries(st.providers).map(([k, v]) => `${k} ${v ? "✔" : "✘ (sem chave)"}`).join(" · ")}<br>IA: ${st.ai_available ? `✔ ${esc(st.ai_model)} (esforço ${esc(st.ai_effort)})` : "✘ ANTHROPIC_API_KEY não configurada"}`;
  const f = $("#settings-form");
  f.innerHTML = SETTINGS_UI.map(([k, type, label, help]) => {
    const v = s[k];
    if (type === "bool") return `<div class="set toggle"><input type="checkbox" id="s-${k}" name="${k}" ${v ? "checked" : ""}><div><label for="s-${k}">${label}</label><div class="help">${help}</div></div></div>`;
    if (type.startsWith("select:")) return `<div class="set"><label for="s-${k}">${label}</label><select id="s-${k}" name="${k}">${type.slice(7).split("|").map((o) => `<option ${o === v ? "selected" : ""}>${o}</option>`).join("")}</select><div class="help">${help}</div></div>`;
    if (type === "text") return `<div class="set"><label for="s-${k}">${label}</label><textarea id="s-${k}" name="${k}" rows="3">${esc(v)}</textarea><div class="help">${help}</div></div>`;
    return `<div class="set"><label for="s-${k}">${label}</label><input type="number" min="0" id="s-${k}" name="${k}" value="${esc(v)}"><div class="help">${help}</div></div>`;
  }).join("") + '<div class="actions"><button class="btn primary" type="submit">Salvar configurações</button></div>';
  f.onsubmit = async (ev) => {
    ev.preventDefault();
    const body = {};
    for (const [k, type] of SETTINGS_UI) {
      const el = f.elements[k];
      body[k] = type === "bool" ? el.checked : type === "int" ? parseInt(el.value || "0", 10) : el.value;
    }
    try { await api("/api/settings", { method: "PUT", body: JSON.stringify(body) }); $("#settings-saved").hidden = false; setTimeout(() => ($("#settings-saved").hidden = true), 2500); }
    catch (e) { alert(e.message); }
  };
}

const table = (head, rows) => `<table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("") || `<tr><td colspan="${head.length}" class="muted">Sem registros.</td></tr>`}</tbody></table>`;

async function loadTab(tab) {
  if (tab === "settings") return loadConfig();
  if (tab === "searches") {
    const h = await api("/api/history?limit=200");
    $("#t-searches").innerHTML = table(["Data", "Código", "Situação", "Google", "Sites lidos", "Falhas", "Anúncios", "Incompletos", "Custo IA"],
      h.map((x) => `<tr><td>${fmtDate(x.collected_at)}</td><td class="mono">${x.status === "done" ? `<a href="#/r/${x.id}">${esc(x.code)}</a>` : esc(x.code)}</td><td>${esc(x.status)}${x.error ? `<div class="muted small">${esc(x.error)}</div>` : ""}</td><td>${x.stats?.google_results ?? ""}</td><td>${x.stats?.sites_accessed ?? ""}</td><td>${x.stats?.sites_failed ?? ""}</td><td>${x.stats?.listings ?? ""}</td><td>${x.stats?.listings_incomplete ?? ""}</td><td>${x.stats?.ai_cost_usd != null ? "US$ " + x.stats.ai_cost_usd.toFixed(4) : ""}</td></tr>`));
  }
  if (tab === "failures") {
    const f = await api("/api/admin/failures");
    $("#t-failures").innerHTML = table(["Data", "Código", "Site", "Ocorrência", "Detalhe"],
      f.map((x) => `<tr><td>${fmtDate(x.at)}</td><td class="mono">${esc(x.code || "")}</td><td><a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener noreferrer">${esc(x.domain)}</a></td><td>${esc(x.outcome)}</td><td>${esc(x.detail)}</td></tr>`));
  }
  if (tab === "tokens") {
    const t = await api("/api/admin/tokens");
    const g = t.total;
    $("#t-tokens").innerHTML = `<div class="totals"><div class="stat"><b>${g.calls}</b><span>chamadas de IA</span></div><div class="stat"><b>${(g.input_tokens || 0).toLocaleString("pt-BR")}</b><span>tokens de entrada</span></div><div class="stat"><b>${(g.output_tokens || 0).toLocaleString("pt-BR")}</b><span>tokens de saída</span></div><div class="stat"><b>US$ ${(g.cost_usd || 0).toFixed(4)}</b><span>custo estimado</span></div></div>
      <h3>Por tipo de análise</h3><div class="table-wrap">${table(["Análise", "Modelo", "Chamadas", "Entrada", "Saída", "Pesquisas web", "Custo (US$)"],
        t.by_operation.map((x) => `<tr><td>${esc(x.operation)}</td><td>${esc(x.model)}</td><td>${x.calls}</td><td>${x.input_tokens}</td><td>${x.output_tokens}</td><td>${x.web_searches}</td><td>${(x.cost_usd || 0).toFixed(4)}</td></tr>`))}</div>
      <h3>Operações recentes</h3><div class="table-wrap">${table(["Data", "Pesquisa", "Análise", "Assunto", "Modelo", "Entrada", "Saída", "Web", "Custo (US$)", "OK"],
        t.rows.map((x) => `<tr><td>${fmtDate(x.at)}</td><td>${x.search_id ?? ""}</td><td>${esc(x.operation)}</td><td>${esc(x.subject)}</td><td>${esc(x.model)}</td><td>${x.input_tokens}</td><td>${x.output_tokens}</td><td>${x.web_searches}</td><td>${(x.cost_usd || 0).toFixed(4)}</td><td>${x.ok ? "✔" : "✘ " + esc(x.detail || "")}</td></tr>`))}</div>`;
  }
  if (tab === "manufacturers") {
    const m = await api("/api/admin/manufacturers");
    $("#t-manufacturers").innerHTML = table(["Data", "Fabricante", "Segmento", "Classificação", "Justificativa", "Fontes"],
      m.map((x) => `<tr><td>${fmtDate(x.at)}</td><td>${esc(x.brand)}</td><td>${esc(x.category)}</td><td class="tier-${esc(x.tier)}">${esc(TIER[x.tier] || x.tier)}</td><td class="small">${esc(x.data.justification)}</td><td class="small">${(x.data.sources || []).map((s) => `<a href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${esc(s.type)}</a>`).join(", ")}</td></tr>`));
  }
}

route();
