/**
 * Acesso a dados (server-only) para a ficha de produto e listagens.
 * Usa as relações do Drizzle para carregar o golden record + camadas anexas.
 */
import "server-only";
import { asc, desc, eq } from "drizzle-orm";
import { getDb } from "@/db";
import { categoryAttributes, ingestionRuns } from "@/db/schema";

/** Frescura visível (§3/§7): última execução bem-sucedida das pipelines. */
export async function getDataFreshness(): Promise<Date | null> {
  const db = getDb();
  const [row] = await db
    .select({ at: ingestionRuns.finishedAt })
    .from(ingestionRuns)
    .where(eq(ingestionRuns.status, "ok"))
    .orderBy(desc(ingestionRuns.finishedAt))
    .limit(1);
  return row?.at ?? null;
}

export type AttributeMeta = {
  label: string;
  unit: string | null;
  dataType: string;
  weightInScore: string;
  displayOrder: number;
  isDiscriminant: boolean;
};

/** Ficha completa de um produto pelo slug (ou null se não existir). */
export async function getProductDetail(slug: string) {
  const db = getDb();

  const product = await db.query.products.findFirst({
    where: (p, { eq }) => eq(p.slug, slug),
    with: {
      category: { with: { parent: { with: { parent: true } } } },
      identifiers: true,
      specs: {
        with: { source: true },
        orderBy: (s, { asc }) => [asc(s.attributeKey)],
      },
      offers: {
        with: { store: true, source: true },
        orderBy: (o, { asc }) => [asc(o.price)],
      },
      reviews: {
        with: { source: true },
        orderBy: (r, { desc }) => [desc(r.reviewCount)],
      },
      themes: {
        orderBy: (t, { desc }) => [desc(t.frequency)],
      },
      score: true,
      signals: { with: { source: true } },
      // Compatibilidade (v3): acessórios deste aparelho / aparelhos deste acessório.
      accessories: { with: { accessory: { with: { offers: true, category: true } } } },
      compatibleWith: { with: { base: { with: { category: true } } } },
    },
  });

  if (!product) return null;

  const attributeMeta = product.categoryId
    ? await getAttributeMeta(product.categoryId)
    : new Map<string, AttributeMeta>();

  return { product, attributeMeta };
}

export type ProductDetail = NonNullable<Awaited<ReturnType<typeof getProductDetail>>>;

/** Mapa attribute_key → metadados (label, unidade, peso) de uma categoria. */
export async function getAttributeMeta(categoryId: string): Promise<Map<string, AttributeMeta>> {
  const db = getDb();
  const rows = await db
    .select()
    .from(categoryAttributes)
    .where(eq(categoryAttributes.categoryId, categoryId))
    .orderBy(asc(categoryAttributes.displayOrder));

  const map = new Map<string, AttributeMeta>();
  for (const r of rows) {
    map.set(r.key, {
      label: r.label,
      unit: r.unit,
      dataType: r.dataType,
      weightInScore: r.weightInScore,
      displayOrder: r.displayOrder,
      isDiscriminant: r.isDiscriminant,
    });
  }
  return map;
}

/** Lista de produtos para a home (com score e categoria). */
export async function getProductList() {
  const db = getDb();
  return db.query.products.findMany({
    with: {
      category: true,
      score: true,
      offers: { orderBy: (o, { asc }) => [asc(o.price)], limit: 1 },
    },
    orderBy: (p) => [desc(p.updatedAt)],
    limit: 24,
  });
}
