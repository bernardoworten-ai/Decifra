/**
 * Preço live on-demand (§3/§7) — caminho do botão "atualizar".
 *
 * Espelha o connector Python (workers/sources/price_live.py): Google Shopping via
 * DataForSEO / Bright Data / SerpApi (escolhe o mais barato configurado). SÓ
 * on-demand (nunca batch, §10). Graceful: sem credenciais devolve {configured:false};
 * em falha de rede devolve lista vazia (não quebra).
 */
import "server-only";
import { and, asc, eq } from "drizzle-orm";
import { getDb } from "@/db";
import { offers, productIdentifiers, products, sources, stores } from "@/db/schema";
import { invalidateProduct } from "./cache";

export type LiveOffer = {
  storeName: string;
  price: number;
  currency: string;
  url: string | null;
  inStock: boolean;
};

function currencyOf(priceText: string | undefined): string | null {
  if (!priceText) return null;
  if (priceText.includes("€")) return "EUR";
  if (priceText.includes("£")) return "GBP";
  if (priceText.includes("$")) return "USD";
  return null;
}

const numOf = (v: unknown): number | null => {
  if (v === null || v === undefined) return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : null;
};

// ──────────────────────────────  parsers (puros)  ───────────────────────────
export function parseSerpapi(payload: { shopping_results?: unknown[] }): LiveOffer[] {
  const out: LiveOffer[] = [];
  for (const r of (payload.shopping_results ?? []) as Record<string, unknown>[]) {
    const price = numOf(r.extracted_price);
    if (price === null) continue;
    out.push({
      storeName: String(r.source ?? r.seller ?? "Loja"),
      price,
      currency: currencyOf(r.price as string) ?? "EUR",
      url: (r.product_link as string) ?? (r.link as string) ?? null,
      inStock: true,
    });
  }
  return out;
}

export function parseDataforseo(result: { items?: unknown[] }): LiveOffer[] {
  const out: LiveOffer[] = [];
  for (const it of (result.items ?? []) as Record<string, unknown>[]) {
    const price = numOf(it.price ?? (it.price_info as Record<string, unknown>)?.current_price);
    if (price === null) continue;
    out.push({
      storeName: String(it.seller ?? it.shop ?? it.source ?? "Loja"),
      price,
      currency: String(it.currency ?? "EUR"),
      url: (it.url as string) ?? (it.link as string) ?? null,
      inStock: it.availability !== false && it.availability !== "out_of_stock",
    });
  }
  return out;
}

export function parseBrightdata(payload: { results?: unknown[]; data?: unknown[] }): LiveOffer[] {
  const rows = (payload.results ?? payload.data ?? []) as Record<string, unknown>[];
  const out: LiveOffer[] = [];
  for (const r of rows) {
    const price = numOf(r.price ?? r.final_price);
    if (price === null) continue;
    out.push({
      storeName: String(r.seller ?? r.merchant ?? "Loja"),
      price,
      currency: String(r.currency ?? "EUR"),
      url: (r.url as string) ?? (r.link as string) ?? null,
      inStock: true,
    });
  }
  return out;
}

// ───────────────────────────────  provider  ─────────────────────────────────
type Provider = "dataforseo" | "brightdata" | "serpapi";

function selectProvider(): Provider | null {
  if (process.env.DATAFORSEO_LOGIN && process.env.DATAFORSEO_PASSWORD) return "dataforseo";
  if (process.env.BRIGHTDATA_TOKEN) return "brightdata";
  if (process.env.SERPAPI_KEY) return "serpapi";
  return null;
}

