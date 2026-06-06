// Popup: deteta o produto na aba ativa e pede o veredicto ao DECIFRA.
// ⚙️ Em produção, troca API_BASE pelo teu domínio (e adiciona-o a host_permissions).
const API_BASE = "http://localhost:3000";

const el = (id) => document.getElementById(id);

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function detect(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { type: "DECIFRA_DETECT" }, (resp) => {
      resolve(chrome.runtime.lastError ? null : resp);
    });
  });
}

async function lookup({ ean, q }) {
  const params = new URLSearchParams();
  if (ean) params.set("ean", ean);
  else if (q) params.set("q", q);
  const res = await fetch(`${API_BASE}/api/lookup?${params.toString()}`);
  return res.json();
}

function render(data) {
  if (!data || !data.found) {
    el("result").innerHTML = `<p class="muted">Sem correspondência no DECIFRA (ainda).</p>`;
    return;
  }
  const p = data.product;
  const price =
    p.cheapest && p.cheapest.price != null
      ? `${p.cheapest.price.toFixed(2)} €${p.cheapest.store ? " · " + p.cheapest.store : ""}`
      : "—";
  el("result").innerHTML = `
    <div class="score">${p.overall != null ? Math.round(p.overall) : "—"}<span>/100</span></div>
    <div class="name">${p.canonicalName ?? ""}</div>
    <div class="price">desde ${price}</div>
    <a class="cta" href="${p.url}" target="_blank" rel="noopener">Ver no DECIFRA →</a>`;
}

async function init() {
  try {
    const tab = await activeTab();
    const detected = tab ? await detect(tab.id) : null;
    if (detected && (detected.ean || detected.title)) {
      el("detected").textContent = detected.ean ? `EAN ${detected.ean}` : detected.title;
      render(await lookup({ ean: detected.ean, q: detected.ean ? null : detected.title }));
    } else {
      el("result").innerHTML = `<p class="muted">Não detetei um produto. Pesquisa manualmente:</p>`;
    }
  } catch {
    el("result").innerHTML = `<p class="muted">Pesquisa um produto:</p>`;
  }
}

el("searchForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = el("q").value.trim();
  if (!q) return;
  el("result").innerHTML = `<p class="muted">A procurar…</p>`;
  render(await lookup({ q }));
});

init();
