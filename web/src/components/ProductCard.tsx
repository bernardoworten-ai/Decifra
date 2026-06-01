import Link from "next/link";
import type { getProductList } from "@/lib/queries";
import { formatPrice } from "@/lib/format";
import { num } from "@/lib/num";

type ListProduct = Awaited<ReturnType<typeof getProductList>>[number];

/** Card de produto para listagens (home, futuras categorias). */
export function ProductCard({ product }: { product: ListProduct }) {
  const overall = num(product.score?.overall ?? null);
  const cheapest = num(product.offers[0]?.price ?? null);

  return (
    <Link
      href={`/produto/${product.slug}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="relative aspect-square overflow-hidden bg-slate-100">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={product.imageUrl ?? ""}
          alt={product.canonicalName ?? "Produto"}
          className="h-full w-full object-cover transition-transform group-hover:scale-105"
        />
        {overall != null && (
          <span className="absolute left-3 top-3 grid h-11 w-11 place-items-center rounded-full bg-slate-900/90 text-sm font-bold text-white">
            {overall.toFixed(0)}
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-4">
        {product.category && (
          <span className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
            {product.category.name}
          </span>
        )}
        <h3 className="mt-0.5 font-semibold text-slate-900">{product.canonicalName}</h3>
        <div className="mt-auto pt-3 text-sm text-slate-500">
          {cheapest != null ? (
            <>
              desde <span className="font-bold text-slate-900">{formatPrice(cheapest)}</span>
            </>
          ) : (
            "sem preço"
          )}
        </div>
      </div>
    </Link>
  );
}
