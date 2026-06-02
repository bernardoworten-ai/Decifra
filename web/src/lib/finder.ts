/**
 * Finder por specs (blueprint §6).
 *
 * Escolhe-se uma categoria → o sistema apresenta as perguntas discriminantes
 * (category_attributes.is_discriminant) → filtra products/specs (modelo EAV) →
 * devolve candidatos ordenados pelo DECIFRA Score, cada um com o *porquê* do match.
 *
 * v1: perguntas data-driven (curadas via category_attributes). A geração
 * adaptativa por IA para a cauda longa entra numa fase seguinte.
 */
import "server-only";
import { and, asc, desc, eq, inArray, isNotNull, sql } from "drizzle-orm";
import { getDb } from "@/db";
import {
  categories,
  categoryAttributes,
  finderSessions,
  products,
  scores,
  specs,
} from "@/db/schema";
import { num } from "./num";

export type FinderOption = { value: string; label: string };
export type FinderQuestion = {
  key: string;
  label: string;
  unit: string | null;
  dataType: string;
  options: FinderOption[];
};

export type FinderCandidate = {
  id: string;
  slug: string;
  brand: string | null;
  canonicalName: string | null;
  imageUrl: string | null;
  overall: number | null;
  why: { label: string; value: string }[];
};

/** Categorias com perguntas discriminantes (i.e., onde o finder é útil). */
export async function getFinderCategories() {
  const db = getDb();
  const discriminant = db
    .selectDistinct({ id: categoryAttributes.categoryId })
    .from(categoryAttributes)
    .where(eq(categoryAttributes.isDiscriminant, true));
  const rows = await db
    .select({ id: categories.id, slug: categories.slug, name: categories.name })
    .from(categories)
    .where(inArray(categories.id, discriminant));

  // Contagem de produtos por categoria (para o cartão).
  const counts = await db
    .select({ categoryId: products.categoryId, n: sql<number>`count(*)::int` })
    .from(products)
    .groupBy(products.categoryId);
  const countMap = new Map(counts.map((c) => [c.categoryId, c.n]));

  return rows.map((r) => ({ ...r, productCount: countMap.get(r.id) ?? 0 }));
}

export async function getFinderCategoryBySlug(slug: string) {
  const db = getDb();
  const [cat] = await db
    .select({ id: categories.id, slug: categories.slug, name: categories.name })
    .from(categories)
    .where(eq(categories.slug, slug))
    .limit(1);
  return cat ?? null;
}

/** Metadados (key → label/unit/dataType) dos atributos discriminantes. */
async function discriminantAttributes(categoryId: string) {
  const db = getDb();
  return db
    .select()
    .from(categoryAttributes)
    .where(and(eq(categoryAttributes.categoryId, categoryId), eq(categoryAttributes.isDiscriminant, true)))
    .orderBy(asc(categoryAttributes.displayOrder));
}

/** Perguntas discriminantes com opções derivadas dos dados reais da categoria. */
export async function getFinderQuestions(categoryId: string): Promise<FinderQuestion[]> {
  const db = getDb();
  const attrs = await discriminantAttributes(categoryId);
  const questions: FinderQuestion[] = [];

  for (const attr of attrs) {
    let options: FinderOption[] = [];

    if (attr.dataType === "bool") {
      options = [
        { value: "sim", label: "Sim" },
        { value: "nao", label: "Não" },
      ];
    } else if (attr.dataType === "number") {
      const rows = await db
        .selectDistinct({ v: specs.valueNum })
        .from(specs)
        .innerJoin(products, eq(products.id, specs.productId))
        .where(
          and(
            eq(products.categoryId, categoryId),
            eq(specs.attributeKey, attr.key),
            isNotNull(specs.valueNum),
          ),
        )
        .orderBy(asc(specs.valueNum));
      const nums = [...new Set(rows.map((r) => num(r.v)).filter((n): n is number => n !== null))];
      const unit = attr.unit ? ` ${attr.unit}` : "";
      options = nums.map((n) => ({ value: String(n), label: `≥ ${n}${unit}` }));
    } else {
      // enum / text → valores distintos presentes nos dados.
      const rows = await db
        .selectDistinct({ v: specs.valueText })
        .from(specs)
        .innerJoin(products, eq(products.id, specs.productId))
        .where(
          and(
            eq(products.categoryId, categoryId),
            eq(specs.attributeKey, attr.key),
            isNotNull(specs.valueText),
          ),
        )
        .orderBy(asc(specs.valueText));
      options = rows
        .map((r) => r.v)
        .filter((v): v is string => Boolean(v))
        .map((v) => ({ value: v, label: v }));
    }

    if (options.length > 0) {
      questions.push({
        key: attr.key,
        label: attr.label,
        unit: attr.unit,
        dataType: attr.dataType,
        options,
      });
    }
  }
  return questions;
}

