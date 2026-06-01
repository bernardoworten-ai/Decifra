# DECIFRA

Comparador de produtos com **confiança verificável**: ficha explicada, preço
multi-loja e reviews agregadas — cada número com **fonte citada** e **selo de
confiança**. A camada curada (DECIFRA Score + rankings) chega quando há densidade
de dados. A IA explica e normaliza, **nunca** é a fonte primária dos números.

> Estado: **v1 — núcleo universal** (em construção). Ver [`docs/blueprint-mvp.md`](docs/blueprint-mvp.md).

## Arquitetura

Monólito modular + serverless. Postgres como núcleo (relacional + `JSONB` +
`pgvector` + full-text).

```
Decifra/
├── web/        Next.js 16 (App Router) + TypeScript — front + API. Drizzle ORM.
├── workers/    Python — ingestão, entity resolution e IA (scaffold).
├── docs/       Blueprint + metodologia do score.
└── docker-compose.yml   Postgres 16 + pgvector para dev local.
```

| Camada | Escolha |
|---|---|
| Frontend + API | Next.js 16 + TypeScript (SSR para SEO) |
| ORM | Drizzle (TypeScript-first, leve, serverless) |
| Base de dados | PostgreSQL + pgvector + full-text (Supabase/Neon em prod) |
| Workers dados/IA | Python (httpx, psycopg, Anthropic) |
| IA | API Anthropic (Claude) — ancorada em fontes |

O esquema completo (19 tabelas, traduzido do blueprint §2.1) está em
[`web/drizzle/0000_init.sql`](web/drizzle/0000_init.sql) e espelhado em Drizzle
em [`web/src/db/schema.ts`](web/src/db/schema.ts). O princípio central é
**entity resolution**: um golden record canónico (`products`) alimentado por
registos-fonte crús (`source_records`).

## Arrancar localmente

Pré-requisitos: Node 20+, Docker.

```bash
# 1. Base de dados (Postgres + pgvector)
docker compose up -d db

# 2. App web
cd web
npm install
cp .env.example .env          # DATABASE_URL já aponta para o Postgres local
npm run db:migrate            # cria o esquema (pgvector, full-text, triggers)
npm run db:seed               # 4 produtos de demonstração (tech)
npm run dev                   # http://localhost:3000
```

Páginas: `/` (lista + pesquisa) e `/produto/sony-wh-1000xm5` (ficha completa:
specs explicadas com fonte, preço multi-loja, reviews por loja, DECIFRA Score).

### Scripts úteis (`web/`)

| Script | Faz |
|---|---|
| `npm run db:migrate` | Aplica as migrações SQL de `drizzle/`. |
| `npm run db:seed` | Recria os dados de demonstração. |
| `npm run db:reset` | Migrate + seed. |
| `npm run db:studio` | Drizzle Studio (inspeção da BD). |
| `npm run build` / `npm run dev` | Build / dev server. |

## O que a v1 já demonstra

- **Modelo de dados universal** (EAV) — auscultadores e SSD partilham zero
  colunas de specs, mas vivem no mesmo esquema.
- **Proveniência em tudo** — cada spec/preço/review traz `source_id` e `confidence`.
- **DECIFRA Score auditável** — compósito ponderado, com selo de confiança
  (verde/amarelo/vermelho). Metodologia em [`docs/decifra-score.md`](docs/decifra-score.md).
- **Fronteira legal das reviews** — guardamos agregados, distribuição,
  autenticidade e resumo próprio; **nunca o texto**. Ligamos à fonte.

## Próximos passos

Ligar fontes reais (workers): EAN APIs, Open Icecat, feeds Awin, fontes de
review. Depois a camada curada (rankings) e a integração Awin (publisher, deep
links, preço live). Ver blueprint §8 e §11.
