# Auditoria de Engenharia — DECIFRA

**Data:** 2026-06-06
**Âmbito:** repositório completo (`web/`, `workers/`, `extension/`, migrations, CI) no commit `4fc8278` (branch `claude/sleepy-johnson-oboPh`).
**Natureza:** auditoria de rigor pré-produção. **Não foi alterado código** — só deteção e proposta.
**Método:** análise estática (tsc, eslint, knip, depcheck, madge, npm audit, ruff, mypy, bandit, pip-audit, semgrep, gitleaks), leitura manual dos caminhos de dados/segurança/concorrência, verificação contra `docs/blueprint-mvp.md` e prova empírica (SQL na BD viva) onde aplicável.

> **Convenção:** cada achado é **[Confirmado]** (com evidência: `ficheiro:linha`, output de ferramenta ou passo de reprodução) ou **[Suspeita]** (plausível, não totalmente provado — indica-se como confirmar). Os **princípios invioláveis** do projeto (IA nunca é fonte primária; nunca guardar texto de reviews; preço live nunca em cron; proveniência em tudo; degradação graceful) **não** são tratados como defeitos — a sua aderência é avaliada na secção 6.

---

## 1. Sumário executivo

O DECIFRA está **bem construído para um MVP**: as varreduras automáticas de segurança estão limpas (`npm audit` 0, `semgrep` 0, `gitleaks` 0 em toda a história, sem segredos hardcoded), não há SQL injection nem SSRF nos caminhos verificados, não há dependências circulares, as migrations são idempotentes e os **cinco princípios invioláveis são respeitados**. A base é sólida.

Porém, "passa nos testes e no audit" **não** significa "correto, seguro e eficiente". A auditoria encontrou um **bug de correção no núcleo** (entity resolution funde produtos distintos), um **controlo de custo contornável** (rate-limit do preço live), e um conjunto de lacunas de robustez (atomicidade, isolamento de falhas), segurança-defensiva (headers, cookie de identidade, XSS por URL externa) e processo (lint/audit não bloqueiam o CI; núcleo dos workers com 0% de cobertura unitária).

| Severidade | Nº de achados |
|---|---|
| 🔴 Crítico | 0 |
| 🟠 Alto | 2 |
| 🟡 Médio | 12 |
| 🟢 Baixo | 13 |
| **Total** | **27** |

### Os 5 maiores riscos

1. **A1 — Entity resolution funde produtos distintos** *(Alto, [Confirmado])*. Com `FUZZY_THRESHOLD=0.55`, a similaridade trigram entre modelos adjacentes é 0.78–0.80 (`Sony WH-1000XM4` vs `XM5` = **0.778**; `iPhone 15` vs `15 Pro` = **0.800**). Ingerir um produto novo (EAN ainda desconhecido) cujo marca+modelo é próximo de um existente fá-lo fundir-se no **golden record errado**, corrompendo o núcleo de dados — sem marcar `needs_review`.
2. **A2 — Rate-limit do preço live contornável** *(Alto, [Confirmado])*. O IP usado no throttle vem do header `X-Forwarded-For` cru (`.split(",")[0]`), forjável pelo cliente. Rodando o header + variando `slug`, um anónimo amplifica chamadas à **API paga** de preço live — exatamente o custo que o blueprint marca como risco-chave (§10).
3. **M4 — Sem transações (autocommit) ⇒ escritas não-atómicas** *(Médio, [Confirmado])*. Operações DELETE+INSERT (sinais de score, snapshots de ranking, refresh de preço) não são atómicas; um crash a meio deixa estado parcial (produto sem sinais, ranking vazio, ofertas em falta momentânea).
4. **M7 — Núcleo dos workers sem testes** *(Médio, [Confirmado])*. `pytest --cov` = **34%** total, com **0%** em `pipelines.py`, `db.py` e `resolution.py` (a função do achado A1). O web não tem testes unitários (só 3 e2e Playwright).
5. **M2/M1 — Postura de segurança web** *(Médio, [Confirmado])*. `next.config.ts` vazio ⇒ **sem CSP/HSTS/X-Frame-Options/…**; o cookie de identidade `decifra_uid` é a **chave primária `users.id` em claro, sem assinatura** (bearer token forjável se o UUID vazar).

### Veredicto de prontidão para produção

**Condicional — ainda NÃO pronto.** As fundações (audit limpo, sem SQLi/SSRF/segredos, degradação graceful, princípios respeitados) permitem avançar com confiança, mas **A1 e A2 devem ser corrigidos antes de produção** (corrompem dados / custam dinheiro) e o conjunto Médio (atomicidade, headers, cookie, gates de CI, cobertura) deve entrar na Fase 1–2. Após a remediação faseada da secção 5, o sistema fica pronto.

