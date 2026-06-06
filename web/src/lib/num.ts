/**
 * Helpers de conversão para colunas `numeric` (que o driver devolve como string).
 */

/** Converte para número, devolvendo `null` se vazio/indefinido/NaN. */
export function num(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Como `num`, mas garante um número usando o fallback (default 0). */
export function numOr(value: string | number | null | undefined, fallback = 0): number {
  const n = num(value);
  return n === null ? fallback : n;
}
