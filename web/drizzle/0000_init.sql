-- ──────────────────────────────────────────────────────────────────────────
-- DECIFRA — Migração inicial (v1, núcleo universal)
-- Esquema canónico traduzido do blueprint (docs/blueprint-mvp.md, secção 2.1).
-- Idempotente: pode ser re-executada sem erro (IF NOT EXISTS / OR REPLACE).
-- O schema Drizzle (src/db/schema.ts) espelha este ficheiro para queries tipadas.
-- ──────────────────────────────────────────────────────────────────────────

-- Extensões: pgvector (finder semântico) + pg_trgm (fuzzy match de marca/modelo).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─────────────────────────────  TAXONOMIA  ─────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id        uuid REFERENCES categories (id),       -- setor > categoria > aparelho
  slug             varchar(160) NOT NULL UNIQUE,
  name             varchar(200) NOT NULL,
  level            integer NOT NULL,                       -- 0=setor, 1=categoria, 2=aparelho
  rankings_enabled boolean NOT NULL DEFAULT false,         -- só onde há densidade de dados
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS categories_parent_idx ON categories (parent_id);

-- Atributos esperados por categoria — alimentam o finder e a normalização de specs.
CREATE TABLE IF NOT EXISTS category_attributes (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id     uuid NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
  key             varchar(80) NOT NULL,                    -- ex: 'capacidade', 'anc', 'tbw'
  label           varchar(200) NOT NULL,                   -- ex: 'Capacidade de armazenamento'
  unit            varchar(40),                             -- ex: 'GB', 'h', null
  data_type       varchar(20) NOT NULL,                    -- number|enum|bool|text
  is_discriminant boolean NOT NULL DEFAULT false,          -- usado pelo finder
  weight_in_score numeric NOT NULL DEFAULT 0,              -- peso no DECIFRA Score da categoria
  display_order   integer NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS category_attributes_cat_key_uq ON category_attributes (category_id, key);

-- ─────────────────────────  PRODUTO (GOLDEN RECORD)  ───────────────────────
CREATE TABLE IF NOT EXISTS products (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id      uuid REFERENCES categories (id),
  slug             varchar(200) NOT NULL UNIQUE,           -- URL SEO-friendly
  brand            varchar(160),
  model            varchar(200),
  canonical_name   varchar(300),
  summary          text,
  image_url        varchar(800),                           -- imagem licenciada (feed/Icecat)
  status           varchar(24) NOT NULL DEFAULT 'a_venda', -- a_venda|descontinuado|substituido
  replaced_by      uuid REFERENCES products (id),
  match_confidence numeric,                                -- confiança do merge (0-1)
  needs_review     boolean NOT NULL DEFAULT false,         -- merges abaixo do threshold
  embedding        vector(1024),                           -- finder semântico (ex.: Voyage)
  search_vector    tsvector GENERATED ALWAYS AS (
                     to_tsvector('simple',
                       coalesce(brand, '') || ' ' ||
                       coalesce(model, '') || ' ' ||
                       coalesce(canonical_name, '') || ' ' ||
                       coalesce(summary, ''))
                   ) STORED,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS products_brand_model_idx ON products (brand, model);
CREATE INDEX IF NOT EXISTS products_category_idx ON products (category_id);
CREATE INDEX IF NOT EXISTS products_search_idx ON products USING gin (search_vector);
CREATE INDEX IF NOT EXISTS products_brand_trgm_idx ON products USING gin (brand gin_trgm_ops, model gin_trgm_ops);
CREATE INDEX IF NOT EXISTS products_embedding_idx ON products USING hnsw (embedding vector_cosine_ops);

-- Todos os identificadores conhecidos do produto → resolvem para products.id.
CREATE TABLE IF NOT EXISTS product_identifiers (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  id_type    varchar(16) NOT NULL,                         -- ean|gtin|upc|mpn|asin
  id_value   varchar(80) NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS product_identifiers_type_value_uq ON product_identifiers (id_type, id_value);
CREATE INDEX IF NOT EXISTS product_identifiers_product_idx ON product_identifiers (product_id);

-- ───────────────────────────────  FONTES  ─────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         varchar(80) NOT NULL UNIQUE,                -- icecat|awin_feed|go_upc|trustpilot...
  kind         varchar(20) NOT NULL,                       -- identity|specs|offers|reviews|expert
  base_url     varchar(400),
  trust_weight numeric NOT NULL DEFAULT 0.5                -- peso de fiabilidade no score
);

-- Registos crús, por fonte, ANTES do merge — base de auditoria e re-matching.
CREATE TABLE IF NOT EXISTS source_records (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id   uuid NOT NULL REFERENCES sources (id),
  product_id  uuid REFERENCES products (id),               -- null enquanto não resolvido
  raw_payload jsonb,
  ean_seen    varchar(80),
  name_seen   varchar(400),
  fetched_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS source_records_product_idx ON source_records (product_id);
CREATE INDEX IF NOT EXISTS source_records_source_idx ON source_records (source_id);

-- Specs normalizadas (modelo EAV — flexível para qualquer categoria).
CREATE TABLE IF NOT EXISTS specs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id    uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  attribute_key varchar(80) NOT NULL,                      -- casa com category_attributes.key
  value_text    varchar(600),
  value_num     numeric,
  unit          varchar(40),
  source_id     uuid REFERENCES sources (id),
  confidence    numeric NOT NULL DEFAULT 0.5,              -- 0-1; alta só se ≥2 fontes coincidem
  corroborations integer NOT NULL DEFAULT 1,
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS specs_product_attr_idx ON specs (product_id, attribute_key);

-- ──────────────────────────────  PREÇO / LOJAS  ───────────────────────────
CREATE TABLE IF NOT EXISTS stores (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name              varchar(120) NOT NULL,                 -- Worten|Fnac|Amazon.es...
  affiliate_network varchar(40),                           -- awin|amazon|null
  country           varchar(8)                             -- PT|ES|EU
);

CREATE TABLE IF NOT EXISTS offers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id    uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  store_id      uuid NOT NULL REFERENCES stores (id),
  price         numeric(12, 2),
  currency      varchar(3) NOT NULL DEFAULT 'EUR',
  url_affiliate varchar(1000),                             -- deep link com tracking (Awin)
  in_stock      boolean NOT NULL DEFAULT true,
  source_id     uuid REFERENCES sources (id),              -- awin_feed (batch) ou serpapi (live)
  captured_at   timestamptz NOT NULL DEFAULT now()         -- frescura visível ao utilizador
);
CREATE INDEX IF NOT EXISTS offers_product_store_idx ON offers (product_id, store_id);

-- ──────────────────────────  REVIEWS (SÓ DERIVADO)  ───────────────────────
-- NUNCA armazenar o texto das reviews. Apenas agregados, resumo próprio e link.
CREATE TABLE IF NOT EXISTS reviews_aggregate (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id         uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  source_id          uuid NOT NULL REFERENCES sources (id),
  rating_raw         numeric,                              -- média publicada
  rating_adjusted    numeric,                              -- após remover suspeitas
  review_count       integer NOT NULL DEFAULT 0,
  distribution       jsonb,                                -- {"5":..,"4":..,..}
  authenticity_score numeric,                              -- 0-1 (deteção por IA)
  sentiment_summary  text,                                 -- resumo PRÓPRIO (sem citar)
  source_url         varchar(1000),                        -- link para a fonte
  fetched_at         timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS reviews_aggregate_product_source_uq ON reviews_aggregate (product_id, source_id);

CREATE TABLE IF NOT EXISTS review_themes (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  theme      varchar(120) NOT NULL,                        -- ex: 'autonomia', 'conforto'
  polarity   varchar(12) NOT NULL,                         -- positivo|negativo|misto
  frequency  integer NOT NULL DEFAULT 0                    -- sinal, não texto
);
CREATE INDEX IF NOT EXISTS review_themes_product_idx ON review_themes (product_id);

-- ──────────────────────  DECIFRA SCORE + RANKINGS  ────────────────────────
CREATE TABLE IF NOT EXISTS scores (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id   uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  overall      numeric,                                    -- 0-100
  sub_expert   numeric,                                    -- testadores independentes
  sub_users    numeric,                                    -- nota ajustada por autenticidade
  sub_material numeric,                                    -- qualidade material / build
  sub_value    numeric,                                    -- overall / preço
  confidence   numeric,                                    -- 0-1 (nº e qualidade das fontes)
  computed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS scores_product_uq ON scores (product_id);

-- Auditabilidade: cada sinal que entra no score, rastreável à fonte.
CREATE TABLE IF NOT EXISTS score_signals (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id  uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  signal_type varchar(40) NOT NULL,                        -- expert_review|user_rating|spec|warranty
  raw_value   numeric,
  normalized  numeric,
  weight      numeric,
  source_id   uuid REFERENCES sources (id),
  captured_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS score_signals_product_idx ON score_signals (product_id);

-- Snapshots mensais/anuais — rankings imutáveis por período.
CREATE TABLE IF NOT EXISTS rankings (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id  uuid NOT NULL REFERENCES categories (id),
  criterion    varchar(24) NOT NULL,                       -- overall|value|cheapest|premium|material|feedback
  period_type  varchar(8) NOT NULL,                        -- month|year
  period_key   varchar(12) NOT NULL,                       -- 2026-06 | 2026
  generated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS rankings_uq ON rankings (category_id, criterion, period_type, period_key);

CREATE TABLE IF NOT EXISTS ranking_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ranking_id    uuid NOT NULL REFERENCES rankings (id) ON DELETE CASCADE,
  rank          integer NOT NULL,                          -- 1..5
  product_id    uuid NOT NULL REFERENCES products (id),
  score_at_time numeric,
  rationale     text                                       -- porque está no top
);
CREATE INDEX IF NOT EXISTS ranking_items_ranking_idx ON ranking_items (ranking_id);

-- ──────────────────────────  FINDER + UTILIZADOR  ─────────────────────────
CREATE TABLE IF NOT EXISTS finder_sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id uuid REFERENCES categories (id),
  answers     jsonb,                                       -- {attribute_key: valor}
  candidates  jsonb,                                       -- product_ids resultantes
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email      varchar(320) NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saved_items (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  product_id  uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  price_alert numeric,                                     -- alerta quando preço < X
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS saved_items_user_product_uq ON saved_items (user_id, product_id);

-- ─────────────────────────────  OPERAÇÃO  ────────────────────────────────
CREATE TABLE IF NOT EXISTS ingestion_runs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id   uuid REFERENCES sources (id),
  kind        varchar(24) NOT NULL,                        -- on_demand|feed_batch|price_refresh|score_recompute
  status      varchar(12) NOT NULL,                        -- ok|partial|error
  items       integer NOT NULL DEFAULT 0,
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  notes       text
);
CREATE INDEX IF NOT EXISTS ingestion_runs_source_idx ON ingestion_runs (source_id);

-- ──────────────────────────  TRIGGER: updated_at  ─────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS products_set_updated_at ON products;
CREATE TRIGGER products_set_updated_at BEFORE UPDATE ON products
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS specs_set_updated_at ON specs;
CREATE TRIGGER specs_set_updated_at BEFORE UPDATE ON specs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
