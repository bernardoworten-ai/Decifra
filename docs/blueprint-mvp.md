# DECIFRA — Blueprint do MVP
### Esquema de base de dados + stack + faseamento
*Documento de arquitetura. Versão 1 — base para o desenvolvimento do MVP, antes da integração Awin.*

---

## 0. Decisões fechadas

| Tema | Decisão |
|---|---|
| **Rankings / qualidade material** | "DECIFRA Score" compósito e auditável, agregado de fontes externas + reviews + specs + preço. Sem testes físicos. Metodologia pública. |
| **Reviews por loja** | Guardar e mostrar **métricas** (nota, volume, distribuição, recência) por plataforma + **resumo próprio** dos temas + **nota ajustada por autenticidade** + link à fonte. **Nunca republicar o texto das reviews.** |
| **Âmbito de categorias** | **Abrangente por design, faseado na profundidade**: ficha/preço/reviews/finder universais desde o v1; rankings rigorosos por densidade de dados (tech → expandir). |

---

## 1. Princípio arquitetural

O produto vive em **duas camadas de dados** com exigências opostas:

- **Camada universal (escala para tudo):** identificação, ficha explicada, preço multi-loja, reviews agregadas e finder por specs. Alimentada por IA + pesquisa web + feeds de afiliado + APIs de EAN. Funciona para *qualquer* produto desde o primeiro dia.
- **Camada curada (exige massa crítica):** rankings e "Top 5" por critério. Exige um score defensável, que por sua vez exige densidade de fontes e de produtos. Arranca em tech e expande categoria a categoria.

Esta separação é o que permite responder "abrangente" sem mentir no "rigoroso".

**Regra de ouro de fiabilidade:** a IA é a camada de *explicação, normalização e raciocínio*, sempre ancorada em factos de fontes reais. Nunca é a fonte primária de números. Tudo o que é facto tem `source_id` e `confidence`.

---

## 2. Modelo de dados

O problema central é **entity resolution**: o mesmo produto chega do Icecat, de um feed Awin, de uma API de EAN e de uma fonte de reviews, cada um com identificadores e nomes diferentes. A solução é um **golden record** canónico (`products`) alimentado por registos-fonte crús (`source_records`), com matching ponderado multi-campo (EAN exato → fuzzy por marca+modelo+specs → revisão de baixa confiança).

### 2.1 Esquema (DBML)

