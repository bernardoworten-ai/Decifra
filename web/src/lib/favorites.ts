/**
 * Favoritos + alertas de preço. Utilizador anónimo identificado por cookie
 * (sem login); o email é opcional e só necessário para receber alertas.
 */
import "server-only";
import { cookies } from "next/headers";
import { and, desc, eq, sql } from "drizzle-orm";
import { getDb } from "@/db";
import { offers, products, savedItems, scores, users } from "@/db/schema";

export const UID_COOKIE = "decifra_uid";

/** Id do utilizador atual a partir do cookie (null se ainda não existir). */
export async function currentUserId(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(UID_COOKIE)?.value ?? null;
}

export async function isSaved(userId: string, productId: string): Promise<boolean> {
  const db = getDb();
  const [row] = await db
    .select({ id: savedItems.id })
    .from(savedItems)
    .where(and(eq(savedItems.userId, userId), eq(savedItems.productId, productId)))
    .limit(1);
  return Boolean(row);
}

export async function getSavedItemFor(userId: string, productId: string) {
  const db = getDb();
  const [row] = await db
    .select()
    .from(savedItems)
    .where(and(eq(savedItems.userId, userId), eq(savedItems.productId, productId)))
    .limit(1);
  return row ?? null;
}

export async function getUserEmail(userId: string): Promise<string | null> {
  const db = getDb();
  const [row] = await db.select({ email: users.email }).from(users).where(eq(users.id, userId)).limit(1);
  return row?.email ?? null;
}

/** Favoritos do utilizador, com preço mais baixo atual e alerta definido. */
export async function getSavedItems(userId: string) {
  const db = getDb();
  return db
    .select({
      savedId: savedItems.id,
      productId: products.id,
      slug: products.slug,
      brand: products.brand,
      canonicalName: products.canonicalName,
      imageUrl: products.imageUrl,
      priceAlert: savedItems.priceAlert,
      overall: scores.overall,
      cheapest: sql<
        string | null
      >`(SELECT min(price) FROM ${offers} o WHERE o.product_id = ${products.id} AND o.in_stock = true)`,
    })
    .from(savedItems)
    .innerJoin(products, eq(products.id, savedItems.productId))
    .leftJoin(scores, eq(scores.productId, products.id))
    .where(eq(savedItems.userId, userId))
    .orderBy(desc(savedItems.createdAt));
}
