import Link from "next/link";
import { getTopsCategories } from "@/lib/rankings";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Tops por critério",
  description: "Os melhores produtos por categoria e critério, segundo o DECIFRA Score — auditável e congelado por período.",
};

export default async function TopsHome() {
  const categories = await getTopsCategories();

  return (
    <div className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Tops por critério</h1>
      <p className="mt-2 max-w-2xl text-slate-600">
        Os melhores por categoria, ordenados pelo <strong>DECIFRA Score</strong> e por critério
        (geral, qualidade/preço, mais baratos, topo de gama…). Cada Top é um{" "}
        <strong>snapshot congelado por período</strong> — não reescrevemos o passado.{" "}
        <Link href="/" className="text-indigo-600 hover:underline">
          Ver metodologia
        </Link>
        .
      </p>

      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {categories.map((c) => (
          <Link
            key={c.id}
            href={`/tops/${c.slug}`}
            className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md"
          >
            <h2 className="text-lg font-semibold text-slate-900 group-hover:text-indigo-600">
              {c.name}
            </h2>
            <span className="mt-2 inline-block text-sm font-medium text-indigo-600">
              Ver Tops →
            </span>
          </Link>
        ))}
        {categories.length === 0 && (
          <p className="text-slate-500">
            Ainda não há rankings gerados. Corre o recompute nos workers
            (<code>score-recompute</code>).
          </p>
        )}
      </div>
    </div>
  );
}
