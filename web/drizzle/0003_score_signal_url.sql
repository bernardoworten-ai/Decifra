-- ──────────────────────────────────────────────────────────────────────────
-- DECIFRA Score completo (§4): link do veredicto de especialista no sinal.
-- Guardamos score + link + fonte — NUNCA o conteúdo da review. Idempotente.
-- ──────────────────────────────────────────────────────────────────────────
ALTER TABLE score_signals ADD COLUMN IF NOT EXISTS source_url varchar(1000);
ALTER TABLE score_signals ADD COLUMN IF NOT EXISTS confidence numeric;
