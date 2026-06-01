import "dotenv/config";
import { defineConfig } from "drizzle-kit";

/**
 * Config do Drizzle Kit (introspecção / diffing futuro).
 * Na v1 a migração canónica é drizzle/0000_init.sql, aplicada por src/db/migrate.ts,
 * porque dá controlo total sobre extensões (pgvector/pg_trgm), coluna gerada
 * (search_vector) e triggers — coisas que o gerador não exprime de forma fiável.
 */
export default defineConfig({
  dialect: "postgresql",
  schema: "./src/db/schema.ts",
  out: "./drizzle",
  dbCredentials: {
    url: process.env.DATABASE_URL ?? "",
  },
});
