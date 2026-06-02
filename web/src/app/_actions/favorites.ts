"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";
import { and, eq } from "drizzle-orm";
import { getDb } from "@/db";
import { savedItems, users } from "@/db/schema";
import { UID_COOKIE } from "@/lib/favorites";

/** Garante um utilizador (anónimo) e o cookie; recria se a linha já não existir. */
async function ensureUserId(): Promise<string> {
  const db = getDb();
  const jar = await cookies();
  const existing = jar.get(UID_COOKIE)?.value;
  if (existing) {
    const [u] = await db.select({ id: users.id }).from(users).where(eq(users.id, existing)).limit(1);
    if (u) return existing;
  }
  const [created] = await db.insert(users).values({}).returning({ id: users.id });
  jar.set(UID_COOKIE, created.id, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
  return created.id;
}

export async function toggleFavorite(formData: FormData) {
  const productId = String(formData.get("productId") ?? "");
  if (!productId) return;
  const db = getDb();
  const userId = await ensureUserId();

  const [existing] = await db
    .select({ id: savedItems.id })
    .from(savedItems)
    .where(and(eq(savedItems.userId, userId), eq(savedItems.productId, productId)))
    .limit(1);

  if (existing) {
    await db.delete(savedItems).where(eq(savedItems.id, existing.id));
  } else {
    await db.insert(savedItems).values({ userId, productId });
  }
  revalidatePath("/favoritos");
}

export async function removeFavorite(formData: FormData) {
  const productId = String(formData.get("productId") ?? "");
  const jar = await cookies();
  const userId = jar.get(UID_COOKIE)?.value;
  if (!userId || !productId) return;
  await getDb()
    .delete(savedItems)
    .where(and(eq(savedItems.userId, userId), eq(savedItems.productId, productId)));
  revalidatePath("/favoritos");
}

export async function setPriceAlert(formData: FormData) {
  const productId = String(formData.get("productId") ?? "");
  const raw = String(formData.get("priceAlert") ?? "").replace(",", ".").trim();
  const value = raw === "" ? null : Number(raw);
  const priceAlert = value !== null && Number.isFinite(value) && value > 0 ? String(value) : null;

  const userId = await ensureUserId();
  await getDb()
    .update(savedItems)
    .set({ priceAlert })
    .where(and(eq(savedItems.userId, userId), eq(savedItems.productId, productId)));
  revalidatePath("/favoritos");
}

export async function setEmail(formData: FormData) {
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const userId = await ensureUserId();
  await getDb()
    .update(users)
    .set({ email: email || null })
    .where(eq(users.id, userId));
  revalidatePath("/favoritos");
}