---

## 2. Achados

### 🟠 Alto

#### A1 · Dados & Correção · `workers/decifra_workers/resolution.py:16,37` + `db.py:96`
**Estado:** [Confirmado]
**Descrição:** O matcher fuzzy aceita qualquer candidato com similaridade trigram ≥ `0.55` em `brand+model` e devolve o produto existente como match (`method="fuzzy"`), sem reavaliar `needs_review`. Modelos vizinhos partilham quase toda a string.
**Impacto:** Fusão silenciosa de produtos distintos no golden record (o núcleo do sistema, §2 do blueprint). O EAN/specs do produto novo são anexados ao produto errado (`ingest_by_ean` → `upsert_identifier`/`upsert_spec`), corrompendo ficha, preço e score. Não fica marcado para revisão humana, ao contrário do que o blueprint pede ("revisão de baixa confiança").
**Evidência (BD viva, `pg_trgm`):**
```
similarity('Sony WH-1000XM4','Sony WH-1000XM5') = 0.778
similarity('Apple iPhone 15','Apple iPhone 15 Pro') = 0.800
similarity('Samsung Galaxy S24','Samsung Galaxy S23') = 0.800   (todos > 0.55)
```
`resolution.py:37-39` aceita o match e devolve sem tocar em `needs_review`; só a *criação* (linha 50) usa `needs_review = match_confidence < 0.8`.
**Solução:**
- Subir o limite (ex.: `FUZZY_THRESHOLD = 0.85`) **e** exigir igualdade do token de modelo, não só similaridade global; idealmente corroborar com ≥1 spec discriminante (como o blueprint §2 prevê).
- Marcar **sempre** `needs_review=true` num merge fuzzy abaixo de `REVIEW_THRESHOLD` e propagar a similaridade:
```python
match = db.fuzzy_match_product(conn, name, FUZZY_THRESHOLD)
if match:
    pid, sim = match
    if sim < REVIEW_THRESHOLD:
        db.flag_needs_review(conn, pid)          # nova primitiva
    return Resolution(pid, created=False, method="fuzzy")
```
- Acrescentar teste unitário a `resolution.py` (hoje 0% cobertura) com os pares XM4/XM5.
**Esforço:** Médio

#### A2 · Segurança · `web/src/app/api/price/refresh/route.ts:18`
**Estado:** [Confirmado]
**Descrição:** O rate-limit por IP+slug usa `request.headers.get("x-forwarded-for") ?? "anon").split(",")[0]` — a **primeira** entrada do `X-Forwarded-For`, que é controlada pelo cliente. Na Vercel o IP real é acrescentado *após* o valor do cliente, pelo que o primeiro elemento é precisamente o forjável.
**Impacto:** Bypass trivial do cooldown de 30 s. Como `/api/price/refresh` dispara a **API paga** de preço live (DataForSEO/Bright Data/SerpApi) sem autenticação, um atacante que rode o header e varie `slug` provoca **amplificação de custo / esgotamento de quota** — o risco que o blueprint §10 destaca ("custo de preço live: nunca correr globalmente").
**Evidência:** `route.ts:18-19`:
```ts
const ip = (request.headers.get("x-forwarded-for") ?? "anon").split(",")[0].trim();
const allowed = await rateLimit(`rl:price:${ip}:${slug}`, COOLDOWN_SECONDS);
```
**Solução:** usar a identidade de cliente fornecida pela plataforma (não confiável no header cru). Na Vercel, `x-real-ip` ou `@vercel/functions#ipAddress(request)`; se usar `x-forwarded-for`, ler o **último** hop (o injetado pela plataforma). Adicionalmente, impor um **rate-limit global** por janela (teto absoluto de chamadas pagas/min) independente do IP, para limitar o custo mesmo sob IPs rotativos.
```ts
import { ipAddress } from "@vercel/functions";
const ip = ipAddress(request) ?? "anon";
// + um segundo balde global: rateLimit(`rl:price:global`, 1) com capacidade N/min
```
**Esforço:** Baixo

---

### 🟡 Médio

