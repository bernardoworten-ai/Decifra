/**
 * Lookup público "cache-first" (blueprint §3): tenta a cache (Upstash) primeiro;
 * em miss lê da BD, monta o resultado e popula a cache. Sem Redis funciona igual
 * (a cache é no-op). Usado pela extensão de browser e por integrações.
 */
import "server-only";
import { and, asc, eq, ilike, or } from "drizzle-orm";
import { getDb } from "@/db";
import { offers, productIdentifiers, products, scores, stores } from "@/db/schema";
import { cacheGet, cacheKeys, cacheSet, registerProductKey, TTL_PRICE } from "./cache";

const productCols = {
  id: products.id,
  slug: products.slug,
  brand: products.brand,
  model: products.model,
  canonicalName: products.canonicalName,
  imageUrl: products.imageUrl,
  overall: scores.overall,
  confidence: scores.confidence,
};

type ProductRow = {
  id: string;
  slug: string;
  brand: string | null;
  model: string | null;
  canonicalName: string | null;
  imageUrl: string | null;
  overall: string | null;
  confidence: string | null;
};

type Cheapest = {
  price: string | null;
  currency: string;
  store: string | null;
  url: string | null;
};

export type LookupResult = { product: ProductRow; cheapest: Cheapest | null };

function cacheKeyFor(opts: { ean?: string; q?: string }): string | null {
  if (opts.ean) return cacheKeys.lookupEan(opts.ean);
  if (opts.q && opts.q.trim()) return cacheKeys.lookupQ(opts.q);
  return null;
}

export async function lookupProduct(opts: { ean?: string; q?: string }): Promise<LookupResult | null> {
  const key = cacheKeyFor(opts);

  // 1) Cache-first.
  if (key) {
    const cached = await cacheGet<LookupResult>(key);
    if (cached) {
      console.info(`[cache] hit ${key}`);
      return cached;
    }
    console.info(`[cache] miss ${key}`);
  }

  // 2) Miss → ler da BD (a "fonte" do lookup).
  console.info(`[lookup] BD query ${key ?? JSON.stringify(opts)}`);
  const db = getDb();
  let product: ProductRow | undefined;

  if (opts.ean) {
    const [row] = await db
      .select(productCols)
      .from(productIdentifiers)
      .innerJoin(products, eq(products.id, productIdentifiers.productId))
      .leftJoin(scores, eq(scores.productId, products.id))
      .where(eq(productIdentifiers.idValue, opts.ean))
      .limit(1);
    product = row;
  }

  if (!product && opts.q && opts.q.trim()) {
    const term = `%${opts.q.trim()}%`;
    const [row] = await db
      .select(productCols)
      .from(products)
      .leftJoin(scores, eq(scores.productId, products.id))
      .where(
        or(
          ilike(products.canonicalName, term),
          ilike(products.brand, term),
          ilike(products.model, term),
        ),
      )
      .limit(1);
    product = row;
  }

  if (!product) return null;

  const [cheapest] = await db
    .select({
      price: offers.price,
      currency: offers.currency,
      store: stores.name,
      url: offers.urlAffiliate,
    })
    .from(offers)
    .leftJoin(stores, eq(stores.id, offers.storeId))
    .where(and(eq(offers.productId, product.id), eq(offers.inStock, true)))
    .orderBy(asc(offers.price))
    .limit(1);

  const result: LookupResult = { product, cheapest: cheapest ?? null };

  // 3) Popular a cache (TTL de preço: o resultado inclui bloco de preço).
  if (key) {
    await cacheSet(key, result, TTL_PRICE);
    await registerProductKey(product.slug, key);
  }
  return result;
}
