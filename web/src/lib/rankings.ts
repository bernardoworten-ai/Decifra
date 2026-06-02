/**
 * Leitura dos rankings (Tops por critério) — snapshots imutáveis por período.
 * Gerados pelos workers (score_recompute_month); aqui só se lê o último mês.
 */
import "server-only";
import { and, eq, sql } from "drizzle-orm";
import { getDb } from "@/db";
import { categories, rankings } from "@/db/schema";

export type CriterionUnit = "score" | "value" | "price";

/** Critérios de ranking, na ordem de apresentação (espelha os workers). */
export const CRITERIA: { key: string; label: string; unit: CriterionUnit; hint: string }[] = [
  { key: "overall", label: "Melhores no geral", unit: "score", hint: "DECIFRA Score global" },
  { key: "value", label: "Melhor relação qualidade/preço", unit: "value", hint: "pontos de score por 100€" },
  { key: "cheapest", label: "Mais baratos", unit: "price", hint: "preço mais baixo em stock" },
  { key: "premium", label: "Topo de gama", unit: "price", hint: "mais caros / topo" },
  { key: "material", label: "Melhor qualidade material", unit: "score", hint: "sub-score de construção" },
  { key: "feedback", label: "Melhores avaliações", unit: "score", hint: "nota de utilizadores ajustada" },
];

/** Categorias que já têm rankings gerados. */
export async function getTopsCategories() {
  const db = getDb();
  return db
    .selectDistinct({ id: categories.id, name: categories.name, slug: categories.slug })
    .from(categories)
    .innerJoin(rankings, eq(rankings.categoryId, categories.id));
}

/** Tops do último mês de uma categoria, agrupados por critério. */
export async function getCategoryTops(slug: string) {
  const db = getDb();
  const [category] = await db
    .select({ id: categories.id, name: categories.name, slug: categories.slug })
    .from(categories)
    .where(eq(categories.slug, slug))
    .limit(1);
  if (!category) return null;

  const [latest] = await db
    .select({ period: sql<string>`max(${rankings.periodKey})` })
    .from(rankings)
    .where(and(eq(rankings.categoryId, category.id), eq(rankings.periodType, "month")));
  const period = latest?.period ?? null;
  if (!period) return { category, period: null, groups: [] };

  const rows = await db.query.rankings.findMany({
    where: (r, { and, eq }) =>
      and(eq(r.categoryId, category.id), eq(r.periodType, "month"), eq(r.periodKey, period)),
    with: {
      items: {
        orderBy: (i, { asc }) => [asc(i.rank)],
        with: { product: { with: { score: true } } },
      },
    },
  });

  const byCriterion = new Map(rows.map((r) => [r.criterion, r]));
  const groups = CRITERIA.filter((c) => byCriterion.has(c.key)).map((c) => ({
    ...c,
    items: byCriterion.get(c.key)!.items,
  }));

  return { category, period, groups };
}

export type CategoryTops = NonNullable<Awaited<ReturnType<typeof getCategoryTops>>>;