| ID | Área | Local | Estado | Resumo |
|---|---|---|---|---|
| M1 | Segurança/Authz | `lib/favorites.ts:20`, `_actions/favorites.ts:16-20` | [Confirmado] | Cookie `decifra_uid` = `users.id` em claro, sem assinatura |
| M2 | Segurança | `next.config.ts` | [Confirmado] | Sem cabeçalhos de segurança (CSP/HSTS/…) |
| M3 | Segurança/XSS | `PriceTable.tsx:54`, `ReviewsBlock.tsx:89` | [Confirmado] sink | URL externa renderizada como `href` sem validar protocolo |
| M4 | Robustez | `db.py:18`, `pipelines.py:449-468`, `priceLive.ts:185-198` | [Confirmado] | `autocommit=True` ⇒ escritas multi-statement não-atómicas |
| M5 | Robustez | `pipelines.py:37` | [Confirmado] | Fan-out de ingestão sem isolamento por fonte |
| M6 | Performance/SEO | `page.tsx:6`, `tops/page.tsx:4`, `tops/[slug]/page.tsx:8` | [Confirmado] | Home/tops `force-dynamic` sem necessidade ⇒ sem ISR/cache CDN |
| M7 | Qualidade/Testes | `workers/` + `web/` | [Confirmado] | 0% cobertura unitária no núcleo; web sem unit tests |
| M8 | CI/CD | `.github/workflows/ci.yml` | [Confirmado] | Lint e `npm audit`/`pip-audit` não bloqueiam o CI |
| M9 | Observabilidade/PII | `pipelines.py:182` | [Confirmado] | Email do utilizador impresso em stdout |
| M10 | Observabilidade | `instrumentation.ts` | [Confirmado] | Sentry web só server-side (`@sentry/node`) |
| M11 | Robustez | `priceLive.ts:108,114,123` | [Confirmado] | `fetch()` externo sem timeout |
| M12 | Dados/Esquema | `0000_init.sql`, `schema.ts` | [Confirmado] | Sem CHECK constraints nas colunas enum |

#### M1 · Cookie de identidade = chave primária, sem assinatura
**Descrição:** `ensureUserId()` grava `created.id` (UUID de `users.id`) diretamente no cookie e relê-o como identidade (`where users.id = cookie`). É um **bearer token igual à PK**, sem HMAC/assinatura.
**Impacto:** Se algum `user.id` vazar (HTML, log, resposta de API, futura feature), qualquer pessoa pode definir `decifra_uid=<uuid>` e **personificar** esse utilizador — ver/alterar favoritos, alertas e **email**. Hoje o `user.id` **não** é exposto (confirmado: `favoritos/page.tsx` usa-o só server-side), pelo que o impacto é **latente** ([Suspeita] quanto à explorabilidade atual), mas o design é frágil. UUIDv4 (122 bits) torna a adivinhação inviável.
**Evidência:** `_actions/favorites.ts:20` `jar.set(UID_COOKIE, created.id, …)`; `favorites.ts:14-17`.
**Solução:** assinar o cookie (HMAC com segredo do servidor) ou emitir um **token de sessão opaco** distinto da PK, mapeado server-side; nunca expor `user.id`. Manter `httpOnly`/`sameSite=lax` (já presentes).
**Esforço:** Médio

#### M2 · Cabeçalhos de segurança em falta
**Descrição:** `next.config.ts` está vazio (config default). Não há `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`/`frame-ancestors`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, nem `poweredByHeader:false`.
**Impacto:** Defesa-em-profundidade ausente (clickjacking, sniffing de MIME, ausência de CSP a mitigar XSS — relevante dado M3). `X-Powered-By` revela a stack.
**Evidência:** `next.config.ts` (7 linhas, sem `headers()`).
**Solução:**
```ts
const nextConfig: NextConfig = {
  poweredByHeader: false,
  async headers() {
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        // CSP: começar em Report-Only e endurecer
        { key: "Content-Security-Policy", value: "default-src 'self'; img-src 'self' https: data:; …" },
      ],
    }];
  },
};
```
**Esforço:** Baixo (CSP afinada: Médio)

#### M3 · URL externa renderizada como `href` sem validar protocolo
**Descrição:** `PriceTable.tsx:54` (`href={o.urlAffiliate ?? "#"}`) e `ReviewsBlock.tsx:89` (`href={r.sourceUrl}`) renderizam URLs vindas de fontes externas semi-confiáveis (feeds Awin, respostas de preço-live scraped, JSON-LD de reviews). Os parsers (`priceLive.ts` `parse*`, `reviews.py`) **não validam** que o esquema é `http(s)`.
**Impacto:** Uma URL `javascript:…` armazenada em `offers.url_affiliate`/`reviews_aggregate.source_url` seria executada ao clicar (XSS armazenado refletido na navegação). `rel="...noopener"` protege contra tabnabbing mas **não** contra o protocolo.
**Estado:** [Confirmado] (o sink existe e os dados são externos) / [Suspeita] quanto à explorabilidade end-to-end (depende de a fonte conseguir injetar `javascript:` e de o React 19 o renderizar executável).
**Solução:** validar/normalizar o protocolo antes de renderizar; centralizar num helper:
```ts
export function safeHref(u: string | null): string {
  try { const p = new URL(u ?? ""); return ["http:", "https:"].includes(p.protocol) ? p.href : "#"; }
  catch { return "#"; }
}
```
Aplicar em ambos os sinks. (Reforçado pela CSP de M2.)
**Esforço:** Baixo

