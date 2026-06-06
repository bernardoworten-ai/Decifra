import type { ProductDetail } from "@/lib/queries";
import { num, numOr } from "@/lib/num";
import { TrustSeal } from "./TrustSeal";

type Score = ProductDetail["product"]["score"];

const SUBS: { key: "subExpert" | "subUsers" | "subMaterial" | "subValue"; label: string }[] = [
  { key: "subExpert", label: "Especialistas" },
  { key: "subUsers", label: "Utilizadores" },
  { key: "subMaterial", label: "Qualidade material" },
  { key: "subValue", label: "Relação qualidade/preço" },
];

/** Painel do DECIFRA Score: overall + sub-scores + selo de confiança. */
export function ScorePanel({ score, sourceCount }: { score: Score; sourceCount: number }) {
  const overall = num(score?.overall ?? null);
  const confidence = num(score?.confidence ?? null);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            DECIFRA Score
          </h2>
          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-4xl font-bold tabular-nums text-slate-900">
              {overall != null ? overall.toFixed(0) : "—"}
            </span>
            <span className="text-lg font-medium text-slate-400">/100</span>
          </div>
        </div>
        <TrustSeal confidence={confidence} sourceCount={sourceCount} />
      </div>

      <dl className="mt-4 space-y-3">
        {SUBS.map(({ key, label }) => {
          const v = num(score?.[key] ?? null);
          return (
            <div key={key}>
              <div className="flex items-center justify-between text-sm">
                <dt className="text-slate-600">{label}</dt>
                <dd className="font-semibold tabular-nums text-slate-800">
                  {v != null ? v.toFixed(0) : "—"}
                </dd>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full origin-left rounded-full bg-indigo-500"
                  style={{ width: `${numOr(v, 0)}%`, animation: "grow-bar .5s ease-out" }}
                />
              </div>
            </div>
          );
        })}
      </dl>

      <p className="mt-4 text-xs leading-relaxed text-slate-400">
        Compósito e auditável: agrega veredictos de especialistas, notas ajustadas por autenticidade,
        qualidade material e preço. Sem testes físicos — estimativa baseada em {sourceCount} fontes,
        cada sinal rastreável à origem.
      </p>
    </section>
  );
}
