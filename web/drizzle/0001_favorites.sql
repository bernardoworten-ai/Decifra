-- ──────────────────────────────────────────────────────────────────────────
-- Favoritos + alertas de preço (v2)
-- Permite utilizadores anónimos (cookie) sem email; o email é opcional e só
-- necessário para receber alertas. Idempotente.
-- ──────────────────────────────────────────────────────────────────────────

-- Email passa a ser opcional (anónimo por cookie). DROP NOT NULL é no-op se já nullable.
ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

-- Acelera a verificação de alertas e a leitura de favoritos por produto.
CREATE INDEX IF NOT EXISTS saved_items_product_idx ON saved_items (product_id);