#### M4 · Sem transações ⇒ escritas multi-statement não-atómicas
**Descrição:** `db.connect(…, autocommit=True)` (db.py:18) faz cada statement auto-commitar. Operações compostas não estão envolvidas em transação:
- `replace_derived_signals` (DELETE + N×INSERT) — `pipelines.py:450`;
- `upsert_ranking` (DELETE itens) + loop `insert_ranking_item` — `pipelines.py:463-468`;
- web `refreshProductPrice`: `delete(offers…)` + loop `insert` — `priceLive.ts:185-198`.
**Impacto:** Um crash/erro a meio deixa estado **parcial**: produto com score mas sem sinais auditáveis; ranking sem itens; janela em que o produto fica sem ofertas. Recuperável no próximo recompute (mensal), mas inconsistente entretanto.
**Evidência:** `db.py:17-18`; chamadas acima.
**Solução:** envolver cada bloco numa transação. Workers (psycopg): `with conn.transaction(): …` por produto/ranking (manter `autocommit=True` na ligação, mas abrir transação explícita nas secções compostas). Web (Drizzle/postgres-js): `await db.transaction(async (tx) => { … })` em `refreshProductPrice`.
**Esforço:** Médio

#### M5 · Fan-out de ingestão sem isolamento por fonte
**Descrição:** Em `ingest_by_ean`, a recolha é `records = [(c, rec) for c in connectors if c.configured() if (rec := c.fetch_by_ean(ean))]` (pipelines.py:37), **fora** do try (que só começa na linha 55). Os connectors `icecat`/`upcitemdb` **relançam** em erro de rede (httpx) ou 429/5xx após 3 retries.
**Impacto:** Uma única fonte a falhar (timeout, 429 sustentado) **aborta toda a ingestão**, perdendo o sucesso parcial das outras (ex.: identidade do UPCitemdb perde-se porque o Icecat teve um timeout). Contradiz a resiliência a falhas parciais.
**Evidência:** `pipelines.py:37` vs `try:` em `pipelines.py:55`; `icecat.py:144-146`/`upcitemdb.py:69-71` relançam `_Retryable`.
**Solução:** isolar cada fonte:
```python
records = []
for c in connectors:
    if not c.configured(): continue
    try:
        if rec := c.fetch_by_ean(ean): records.append((c, rec))
    except Exception as exc:
        observability.capture(exc, source=c.name, ean=ean)   # skip gracioso
```
**Esforço:** Baixo

#### M6 · Páginas SEO-críticas `force-dynamic` (sem ISR/cache CDN)
**Descrição:** As páginas declaram `export const dynamic = "force-dynamic"`. A **home (`/`)** e os **tops (`/tops`, `/tops/[slug]`)** **não dependem de cookie** (confirmado por grep — não usam `currentUserId`/`FavoriteBox`/`cookies()`), pelo que o `force-dynamic` aí é **desnecessário**. O blueprint marca SEO como "o canal de aquisição decisivo" (§7).
**Nuance (verificada):** a **ficha `/produto/[slug]` lê o cookie** via `FavoriteBox` (server component que chama `currentUserId()` em `FavoriteBox.tsx:7`), pelo que aí o `force-dynamic` é **justificado** — tornar a ficha cacheável exige refactor (transformar o `FavoriteBox` em ilha cliente que busca o seu estado, ou Partial Prerendering), não basta trocar a flag.
**Impacto:** Home e tops sem static/ISR ⇒ HTML não cacheável em CDN; cada hit de crawler = SSR + queries à BD. Pior latência/custo e desperdício da camada de cache (`invalidateProduct` já existe para invalidação on-demand).
**Evidência:** `grep "force-dynamic"` → 9 ocorrências; `next build` lista tudo como `ƒ (Dynamic)`. Grep confirma cookie só em `_actions/favorites.ts`, `lib/favorites.ts` e `FavoriteBox.tsx`; home/tops não os importam. `generateMetadata` presente (SEO de meta ✓), mas o render dinâmico anula a cacheabilidade.
**Solução:** **ganho direto** — `export const revalidate = 300` (ISR) na home e em `/tops/*`, invalidando on-demand via `revalidateTag`/`revalidatePath` nos pontos que já chamam `invalidateProduct` (feed batch, price refresh, recompute). **Ficha de produto (refactor, Fase 3)** — extrair o `FavoriteBox` para uma ilha cliente (ou PPR) e então aplicar ISR à ficha. Manter `force-dynamic` em `favoritos` e nas rotas de API.
**Esforço:** Baixo (home/tops) · Médio (ficha)

