import type { ProductDetail } from "@/lib/queries";
import { formatRating } from "@/lib/format";
import { num } from "@/lib/num";

type Reviews = ProductDetail["product"]["reviews"];
type Themes = ProductDetail["product"]["themes"];

const POLARITY = {
  positivo: "bg-green-50 text-green-700 ring-green-200",
  negativo: "bg-red-50 text-red-700 ring-red-200",
  misto: "bg-slate-100 text-slate-600 ring-slate-200",
} as const;

function aggregate(reviews: Reviews) {
  let weighted = 0;
  let total = 0;
  for (const r of reviews) {
    const adj = num(r.ratingAdjusted) ?? num(r.ratingRaw);
    if (adj != null) {
      weighted += adj * r.reviewCount;
      total += r.reviewCount;
    }
  }
  return { rating: total > 0 ? weighted / total : null, total };
}

/** Reviews por loja: agregados, ajustados por autenticidade, resumo próprio e link. */
export function ReviewsBlock({ reviews, themes }: { reviews: Reviews; themes: Themes }) {
  const agg = aggregate(reviews);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="font-semibold text-slate-900">Reviews por loja</h2>
          <p className="text-xs text-slate-500">
            Mostramos métricas e um resumo próprio — nunca o texto original. Lê na fonte.
          </p>
        </div>
        {agg.rating != null && (
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums text-slate-900">
              {formatRating(agg.rating)}<span className="text-base font-medium text-slate-400">/5</span>
            </div>
            <div className="text-xs text-slate-400">
              ponderado · {agg.total.toLocaleString("pt-PT")} reviews
            </div>
          </div>
        )}
      </div>

      <ul className="divide-y divide-slate-100">
        {reviews.map((r) => {
          const raw = num(r.ratingRaw);
          const adj = num(r.ratingAdjusted);
          const auth = num(r.authenticityScore);
          return (
            <li key={r.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium capitalize text-slate-900">{r.source?.name ?? "—"}</span>
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-bold tabular-nums text-slate-900">{formatRating(adj)}</span>
                  {raw != null && adj != null && Math.abs(raw - adj) >= 0.05 && (
                    <span className="text-xs text-slate-400">
                      (bruto {formatRating(raw)} · ajustado por autenticidade)
                    </span>
                  )}
                  <span className="text-slate-400">· {r.reviewCount.toLocaleString("pt-PT")}</span>
                </div>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-3">
                <Distribution dist={r.distribution} count={r.reviewCount} />
                {auth != null && (
                  <span
                    title="Probabilidade de reviews autênticas (deteção de padrões por IA)."
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600"
                  >
                    Autenticidade {Math.round(auth * 100)}%
                  </span>
                )}
              </div>

              {r.sentimentSummary && (
                <p className="mt-2 text-sm leading-relaxed text-slate-600">{r.sentimentSummary}</p>
              )}
              {r.sourceUrl && (
                <a
                  href={r.sourceUrl}
                  target="_blank"
                  rel="nofollow noopener"
                  className="mt-1 inline-block text-xs font-medium text-indigo-600 hover:underline"
                >
                  Ler as reviews na fonte →
                </a>
              )}
            </li>
          );
        })}
      </ul>

      {themes.length > 0 && (
        <div className="border-t border-slate-100 px-5 py-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Temas mencionados
          </h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {themes.map((t) => (
              <span
                key={t.id}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${
                  POLARITY[t.polarity as keyof typeof POLARITY] ?? POLARITY.misto
                }`}
              >
                {t.theme}
                <span className="opacity-60">· {t.frequency}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function Distribution({ dist, count }: { dist: Record<string, number> | null; count: number }) {
  if (!dist || count <= 0) return null;
  return (
    <div className="flex-1 space-y-0.5">
      {[5, 4, 3, 2, 1].map((star) => {
        const n = dist[String(star)] ?? 0;
        const pct = Math.round((n / count) * 100);
        return (
          <div key={star} className="flex items-center gap-2 text-[11px] text-slate-400">
            <span className="w-3 tabular-nums">{star}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full origin-left rounded-full bg-amber-400"
                style={{ width: `${pct}%`, animation: "grow-bar .5s ease-out" }}
              />
            </div>
            <span className="w-8 text-right tabular-nums">{pct}%</span>
          </div>
        );
      })}
    </div>
  );
}