```dbml
// ─────────────────────────────  TAXONOMIA  ─────────────────────────────
Table categories {
  id            uuid [pk]
  parent_id     uuid [ref: > categories.id, note: 'hierarquia: setor > categoria > tipo de aparelho']
  slug          varchar [unique]
  name          varchar
  level         int            // 0=setor, 1=categoria, 2=aparelho
  rankings_enabled boolean [default: false] // true só onde há densidade de dados
  created_at    timestamptz [default: `now()`]
}

// Atributos esperados por categoria — alimentam o finder e a normalização de specs
Table category_attributes {
  id            uuid [pk]
  category_id   uuid [ref: > categories.id]
  key           varchar        // ex: 'capacidade', 'anc', 'tbw'
  label         varchar        // ex: 'Capacidade de armazenamento'
  unit          varchar        // ex: 'GB', 'h', null
  data_type     varchar        // 'number' | 'enum' | 'bool' | 'text'
  is_discriminant boolean [default: false] // usado pelo finder para distinguir modelos
  weight_in_score numeric [default: 0]     // peso desta spec no DECIFRA Score da categoria
  indexes { (category_id, key) [unique] }
}

// ─────────────────────────  PRODUTO (GOLDEN RECORD)  ──────────────────────
Table products {
  id            uuid [pk]
  category_id   uuid [ref: > categories.id]
  brand         varchar
  model         varchar
  canonical_name varchar
  summary       text
  image_url     varchar        // imagem licenciada (feed/Icecat)
  status        varchar        // 'a_venda' | 'descontinuado' | 'substituido'
  replaced_by   uuid [ref: > products.id, null]
  match_confidence numeric      // confiança do merge (0-1)
  needs_review  boolean [default: false] // merges abaixo do threshold
  created_at    timestamptz [default: `now()`]
  updated_at    timestamptz
  indexes { (brand, model) }
}

// Todos os identificadores conhecidos do produto → resolvem para products.id
Table product_identifiers {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  id_type       varchar        // 'ean' | 'gtin' | 'upc' | 'mpn' | 'asin'
  id_value      varchar
  indexes { (id_type, id_value) [unique] }
}

// Registos crús, por fonte, ANTES do merge — base de auditoria e re-matching
Table source_records {
  id            uuid [pk]
  source_id     uuid [ref: > sources.id]
  product_id    uuid [ref: > products.id, null] // null enquanto não resolvido
  raw_payload   jsonb          // resposta original da fonte
  ean_seen      varchar
  name_seen     varchar
  fetched_at    timestamptz [default: `now()`]
}

Table sources {
  id            uuid [pk]
  name          varchar        // 'icecat' | 'awin_feed' | 'go_upc' | 'serpapi' | 'trustpilot' ...
  kind          varchar        // 'identity' | 'specs' | 'offers' | 'reviews'
  base_url      varchar
  trust_weight  numeric        // peso de fiabilidade da fonte no score
}

// Specs normalizadas (modelo EAV — flexível para qualquer categoria)
Table specs {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  attribute_key varchar        // casa com category_attributes.key
  value_text    varchar
  value_num     numeric [null]
  unit          varchar [null]
  source_id     uuid [ref: > sources.id]
  confidence    numeric        // 0-1; 'alta' só se ≥2 fontes coincidem
  corroborations int [default: 1]
  updated_at    timestamptz
  indexes { (product_id, attribute_key) }
}

// ──────────────────────────────  PREÇO / LOJAS  ───────────────────────────
Table stores {
  id            uuid [pk]
  name          varchar        // 'Worten' | 'Fnac' | 'Amazon.es' ...
  affiliate_network varchar     // 'awin' | 'amazon' | null
  country       varchar         // 'PT' | 'ES' | 'EU'
}

Table offers {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  store_id      uuid [ref: > stores.id]
  price         numeric
  currency      varchar [default: 'EUR']
  url_affiliate varchar         // deep link com tracking (Awin) em produção
  in_stock      boolean
  source_id     uuid [ref: > sources.id] // 'awin_feed' (batch) ou 'serpapi' (live)
  captured_at   timestamptz     // frescura visível ao utilizador
  indexes { (product_id, store_id) }
}

// ──────────────────────────  REVIEWS (SÓ DERIVADO)  ───────────────────────
// NUNCA armazenar o texto das reviews. Apenas agregados, resumo próprio e link.
Table reviews_aggregate {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  source_id     uuid [ref: > sources.id]  // Amazon, Worten, Trustpilot, Google...
  rating_raw    numeric          // média publicada
  rating_adjusted numeric         // média após remover suspeitas (estilo ReviewMeta)
  review_count  int
  distribution  jsonb            // {5:..,4:..,3:..,2:..,1:..}
  authenticity_score numeric      // 0-1 (deteção de padrões falsos por IA)
  sentiment_summary text          // resumo PRÓPRIO dos temas (palavras nossas, sem citar)
  source_url    varchar          // link para ler as reviews originais
  fetched_at    timestamptz
  indexes { (product_id, source_id) [unique] }
}

Table review_themes {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  theme         varchar          // ex: 'autonomia', 'conforto', 'fiabilidade do ANC'
  polarity      varchar          // 'positivo' | 'negativo' | 'misto'
  frequency     int              // quantas reviews mencionam (sinal, não texto)
}

// ──────────────────────  DECIFRA SCORE + RANKINGS  ────────────────────────
Table scores {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  overall       numeric          // 0-100
  sub_expert    numeric          // agregado de testadores independentes
  sub_users     numeric          // nota ajustada por autenticidade
  sub_material  numeric          // "qualidade material" / build
  sub_value     numeric          // overall / preço
  confidence    numeric          // 0-1 (nº e qualidade das fontes)
  computed_at   timestamptz
  indexes { (product_id) [unique] }
}

// Auditabilidade: cada sinal que entra no score, rastreável à fonte
Table score_signals {
  id            uuid [pk]
  product_id    uuid [ref: > products.id]
  signal_type   varchar          // 'expert_review' | 'user_rating' | 'spec' | 'warranty' ...
  raw_value     numeric
  normalized    numeric
  weight        numeric
  source_id     uuid [ref: > sources.id]
  captured_at   timestamptz
}

// Snapshots mensais/anuais — rankings são imutáveis por período (não recalculam o passado)
Table rankings {
  id            uuid [pk]
  category_id   uuid [ref: > categories.id]
  criterion     varchar          // 'overall' | 'value' | 'cheapest' | 'premium' | 'material' | 'feedback'
  period_type   varchar          // 'month' | 'year'
  period_key    varchar          // '2026-06' | '2026'
  generated_at  timestamptz
  indexes { (category_id, criterion, period_type, period_key) [unique] }
}

Table ranking_items {
  id            uuid [pk]
  ranking_id    uuid [ref: > rankings.id]
  rank          int              // 1..5
  product_id    uuid [ref: > products.id]
  score_at_time numeric
  rationale     text             // porque está no top (gerado a partir dos sinais)
}

// ──────────────────────────  FINDER + UTILIZADOR  ─────────────────────────
Table finder_sessions {
  id            uuid [pk]
  category_id   uuid [ref: > categories.id]
  answers       jsonb            // {attribute_key: valor} recolhidos (1-5 perguntas)
  candidates    jsonb            // product_ids resultantes
  created_at    timestamptz [default: `now()`]
}

Table users {
  id            uuid [pk]
  email         varchar [unique]
  created_at    timestamptz [default: `now()`]
}

Table saved_items {
  id            uuid [pk]
  user_id       uuid [ref: > users.id]
  product_id    uuid [ref: > products.id]
  price_alert   numeric [null]   // alerta quando preço < X
  created_at    timestamptz [default: `now()`]
}

// ─────────────────────────────  OPERAÇÃO  ────────────────────────────────
Table ingestion_runs {
  id            uuid [pk]
  source_id     uuid [ref: > sources.id]
  kind          varchar          // 'on_demand' | 'feed_batch' | 'price_refresh' | 'score_recompute'
  status        varchar          // 'ok' | 'partial' | 'error'
  items         int
  started_at    timestamptz
  finished_at   timestamptz
  notes         text
}
```

