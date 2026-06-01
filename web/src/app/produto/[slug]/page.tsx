import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PriceTable } from "@/components/PriceTable";
import { ReviewsBlock } from "@/components/ReviewsBlock";
import { ScorePanel } from "@/components/ScorePanel";
import { SpecsTable } from "@/components/SpecsTable";
import { getProductDetail } from "@/lib/queries";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const data = await getProductDetail(slug);
  if (!data) return { title: "Produto não encontrado" };
  const { product } = data;
  return {
    title: product.canonicalName ?? "Produto",
    description: product.summary ?? undefined,
  };
}

function distinctSources(data: NonNullable<Awaited<ReturnType<typeof getProductDetail>>>): number {
  const ids = new Set<string>();
  for (const s of data.product.specs) if (s.sourceId) ids.add(s.sourceId);
  for (const r of data.product.reviews) if (r.sourceId) ids.add(r.sourceId);
  for (const sg of data.product.signals) if (sg.sourceId) ids.add(sg.sourceId);
  return ids.size;
}

export default async function ProductPage({ params }: PageProps) {
  const { slug } = await params;
  const data = await getProductDetail(slug);
  if (!data) notFound();

  const { product, attributeMeta } = data;
  const sourceCount = distinctSources(data);
  const ean = product.identifiers.find((i) => i.idType === "ean")?.idValue;

  // Migalhas: setor > categoria > aparelho.
  const crumbs = [
    product.category?.parent?.parent,
    product.category?.parent,
    product.category,
  ].filter((c): c is NonNullable<typeof c> => Boolean(c));

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <nav className="mb-4 flex flex-wrap items-center gap-1 text-sm text-slate-500">
        <Link href="/" className="hover:text-slate-700">
          Início
        </Link>
        {crumbs.map((c) => (
          <span key={c.id} className="flex items-center gap-1">
            <span className="text-slate-300">/</span>
            <Link href={`/?q=${encodeURIComponent(c.name)}`} className="hover:text-slate-700">
              {c.name}
            </Link>
          </span>
        ))}
      </nav>

      {/* Cabeçalho */}
      <header className="mb-6 grid grid-cols-1 gap-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-[220px_1fr]">
        <div className="aspect-square overflow-hidden rounded-xl bg-slate-100">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={product.imageUrl ?? ""}
            alt={product.canonicalName ?? "Produto"}
            className="h-full w-full object-cover"
          />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-indigo-600">
              {product.brand}
            </span>
            {product.status !== "a_venda" && (
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
                {product.status}
              </span>
            )}
          </div>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
            {product.canonicalName}
          </h1>
          {product.summary && (
            <p className="mt-2 max-w-2xl text-slate-600">{product.summary}</p>
          )}
          <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
            {product.model && (
              <div>
                <dt className="inline font-medium text-slate-500">Modelo: </dt>
                <dd className="inline">{product.model}</dd>
              </div>
            )}
            {ean && (
              <div>
                <dt className="inline font-medium text-slate-500">EAN: </dt>
                <dd className="inline tabular-nums">{ean}</dd>
              </div>
            )}
          </dl>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <SpecsTable specs={product.specs} meta={attributeMeta} />
          <ReviewsBlock reviews={product.reviews} themes={product.themes} />
        </div>
        <div className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <ScorePanel score={product.score} sourceCount={sourceCount} />
          <PriceTable offers={product.offers} />
        </div>
      </div>
    </div>
  );
}