#### M7 · Cobertura de testes do núcleo
**Descrição:** `pytest --cov` (unit) = **34%** total. **0%** em `pipelines.py` (341 stmts), `db.py` (136), `resolution.py` (23), `__main__.py`, `observability.py`. Bem cobertos só os puros (scoring 97%, models/text_utils 100%, parsers 55-62%). O **web não tem testes unitários** (só 3 e2e Playwright); a matemática de `score.ts` e a lógica de `finder.ts`/`lookup.ts` não têm testes.
**Impacto:** O núcleo de dados (orquestração, persistência, entity resolution — onde vive A1) não tem rede de segurança unitária; os 3 testes de integração não apanharam a fusão fuzzy.
**Evidência:** output de cobertura (secção 3).
**Solução:** testes unitários a `resolution.py` (casos XM4/XM5), `pipelines.score_recompute` (renormalização/atomicidade), e a `db.py` com uma BD efémera (já existe no CI). No web, adicionar `vitest` para `score.ts`/`num.ts`/`finder.ts` (e pôr os `parse*` exportados — hoje sem uso — sob teste). Meta inicial: ≥60% no núcleo.
**Esforço:** Alto

#### M8 · CI não bloqueia lint nem audit
**Descrição:** `ci.yml` corre `build` (que faz type-check) + `pytest` + Playwright + integração. **Não corre** `npm run lint`/ESLint, nem `npm audit`, nem `pip-audit`, nem `ruff`/`mypy`/`bandit`.
**Impacto:** O `npm audit` 0 conquistado nos lotes anteriores pode **regredir sem gate**; lint/tipos Python e segurança não são forçados.
**Evidência:** `ci.yml` (jobs `web`, `workers`, `e2e-ui`, `workers-e2e` — nenhum com lint/audit).
**Solução:** acrescentar ao job `web` `npm run lint` e `npm audit --audit-level=high`; ao job `workers` `ruff check`, `ruff format --check`, `mypy decifra_workers`, `pip-audit -r requirements.txt`. (Definir primeiro a baseline de ruff/format — ver B10.)
**Esforço:** Baixo

#### M9 · PII (email) em stdout
**Descrição:** `check_price_alerts` imprime `print(f"[alerta] {name}: … → {dest}")` onde `dest` é o **email** do utilizador.
**Impacto:** Email (PII) nos logs do cron (GitHub Actions / agregador). Risco de privacidade/conformidade.
**Evidência:** `pipelines.py:181-182`.
**Solução:** não logar o email; logar um id opaco ou hash, ou só a contagem. Quando o envio real existir, manter o email fora dos logs estruturados.
**Esforço:** Baixo

#### M10 · Sentry web só captura servidor
**Descrição:** `instrumentation.ts` usa `@sentry/node` + `onRequestError` (server/RSC). **Erros client-side** (browser) não são capturados; não há SDK de browser nem `@sentry/nextjs`.
**Impacto:** Observabilidade parcial — bugs de UI/hidratação/cliente passam despercebidos, contrariando o requisito "apanhar falhas cedo" (§7).
**Evidência:** `instrumentation.ts:7` (`@sentry/node`); `package.json` sem `@sentry/nextjs`/browser.
**Solução:** adotar `@sentry/nextjs` (instrumenta server + client + edge, com source maps), ou adicionar um SDK de browser. Manter o gating por DSN (graceful).
**Esforço:** Médio

#### M11 · `fetch()` externo sem timeout no web
**Descrição:** Em `priceLive.ts`, os `fetch` a SerpApi/Bright Data/DataForSEO (linhas 108, 114, 123) **não têm timeout/AbortController** — ao contrário do worker equivalente (`price_live.py` usa `timeout=30` + tenacity).
**Impacto:** Um upstream lento pendura o pedido on-demand até ao limite da plataforma; pior latência e ocupação de função serverless.
**Evidência:** `priceLive.ts:108/114/123` (sem `signal`); contraste `price_live.py:132,173`.
**Solução:** `AbortSignal.timeout(8000)` em cada `fetch`, com `catch` a degradar para `[]` (já existe o try/catch que devolve `[]`).
**Esforço:** Baixo

#### M12 · Sem CHECK constraints nas colunas enum
**Descrição:** Colunas enum-like são `varchar` livres sem CHECK: `products.status`, `sources.kind`, `category_attributes.data_type`, `product_identifiers.id_type`, `rankings.criterion`/`period_type`, `review_themes.polarity`, `product_compatibility.relation`. A integridade é só da app.
**Impacto:** Um worker/SQL com um valor inválido (ex.: `status='a_vender'`, `polarity='pos'`) entra sem erro e parte filtros/joins silenciosamente.
**Evidência:** `0000_init.sql:48,83,…`; `schema.ts` (varchar sem CHECK).
**Solução:** adicionar CHECKs (idempotentes) numa nova migração, ou enums Postgres. Ex.: `ALTER TABLE products ADD CONSTRAINT products_status_chk CHECK (status IN ('a_venda','descontinuado','substituido'));`
**Esforço:** Baixo