async function fetchLiveOffers(
  provider: Provider,
  ean: string | null,
  title: string | null,
): Promise<LiveOffer[]> {
  const query = ean || title;
  if (!query) return [];
  try {
    if (provider === "serpapi") {
      const base = process.env.SERPAPI_BASE_URL ?? "https://serpapi.com";
      const url = `${base}/search.json?engine=google_shopping&gl=pt&hl=pt&q=${encodeURIComponent(query)}&api_key=${process.env.SERPAPI_KEY}`;
      const res = await fetch(url);
      if (!res.ok) return [];
      return parseSerpapi(await res.json());
    }
    if (provider === "brightdata") {
      const base = process.env.BRIGHTDATA_BASE_URL ?? "https://api.brightdata.com";
      const res = await fetch(`${base}/serp/google/shopping?country=pt&q=${encodeURIComponent(query)}`, {
        headers: { Authorization: `Bearer ${process.env.BRIGHTDATA_TOKEN}` },
      });
      if (!res.ok) return [];
      return parseBrightdata(await res.json());
    }
    // dataforseo
    const base = process.env.DATAFORSEO_BASE_URL ?? "https://api.dataforseo.com";
    const auth = Buffer.from(`${process.env.DATAFORSEO_LOGIN}:${process.env.DATAFORSEO_PASSWORD}`).toString("base64");
    const res = await fetch(`${base}/v3/merchant/google/products/live/advanced`, {
      method: "POST",
      headers: { Authorization: `Basic ${auth}`, "content-type": "application/json" },
      body: JSON.stringify([{ keyword: query, location_code: 2620, language_code: "pt" }]),
    });
    if (!res.ok) return [];
    const data = await res.json();
    const result = data?.tasks?.[0]?.result?.[0] ?? {};
    return parseDataforseo(result);
  } catch {
    return [];
  }
}

// ───────────────────────────────  helpers DB  ───────────────────────────────
async function ensureSourceId(name: string): Promise<string> {
  const db = getDb();
  const [e] = await db.select({ id: sources.id }).from(sources).where(eq(sources.name, name)).limit(1);
  if (e) return e.id;
  const [c] = await db
    .insert(sources)
    .values({ name, kind: "offers", trustWeight: "0.6" })
    .returning({ id: sources.id });
  return c.id;
}

async function ensureStoreId(name: string): Promise<string> {
  const db = getDb();
  const [e] = await db.select({ id: stores.id }).from(stores).where(eq(stores.name, name)).limit(1);
  if (e) return e.id;
  const [c] = await db.insert(stores).values({ name }).returning({ id: stores.id });
  return c.id;
}

export type RefreshResult =
  | { configured: false }
  | { configured: true; found: false }
  | { configured: true; found: true; offers: { store: string | null; price: number | null; currency: string }[]; checkedAt: string };

/** Atualiza as offers de um produto via preço live (só a fonte live; mantém os feeds). */
export async function refreshProductPrice(slug: string): Promise<RefreshResult> {
  const provider = selectProvider();
  if (!provider) return { configured: false };

  const db = getDb();
  const [product] = await db
    .select({ id: products.id, name: products.canonicalName })
    .from(products)
    .where(eq(products.slug, slug))
    .limit(1);
  if (!product) return { configured: true, found: false };

  const [eanRow] = await db
    .select({ v: productIdentifiers.idValue })
    .from(productIdentifiers)
    .where(and(eq(productIdentifiers.productId, product.id), eq(productIdentifiers.idType, "ean")))
    .limit(1);

  const live = await fetchLiveOffers(provider, eanRow?.v ?? null, product.name);
  const sourceId = await ensureSourceId(provider);

  // Substitui apenas as offers desta fonte live (não toca nos feeds Awin).
  await db.delete(offers).where(and(eq(offers.productId, product.id), eq(offers.sourceId, sourceId)));
  for (const o of live) {
    const storeId = await ensureStoreId(o.storeName);
    await db.insert(offers).values({
      productId: product.id,
      storeId,
      price: String(o.price),
      currency: o.currency,
      urlAffiliate: o.url,
      inStock: o.inStock,
      sourceId,
      capturedAt: new Date(),
    });
  }

  await invalidateProduct(slug);

  const updated = await db
    .select({ store: stores.name, price: offers.price, currency: offers.currency })
    .from(offers)
    .leftJoin(stores, eq(stores.id, offers.storeId))
    .where(eq(offers.productId, product.id))
    .orderBy(asc(offers.price));

  return {
    configured: true,
    found: true,
    offers: updated.map((u) => ({ store: u.store, price: numOf(u.price), currency: u.currency })),
    checkedAt: new Date().toISOString(),
  };
}
