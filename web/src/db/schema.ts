/**
 * Schema Drizzle do DECIFRA — espelha drizzle/0000_init.sql (canónico).
 * Serve para queries tipadas e relações; as migrações vivem em /drizzle.
 * Tradução directa do blueprint (docs/blueprint-mvp.md §2.1).
 *
 * Nota: colunas `numeric` regressam como `string` (precisão preservada).
 * Usa os helpers de src/lib/num.ts para converter quando precisas de Number.
 */
import { relations, sql, type SQL } from "drizzle-orm";
import {
  boolean,
  customType,
  index,
  integer,
  jsonb,
  numeric,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
  vector,
  type AnyPgColumn,
} from "drizzle-orm/pg-core";

/** Tipo tsvector do Postgres para full-text search (coluna gerada na BD). */
const tsvector = customType<{ data: string; driverData: string }>({
  dataType() {
    return "tsvector";
  },
});

// ─────────────────────────────  TAXONOMIA  ─────────────────────────────────
export const categories = pgTable(
  "categories",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    parentId: uuid("parent_id").references((): AnyPgColumn => categories.id),
    slug: varchar("slug", { length: 160 }).notNull().unique(),
    name: varchar("name", { length: 200 }).notNull(),
    level: integer("level").notNull(), // 0=setor, 1=categoria, 2=aparelho
    rankingsEnabled: boolean("rankings_enabled").notNull().default(false),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("categories_parent_idx").on(t.parentId)],
);

export const categoryAttributes = pgTable(
  "category_attributes",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    categoryId: uuid("category_id")
      .notNull()
      .references(() => categories.id, { onDelete: "cascade" }),
    key: varchar("key", { length: 80 }).notNull(),
    label: varchar("label", { length: 200 }).notNull(),
    unit: varchar("unit", { length: 40 }),
    dataType: varchar("data_type", { length: 20 }).notNull(), // number|enum|bool|text
    isDiscriminant: boolean("is_discriminant").notNull().default(false),
    weightInScore: numeric("weight_in_score").notNull().default("0"),
    displayOrder: integer("display_order").notNull().default(0),
  },
  (t) => [uniqueIndex("category_attributes_cat_key_uq").on(t.categoryId, t.key)],
);

// ─────────────────────────  PRODUTO (GOLDEN RECORD)  ───────────────────────
export const products = pgTable(
  "products",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    categoryId: uuid("category_id").references(() => categories.id),
    slug: varchar("slug", { length: 200 }).notNull().unique(),
    brand: varchar("brand", { length: 160 }),
    model: varchar("model", { length: 200 }),
    canonicalName: varchar("canonical_name", { length: 300 }),
    summary: text("summary"),
    imageUrl: varchar("image_url", { length: 800 }),
    status: varchar("status", { length: 24 }).notNull().default("a_venda"),
    replacedBy: uuid("replaced_by").references((): AnyPgColumn => products.id),
    matchConfidence: numeric("match_confidence"),
    needsReview: boolean("needs_review").notNull().default(false),
    embedding: vector("embedding", { dimensions: 1024 }),
    searchVector: tsvector("search_vector").generatedAlwaysAs(
      (): SQL =>
        sql`to_tsvector('simple', coalesce(brand,'') || ' ' || coalesce(model,'') || ' ' || coalesce(canonical_name,'') || ' ' || coalesce(summary,''))`,
    ),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("products_brand_model_idx").on(t.brand, t.model),
    index("products_category_idx").on(t.categoryId),
  ],
);

export const productIdentifiers = pgTable(
  "product_identifiers",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    idType: varchar("id_type", { length: 16 }).notNull(), // ean|gtin|upc|mpn|asin
    idValue: varchar("id_value", { length: 80 }).notNull(),
  },
  (t) => [
    uniqueIndex("product_identifiers_type_value_uq").on(t.idType, t.idValue),
    index("product_identifiers_product_idx").on(t.productId),
  ],
);