---

### 🟢 Baixo

| ID | Área | Local | Estado | Resumo / Solução curta |
|---|---|---|---|---|
| B1 | Segurança/XSS | `extension/popup.js:38-42` | [Confirmado] | `innerHTML` com dados de produto externos. Mitigado pela CSP do Manifest V3 (bloqueia script inline) ⇒ injeção de HTML/phishing, não exec. **Usar `textContent`/DOM em vez de `innerHTML`.** |
| B2 | Robustez/Custo | `workers/cache.py:54` | [Confirmado] | Token-bucket `allow()` (throttle das APIs pagas, §7) **nunca é chamado** (confirmado por grep). Ligar nos connectors pagos ou remover (dead code). |
| B3 | Observabilidade | `lib/lookup.ts:56,59,63` | [Confirmado] | `console.info` no hot path a logar input (`q`/`ean`). Remover ou trocar por log estruturado com nível. |
| B4 | Robustez/UX | `_actions/favorites.ts:74-82` | [Suspeita] | `setEmail` sem validação de formato e **sem tratar violação de UNIQUE** (email já usado → exceção não capturada → 500). Validar formato e capturar a colisão devolvendo erro amigável. *Confirmar: definir email duplicado em duas sessões.* |
| B5 | Dados/DevEx | `web/src/db/migrate.ts` | [Confirmado] | Runner re-corre **todas** as migrations (sem ledger `__migrations`), fora de transação. Funciona por serem idempotentes, mas frágil para futuras `ALTER`/data-migrations. Adotar `drizzle-kit migrate` ou uma tabela de controlo + transação por ficheiro. |
| B6 | Arquitetura/Dead code | `pipelines.py:488`; knip | [Confirmado] | `score_recompute_year` (NotImplementedError) é dead code (o cron usa `--period year`); 12 exports + 4 tipos não usados (`isSaved`, `formatDate`, `parse*`, `CRITERIA`, `DEFAULT_WEIGHTS`…). Remover/!inline. |
| B7 | Performance | `queries.ts:106`; `finder.ts:103-145`; `db.py:289`; `lookup.ts:78-93` | [Confirmado] | Sem índice em `products.updated_at` (ordenação da home); N+1 em `getFinderQuestions` (≤5 queries) e no batch `attribute_stats`; `ilike('%q%')` em `canonical_name` sem índice trgm (só `brand,model` o têm). Índice em `updated_at`; trgm em `canonical_name`; agregar as queries do finder. |
| B8 | Performance | `lib/cache.ts:79,93` | [Confirmado] | Fallback de rate-limit em memória é **per-instância** (inútil em serverless multi-instância) e o `Map _memRate` **cresce sem evição** (leak lento). Documentar como só-dev; evitar acumulação (TTL/limpeza). |
| B9 | Arquitetura/Manutenção | `score.ts` + `scoring.py`; `schema.ts` + `*.sql` | [Confirmado] | Dupla implementação da matemática do score (TS/Py) sem teste cruzado; dupla fonte do esquema (SQL hand-written + `schema.ts` manual). Hoje consistentes; adicionar teste/golden que fixe a paridade. |
| B10 | Qualidade | `workers/` (ruff/mypy) | [Confirmado] | `ruff`: 215×E501 (linha>88) + 2×S110 (`try-except-pass`); `ruff format`: 26 ficheiros divergem (sem config de formatter no projeto); `mypy`: 13 erros (**verificados como falsos positivos** — narrowing de `.get()` duplo e `INSERT…RETURNING`/agregados que nunca devolvem None). Definir `pyproject.toml` (line-length, ruff/format) e adotar baseline antes de gate no CI. |
| B11 | DevEx | `web/.env.example` | [Confirmado] | Inclui chaves que o web **não lê** (`GO_UPC_API_KEY`, `ICECAT_USERNAME`, `AWIN_PUBLISHER_ID` são dos workers) e omite os `*_BASE_URL` opcionais (têm default). Limpar/comentar a separação web↔workers. |
| B12 | Concorrência | `workers/db.py:115-120` | [Confirmado] sink / [Suspeita] gatilho | `_unique_slug` é TOCTOU (SELECT-depois-INSERT); sob ingestão concorrente do mesmo produto, o 2.º INSERT viola o unique de `slug` e (com autocommit) aborta. Tratar a violação com retry, ou `INSERT … ON CONFLICT`. |
| B13 | DevEx | `lib/*.ts` (knip/depcheck) | [Confirmado] | `server-only` é dependência usada mas não declarada (resolve via Next). Adicionar a `dependencies` para correção. |

