-- ──────────────────────────────────────────────────────────────────────────
-- Compatibilidade / acessórios (v3)
-- Liga um acessório (accessory_id) ao dispositivo com que encaixa (base_id).
-- Blueprint §6: "acessório que encaixa no modelo X". Idempotente.
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS product_compatibility (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  accessory_id uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,  -- o acessório
  base_id      uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,  -- o aparelho-base
  relation     varchar(24) NOT NULL DEFAULT 'accessory',  -- accessory|fits|requires|variant
  note         varchar(300),
  source_id    uuid REFERENCES sources (id),
  confidence   numeric NOT NULL DEFAULT 0.8,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS product_compat_uq
  ON product_compatibility (accessory_id, base_id, relation);
CREATE INDEX IF NOT EXISTS product_compat_base_idx ON product_compatibility (base_id);
CREATE INDEX IF NOT EXISTS product_compat_accessory_idx ON product_compatibility (accessory_id);
