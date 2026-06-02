import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { FinderResult } from "@/components/FinderResult";
import {
  getFinderCategoryBySlug,
  getFinderQuestions,
  recordFinderSession,
  runFinder,
} from "@/lib/finder";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const cat = await getFinderCategoryBySlug(slug);
  return { title: cat ? `Finder · ${cat.name}` : "Finder" };
}

const pick = (v: string | string[] | undefined): string | undefined =>
  Array.isArray(v) ? v[0] : v;

function buildHref(
  slug: string,
  answers: Record<string, string>,
  key: string,
  value: string | null,
): string {
  const next = { ...answers };
  if (value === null) delete next[key];
  else next[key] = value;
  const qs = new URLSearchParams(next).toString();
  return qs ? `/finder/${slug}?${qs}` : `/finder/${slug}`;
}

export default async function FinderCategoryPage({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const sp = await searchParams;
  const category = await getFinderCategoryBySlug(slug);
  if (!category) notFound();

  const questions = await getFinderQuestions(category.id);
  if (questions.length === 0) notFound();

  // Respostas válidas = só chaves de perguntas conhecidas.
  const answers: Record<string, string> = {};
  for (const q of questions) {
    const v = pick(sp[q.key]);
    if (v) answers[q.key] = v;
  }

  const { candidates, total, answeredCount } = await runFinder(category.id, answers);

  // Analítica: regista a sessão quando o funil está completo (baixo volume).
  if (answeredCount > 0 && answeredCount === questions.length) {
    await recordFinderSession(category.id, answers, candidates.map((c) => c.id));
  }

  const hasAnswers = answeredCount > 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <nav className="mb-3 flex items-center gap-1 text-sm text-slate-500">
        <Link href="/finder" className="hover:text-slate-700">
          Finder
        </Link>
        <span className="text-slate-300">/</span>
        <span className="text-slate-700">{category.name}</span>
      </nav>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Encontrar {category.name.toLowerCase()}
        </h1>
        {hasAnswers && (
          <Link href={`/finder/${slug}`} className="text-sm font-medium text-indigo-600 hover:underline">
            Limpar filtros
          </Link>
        )}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[320px_1fr]">
        {/* Perguntas discriminantes */}
        <div className="space-y-5">
          {questions.map((q) => {
            const current = answers[q.key];
            return (
              <fieldset key={q.key}>
                <legend className="mb-2 text-sm font-semibold text-slate-700">
                  {q.label}
                  {q.unit ? <span className="font-normal text-slate-400"> ({q.unit})</span> : null}
                </legend>
                <div className="flex flex-wrap gap-2">
                  <Chip href={buildHref(slug, answers, q.key, null)} active={!current}>
                    Indiferente
                  </Chip>
                  {q.options.map((opt) => (
                    <Chip
                      key={opt.value}
                      href={buildHref(slug, answers, q.key, current === opt.value ? null : opt.value)}
                      active={current === opt.value}
                    >
                      {opt.label}
                    </Chip>
                  ))}
                </div>
              </fieldset>
            );
          })}
        </div>

        {/* Resultados */}
        <div>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="font-semibold text-slate-900">
              {candidates.length} {candidates.length === 1 ? "candidato" : "candidatos"}
            </h2>
            <span className="text-sm text-slate-400">de {total} na categoria</span>
          </div>
          {candidates.length > 0 ? (
            <div className="space-y-3">
              {candidates.map((c, i) => (
                <FinderResult key={c.id} candidate={c} rank={i + 1} />
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
              <p className="text-slate-500">Nenhum produto cumpre todos os critérios.</p>
              <Link
                href={`/finder/${slug}`}
                className="mt-2 inline-block text-sm font-medium text-indigo-600 hover:underline"
              >
                Aliviar filtros
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded-full px-3 py-1.5 text-sm font-medium ring-1 transition-colors ${
        active
          ? "bg-indigo-600 text-white ring-indigo-600"
          : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50"
      }`}
    >
      {children}
    </Link>
  );
}
