import Link from "next/link";
import { ProductImage } from "@/components/ProductImage";
import type { FinderCandidate } from "@/lib/finder";

/** Cartão de candidato do finder: produto + score + porquê do match. */
export function FinderResult({ candidate, rank }: { candidate: FinderCandidate; rank: number }) {
  return (
    <Link
      href={`/produto/${candidate.slug}`}
      className="group flex gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="relative h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-slate-100">
        <ProductImage
          src={candidate.imageUrl}
          alt={candidate.canonicalName ?? "Produto"}
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
        />
        <span className="absolute left-1 top-1 rounded-full bg-slate-900/80 px-1.5 text-[10px] font-bold text-white">
          #{rank}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            {candidate.brand && (
              <span className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                {candidate.brand}
              </span>
            )}
            <h3 className="truncate font-semibold text-slate-900">{candidate.canonicalName}</h3>
          </div>
          {candidate.overall != null && (
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-slate-900 text-sm font-bold text-white">
              {candidate.overall.toFixed(0)}
            </span>
          )}
        </div>
        {candidate.why.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {candidate.why.map((w) => (
              <span
                key={w.label}
                className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700 ring-1 ring-green-200"
              >
                <span className="text-green-500" aria-hidden>
                  ✓
                </span>
                {w.label}: {w.value}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}
