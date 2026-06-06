import Link from "next/link";
import { getFinderCategories } from "@/lib/finder";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Finder por specs",
  description: "Responde a algumas perguntas e encontra o produto certo, ordenado pelo DECIFRA Score.",
};

export default async function FinderHome() {
  const categories = await getFinderCategories();

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Finder por specs</h1>
      <p className="mt-2 max-w-2xl text-slate-600">
        Não sabes o modelo? Escolhe a categoria, responde a 1–5 perguntas e mostramos os candidatos
        ordenados pelo DECIFRA Score — com o porquê de cada um.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {categories.map((c) => (
          <Link
            key={c.id}
            href={`/finder/${c.slug}`}
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
          >
            <h2 className="text-lg font-semibold text-slate-900 group-hover:text-indigo-600">
              {c.name}
            </h2>
            <p className="mt-1 text-sm text-slate-500">{c.productCount} produto(s)</p>
            <span className="mt-3 inline-block text-sm font-medium text-indigo-600">
              Começar →
            </span>
          </Link>
        ))}
        {categories.length === 0 && (
          <p className="text-slate-500">Ainda não há categorias com perguntas discriminantes.</p>
        )}
      </div>
    </div>
  );
}
