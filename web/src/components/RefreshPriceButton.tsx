"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

/** Botão on-demand de refresh de preço (§3). Chama a route, com skeleton + estado. */
export function RefreshPriceButton({ slug }: { slug: string }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  async function onClick() {
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetch(`/api/price/refresh?slug=${encodeURIComponent(slug)}`, {
        method: "POST",
      });
      const data = await res.json();
      if (!data.ok) {
        setMessage(data.message ?? "Não foi possível atualizar.");
      } else {
        setMessage("verificado agora mesmo");
        startTransition(() => router.refresh()); // re-renderiza a tabela com as offers novas
      }
    } catch {
      setMessage("Erro de rede ao atualizar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {message && <span className="text-[11px] text-slate-400">{message}</span>}
      <button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60"
      >
        <span className={loading ? "animate-spin" : ""} aria-hidden>
          ↻
        </span>
        {loading ? "a atualizar…" : "Atualizar preço"}
      </button>
    </div>
  );
}
