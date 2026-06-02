/**
 * Lookup público (usado pela extensão de browser e por integrações):
 * resolve um produto por EAN ou por texto, devolvendo score + preço mais baixo.
 */
import "server-only";
import { and, asc, eq, ilike, or } from "drizzle-orm";
import { getDb } from "@/db";
import { offers, productIdentifiers, products, scores, stores } from "@/db/schema";

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

export async function lookupProduct(opts: { ean?: string; q?: string }) {
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

  return { product, cheapest: cheapest ?? null };
}
