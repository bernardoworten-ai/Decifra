import type { ProductDetail } from "@/lib/queries";
import { formatPrice, freshness } from "@/lib/format";
import { num } from "@/lib/num";

type Offers = ProductDetail["product"]["offers"];

/** Comparação de preço multi-loja. Realça o melhor preço em stock. */
export function PriceTable({ offers }: { offers: Offers }) {
  const inStock = offers.filter((o) => o.inStock);
  const cheapestId = inStock.length
    ? inStock.reduce((min, o) => (num(o.price)! < num(min.price)! ? o : min)).id
    : null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <h2 className="font-semibold text-slate-900">Preço nas lojas</h2>
        <span className="text-xs text-slate-400">
          via feeds · atualização live por pedido (fase seguinte)
        </span>
      </div>
      <ul className="divide-y divide-slate-100">
        {offers.map((o) => {
          const isBest = o.id === cheapestId;
          return (
            <li
              key={o.id}
              className={`flex flex-wrap items-center gap-3 px-5 py-3 ${isBest ? "bg-green-50/60" : ""}`}
            >
              <div className="min-w-32 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-900">{o.store?.name ?? "—"}</span>
                  {o.store?.country && (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                      {o.store.country}
                    </span>
                  )}
                  {isBest && (
                    <span className="rounded-full bg-green-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                      Melhor preço
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {freshness(o.capturedAt)}
                  {o.inStock ? "" : " · sem stock"}
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold tabular-nums text-slate-900">
                  {formatPrice(num(o.price), o.currency)}
                </div>
              </div>
              <a
                href={o.urlAffiliate ?? "#"}
                target="_blank"
                rel="sponsored nofollow noopener"
                className={`rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
                  o.inStock
                    ? "bg-indigo-600 text-white hover:bg-indigo-700"
                    : "pointer-events-none bg-slate-100 text-slate-400"
                }`}
              >
                Ver na loja
              </a>
            </li>
          );
        })}
        {offers.length === 0 && (
          <li className="px-5 py-6 text-center text-sm text-slate-400">
            Ainda sem ofertas registadas para este produto.
          </li>
        )}
      </ul>
      <p className="border-t border-slate-100 px-5 py-3 text-[11px] text-slate-400">
        Links de afiliado: podemos receber comissão sem custo adicional para ti.
      </p>
    </section>
  );
}
