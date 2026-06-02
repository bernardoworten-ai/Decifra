import { setPriceAlert, toggleFavorite } from "@/app/_actions/favorites";
import { currentUserId, getSavedItemFor } from "@/lib/favorites";
import { num } from "@/lib/num";

/** Guardar nos favoritos + definir alerta de preço (server actions, SSR). */
export async function FavoriteBox({ productId }: { productId: string }) {
  const userId = await currentUserId();
  const saved = userId ? await getSavedItemFor(userId, productId) : null;
  const alert = saved ? num(saved.priceAlert) : null;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <form action={toggleFavorite}>
        <input type="hidden" name="productId" value={productId} />
        <button
          type="submit"
          className={`w-full rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${
            saved
              ? "bg-rose-50 text-rose-600 ring-1 ring-rose-200 hover:bg-rose-100"
              : "bg-slate-900 text-white hover:bg-slate-800"
          }`}
        >
          {saved ? "♥ Guardado — remover" : "♡ Guardar nos favoritos"}
        </button>
      </form>

      {saved && (
        <form action={setPriceAlert} className="mt-3">
          <input type="hidden" name="productId" value={productId} />
          <label className="text-xs font-medium text-slate-500">
            Alerta de preço — avisa quando descer abaixo de:
          </label>
          <div className="mt-1 flex gap-2">
            <input
              type="number"
              name="priceAlert"
              step="0.01"
              min="0"
              defaultValue={alert ?? ""}
              placeholder="€"
              className="w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            />
            <button
              type="submit"
              className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700"
            >
              Definir
            </button>
          </div>
        </form>
      )}

      <a href="/favoritos" className="mt-3 inline-block text-xs font-medium text-indigo-600 hover:underline">
        Ver os meus favoritos →
      </a>
    </section>
  );
}