function formatSpecValue(
  dataType: string,
  unit: string | null,
  valueText: string | null,
  valueNum: string | null,
): string {
  if (valueText) return valueText;
  const n = num(valueNum);
  if (n === null) return "—";
  return unit ? `${n} ${unit}` : String(n);
}

/** Filtra a categoria pelas respostas (AND sobre specs) e ordena por score. */
export async function runFinder(categoryId: string, answers: Record<string, string>) {
  const db = getDb();
  const attrs = await discriminantAttributes(categoryId);
  const attrByKey = new Map(attrs.map((a) => [a.key, a]));

  const conditions = [eq(products.categoryId, categoryId)];
  const answeredKeys: string[] = [];

  for (const [key, raw] of Object.entries(answers)) {
    const attr = attrByKey.get(key);
    if (!attr || !raw) continue;
    answeredKeys.push(key);

    if (attr.dataType === "bool") {
      if (raw === "sim") {
        conditions.push(
          sql`EXISTS (SELECT 1 FROM ${specs} s WHERE s.product_id = ${products.id}
            AND s.attribute_key = ${key} AND (s.value_num = 1 OR lower(s.value_text) = 'sim'))`,
        );
      } else {
        conditions.push(
          sql`NOT EXISTS (SELECT 1 FROM ${specs} s WHERE s.product_id = ${products.id}
            AND s.attribute_key = ${key} AND (s.value_num = 1 OR lower(s.value_text) = 'sim'))`,
        );
      }
    } else if (attr.dataType === "number") {
      const threshold = Number(raw);
      if (Number.isFinite(threshold)) {
        conditions.push(
          sql`EXISTS (SELECT 1 FROM ${specs} s WHERE s.product_id = ${products.id}
            AND s.attribute_key = ${key} AND s.value_num >= ${threshold})`,
        );
      }
    } else {
      conditions.push(
        sql`EXISTS (SELECT 1 FROM ${specs} s WHERE s.product_id = ${products.id}
          AND s.attribute_key = ${key} AND s.value_text = ${raw})`,
      );
    }
  }

  const rows = await db
    .select({
      id: products.id,
      slug: products.slug,
      brand: products.brand,
      canonicalName: products.canonicalName,
      imageUrl: products.imageUrl,
      overall: scores.overall,
    })
    .from(products)
    .leftJoin(scores, eq(scores.productId, products.id))
    .where(and(...conditions))
    .orderBy(desc(scores.overall));

  // "Porquê": valores das specs respondidas, por produto.
  const ids = rows.map((r) => r.id);
  const why = new Map<string, { label: string; value: string }[]>();
  if (ids.length > 0 && answeredKeys.length > 0) {
    const matched = await db
      .select({
        productId: specs.productId,
        key: specs.attributeKey,
        valueText: specs.valueText,
        valueNum: specs.valueNum,
        unit: specs.unit,
      })
      .from(specs)
      .where(and(inArray(specs.productId, ids), inArray(specs.attributeKey, answeredKeys)));
    for (const m of matched) {
      const attr = attrByKey.get(m.key);
      const list = why.get(m.productId) ?? [];
      list.push({
        label: attr?.label ?? m.key,
        value: formatSpecValue(attr?.dataType ?? "text", attr?.unit ?? m.unit, m.valueText, m.valueNum),
      });
      why.set(m.productId, list);
    }
  }

  const totalRow = await db
    .select({ n: sql<number>`count(*)::int` })
    .from(products)
    .where(eq(products.categoryId, categoryId));

  const candidates: FinderCandidate[] = rows.map((r) => ({
    id: r.id,
    slug: r.slug,
    brand: r.brand,
    canonicalName: r.canonicalName,
    imageUrl: r.imageUrl,
    overall: num(r.overall),
    why: why.get(r.id) ?? [],
  }));

  return { candidates, total: totalRow[0]?.n ?? 0, answeredCount: answeredKeys.length };
}

/** Regista a sessão de finder (analítica). Best-effort — nunca quebra a página. */
export async function recordFinderSession(
  categoryId: string,
  answers: Record<string, string>,
  candidateIds: string[],
) {
  try {
    await getDb().insert(finderSessions).values({ categoryId, answers, candidates: candidateIds });
  } catch {
    // analítica não-crítica
  }
}