### 2.2 Notas de modelação

- **`specs` em EAV** (entity-attribute-value) em vez de colunas fixas: obrigatório para "qualquer categoria" — um SSD e uns auscultadores não partilham colunas. `category_attributes` dá a estrutura/validação por categoria.
- **`source_records` separado de `products`**: guardar o crú permite re-fazer o matching quando os algoritmos melhoram, e auditar de onde veio cada facto.
- **Rankings são snapshots imutáveis por período**: o "Top 5 de junho" fica congelado; não se reescreve o passado. Os de mês corrente recalculam até fecharem.
- **Reviews**: repare-se que **não há tabela de texto de reviews** — só agregados, temas e resumo próprio. É a fronteira legal.

---

## 3. Pipelines e jobs (frescura)

| Pipeline | Gatilho | O que faz |
|---|---|---|
| **Ingestão por EAN** | On-demand (cache-first) | Cache → se *miss*: fan-out a EAN API (identidade), Icecat/feeds (specs+imagem+preço), fontes de review (agregados) → entity resolution → golden record → cache. |
| **Refresh de preço (live)** | Botão "atualizar" | Google Shopping API (SerpApi/Bright Data) → atualiza `offers` desse produto. Pago por consulta — só on-demand. |
| **Feed batch** | Cron diário | Importa feeds Awin (preço, imagem, link de afiliado) → atualiza `offers` e imagens em massa. |
| **Score recompute (mês)** | Cron, **dia 10** | Recalcula `scores` e gera snapshots `rankings` (period_type='month') de cada categoria com `rankings_enabled`. O dia 10 dá tempo a consolidar reviews/preços do mês anterior. |
| **Score recompute (ano)** | Cron, início de janeiro | Gera snapshots `rankings` (period_type='year') do ano anterior. |
| **Review refresh** | Cron por popularidade | Re-busca agregados das fontes para produtos mais vistos. |