// ───────────────────────────────  FONTES  ─────────────────────────────────
export const sources = pgTable("sources", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: varchar("name", { length: 80 }).notNull().unique(),
  kind: varchar("kind", { length: 20 }).notNull(), // identity|specs|offers|reviews|expert
  baseUrl: varchar("base_url", { length: 400 }),
  trustWeight: numeric("trust_weight").notNull().default("0.5"),
});

export const sourceRecords = pgTable(
  "source_records",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    sourceId: uuid("source_id")
      .notNull()
      .references(() => sources.id),
    productId: uuid("product_id").references(() => products.id),
    rawPayload: jsonb("raw_payload"),
    eanSeen: varchar("ean_seen", { length: 80 }),
    nameSeen: varchar("name_seen", { length: 400 }),
    fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    index("source_records_product_idx").on(t.productId),
    index("source_records_source_idx").on(t.sourceId),
  ],
);

export const specs = pgTable(
  "specs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    attributeKey: varchar("attribute_key", { length: 80 }).notNull(),
    valueText: varchar("value_text", { length: 600 }),
    valueNum: numeric("value_num"),
    unit: varchar("unit", { length: 40 }),
    sourceId: uuid("source_id").references(() => sources.id),
    confidence: numeric("confidence").notNull().default("0.5"),
    corroborations: integer("corroborations").notNull().default(1),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("specs_product_attr_idx").on(t.productId, t.attributeKey)],
);

// ──────────────────────────────  PREÇO / LOJAS  ───────────────────────────
export const stores = pgTable("stores", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: varchar("name", { length: 120 }).notNull(),
  affiliateNetwork: varchar("affiliate_network", { length: 40 }), // awin|amazon|null
  country: varchar("country", { length: 8 }), // PT|ES|EU
});