---

## 3. Resultados das ferramentas

| Ferramenta | Alvo | Resultado |
|---|---|---|
| `tsc --noEmit` | web | **0 erros** (exit 0) |
| `eslint .` | web | **0 problemas** (exit 0) |
| `next build` | web | **OK** (exit 0; todas as rotas `ƒ` dinâmicas — ver M6) |
| `npm audit` | web | **0 vulnerabilidades** |
| `knip` | web | 7 deps não listadas (`server-only`), **12 exports + 4 tipos não usados** (dead code — B6) |
| `depcheck` | web | `server-only` em falta (B13); `tailwindcss`/`@tailwindcss/postcss`/`@types/react-dom` marcados unused = **falsos positivos** (Tailwind v4 liga via config) |
| `madge --circular` | web (38 ficheiros) | **0 dependências circulares** ✓ |
| `ruff check` | workers (pacote) | 223 (215×E501 estilo + **2×S110** + 6 menores). Em testes: muitos S101 (asserts, esperado) |
| `ruff format --check` | workers | 26 ficheiros divergem (sem formatter configurado — B10) |
| `mypy decifra_workers` | workers | 13 erros em 6 ficheiros — **verificados manualmente como falsos positivos** (narrowing; `INSERT…RETURNING`/agregados) |
| `bandit -r decifra_workers` | workers | **2 Low** (os `try-except-pass`); 0 Medium/High |
| `pip-audit -r requirements.txt` | workers (só projeto) | **0 vulnerabilidades** |
| `pip-audit` (venv completo) | — | 4 em `pyjwt` — **descartado**: `Required-by: mcp, semgrep` (tooling que instalei), **não** do projeto |
| `pytest -m "not integration" --cov` | workers | **32 passed; cobertura 34%** (0% em pipelines/db/resolution — M7) |
| `pytest -m integration` | workers | 3 passed |
| `semgrep` (security-audit + owasp-top-ten + secrets) | web/src + workers | **0 findings**, 0 erros de parse |
| `gitleaks detect` | repo + **história (22 commits)** | **no leaks found** ✓ |
| `psql similarity()` | BD viva | Prova de A1 (0.778 / 0.800) |

> **Nota de rigor:** `gitleaks`, `ruff`, `mypy`, `bandit`, `pip-audit`, `semgrep` e `pytest-cov` foram **instalados** neste ambiente (havia rede). Não foi simulado nenhum output. A contaminação do venv pelo tooling foi isolada via `pip-audit -r requirements.txt` (só os requirements do projeto).

---

## 4. Conformidade com o blueprint

**Princípios invioláveis — todos respeitados:**

| Princípio | Estado | Evidência |
|---|---|---|
| #1 IA nunca é fonte primária | ✅ | `ai.py` — todos os prompts instruem "NÃO inventes números/specs"; a IA só gera texto ou escolhe *keys* validadas contra o que varia; autenticidade é estimada de **sinais agregados**, sancionada por §5 |
| #2 Nunca guardar texto de reviews | ✅ | `reviews.py` lê só `aggregateRating`/notas/datas/positiveNotes (≤80 char), **nunca `reviewBody`**; sem tabela de texto |
| #3 Preço live nunca em cron | ✅ | `scheduled-jobs.yml` tem feed/score-month/score-year/review-popular — **nenhum `refresh-price`** |
| #4 Proveniência em tudo | ✅ | `source_id`+`confidence` em `specs`, `offers`, `reviews_aggregate`, `score_signals`, `product_compatibility` |
| #5 Degradação graceful | ⚠️ Maioritariamente | Connectors `configured()`/skip, status `partial`, no-op sem Redis/Sentry — **exceto o fan-out de ingestão (M5)** |

**Desvios face ao blueprint (funcionalidade):**

| Área | Blueprint | Estado atual | Achado |
|---|---|---|---|
| Entity resolution | EAN → fuzzy marca+modelo+**specs** → revisão de baixa confiança | Fuzzy só por marca+modelo a 0.55; **sem `needs_review` em merges** | A1 |
| Throttle de APIs pagas | "throttling das APIs pagas" (§7) | `cache.allow()` existe mas **não ligado** | B2 |
| Finder semântico (pgvector) | Busca por embeddings/`pgvector` (§6) | Coluna `embedding(1024)` + índice HNSW existem, mas **nada popula embeddings** | [Suspeita] — semântica inativa |
| Full-text search | full-text no Postgres (§6) | `search_vector` (tsvector+GIN) existe, mas `lookup` usa `ilike('%q%')` em vez de `to_tsquery` | Otimização por usar |
| Finder adaptativo por IA | "pergunta seguinte depende da anterior" (§6) | Web é data-driven estático; IA escolhe discriminantes offline | Parcial (aceitável p/ v1) |
| Recompute anual | cron de janeiro | Funciona via `score-recompute --period year`; `score_recompute_year()` é stub morto | B6 |

