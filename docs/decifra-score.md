# Metodologia do DECIFRA Score

> Metodologia pública e auditável. O score é um **compósito de sinais externos**
> (testadores independentes, reviews, specs, preço). **Não fazemos testes físicos** —
> cada item indica explicitamente "estimativa baseada em N fontes". Toda a implementação
> vive em [`web/src/lib/score.ts`](../web/src/lib/score.ts).

## Fórmula

```
overall = wE·subExpert + wU·subUsers + wM·subMaterial + wS·subValue
```

Os pesos `w` são definidos **por categoria** (configurados em `category_attributes.weight_in_score`
e na config de categoria), porque o que importa varia: autonomia pesa mais num portátil,
build num eletrodoméstico. Sub-scores ausentes são ignorados e os pesos **renormalizados**
sobre os presentes — nunca inventamos números.

Pesos por defeito (quando a categoria não define os seus):

| Sub-score | Peso | O que mede |
|---|---|---|
| `subExpert` | 0.35 | Veredictos normalizados (0-100) de testadores independentes reputados (RTINGS, Consumer Reports, imprensa). Guarda-se o *score* e o *link* — nunca o conteúdo. |
| `subUsers` | 0.30 | Nota média **ajustada por autenticidade**, ponderada por volume e recência, agregada multi-loja. |
| `subMaterial` | 0.20 | "Qualidade material": build de especialistas + materiais/certificações (IP, MIL-STD) + garantia/MTBF + sinais de durabilidade dos temas de review. |
| `subValue` | 0.15 | Relação qualidade/preço (alimenta também o ranking `value`). |

## Confiança (selo verde / amarelo / vermelho)

A confiança (0-1) é função do **número** e do **`trust_weight`** das fontes:

```
confidence = (1 − e^(−0.55·nFontes)) · (0.5 + 0.5·trustMédio)
```

| Confiança | Selo | Significado |
|---|---|---|
| ≥ 0.75 | 🟢 verde | Corroborado por várias fontes fiáveis. |
| ≥ 0.50 | 🟡 amarelo | Fontes suficientes, corroboração parcial. |
| < 0.50 | 🔴 vermelho | Poucas fontes ou divergência. |

## De onde vêm os sub-scores (recompute)

O recompute (`workers`, `python -m decifra_workers score-recompute`) **deriva** os 4
sub-scores de sinais reais e grava-os em `scores` (a matemática vive em
`workers/decifra_workers/scoring.py`):

- **sub_expert** — média ponderada (por `trust_weight`) dos veredictos curados em
  `score_signals` (`signal_type='expert_review'`, com `source_url` para a fonte — **nunca** o conteúdo).
- **sub_users** — `reviews_aggregate.rating_adjusted` (0-5 → 0-100), ponderado por volume.
- **sub_material** — garantia + TBW + certificações (IP/MIL-STD nas specs) + temas de
  durabilidade/construção dos `review_themes`.
- **sub_value** — qualidade-base por € **relativa à categoria** (mapeada para 50-100).

Cada contribuição fica em `score_signals` com `source_id`/`confidence` (auditável).

### Como adicionar fontes de especialista

Insere um sinal curado (sem republicar conteúdo):

```sql
INSERT INTO score_signals (product_id, signal_type, normalized, weight, source_id, source_url, confidence)
VALUES ('<product_id>', 'expert_review', 92, 0.35, '<source_id>', 'https://rtings.com/…', 0.9);
```

O próximo recompute recalcula `sub_expert` a partir destes sinais (renormalizando se faltarem).

## Auditabilidade

Cada sinal que entra no score é gravado em `score_signals` com `raw_value`, `normalized`,
`weight`, `source_id`, `source_url`, `confidence` e `captured_at`. É sempre possível
reconstruir o porquê de um número.

## Rankings (imutáveis por período)

Cada critério é apenas um **ordenamento** do mesmo conjunto de produtos:
`overall`, `value` (preço-qualidade), `cheapest`, `premium`, `material`, `feedback`.

Os rankings são **snapshots congelados por período** (`rankings` + `ranking_items`): o
"Top 5 de junho" não se reescreve. Os do mês corrente recalculam até fechar (recompute no **dia 10**,
para dar tempo a consolidar reviews/preços do mês anterior). Só geramos rankings em categorias com
`rankings_enabled = true` (densidade de dados suficiente).
