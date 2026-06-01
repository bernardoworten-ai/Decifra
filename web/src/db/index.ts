/**
 * Cliente Postgres + Drizzle.
 *
 * Singleton lazy: a ligação só é criada na primeira query (não no import),
 * para que `next build` não falhe quando DATABASE_URL não está presente em
 * tempo de build. Em produção (Vercel) o DATABASE_URL aponta para Supabase/Neon.
 */
import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

export type Database = PostgresJsDatabase<typeof schema>;

let cached: { db: Database; client: postgres.Sql } | undefined;

function init(): { db: Database; client: postgres.Sql } {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL não está definido. Copia web/.env.example para web/.env e arranca a BD (docker compose up -d db).",
    );
  }
  // `max: 1` evita esgotar ligações em ambiente serverless (uma por invocação).
  const client = postgres(url, { max: 1, prepare: false });
  const db = drizzle(client, { schema });
  return { db, client };
}

/** Devolve o singleton do Drizzle, criando a ligação na primeira utilização. */
export function getDb(): Database {
  if (!cached) cached = init();
  return cached.db;
}

export { schema };
