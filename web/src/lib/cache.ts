/**
 * Cache best-effort (Upstash Redis, REST) para o caminho "cache-first" (blueprint §3/§7).
 *
 * Sem UPSTASH_REDIS_REST_URL/TOKEN degrada para no-op: tudo funciona igual, só sem
 * cache. A cache guarda o golden record JÁ MONTADO — nunca inventa factos; a regra
 * source/confidence mantém-se a montante (§1).
 */
import "server-only";
import { Redis } from "@upstash/redis";

// TTLs configuráveis: ficha estável (24h) vs bloco de preço/volátil (1h).
export const TTL_SHEET = 60 * 60 * 24;
export const TTL_PRICE = 60 * 60;

let client: Redis | null | undefined;

function getClient(): Redis | null {
  if (client !== undefined) return client;
  const url = process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN;
  client = url && token ? new Redis({ url, token }) : null;
  return client;
}

export function cacheEnabled(): boolean {
  return getClient() !== null;
}

export const cacheKeys = {
  lookupEan: (ean: string) => `decifra:lookup:ean:${ean}`,
  lookupQ: (q: string) => `decifra:lookup:q:${q.toLowerCase().replace(/\s+/g, " ").trim()}`,
  productIndex: (slug: string) => `decifra:idx:product:${slug}`,
};

export async function cacheGet<T>(key: string): Promise<T | null> {
  const c = getClient();
  if (!c) return null;
  try {
    return (await c.get<T>(key)) ?? null;
  } catch {
    return null; // best-effort: falha de cache nunca quebra a leitura
  }
}

export async function cacheSet(key: string, value: unknown, ttlSeconds: number): Promise<void> {
  const c = getClient();
  if (!c) return;
  try {
    await c.set(key, value, { ex: ttlSeconds });
  } catch {
    /* no-op */
  }
}

export async function cacheDel(...keys: string[]): Promise<void> {
  const c = getClient();
  if (!c || keys.length === 0) return;
  try {
    await c.del(...keys);
  } catch {
    /* no-op */
  }
}

/** Regista uma chave de lookup sob o índice do produto, para invalidação por slug. */
export async function registerProductKey(slug: string, key: string): Promise<void> {
  const c = getClient();
  if (!c) return;
  try {
    const idx = cacheKeys.productIndex(slug);
    await c.sadd(idx, key);
    await c.expire(idx, TTL_SHEET);
  } catch {
    /* no-op */
  }
}

// Fallback em memória (single-instance) quando não há Redis.
const _memRate = new Map<string, number>();

/** Rate-limit best-effort: true se a ação é permitida agora; false se em cooldown. */
export async function rateLimit(key: string, windowSeconds: number): Promise<boolean> {
  const c = getClient();
  if (c) {
    try {
      const res = await c.set(key, "1", { nx: true, ex: windowSeconds });
      return res === "OK";
    } catch {
      /* cai para memória */
    }
  }
  const now = Date.now();
  if (now < (_memRate.get(key) ?? 0)) return false;
  _memRate.set(key, now + windowSeconds * 1000);
  return true;
}

/** Invalida todas as chaves de cache de um produto (preço/score mudaram). */
export async function invalidateProduct(slug: string): Promise<void> {
  const c = getClient();
  if (!c) return;
  try {
    const idx = cacheKeys.productIndex(slug);
    const members = (await c.smembers(idx)) as string[];
    if (members.length > 0) await c.del(...members);
    await c.del(idx);
  } catch {
    /* no-op */
  }
}