export const offers = pgTable(
  "offers",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    storeId: uuid("store_id")
      .notNull()
      .references(() => stores.id),
    price: numeric("price", { precision: 12, scale: 2 }),
    currency: varchar("currency", { length: 3 }).notNull().default("EUR"),
    urlAffiliate: varchar("url_affiliate", { length: 1000 }),
    inStock: boolean("in_stock").notNull().default(true),
    sourceId: uuid("source_id").references(() => sources.id),
    capturedAt: timestamp("captured_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("offers_product_store_idx").on(t.productId, t.storeId)],
);

// ──────────────────────────  REVIEWS (SÓ DERIVADO)  ───────────────────────
export const reviewsAggregate = pgTable(
  "reviews_aggregate",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    sourceId: uuid("source_id")
      .notNull()
      .references(() => sources.id),
    ratingRaw: numeric("rating_raw"),
    ratingAdjusted: numeric("rating_adjusted"),
    reviewCount: integer("review_count").notNull().default(0),
    distribution: jsonb("distribution").$type<Record<string, number>>(),
    authenticityScore: numeric("authenticity_score"),
    sentimentSummary: text("sentiment_summary"),
    sourceUrl: varchar("source_url", { length: 1000 }),
    fetchedAt: timestamp("fetched_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("reviews_aggregate_product_source_uq").on(t.productId, t.sourceId)],
);

export const reviewThemes = pgTable(
  "review_themes",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    theme: varchar("theme", { length: 120 }).notNull(),
    polarity: varchar("polarity", { length: 12 }).notNull(), // positivo|negativo|misto
    frequency: integer("frequency").notNull().default(0),
  },
  (t) => [index("review_themes_product_idx").on(t.productId)],
);

// ──────────────────────  DECIFRA SCORE + RANKINGS  ────────────────────────
export const scores = pgTable(
  "scores",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    overall: numeric("overall"),
    subExpert: numeric("sub_expert"),
    subUsers: numeric("sub_users"),
    subMaterial: numeric("sub_material"),
    subValue: numeric("sub_value"),
    confidence: numeric("confidence"),
    computedAt: timestamp("computed_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("scores_product_uq").on(t.productId)],
);

export const scoreSignals = pgTable(
  "score_signals",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    signalType: varchar("signal_type", { length: 40 }).notNull(),
    rawValue: numeric("raw_value"),
    normalized: numeric("normalized"),
    weight: numeric("weight"),
    sourceId: uuid("source_id").references(() => sources.id),
    sourceUrl: varchar("source_url", { length: 1000 }), // link ao veredicto (nunca o conteúdo)
    confidence: numeric("confidence"),
    capturedAt: timestamp("captured_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("score_signals_product_idx").on(t.productId)],
);

export const rankings = pgTable(
  "rankings",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    categoryId: uuid("category_id")
      .notNull()
      .references(() => categories.id),
    criterion: varchar("criterion", { length: 24 }).notNull(),
    periodType: varchar("period_type", { length: 8 }).notNull(),
    periodKey: varchar("period_key", { length: 12 }).notNull(),
    generatedAt: timestamp("generated_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("rankings_uq").on(t.categoryId, t.criterion, t.periodType, t.periodKey)],
);

export const rankingItems = pgTable(
  "ranking_items",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    rankingId: uuid("ranking_id")
      .notNull()
      .references(() => rankings.id, { onDelete: "cascade" }),
    rank: integer("rank").notNull(),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id),
    scoreAtTime: numeric("score_at_time"),
    rationale: text("rationale"),
  },
  (t) => [index("ranking_items_ranking_idx").on(t.rankingId)],
);

// ──────────────────────────  FINDER + UTILIZADOR  ─────────────────────────
export const finderSessions = pgTable("finder_sessions", {
  id: uuid("id").primaryKey().defaultRandom(),
  categoryId: uuid("category_id").references(() => categories.id),
  answers: jsonb("answers").$type<Record<string, unknown>>(),
  candidates: jsonb("candidates").$type<string[]>(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const users = pgTable("users", {
  id: uuid("id").primaryKey().defaultRandom(),
  // Opcional: utilizadores anónimos (cookie) não têm email; só é preciso p/ alertas.
  email: varchar("email", { length: 320 }).unique(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const savedItems = pgTable(
  "saved_items",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    userId: uuid("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    productId: uuid("product_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    priceAlert: numeric("price_alert"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [uniqueIndex("saved_items_user_product_uq").on(t.userId, t.productId)],
);

// ─────────────────────────────  OPERAÇÃO  ────────────────────────────────
export const ingestionRuns = pgTable(
  "ingestion_runs",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    sourceId: uuid("source_id").references(() => sources.id),
    kind: varchar("kind", { length: 24 }).notNull(),
    status: varchar("status", { length: 12 }).notNull(),
    items: integer("items").notNull().default(0),
    startedAt: timestamp("started_at", { withTimezone: true }).notNull().defaultNow(),
    finishedAt: timestamp("finished_at", { withTimezone: true }),
    notes: text("notes"),
  },
  (t) => [index("ingestion_runs_source_idx").on(t.sourceId)],
);

// ─────────────────────  COMPATIBILIDADE / ACESSÓRIOS  ─────────────────────
export const productCompatibility = pgTable(
  "product_compatibility",
  {
    id: uuid("id").primaryKey().defaultRandom(),
    accessoryId: uuid("accessory_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    baseId: uuid("base_id")
      .notNull()
      .references(() => products.id, { onDelete: "cascade" }),
    relation: varchar("relation", { length: 24 }).notNull().default("accessory"),
    note: varchar("note", { length: 300 }),
    sourceId: uuid("source_id").references(() => sources.id),
    confidence: numeric("confidence").notNull().default("0.8"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    uniqueIndex("product_compat_uq").on(t.accessoryId, t.baseId, t.relation),
    index("product_compat_base_idx").on(t.baseId),
    index("product_compat_accessory_idx").on(t.accessoryId),
  ],
);

// ─────────────────────────────  RELAÇÕES  ────────────────────────────────
export const categoriesRelations = relations(categories, ({ one, many }) => ({
  parent: one(categories, {
    fields: [categories.parentId],
    references: [categories.id],
    relationName: "category_hierarchy",
  }),
  children: many(categories, { relationName: "category_hierarchy" }),
  attributes: many(categoryAttributes),
  products: many(products),
}));

export const categoryAttributesRelations = relations(categoryAttributes, ({ one }) => ({
  category: one(categories, {
    fields: [categoryAttributes.categoryId],
    references: [categories.id],
  }),
}));

export const productsRelations = relations(products, ({ one, many }) => ({
  category: one(categories, {
    fields: [products.categoryId],
    references: [categories.id],
  }),
  identifiers: many(productIdentifiers),
  specs: many(specs),
  offers: many(offers),
  reviews: many(reviewsAggregate),
  themes: many(reviewThemes),
  score: one(scores),
  signals: many(scoreSignals),
  // Compatibilidade: acessórios deste aparelho / aparelhos com que este acessório encaixa.
  accessories: many(productCompatibility, { relationName: "compat_base" }),
  compatibleWith: many(productCompatibility, { relationName: "compat_accessory" }),
}));

export const productCompatibilityRelations = relations(productCompatibility, ({ one }) => ({
  accessory: one(products, {
    fields: [productCompatibility.accessoryId],
    references: [products.id],
    relationName: "compat_accessory",
  }),
  base: one(products, {
    fields: [productCompatibility.baseId],
    references: [products.id],
    relationName: "compat_base",
  }),
}));

export const productIdentifiersRelations = relations(productIdentifiers, ({ one }) => ({
  product: one(products, {
    fields: [productIdentifiers.productId],
    references: [products.id],
  }),
}));

export const specsRelations = relations(specs, ({ one }) => ({
  product: one(products, { fields: [specs.productId], references: [products.id] }),
  source: one(sources, { fields: [specs.sourceId], references: [sources.id] }),
}));

export const offersRelations = relations(offers, ({ one }) => ({
  product: one(products, { fields: [offers.productId], references: [products.id] }),
  store: one(stores, { fields: [offers.storeId], references: [stores.id] }),
  source: one(sources, { fields: [offers.sourceId], references: [sources.id] }),
}));

export const reviewsAggregateRelations = relations(reviewsAggregate, ({ one }) => ({
  product: one(products, { fields: [reviewsAggregate.productId], references: [products.id] }),
  source: one(sources, { fields: [reviewsAggregate.sourceId], references: [sources.id] }),
}));

export const reviewThemesRelations = relations(reviewThemes, ({ one }) => ({
  product: one(products, { fields: [reviewThemes.productId], references: [products.id] }),
}));

export const scoresRelations = relations(scores, ({ one }) => ({
  product: one(products, { fields: [scores.productId], references: [products.id] }),
}));

export const scoreSignalsRelations = relations(scoreSignals, ({ one }) => ({
  product: one(products, { fields: [scoreSignals.productId], references: [products.id] }),
  source: one(sources, { fields: [scoreSignals.sourceId], references: [sources.id] }),
}));

export const rankingsRelations = relations(rankings, ({ one, many }) => ({
  category: one(categories, { fields: [rankings.categoryId], references: [categories.id] }),
  items: many(rankingItems),
}));

export const rankingItemsRelations = relations(rankingItems, ({ one }) => ({
  ranking: one(rankings, { fields: [rankingItems.rankingId], references: [rankings.id] }),
  product: one(products, { fields: [rankingItems.productId], references: [products.id] }),
}));

export const stores_Relations = relations(stores, ({ many }) => ({
  offers: many(offers),
}));

export const sourcesRelations = relations(sources, ({ many }) => ({
  specs: many(specs),
  offers: many(offers),
  reviews: many(reviewsAggregate),
}));
