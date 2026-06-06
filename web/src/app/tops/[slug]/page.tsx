import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { formatPrice, monthLabel } from "@/lib/format";
import { num } from "@/lib/num";
import { getCategoryTops, type CriterionUnit } from "@/lib/rankings";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const data = await getCategoryTops(slug);
  return { title: data?.category ? `Tops · ${data.category.name}` : "Tops" };
}

function formatMetric(unit: CriterionUnit, value: number | null): string {
  if (value === null) return "—";
  if (unit === "price") return formatPrice(value);
  if (unit === "value") return `${value.toFixed(1)} pts/100€`;
  return `${Math.round(value)}/100`;
}

export default async function CategoryTopsPage({ params }: PageProps) {
  const { slug } = await params;
  const data = await getCategoryTops(slug);
  if (!data) notFound();

  const { category, period, groups } = data;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <nav className="mb-3 flex items-center gap-1 text-sm text-slate-500">
        <Link href="/tops" className="hover:text-slate-700">
          Tops
        </Link>
        <span className="text-slate-300">/</span>
        <span className="text-slate-700">{category.name}</span>
      </nav>

      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        Tops de {category.name.toLowerCase()}
      </h1>
      {period && (
        <p className="mt-1 text-sm text-slate-500">
          Snapshot de <strong>{monthLabel(period)}</strong> — congelado para este período.
        </p>
      )}

      {groups.length === 0 ? (
        <p className="mt-8 text-slate-500">Ainda não há rankings para esta categoria.</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          {groups.map((g) => (
            <section key={g.key} className="rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="font-semibold text-slate-900">{g.label}</h2>
                <p className="text-xs text-slate-400">{g.hint}</p>
              </div>
              <ol className="divide-y divide-slate-100">
                {g.items.map((item) => (
                  <li key={item.id} className="flex gap-3 px-5 py-3">
                    <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-slate-900 text-xs font-bold text-white">
                      {item.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-2">
                        <Link
                          href={`/produto/${item.product.slug}`}
                          className="truncate font-medium text-slate-900 hover:text-indigo-600"
                        >
                          {item.product.canonicalName}
                        </Link>
                        <span className="shrink-0 text-sm font-bold tabular-nums text-slate-700">
                          {formatMetric(g.unit, num(item.scoreAtTime))}
                        </span>
                      </div>
                      {item.rationale && (
                        <p className="mt-0.5 text-xs leading-relaxed text-slate-500">
                          {item.rationale}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}

      <p className="mt-6 text-xs text-slate-400">
        Os Tops derivam do DECIFRA Score (compósito e auditável). Cada posição traz o porquê,
        ancorado nos sinais; os snapshots não recalculam o passado.
      </p>
    </div>
  );
}