> Os desvios de pgvector/full-text/finder-adaptativo são **coerentes com o faseamento v1** (núcleo universal); ficam registados como trabalho pendente, não como defeitos.

---

## 5. Plano de remediação faseado

### Fase 1 — Quick wins de baixo risco (1–2 dias)
*Ordenar por impacto; sem dependências entre si, exceto onde indicado.*

1. **A2** — IP fiável + teto global no rate-limit do preço live *(corta custo já)*.
2. **M2** — cabeçalhos de segurança em `next.config.ts` (CSP em Report-Only primeiro).
3. **M3** — helper `safeHref()` nos 2 sinks *(beneficia da CSP de M2)*.
4. **M5** — try/except por fonte no fan-out de ingestão.
5. **M9** — remover email dos logs.
6. **M11** — timeout nos `fetch` do `priceLive.ts`.
7. **M8** — adicionar lint + `npm audit`/`pip-audit` ao CI *(depende de B10 para o ruff/format não falhar)*.
8. **B3, B6, B13** — limpar `console.info`, dead code e `server-only`.

### Fase 2 — Correções de fundo (3–5 dias)
9. **A1** — endurecer o entity resolution (threshold + token de modelo + `needs_review`) **com testes** *(depende de M7 para a infra de teste de `resolution.py`)*.
10. **M4** — transações nas escritas compostas (workers + web).
11. **M1** — assinar o cookie de identidade / token opaco.
12. **M7** — testes unitários do núcleo (resolution, pipelines, db; vitest no web).
13. **M12** — CHECK constraints (nova migração idempotente).
14. **M10** — migrar para `@sentry/nextjs` (client + server).

### Fase 3 — Estrutural / dívida (1–2 semanas)
15. **M6 (parte estrutural)** — extrair `FavoriteBox` para ilha cliente / PPR e aplicar ISR à ficha de produto. *(O ISR de home/tops é quick-win e pode subir para a Fase 1; pareia com `invalidateProduct` existente.)*
16. **B5** — adotar ledger de migrações (`drizzle-kit migrate`).
17. **B2** — ligar (ou remover) o throttle de APIs pagas.
18. **B9/B10** — `pyproject.toml` (ruff/format/mypy), teste de paridade `score.ts`↔`scoring.py`, baseline de estilo.
19. **B7/B8** — índices em falta (`updated_at`, trgm em `canonical_name`), agregar N+1 do finder, limpar fallback de rate-limit.
20. Blueprint pendente: popular `embedding` (pgvector) e usar `to_tsquery` no lookup.

---

## 6. O que está bem (preservar na remediação)

- **Segurança de base limpa:** `npm audit` 0, `semgrep` 0, `gitleaks` 0 em **toda a história**, **zero segredos hardcoded** (tudo de env via `config.py`/`process.env`), `.env` corretamente gitignored (só `.env.example` commitados).
- **Sem as classes graves clássicas:** **sem SQL injection** (tudo parametrizado, incluindo os `sql` templates do Drizzle no finder), **sem SSRF** (destinos de `fetch` fixados em env; query = dado interno codificado), **sem `dangerouslySetInnerHTML`**, **sem dependências circulares**.
- **Princípios do produto respeitados** (secção 4) — incluindo a fronteira legal das reviews e o preço live fora dos crons.
- **Esquema e dados:** migrations **idempotentes** (0000–0003 verificadas), índices abrangentes (GIN full-text, GIN trgm, HNSW pgvector, todos os FK, uniques corretos), `tsvector` gerado, proveniência em todas as tabelas de factos.
- **Acesso a dados eficiente:** queries relacionais do Drizzle (**sem N+1** nos caminhos quentes — ficha e home), singleton lazy `max:1` (seguro em serverless), `numeric`→`string` (precisão preservada).
- **Workers resilientes:** `tenacity` (retry+backoff) e timeouts nos connectors, parsing defensivo, skips graciosos, **logs estruturados JSON**, fronteira de job que captura tudo e regista em `ingestion_runs`; degradação graceful documentada e real.
- **SEO de meta:** `generateMetadata` nas páginas (títulos/descrições dinâmicos).
- **Higiene mantida:** `tsc`/`eslint` limpos, override `esbuild` *scoped* (audit 0), `score.ts`↔`scoring.py` atualmente consistentes, boa cobertura nas funções puras (scoring 97%, models/text_utils 100%).

---

*Fim da auditoria. Nenhum código, esquema, migração ou configuração foi alterado nesta fase — a aplicação das correções fica sujeita a aprovação.*