Cada execução grava em `ingestion_runs` (auditoria + frescura visível: "verificado a …").

---

## 4. Metodologia do DECIFRA Score

`overall = wE·sub_expert + wU·sub_users + wM·sub_material + wS·sub_value` — pesos `w` definidos **por categoria** (em `category_attributes`/config), porque o que importa varia (autonomia pesa mais num portátil, build num eletrodoméstico).

- **sub_expert** — agregado normalizado (0-100) de veredictos de testadores independentes reputados (ex.: RTINGS, Consumer Reports, imprensa). Guarda-se o *score* e o *link*, nunca o conteúdo.
- **sub_users** — nota média ajustada por autenticidade, ponderada por volume e recência, agregada multi-loja (`reviews_aggregate.rating_adjusted`).
- **sub_material** ("qualidade material") — combina: sub-score de build de especialistas (quando existe) + materiais/construção declarados nas specs + certificações (IP, MIL-STD) + garantia/MTBF + sinais de durabilidade extraídos dos `review_themes`.
- **sub_value** — `overall / preço atual` (dos `offers`), para o ranking preço-qualidade.

**Confiança**: função do número e do `trust_weight` das fontes. Liga ao selo já existente no protótipo (verde/amarelo/vermelho). Onde não há teste físico, o item é marcado "estimativa baseada em N fontes".

**Critérios de ranking** (cada um é só um ordenamento): `overall`, `value` (preço-qualidade), `cheapest`, `premium` (mais caro/topo de gama), `material` (qualidade material), `feedback` (melhores notas de utilizadores). Fáceis de acrescentar mais.

---

## 5. Reviews por loja (legal + útil)

- **Mostra-se, por plataforma**: nota, volume, distribuição, recência, nota ajustada, score de autenticidade, e um resumo próprio dos temas — mais um agregado ponderado entre fontes.
- **Não se faz**: armazenar/republicar o texto das reviews (copyright + ToS). O utilizador segue o link para ler na fonte.
- **Aquisição**: APIs oficiais onde existem (ex.: Trustpilot, Google), dados derivados e link nas restantes, respeitando `robots.txt`/ToS. Onde não for permitido recolher, mostra-se só a nota pública + link.
- **Autenticidade**: deteção de padrões suspeitos por IA (volume anómalo, linguagem repetida, picos) — preenche o gap deixado pelo fecho do Fakespot (2025) e do ReviewMeta (2026).

---

## 6. Finder guiado por specs (quando não há modelo)

Fluxo: utilizador escolhe setor → categoria → aparelho (ou a IA infere) → o sistema apresenta **1 a 5 perguntas discriminantes** (vindas de `category_attributes.is_discriminant`) → filtra `products`/`specs` → devolve candidatos ordenados pelo DECIFRA Score, cada um com o *porquê* do match.

- **Top categorias**: perguntas curadas (controlo de qualidade).
- **Cauda longa** (abrangência): perguntas geradas por IA a partir dos atributos da categoria, de forma adaptativa (a pergunta seguinte depende da resposta anterior).
- **Busca**: full-text + `pgvector` (embeddings) no Postgres para casar descrições em linguagem natural com produtos — sem precisar de motor de busca externo no início.
- **Extensão futura**: compatibilidade (ex.: acessório que encaixa no modelo X), via regras sobre atributos.

---

## 7. Stack (pensada para uma pessoa manter)

Princípio: **monólito modular + serverless**, não microserviços. Postgres como núcleo que faz quase tudo.

