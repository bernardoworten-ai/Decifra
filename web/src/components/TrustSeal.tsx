import { trustSeal } from "@/lib/score";

const STYLES = {
  verde: "bg-green-50 text-green-700 ring-green-200",
  amarelo: "bg-amber-50 text-amber-700 ring-amber-200",
  vermelho: "bg-red-50 text-red-700 ring-red-200",
} as const;

const DOT = {
  verde: "bg-green-500",
  amarelo: "bg-amber-500",
  vermelho: "bg-red-500",
} as const;

/** Selo de confiança verde/amarelo/vermelho (mapeia a confiança 0-1). */
export function TrustSeal({
  confidence,
  sourceCount,
  className = "",
}: {
  confidence: number | null;
  sourceCount?: number;
  className?: string;
}) {
  const seal = trustSeal(confidence);
  const pct = confidence != null ? Math.round(confidence * 100) : null;
  return (
    <span
      title={seal.description}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${STYLES[seal.color]} ${className}`}
    >
      <span className={`h-2 w-2 rounded-full ${DOT[seal.color]}`} aria-hidden />
      {seal.label}
      {pct != null ? ` · ${pct}%` : ""}
      {sourceCount ? ` · ${sourceCount} fontes` : ""}
    </span>
  );
}
