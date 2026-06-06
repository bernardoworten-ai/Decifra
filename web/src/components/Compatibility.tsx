import Link from "next/link";
import type { ProductDetail } from "@/lib/queries";
import { formatPrice } from "@/lib/format";
import { num } from "@/lib/num";

type Product = ProductDetail["product"];

function cheapestOf(offers: { price: string | null; inStock: boolean }[]): number | null {
  const prices = offers
    .filter((o) => o.inStock)
    .map((o) => num(o.price))
    .filter((n): n is number => n !== null);
  return prices.length ? Math.min(...prices) : null;
}

/** Acessórios compatíveis (se for um aparelho) e/ou "Compatível com" (se for acessório). */
export function Compatibility({ product }: { product: Product }) {
  const accessories = product.accessories;
  const bases = product.compatibleWith;
  if (accessories.length === 0 && bases.length === 0) return null;

  const cats = new Map<string, string>();
  for (const a of accessories) {
    if (a.accessory.category) cats.set(a.accessory.category.slug, a.accessory.category.name);
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      {accessories.length > 0 && (
        <div className="border-b border-slate-100 px-5 py-4 last:border-b-0">
          <h2 className="font-semibold text-slate-900">Acessórios compatíveis</h2>
          <p className="text-xs text-slate-500">Encaixam neste produto (compatibilidade verificada).</p>
          <ul className="mt-3 divide-y divide-slate-100">
            {accessories.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <Link
                    href={`/produto/${a.accessory.slug}`}
                    className="font-medium text-slate-900 hover:text-indigo-600"
                  >
                    {a.accessory.canonicalName}
                  </Link>
                  {a.note && <span className="ml-2 text-xs text-slate-400">{a.note}</span>}
                </div>
                <span className="shrink-0 text-sm font-semibold tabular-nums text-slate-700">
                  {formatPrice(cheapestOf(a.accessory.offers))}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap gap-3">
            {[...cats].map(([slug, name]) => (
              <Link
                key={slug}
                href={`/finder/${slug}?fits=${product.slug}`}
                className="text-xs font-medium text-indigo-600 hover:underline"
              >
                Explorar {name.toLowerCase()} compatíveis no finder →
              </Link>
            ))}
          </div>
        </div>
      )}

      {bases.length > 0 && (
        <div className="px-5 py-4">
          <h2 className="font-semibold text-slate-900">Compatível com</h2>
          <ul className="mt-3 flex flex-wrap gap-2">
            {bases.map((b) => (
              <li key={b.id}>
                <Link
                  href={`/produto/${b.base.slug}`}
                  className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-200"
                >
                  {b.base.canonicalName}
                  {b.note ? <span className="text-xs text-slate-400">· {b.note}</span> : null}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
