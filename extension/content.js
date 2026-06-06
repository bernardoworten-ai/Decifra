// Content script: deteta o EAN/título do produto na página da loja.
// Responde a pedidos do popup (mensagem DECIFRA_DETECT).

function digits(s) {
  return String(s || "").replace(/\D/g, "");
}

function extractEan() {
  // 1) JSON-LD (schema.org Product / Offer)
  for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const data = JSON.parse(node.textContent);
      const list = Array.isArray(data) ? data : [data];
      for (const d of list) {
        const g =
          d.gtin13 || d.gtin || d.gtin12 || d.gtin8 || d.ean ||
          (d.offers && (d.offers.gtin13 || d.offers.gtin));
        if (g) return digits(g);
      }
    } catch {
      /* ignora JSON inválido */
    }
  }
  // 2) Microdata / meta
  const meta = document.querySelector(
    '[itemprop="gtin13"],[itemprop="gtin"],[itemprop="gtin12"],[property="product:ean"]',
  );
  if (meta) {
    const v = digits(meta.getAttribute("content") || meta.textContent);
    if (v.length >= 8) return v;
  }
  // 3) Texto: "EAN: 4548736132919"
  const text = document.body ? document.body.innerText : "";
  const m = text.match(/EAN[:\s]*([0-9]{13})/i) || text.match(/\b(\d{13})\b/);
  return m ? m[1] : null;
}

function extractTitle() {
  const og = document.querySelector('meta[property="og:title"]');
  if (og && og.content) return og.content.trim();
  const h1 = document.querySelector("h1");
  if (h1 && h1.innerText) return h1.innerText.trim();
  return document.title;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "DECIFRA_DETECT") {
    sendResponse({ ean: extractEan(), title: extractTitle(), url: location.href });
  }
  return true;
});
