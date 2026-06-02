/**
 * Seed de demonstração (v1). Dados realistas em tech para exercitar o modelo
 * universal (EAV) — auscultadores + SSD partilham zero colunas de specs.
 *
 * Cada facto traz source_id + confidence + corroborations. O DECIFRA Score é
 * calculado a partir dos sub-scores (lib/score.ts), nunca inventado à mão.
 *   npm run db:seed
 */
import "dotenv/config";
import { eq, sql } from "drizzle-orm";
import { getDb } from "./index";
import {
  categories,
  categoryAttributes,
  ingestionRuns,
  offers,
  productCompatibility,
  productIdentifiers,
  products,
  reviewThemes,
  reviewsAggregate,
  scoreSignals,
  scores,
  sources,
  specs,
  stores,
} from "./schema";
import { computeOverall, confidenceFromSources, valueIndex, type SubScores } from "@/lib/score";

const db = getDb();
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000);
const img = (label: string) =>
  `https://placehold.co/600x600/0f172a/e2e8f0?text=${encodeURIComponent(label)}`;

async function main() {
  console.log("→ a limpar tabelas…");
  await db.execute(sql`TRUNCATE TABLE
    saved_items, users, finder_sessions, ranking_items, rankings,
    score_signals, scores, review_themes, reviews_aggregate, offers,
    specs, source_records, product_identifiers, products,
    category_attributes, categories, stores, sources, ingestion_runs
    RESTART IDENTITY CASCADE`);

  // ── Fontes ──────────────────────────────────────────────────────────────
  const srcRows = await db
    .insert(sources)
    .values([
      { name: "rtings", kind: "expert", baseUrl: "https://www.rtings.com", trustWeight: "0.95" },
      { name: "icecat", kind: "specs", baseUrl: "https://icecat.biz", trustWeight: "0.9" },
      { name: "go_upc", kind: "identity", baseUrl: "https://go-upc.com", trustWeight: "0.7" },
      { name: "awin_feed", kind: "offers", baseUrl: "https://www.awin.com", trustWeight: "0.8" },
      { name: "serpapi", kind: "offers", baseUrl: "https://serpapi.com", trustWeight: "0.6" },
      { name: "amazon", kind: "reviews", baseUrl: "https://www.amazon.es", trustWeight: "0.65" },
      { name: "worten", kind: "reviews", baseUrl: "https://www.worten.pt", trustWeight: "0.6" },
      { name: "google", kind: "reviews", baseUrl: "https://www.google.com", trustWeight: "0.7" },
    ])
    .returning({ id: sources.id, name: sources.name });
  src = Object.fromEntries(srcRows.map((r) => [r.name, r.id])) as Record<string, string>;

  // ── Lojas ───────────────────────────────────────────────────────────────
  const storeRows = await db
    .insert(stores)
    .values([
      { name: "Worten", affiliateNetwork: "awin", country: "PT" },
      { name: "Fnac", affiliateNetwork: "awin", country: "PT" },
      { name: "Amazon.es", affiliateNetwork: "amazon", country: "ES" },
      { name: "MediaMarkt", affiliateNetwork: "awin", country: "PT" },
      { name: "PCDIGA", affiliateNetwork: "awin", country: "PT" },
    ])
    .returning({ id: stores.id, name: stores.name });
  store = Object.fromEntries(storeRows.map((r) => [r.name, r.id])) as Record<string, string>;

  // ── Taxonomia ─────────────────────────────────────────────────────────────
  const setorTech = await insertCategory({ slug: "tecnologia", name: "Tecnologia", level: 0 });
  const catAudio = await insertCategory({
    slug: "audio",
    name: "Áudio",
    level: 1,
    parentId: setorTech,
  });
  const tipoHeadphones = await insertCategory({
    slug: "auscultadores",
    name: "Auscultadores",
    level: 2,
    parentId: catAudio,
    rankingsEnabled: true,
  });
  const catArmazenamento = await insertCategory({
    slug: "armazenamento",
    name: "Armazenamento",
    level: 1,
    parentId: setorTech,
  });
  const tipoSsd = await insertCategory({
    slug: "ssd",
    name: "SSD",
    level: 2,
    parentId: catArmazenamento,
    rankingsEnabled: true,
  });
  // Cauda longa: categoria SEM atributos discriminantes curados — o finder usa IA
  // (Haiku, worker finder-questions) para escolher as perguntas discriminantes.
  const catWearables = await insertCategory({
    slug: "wearables",
    name: "Wearables",
    level: 1,
    parentId: setorTech,
  });
  const tipoSmartwatch = await insertCategory({
    slug: "smartwatches",
    name: "Smartwatches",
    level: 2,
    parentId: catWearables,
  });
  // Acessórios (v3: compatibilidade com aparelhos-base).
  const catAcessorios = await insertCategory({
    slug: "acessorios",
    name: "Acessórios",
    level: 1,
    parentId: setorTech,
  });
  const tipoBandas = await insertCategory({
    slug: "bandas-smartwatch",
    name: "Bandas para smartwatch",
    level: 2,
    parentId: catAcessorios,
  });
  const tipoAlmofadas = await insertCategory({
    slug: "almofadas-auscultadores",
    name: "Almofadas para auscultadores",
    level: 2,
    parentId: catAcessorios,
  });

  // Atributos por categoria (alimentam finder + explicação de specs).
  await db.insert(categoryAttributes).values([
    attr(tipoHeadphones, "tipo", "Tipo", null, "enum", 0, { disc: true, w: 0.05 }),
    attr(tipoHeadphones, "anc", "Cancelamento de ruído (ANC)", null, "bool", 1, { disc: true, w: 0.2 }),
    attr(tipoHeadphones, "autonomia", "Autonomia", "h", "number", 2, { disc: true, w: 0.2 }),
    attr(tipoHeadphones, "bluetooth", "Versão Bluetooth", null, "enum", 3, { w: 0.05 }),
    attr(tipoHeadphones, "drivers", "Diâmetro dos drivers", "mm", "number", 4, { w: 0.1 }),
    attr(tipoHeadphones, "peso", "Peso", "g", "number", 5, { w: 0.05 }),
    attr(tipoHeadphones, "codecs", "Codecs suportados", null, "text", 6, { w: 0.05 }),
    attr(tipoHeadphones, "garantia", "Garantia", "anos", "number", 7, { w: 0.1 }),
    // SSD
    attr(tipoSsd, "capacidade", "Capacidade", "GB", "number", 0, { disc: true, w: 0.2 }),
    attr(tipoSsd, "interface", "Interface", null, "enum", 1, { disc: true, w: 0.1 }),
    attr(tipoSsd, "leitura_seq", "Leitura sequencial", "MB/s", "number", 2, { w: 0.2 }),
    attr(tipoSsd, "escrita_seq", "Escrita sequencial", "MB/s", "number", 3, { w: 0.15 }),
    attr(tipoSsd, "tbw", "Resistência (TBW)", "TB", "number", 4, { w: 0.15 }),
    attr(tipoSsd, "garantia", "Garantia", "anos", "number", 5, { w: 0.1 }),
    // Smartwatches — SEM disc:true de propósito (a IA decide quais são discriminantes).
    attr(tipoSmartwatch, "mostrador", "Tipo de mostrador", null, "enum", 0, { w: 0.1 }),
    attr(tipoSmartwatch, "gps", "GPS integrado", null, "bool", 1, { w: 0.1 }),
    attr(tipoSmartwatch, "autonomia", "Autonomia", "dias", "number", 2, { w: 0.2 }),
    attr(tipoSmartwatch, "ecg", "Sensor ECG", null, "bool", 3, { w: 0.1 }),
    attr(tipoSmartwatch, "sistema", "Sistema operativo", null, "enum", 4, { w: 0.05 }),
    attr(tipoSmartwatch, "caixa", "Tamanho da caixa", "mm", "number", 5, { w: 0.05 }),
    // Bandas (acessório) — discriminantes curados.
    attr(tipoBandas, "material", "Material", null, "enum", 0, { disc: true, w: 0.1 }),
    attr(tipoBandas, "compat_caixa", "Caixa compatível", "mm", "number", 1, { disc: true, w: 0.1 }),
  ]);

  // ── Produtos ──────────────────────────────────────────────────────────────
  // Sony WH-1000XM5
  await seedProduct({
    categoryId: tipoHeadphones,
    slug: "sony-wh-1000xm5",
    brand: "Sony",
    model: "WH-1000XM5",
    canonicalName: "Sony WH-1000XM5",
    summary:
      "Auscultadores over-ear sem fios com cancelamento de ruído de topo, 30 h de autonomia e suporte LDAC. Referência de mercado em ANC e conforto.",
    ean: "4548736132917",
    matchConfidence: "0.98",
    specs: [
      spec("tipo", { text: "Over-ear", src: "icecat", conf: 0.95, corr: 3 }),
      spec("anc", { text: "Sim", num: 1, src: "rtings", conf: 0.97, corr: 4 }),
      spec("autonomia", { num: 30, unit: "h", src: "icecat", conf: 0.9, corr: 3 }),
      spec("bluetooth", { text: "5.2", src: "icecat", conf: 0.85, corr: 2 }),
      spec("drivers", { num: 30, unit: "mm", src: "icecat", conf: 0.8, corr: 2 }),
      spec("peso", { num: 250, unit: "g", src: "icecat", conf: 0.9, corr: 3 }),
      spec("codecs", { text: "SBC, AAC, LDAC", src: "rtings", conf: 0.9, corr: 2 }),
      spec("garantia", { num: 2, unit: "anos", src: "worten", conf: 0.7, corr: 1 }),
    ],
    offers: [
      offer("Amazon.es", 339.9, { src: "awin_feed", days: 1 }),
      offer("Worten", 349.99, { src: "awin_feed", days: 1 }),
      offer("Fnac", 359.0, { src: "awin_feed", days: 2 }),
      offer("MediaMarkt", 369.0, { src: "serpapi", days: 0, stock: false }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.6,
        adjusted: 4.4,
        count: 12480,
        dist: { "5": 8200, "4": 2600, "3": 980, "2": 380, "1": 320 },
        auth: 0.82,
        summary:
          "Os utilizadores destacam o cancelamento de ruído e o conforto em viagens longas; algumas queixas sobre a app e o preço.",
        url: "https://www.amazon.es/dp/B09XS7JWHH",
      }),
      review("worten", {
        raw: 4.7,
        adjusted: 4.6,
        count: 860,
        dist: { "5": 640, "4": 150, "3": 40, "2": 18, "1": 12 },
        auth: 0.9,
        summary: "Feedback muito positivo sobre qualidade de som e construção; poucos relatos de problemas.",
        url: "https://www.worten.pt/sony-wh-1000xm5",
      }),
      review("google", {
        raw: 4.5,
        adjusted: 4.4,
        count: 5400,
        dist: { "5": 3300, "4": 1300, "3": 500, "2": 180, "1": 120 },
        auth: 0.78,
        summary: "Consenso de que é uma referência em ANC, com ressalvas pontuais sobre durabilidade das almofadas.",
        url: "https://www.google.com/search?q=Sony+WH-1000XM5+reviews",
      }),
    ],
    themes: [
      theme("Cancelamento de ruído", "positivo", 410),
      theme("Autonomia", "positivo", 320),
      theme("Conforto", "positivo", 280),
      theme("Qualidade da app", "misto", 95),
      theme("Preço", "negativo", 88),
    ],
    sub: { expert: 90, users: 88, material: 86, value: 78 },
  });

  // Bose QuietComfort Ultra
  await seedProduct({
    categoryId: tipoHeadphones,
    slug: "bose-quietcomfort-ultra",
    brand: "Bose",
    model: "QuietComfort Ultra",
    canonicalName: "Bose QuietComfort Ultra",
    summary:
      "Auscultadores premium com ANC e áudio imersivo (Bose Immersive Audio). Conforto de referência, autonomia de 24 h.",
    ean: "017817845476",
    matchConfidence: "0.96",
    specs: [
      spec("tipo", { text: "Over-ear", src: "icecat", conf: 0.95, corr: 3 }),
      spec("anc", { text: "Sim", num: 1, src: "rtings", conf: 0.96, corr: 3 }),
      spec("autonomia", { num: 24, unit: "h", src: "icecat", conf: 0.88, corr: 2 }),
      spec("bluetooth", { text: "5.3", src: "icecat", conf: 0.85, corr: 2 }),
      spec("drivers", { num: 35, unit: "mm", src: "rtings", conf: 0.7, corr: 1 }),
      spec("peso", { num: 254, unit: "g", src: "icecat", conf: 0.88, corr: 2 }),
      spec("codecs", { text: "SBC, AAC, aptX Adaptive", src: "rtings", conf: 0.85, corr: 2 }),
      spec("garantia", { num: 2, unit: "anos", src: "worten", conf: 0.7, corr: 1 }),
    ],
    offers: [
      offer("Fnac", 399.99, { src: "awin_feed", days: 1 }),
      offer("Worten", 409.99, { src: "awin_feed", days: 1 }),
      offer("Amazon.es", 419.0, { src: "awin_feed", days: 3 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.4,
        adjusted: 4.2,
        count: 3820,
        dist: { "5": 2300, "4": 820, "3": 380, "2": 180, "1": 140 },
        auth: 0.8,
        summary: "Elogios ao conforto e ao áudio imersivo; críticas à autonomia e ao preço face à concorrência.",
        url: "https://www.amazon.es/dp/B0CCZ1CywB",
      }),
      review("worten", {
        raw: 4.5,
        adjusted: 4.4,
        count: 320,
        dist: { "5": 220, "4": 64, "3": 22, "2": 8, "1": 6 },
        auth: 0.88,
        summary: "Boa receção geral, com destaque para o isolamento e a qualidade de chamadas.",
        url: "https://www.worten.pt/bose-quietcomfort-ultra",
      }),
    ],
    themes: [
      theme("Conforto", "positivo", 300),
      theme("Áudio imersivo", "positivo", 210),
      theme("Cancelamento de ruído", "positivo", 260),
      theme("Autonomia", "negativo", 130),
      theme("Preço", "negativo", 110),
    ],
    sub: { expert: 87, users: 85, material: 88, value: 70 },
  });

  // Apple AirPods Max
  await seedProduct({
    categoryId: tipoHeadphones,
    slug: "apple-airpods-max",
    brand: "Apple",
    model: "AirPods Max",
    canonicalName: "Apple AirPods Max",
    summary:
      "Auscultadores over-ear da Apple com ANC, áudio espacial e construção em alumínio. Integração forte no ecossistema Apple.",
    ean: "194252056660",
    matchConfidence: "0.97",
    specs: [
      spec("tipo", { text: "Over-ear", src: "icecat", conf: 0.95, corr: 3 }),
      spec("anc", { text: "Sim", num: 1, src: "rtings", conf: 0.95, corr: 3 }),
      spec("autonomia", { num: 20, unit: "h", src: "icecat", conf: 0.9, corr: 3 }),
      spec("bluetooth", { text: "5.0", src: "icecat", conf: 0.85, corr: 2 }),
      spec("drivers", { num: 40, unit: "mm", src: "rtings", conf: 0.75, corr: 1 }),
      spec("peso", { num: 384, unit: "g", src: "icecat", conf: 0.92, corr: 3 }),
      spec("codecs", { text: "SBC, AAC", src: "rtings", conf: 0.9, corr: 2 }),
      spec("garantia", { num: 2, unit: "anos", src: "worten", conf: 0.7, corr: 1 }),
    ],
    offers: [
      offer("Amazon.es", 519.0, { src: "awin_feed", days: 1 }),
      offer("Worten", 549.99, { src: "awin_feed", days: 2 }),
      offer("Fnac", 559.0, { src: "awin_feed", days: 2 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.5,
        adjusted: 4.3,
        count: 6900,
        dist: { "5": 4400, "4": 1400, "3": 600, "2": 280, "1": 220 },
        auth: 0.76,
        summary: "Qualidade de construção e áudio muito elogiados; peso e preço são as queixas recorrentes.",
        url: "https://www.amazon.es/dp/B08SM5WWNS",
      }),
      review("google", {
        raw: 4.4,
        adjusted: 4.3,
        count: 4100,
        dist: { "5": 2500, "4": 1000, "3": 380, "2": 130, "1": 90 },
        auth: 0.79,
        summary: "Bem avaliado no ecossistema Apple; críticas ao estojo e à ausência de codecs de alta resolução.",
        url: "https://www.google.com/search?q=AirPods+Max+reviews",
      }),
    ],
    themes: [
      theme("Qualidade de construção", "positivo", 340),
      theme("Áudio espacial", "positivo", 190),
      theme("Peso", "negativo", 220),
      theme("Preço", "negativo", 260),
      theme("Estojo (Smart Case)", "negativo", 140),
    ],
    sub: { expert: 84, users: 86, material: 92, value: 60 },
  });

  // Samsung 990 Pro 2TB (categoria diferente → specs EAV diferentes)
  await seedProduct({
    categoryId: tipoSsd,
    slug: "samsung-990-pro-2tb",
    brand: "Samsung",
    model: "990 PRO 2TB",
    canonicalName: "Samsung 990 PRO 2TB NVMe",
    summary:
      "SSD NVMe PCIe 4.0 de alto desempenho, com leituras até 7450 MB/s. Excelente para gaming e cargas de trabalho intensas.",
    ean: "8806094215501",
    matchConfidence: "0.99",
    specs: [
      spec("capacidade", { num: 2000, unit: "GB", src: "icecat", conf: 0.97, corr: 3 }),
      spec("interface", { text: "PCIe 4.0 x4 NVMe", src: "icecat", conf: 0.95, corr: 3 }),
      spec("leitura_seq", { num: 7450, unit: "MB/s", src: "rtings", conf: 0.9, corr: 2 }),
      spec("escrita_seq", { num: 6900, unit: "MB/s", src: "rtings", conf: 0.9, corr: 2 }),
      spec("tbw", { num: 1200, unit: "TB", src: "icecat", conf: 0.85, corr: 2 }),
      spec("garantia", { num: 5, unit: "anos", src: "icecat", conf: 0.9, corr: 2 }),
    ],
    offers: [
      offer("PCDIGA", 149.99, { src: "awin_feed", days: 0 }),
      offer("Amazon.es", 154.9, { src: "awin_feed", days: 1 }),
      offer("Worten", 159.99, { src: "awin_feed", days: 1 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.8,
        adjusted: 4.7,
        count: 9200,
        dist: { "5": 7600, "4": 1100, "3": 300, "2": 120, "1": 80 },
        auth: 0.88,
        summary: "Desempenho e fiabilidade muito elogiados; raras queixas sobre temperaturas sem dissipador.",
        url: "https://www.amazon.es/dp/B0BHJJ9Y77",
      }),
      review("google", {
        raw: 4.7,
        adjusted: 4.6,
        count: 3100,
        dist: { "5": 2400, "4": 480, "3": 130, "2": 60, "1": 30 },
        auth: 0.85,
        summary: "Considerado um dos melhores SSD PCIe 4.0 pela comunidade; boa relação desempenho/consumo.",
        url: "https://www.google.com/search?q=Samsung+990+Pro+review",
      }),
    ],
    themes: [
      theme("Desempenho", "positivo", 520),
      theme("Fiabilidade", "positivo", 300),
      theme("Temperatura", "misto", 140),
      theme("Preço", "positivo", 160),
    ],
    sub: { expert: 92, users: 94, material: 88, value: 90 },
  });

  // ── Smartwatches (cauda longa: specs com variância p/ a IA escolher) ────────
  await seedProduct({
    categoryId: tipoSmartwatch,
    slug: "apple-watch-series-9",
    brand: "Apple",
    model: "Watch Series 9",
    canonicalName: "Apple Watch Series 9 45mm",
    summary: "Smartwatch da Apple com ecrã AMOLED, ECG e GPS. Integração forte no ecossistema Apple.",
    ean: "195949022112",
    matchConfidence: "0.97",
    specs: [
      spec("mostrador", { text: "AMOLED", src: "icecat", conf: 0.9, corr: 2 }),
      spec("gps", { text: "Sim", num: 1, src: "icecat", conf: 0.9, corr: 2 }),
      spec("autonomia", { num: 1, unit: "dias", src: "rtings", conf: 0.85, corr: 2 }),
      spec("ecg", { text: "Sim", num: 1, src: "icecat", conf: 0.9, corr: 2 }),
      spec("sistema", { text: "watchOS", src: "icecat", conf: 0.95, corr: 3 }),
      spec("caixa", { num: 45, unit: "mm", src: "icecat", conf: 0.9, corr: 2 }),
    ],
    offers: [
      offer("Amazon.es", 439.0, { src: "awin_feed", days: 1 }),
      offer("Worten", 449.0, { src: "awin_feed", days: 1 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.7, adjusted: 4.6, count: 5200,
        dist: { "5": 3800, "4": 900, "3": 300, "2": 120, "1": 80 }, auth: 0.84,
        summary: "Ecrã e integração elogiados; autonomia de cerca de um dia é a queixa principal.",
        url: "https://www.amazon.es/dp/B0CHX3QBCH",
      }),
    ],
    themes: [theme("Ecrã", "positivo", 210), theme("Autonomia", "negativo", 180)],
    sub: { expert: 88, users: 90, material: 90, value: 70 },
  });

  await seedProduct({
    categoryId: tipoSmartwatch,
    slug: "samsung-galaxy-watch6",
    brand: "Samsung",
    model: "Galaxy Watch6",
    canonicalName: "Samsung Galaxy Watch6 44mm",
    summary: "Smartwatch com Wear OS, ECG e GPS, com bom equilíbrio entre funcionalidades e preço.",
    ean: "8806095043564",
    matchConfidence: "0.96",
    specs: [
      spec("mostrador", { text: "AMOLED", src: "icecat", conf: 0.9, corr: 2 }),
      spec("gps", { text: "Sim", num: 1, src: "icecat", conf: 0.9, corr: 2 }),
      spec("autonomia", { num: 2, unit: "dias", src: "rtings", conf: 0.85, corr: 2 }),
      spec("ecg", { text: "Sim", num: 1, src: "icecat", conf: 0.9, corr: 2 }),
      spec("sistema", { text: "Wear OS", src: "icecat", conf: 0.95, corr: 3 }),
      spec("caixa", { num: 44, unit: "mm", src: "icecat", conf: 0.9, corr: 2 }),
    ],
    offers: [
      offer("Amazon.es", 319.0, { src: "awin_feed", days: 1 }),
      offer("Worten", 329.0, { src: "awin_feed", days: 2 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.5, adjusted: 4.4, count: 3100,
        dist: { "5": 2000, "4": 700, "3": 250, "2": 90, "1": 60 }, auth: 0.82,
        summary: "Boa relação qualidade/preço; autonomia mediana e ecossistema Android destacados.",
        url: "https://www.amazon.es/dp/B0C7KSF8X4",
      }),
    ],
    themes: [theme("Preço", "positivo", 160), theme("Autonomia", "misto", 120)],
    sub: { expert: 84, users: 85, material: 84, value: 78 },
  });

  await seedProduct({
    categoryId: tipoSmartwatch,
    slug: "garmin-forerunner-265",
    brand: "Garmin",
    model: "Forerunner 265",
    canonicalName: "Garmin Forerunner 265",
    summary: "Relógio de corrida com GPS, ecrã AMOLED e autonomia de vários dias. Foco em desporto.",
    ean: "753759308980",
    matchConfidence: "0.97",
    specs: [
      spec("mostrador", { text: "AMOLED", src: "icecat", conf: 0.9, corr: 2 }),
      spec("gps", { text: "Sim", num: 1, src: "icecat", conf: 0.9, corr: 2 }),
      spec("autonomia", { num: 13, unit: "dias", src: "rtings", conf: 0.85, corr: 2 }),
      spec("ecg", { text: "Não", num: 0, src: "icecat", conf: 0.85, corr: 2 }),
      spec("sistema", { text: "Garmin OS", src: "icecat", conf: 0.95, corr: 3 }),
      spec("caixa", { num: 46, unit: "mm", src: "icecat", conf: 0.9, corr: 2 }),
    ],
    offers: [
      offer("Amazon.es", 479.0, { src: "awin_feed", days: 1 }),
      offer("Worten", 499.0, { src: "awin_feed", days: 2 }),
    ],
    reviews: [
      review("amazon", {
        raw: 4.8, adjusted: 4.7, count: 2400,
        dist: { "5": 1900, "4": 350, "3": 90, "2": 40, "1": 20 }, auth: 0.86,
        summary: "Autonomia e métricas de treino muito elogiadas; menos vocacionado para uso geral.",
        url: "https://www.amazon.es/dp/B0BS1NHy3K",
      }),
    ],
    themes: [theme("Autonomia", "positivo", 240), theme("GPS / treino", "positivo", 200)],
    sub: { expert: 90, users: 92, material: 86, value: 72 },
  });

  // ── Acessórios + compatibilidade (v3) ───────────────────────────────────────
  const banda45 = await seedAccessory({
    categoryId: tipoBandas,
    slug: "banda-desportiva-45mm",
    brand: "Spigen",
    model: "Banda Desportiva 45mm",
    canonicalName: "Spigen Banda Desportiva 45mm",
    summary: "Banda desportiva em silicone para smartwatches de caixa 45 mm.",
    ean: "8809811864521",
    price: 24.99,
    specs: [
      spec("material", { text: "Silicone", src: "icecat", conf: 0.85, corr: 1 }),
      spec("compat_caixa", { num: 45, unit: "mm", src: "icecat", conf: 0.9, corr: 1 }),
    ],
  });
  const banda44 = await seedAccessory({
    categoryId: tipoBandas,
    slug: "banda-pele-44mm",
    brand: "Spigen",
    model: "Banda em Pele 44mm",
    canonicalName: "Spigen Banda em Pele 44mm",
    summary: "Banda em pele para smartwatches de caixa 44 mm.",
    ean: "8809811864538",
    price: 29.99,
    specs: [
      spec("material", { text: "Pele", src: "icecat", conf: 0.85, corr: 1 }),
      spec("compat_caixa", { num: 44, unit: "mm", src: "icecat", conf: 0.9, corr: 1 }),
    ],
  });
  const almofadas = await seedAccessory({
    categoryId: tipoAlmofadas,
    slug: "almofadas-substituicao-overear",
    brand: "Brainwavz",
    model: "Almofadas Over-ear",
    canonicalName: "Brainwavz Almofadas de Substituição Over-ear",
    summary: "Almofadas de substituição em espuma com memória para auscultadores over-ear.",
    ean: "0700604300012",
    price: 19.99,
  });

  // Ligações de compatibilidade (acessório → aparelho-base, golden record ↔ golden record).
  const appleWatch = await pidBySlug("apple-watch-series-9");
  const galaxyWatch = await pidBySlug("samsung-galaxy-watch6");
  const sonyHp = await pidBySlug("sony-wh-1000xm5");
  const boseHp = await pidBySlug("bose-quietcomfort-ultra");
  await db.insert(productCompatibility).values([
    { accessoryId: banda45, baseId: appleWatch, relation: "fits", note: "Caixa de 45 mm", confidence: "0.95" },
    { accessoryId: banda44, baseId: galaxyWatch, relation: "fits", note: "Caixa de 44 mm", confidence: "0.95" },
    { accessoryId: almofadas, baseId: sonyHp, relation: "fits", note: "Almofadas over-ear", confidence: "0.8" },
    { accessoryId: almofadas, baseId: boseHp, relation: "fits", note: "Almofadas over-ear", confidence: "0.8" },
  ]);

  // ── Operação (auditoria / frescura) ───────────────────────────────────────
  await db.insert(ingestionRuns).values([
    {
      sourceId: src.awin_feed,
      kind: "feed_batch",
      status: "ok",
      items: 5,
      startedAt: daysAgo(1),
      finishedAt: daysAgo(1),
      notes: "Importação diária de feeds Awin (preço + imagem + deep link).",
    },
    {
      sourceId: src.icecat,
      kind: "on_demand",
      status: "ok",
      items: 4,
      startedAt: daysAgo(2),
      finishedAt: daysAgo(2),
      notes: "Specs Open Icecat + resolução de identidade por EAN.",
    },
  ]);

  console.log("✓ Seed concluído: 10 produtos (+ acessórios e compatibilidade v3).");
  await closeDb();
}

