import type { AttributeMeta, ProductDetail } from "@/lib/queries";
import { num } from "@/lib/num";
import { trustSeal } from "@/lib/score";

type Specs = ProductDetail["product"]["specs"];

const DOT = { verde: "bg-green-500", amarelo: "bg-amber-500", vermelho: "bg-red-500" } as const;

function formatValue(
  spec: Specs[number],
  meta: AttributeMeta | undefined,
): string {
  if (spec.valueText) return spec.valueText;
  const n = num(spec.valueNum);
  if (n === null) return "—";
  const unit = spec.unit ?? meta?.unit ?? "";
  return unit ? `${n} ${unit}` : String(n);
}

/** Ficha de specs explicada: valor + fonte + corroboração + confiança por linha. */
export function SpecsTable({ specs, meta }: { specs: Specs; meta: ProductDetail["attributeMeta"] }) {
  const ordered = [...specs].sort((a, b) => {
    const oa = meta.get(a.attributeKey)?.displayOrder ?? 99;
    const ob = meta.get(b.attributeKey)?.displayOrder ?? 99;
    return oa - ob;
  });

  return (
    <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="font-semibold text-slate-900">Ficha técnica explicada</h2>
        <p className="text-xs text-slate-500">
          Cada característica tem fonte e nível de confiança. &quot;Alta&quot; só quando ≥2 fontes coincidem.
        </p>
      </div>
      <ul className="divide-y divide-slate-100">
        {ordered.map((spec) => {
          const m = meta.get(spec.attributeKey);
          const conf = num(spec.confidence);
          const seal = trustSeal(conf);
          return (
            <li key={spec.id} className="grid grid-cols-1 gap-1 px-5 py-3 sm:grid-cols-12 sm:items-center">
              <div className="text-sm text-slate-500 sm:col-span-4">
                {m?.label ?? spec.attributeKey}
              </div>
              <div className="font-medium text-slate-900 sm:col-span-4">
                {formatValue(spec, m)}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs sm:col-span-4 sm:justify-end">
                {spec.source && (
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-600">
                    {spec.source.name}
                  </span>
                )}
                <span className="text-slate-400">
                  {spec.corroborations} {spec.corroborations === 1 ? "fonte" : "fontes"}
                </span>
                <span
                  title={`${seal.label} · ${seal.description}`}
                  className="inline-flex items-center gap-1 text-slate-400"
                >
                  <span className={`h-2 w-2 rounded-full ${DOT[seal.color]}`} aria-hidden />
                  {conf != null ? `${Math.round(conf * 100)}%` : "—"}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
