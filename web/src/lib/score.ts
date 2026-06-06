/**
 * DECIFRA Score — metodologia (ver docs/decifra-score.md).
 *
 *   overall = wE·subExpert + wU·subUsers + wM·subMaterial + wS·subValue
 *
 * Os pesos `w` são definidos POR CATEGORIA (o que importa varia: autonomia
 * pesa mais num portátil, build num eletrodoméstico). Sub-scores ausentes são
 * ignorados e os pesos renormalizados — nunca inventamos números.
 *
 * Regra de ouro: a IA explica/normaliza, nunca é a fonte primária. Todo o
 * sinal que entra no score é rastreável a uma fonte (tabela score_signals).
 */

export type SubScores = {
  expert: number | null;
  users: number | null;
  material: number | null;
  value: number | null;
};

export type ScoreWeights = {
  expert: number;
  users: number;
  material: number;
  value: number;
};

/** Pesos por defeito (usados quando a categoria não define os seus). */
export const DEFAULT_WEIGHTS: ScoreWeights = {
  expert: 0.35,
  users: 0.3,
  material: 0.2,
  value: 0.15,
};

/**
 * Combina os sub-scores num overall 0-100, renormalizando os pesos sobre os
 * sub-scores efectivamente presentes. Devolve null se não houver nenhum.
 */
export function computeOverall(
  subs: SubScores,
  weights: ScoreWeights = DEFAULT_WEIGHTS,
): number | null {
  const parts: Array<[number, number]> = [];
  if (subs.expert !== null) parts.push([subs.expert, weights.expert]);
  if (subs.users !== null) parts.push([subs.users, weights.users]);
  if (subs.material !== null) parts.push([subs.material, weights.material]);
  if (subs.value !== null) parts.push([subs.value, weights.value]);

  const totalWeight = parts.reduce((acc, [, w]) => acc + w, 0);
  if (totalWeight === 0) return null;

  const weighted = parts.reduce((acc, [v, w]) => acc + v * w, 0);
  return Math.round((weighted / totalWeight) * 10) / 10;
}

/**
 * Índice preço-qualidade: pontos de DECIFRA Score por cada 100 € de preço.
 * Quanto maior, melhor relação qualidade/preço. Alimenta o ranking 'value'.
 */
export function valueIndex(overall: number | null, price: number | null): number | null {
  if (overall === null || !price || price <= 0) return null;
  return Math.round(((overall / price) * 100) * 10) / 10;
}

// ──────────────────────────────  Confiança  ───────────────────────────────

export type TrustTier = "alta" | "media" | "baixa";

export type TrustSeal = {
  tier: TrustTier;
  /** Token de cor do selo (verde/amarelo/vermelho do protótipo). */
  color: "verde" | "amarelo" | "vermelho";
  label: string;
  description: string;
};

/** Mapeia a confiança (0-1) para o selo verde/amarelo/vermelho. */
export function trustSeal(confidence: number | null): TrustSeal {
  const c = confidence ?? 0;
  if (c >= 0.75) {
    return {
      tier: "alta",
      color: "verde",
      label: "Confiança alta",
      description: "Corroborado por várias fontes fiáveis.",
    };
  }
  if (c >= 0.5) {
    return {
      tier: "media",
      color: "amarelo",
      label: "Confiança média",
      description: "Fontes suficientes, mas com corroboração parcial.",
    };
  }
  return {
    tier: "baixa",
    color: "vermelho",
    label: "Confiança baixa",
    description: "Poucas fontes ou divergência entre elas.",
  };
}

/**
 * Confiança agregada (0-1) a partir do nº de fontes e do seu trust_weight médio.
 * Satura suavemente: mais fontes e mais fiáveis ⇒ mais confiança.
 */
export function confidenceFromSources(sourceCount: number, avgTrustWeight: number): number {
  if (sourceCount <= 0) return 0;
  // Saturação por volume: 1 fonte ~0.55, 2 ~0.75, 3 ~0.85, 4+ aproxima 1.
  const volumeFactor = 1 - Math.exp(-0.55 * sourceCount);
  const confidence = volumeFactor * (0.5 + 0.5 * clamp01(avgTrustWeight));
  return Math.round(clamp01(confidence) * 100) / 100;
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, n));
}