// ─────────────────────────────  Helpers  ──────────────────────────────────

async function insertCategory(vals: {
  slug: string;
  name: string;
  level: number;
  parentId?: string;
  rankingsEnabled?: boolean;
}): Promise<string> {
  const [row] = await db
    .insert(categories)
    .values({
      slug: vals.slug,
      name: vals.name,
      level: vals.level,
      parentId: vals.parentId ?? null,
      rankingsEnabled: vals.rankingsEnabled ?? false,
    })
    .returning({ id: categories.id });
  return row.id;
}

async function seedAccessory(p: {
  categoryId: string;
  slug: string;
  brand: string;
  model: string;
  canonicalName: string;
  summary: string;
  ean: string;
  price: number;
  specs?: ReturnType<typeof spec>[];
}): Promise<string> {
  const [prod] = await db
    .insert(products)
    .values({
      categoryId: p.categoryId,
      slug: p.slug,
      brand: p.brand,
      model: p.model,
      canonicalName: p.canonicalName,
      summary: p.summary,
      imageUrl: img(p.canonicalName),
      status: "a_venda",
      matchConfidence: "0.9",
      needsReview: false,
    })
    .returning({ id: products.id });
  const productId = prod.id;

  await db.insert(productIdentifiers).values({ productId, idType: "ean", idValue: p.ean });
  await db.insert(offers).values({
    productId,
    storeId: store["Amazon.es"],
    price: String(p.price),
    currency: "EUR",
    urlAffiliate: `https://www.awin1.com/cread.php?awinmid=0&p=${encodeURIComponent(
      `https://example.com/${p.slug}`,
    )}`,
    inStock: true,
    sourceId: src.awin_feed,
    capturedAt: daysAgo(1),
  });
  if (p.specs?.length) {
    await db.insert(specs).values(
      p.specs.map((s) => ({
        productId,
        attributeKey: s.key,
        valueText: s.text ?? null,
        valueNum: s.num !== undefined ? String(s.num) : null,
        unit: s.unit ?? null,
        sourceId: src[s.src],
        confidence: String(s.conf),
        corroborations: s.corr,
      })),
    );
  }
  return productId;
}

async function pidBySlug(slug: string): Promise<string> {
  const [r] = await db.select({ id: products.id }).from(products).where(eq(products.slug, slug)).limit(1);
  return r.id;
}

function attr(
  categoryId: string,
  key: string,
  label: string,
  unit: string | null,
  dataType: string,
  order: number,
  opts: { disc?: boolean; w?: number } = {},
) {
  return {
    categoryId,
    key,
    label,
    unit,
    dataType,
    displayOrder: order,
    isDiscriminant: opts.disc ?? false,
    weightInScore: String(opts.w ?? 0),
  };
}

type SpecInput = {
  text?: string;
  num?: number;
  unit?: string;
  src: string;
  conf: number;
  corr: number;
};
function spec(key: string, v: SpecInput) {
  return { key, ...v };
}

type OfferInput = { src: string; days: number; stock?: boolean };
function offer(storeName: string, price: number, v: OfferInput) {
  return { storeName, price, ...v };
}

type ReviewInput = {
  raw: number;
  adjusted: number;
  count: number;
  dist: Record<string, number>;
  auth: number;
  summary: string;
  url: string;
};
function review(sourceName: string, v: ReviewInput) {
  return { sourceName, ...v };
}

function theme(name: string, polarity: "positivo" | "negativo" | "misto", frequency: number) {
  return { name, polarity, frequency };
}

// Mantemos os mapas fonte/loja acessíveis aos helpers via closures de main().
let src: Record<string, string>;
let store: Record<string, string>;

async function seedProduct(p: {
  categoryId: string;
  slug: string;
  brand: string;
  model: string;
  canonicalName: string;
  summary: string;
  ean: string;
  matchConfidence: string;
  specs: ReturnType<typeof spec>[];
  offers: ReturnType<typeof offer>[];
  reviews: ReturnType<typeof review>[];
  themes: ReturnType<typeof theme>[];
  sub: { expert: number; users: number; material: number; value: number };
}) {
  const [prod] = await db
    .insert(products)
    .values({
      categoryId: p.categoryId,
      slug: p.slug,
      brand: p.brand,
      model: p.model,
      canonicalName: p.canonicalName,
      summary: p.summary,
      imageUrl: img(p.canonicalName),
      status: "a_venda",
      matchConfidence: p.matchConfidence,
      needsReview: false,
    })
    .returning({ id: products.id });
  const productId = prod.id;

  await db.insert(productIdentifiers).values({ productId, idType: "ean", idValue: p.ean });

  await db.insert(specs).values(
    p.specs.map((s) => ({
      productId,
      attributeKey: s.key,
      valueText: s.text ?? null,
      valueNum: s.num !== undefined ? String(s.num) : null,
      unit: s.unit ?? null,
      sourceId: src[s.src],
      confidence: String(s.conf),
      corroborations: s.corr,
    })),
  );

  await db.insert(offers).values(
    p.offers.map((o) => ({
      productId,
      storeId: store[o.storeName],
      price: String(o.price),
      currency: "EUR",
      urlAffiliate: `https://www.awin1.com/cread.php?awinmid=0&p=${encodeURIComponent(
        `https://example.com/${p.slug}`,
      )}`,
      inStock: o.stock ?? true,
      sourceId: src[o.src],
      capturedAt: daysAgo(o.days),
    })),
  );

  await db.insert(reviewsAggregate).values(
    p.reviews.map((r) => ({
      productId,
      sourceId: src[r.sourceName],
      ratingRaw: String(r.raw),
      ratingAdjusted: String(r.adjusted),
      reviewCount: r.count,
      distribution: r.dist,
      authenticityScore: String(r.auth),
      sentimentSummary: r.summary,
      sourceUrl: r.url,
      fetchedAt: daysAgo(2),
    })),
  );

  await db.insert(reviewThemes).values(
    p.themes.map((t) => ({ productId, theme: t.name, polarity: t.polarity, frequency: t.frequency })),
  );

  // DECIFRA Score: calculado a partir dos sub-scores (consistência interna).
  const subs: SubScores = {
    expert: p.sub.expert,
    users: p.sub.users,
    material: p.sub.material,
    value: p.sub.value,
  };
  const overall = computeOverall(subs);
  const reviewSources = p.reviews.length;
  const avgTrust =
    p.reviews.reduce((acc, r) => acc + Number(srcTrust[r.sourceName] ?? 0.6), 0) / reviewSources;
  const confidence = confidenceFromSources(reviewSources + 2, avgTrust); // +2: specs(icecat)+expert(rtings)

  await db.insert(scores).values({
    productId,
    overall: overall !== null ? String(overall) : null,
    subExpert: String(p.sub.expert),
    subUsers: String(p.sub.users),
    subMaterial: String(p.sub.material),
    subValue: String(p.sub.value),
    confidence: String(confidence),
  });

  // Sinais auditáveis (subconjunto rastreável à fonte).
  const cheapest = Math.min(...p.offers.map((o) => o.price));
  await db.insert(scoreSignals).values([
    {
      productId,
      signalType: "expert_review",
      rawValue: String(p.sub.expert),
      normalized: String(p.sub.expert),
      weight: "0.35",
      sourceId: src.rtings,
    },
    {
      productId,
      signalType: "user_rating",
      rawValue: String(p.reviews[0].raw),
      normalized: String(p.sub.users),
      weight: "0.3",
      sourceId: src[p.reviews[0].sourceName],
    },
    {
      productId,
      signalType: "value",
      rawValue: String(cheapest),
      normalized: String(valueIndex(overall, cheapest) ?? 0),
      weight: "0.15",
      sourceId: src.awin_feed,
    },
  ]);
}

const srcTrust: Record<string, number> = {
  rtings: 0.95,
  icecat: 0.9,
  go_upc: 0.7,
  awin_feed: 0.8,
  serpapi: 0.6,
  amazon: 0.65,
  worten: 0.6,
  google: 0.7,
};

async function closeDb() {
  // postgres-js mantém o pool aberto; terminamos o processo explicitamente.
  process.exit(0);
}

// Bootstrap: preencher os mapas globais usados pelos helpers.
main().catch((err) => {
  console.error("✗ Falha no seed:", err);
  process.exit(1);
});