| Camada | Escolha | Porquê |
|---|---|---|
| **Frontend + SSR** | Next.js (React) + TypeScript | SSR/SSG para **SEO** (o canal de aquisição decisivo) e uma só base de código web+mobile (PWA). |
| **Backend/API** | Next.js (API routes / Route Handlers) | Full-stack coeso numa codebase. Menos partes móveis para manter. |
| **Workers de dados/IA** | Python (FastAPI ou jobs) | Onde és forte; ideal para os pipelines de ingestão, matching e IA. Comunica com o Postgres. |
| **Base de dados** | PostgreSQL (Supabase ou Neon) | Relacional + `JSONB` (specs flexíveis) + `pgvector` (finder semântico) + full-text. Substitui Elastic/Mongo no início. |
| **Cache / rate limit** | Redis (Upstash) | Cache de fichas (custo por consulta cai), throttling das APIs pagas. |
| **Jobs agendados** | Cron serverless (Vercel Cron / Supabase scheduled / GitHub Actions) | Recompute mensal (dia 10) e anual, refresh de feeds. |
| **IA** | API Anthropic (Claude) | Extração/normalização de specs, resumos de reviews, finder, veredictos. Sempre ancorada em fontes. |
| **Dados de produto** | Go-UPC/UPCitemdb (EAN), Open Icecat (tech, grátis), feeds Awin (preço+imagem+link), Google Shopping API (preço live) | Cobre identidade universal + specs tech + preço/imagem licenciada + preço ao segundo. |
| **Observabilidade** | Sentry + logs estruturados | Apanhar falhas cedo (o teu requisito "sem falhas"). |
| **Hosting** | Vercel (front+API+cron) + Supabase/Neon (DB) + Upstash (Redis) | Tudo serverless, baixa manutenção, escala automática. |

---

## 8. Faseamento

- **v1 — Núcleo universal** *(complexidade média-alta)*
  Ficha explicada + fontes citadas + selo de confiança + preço multi-loja (feeds) + finder por specs + reviews por loja (métricas + resumo + autenticidade). Funciona para qualquer categoria. **Sem rankings ainda.**
- **v2 — Rankings + retenção** *(complexidade média)*
  DECIFRA Score + Tops por critério em **tech + eletrodomésticos** (categorias com densidade). Favoritos e alertas de preço.
- **v3 — Expansão** *(complexidade alta)*
  Rankings em mais categorias, compatibilidade/acessórios no finder, extensão de browser, e preparação para comércio agêntico. App nativa só com tração.

---

## 9. Custos por fase (ordem de grandeza)

| Item | v1 (validação) | v2 | v3 / escala |
|---|---|---|---|
| EAN API | grátis (tier) | dezenas €/mês | plano superior |
| Specs (Open Icecat) | grátis | grátis | + Icecat pago (~300 €/mês) se tech for core |
| Preço live (SerpApi/Bright Data) | mínimo, on-demand | ~75 $/5k consultas | conforme volume |
| IA (Claude) | cêntimos/consulta | escala com tráfego | escala |
| DB/Cache (Supabase+Upstash) | free tier | ~25-50 €/mês | conforme volume |
| Hosting (Vercel) | free/€20 | ~€20-40 | conforme tráfego |
| Awin (publisher) | grátis | grátis | grátis |
| **Total/mês** | **~€0-50** | **~€150-450** | **€500-1000+** |

Cache agressivo (Redis + base própria a crescer) é o que mantém o custo por utilizador a cair com a escala.

---

## 10. Riscos (honestos)

- **Scope / solo**: o maior risco. O faseamento acima não é opcional — é o que torna isto viável para uma pessoa.
- **Legal**: reviews (não republicar texto), scraping (respeitar ToS/robots), redistribuição de feeds/Icecat (cumprir termos de licença), afiliados (divulgação obrigatória).
- **Fiabilidade do score**: mitigada por transparência (sinais rastreáveis), confiança explícita e congelamento de snapshots.
- **Comércio agêntico**: ChatGPT/Google a fechar compras dentro do chat podem comprimir o modelo de afiliados a médio prazo. Defesa: o teu ângulo de **confiança verificável e neutralidade** (que esses assistentes não dão de forma transparente).
- **Custo de preço live**: nunca correr globalmente; só no botão "atualizar" e em batch via feeds.

---

## 11. Próximo passo

Construir o **v1** (núcleo universal). Quando estiver funcional, integrar a **Awin** (inscrição como publisher, importação de feeds, matching por EAN, deep links de afiliado e camada de preço live) — guia dedicado nessa altura.
