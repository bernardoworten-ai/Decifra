/**
 * Aplica as migrações SQL de /drizzle por ordem alfabética.
 * Idempotente (cada migração usa IF NOT EXISTS / OR REPLACE).
 *   npm run db:migrate
 */
import "dotenv/config";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import postgres from "postgres";

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL não definido. Vê web/.env.example.");

  const sql = postgres(url, { max: 1 });
  const dir = join(process.cwd(), "drizzle");
  const files = readdirSync(dir)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  for (const file of files) {
    const ddl = readFileSync(join(dir, file), "utf8");
    process.stdout.write(`→ a aplicar ${file}…\n`);
    await sql.unsafe(ddl);
  }

  await sql.end();
  console.log(`✓ ${files.length} migração(ões) aplicada(s).`);
}

main().catch((err) => {
  console.error("✗ Falha na migração:", err);
  process.exit(1);
});
