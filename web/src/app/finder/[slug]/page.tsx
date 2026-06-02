import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { FinderResult } from "@/components/FinderResult";
import {
  getBaseProduct,
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
  fits?: string,
): string {
  const next = { ...answers };
  if (value === null) delete next[key];
  else next[key] = value;
  const params = new URLSearchParams(next);
  if (fits) params.set("fits", fits);
  const qs = params.toString();
  return qs ? `/finder/${slug}?${qs}` : `/finder/${slug}`;
}

export default async function FinderCategoryPage({ params, searchParams }: PageProps) {
  const { slug } = await params;
  const sp = await searchParams;
  const category = await getFinderCategoryBySlug(slug);
  if (!category) notFound();

  const fits = pick(sp.fits);
  const base = fits ? await getBaseProduct(fits) : null;
  const questions = await getFinderQuestions(category.id);
  // Só 404 se não houver perguntas nem filtro de compatibilidade.
  if (questions.length === 0 && !base) notFound();

  const answers: Record<string, string> = {};
  for (const q of questions) {
    const v = pick(sp[q.key]);
    if (v) answers[q.key] = v;
  }

  const { candidates, total, answeredCount } = await runFinder(category.id, answers, base?.id);

  if (answeredCount > 0 && answeredCount === questions.length) {
    await recordFinderSession(category.id, answers, candidates.map((c) => c.id));
  }

  const hasAnswers = answeredCount > 0;
  const clearHref = fits ? `/finder/${slug}?fits=${fits}` : `/finder/${slug}`;

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
          <Link href={clearHref} className="text-sm font-medium text-indigo-600 hover:underline">
            Limpar filtros
          </Link>
        )}
      </div>

      {base && (
        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl bg-indigo-50 px-4 py-2 text-sm text-indigo-800 ring-1 ring-indigo-100">
          <span>
            A mostrar apenas compatíveis com <strong>{base.canonicalName}</strong>.
          </span>
          <Link href={`/finder/${slug}`} className="font-medium underline">
            ver todos
          </Link>
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-8 lg:grid-cols-[320px_1fr]">
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
                  <Chip href={buildHref(slug, answers, q.key, null, fits)} active={!current}>
                    Indiferente
                  </Chip>
                  {q.options.map((opt) => (
                    <Chip
                      key={opt.value}
                      href={buildHref(
                        slug,
                        answers,
                        q.key,
                        current === opt.value ? null : opt.value,
                        fits,
                      )}
                      active={current === opt.value}
                    >
                      {opt.label}
                    </Chip>
                  ))}
                </div>
              </fieldset>
            );
          })}
          {questions.length === 0 && (
            <p className="text-sm text-slate-400">Sem perguntas — filtrado por compatibilidade.</p>
          )}
        </div>

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
              <Link href={clearHref} className="mt-2 inline-block text-sm font-medium text-indigo-600 hover:underline">
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
