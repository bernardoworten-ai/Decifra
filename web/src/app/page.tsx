import Link from "next/link";
import { ProductCard } from "@/components/ProductCard";
import { getProductList } from "@/lib/queries";

// Lê da BD a cada pedido (preços/scores frescos).
export const dynamic = "force-dynamic";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const all = await getProductList();
  const query = (q ?? "").trim().toLowerCase();
  const products = query
    ? all.filter((p) =>
        [p.canonicalName, p.brand, p.model, p.category?.name]
          .filter(Boolean)
          .some((s) => s!.toLowerCase().includes(query)),
      )
    : all;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <section className="mb-10">
        <h1 className="max-w-3xl text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          Decide com base em factos, não em opacidade.
        </h1>
        <p className="mt-3 max-w-2xl text-lg text-slate-600">
          Ficha explicada, preço multi-loja e reviews agregadas — cada número com fonte citada e selo
          de confiança. A camada curada (rankings &amp; DECIFRA Score) chega quando há densidade de dados.
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-500">
          <Feature>Fontes citadas + confiança</Feature>
          <Feature>Preço multi-loja</Feature>
          <Feature>Reviews ajustadas por autenticidade</Feature>
          <Feature>Finder por specs</Feature>
        </div>
      </section>

      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-slate-900">
          {query ? `Resultados para “${q}”` : "Produtos"}
        </h2>
        <span className="text-sm text-slate-400">{products.length} produto(s)</span>
      </div>

      {products.length > 0 ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {products.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <p className="text-slate-500">Sem resultados para “{q}”.</p>
          <Link href="/" className="mt-2 inline-block text-sm font-medium text-indigo-600 hover:underline">
            Ver todos os produtos
          </Link>
        </div>
      )}
    </div>
  );
}

function Feature({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-slate-200 bg-white px-3 py-1">{children}</span>
  );
}
