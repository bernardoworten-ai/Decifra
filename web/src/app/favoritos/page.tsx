import Link from "next/link";
import { removeFavorite, setEmail, setPriceAlert } from "@/app/_actions/favorites";
import { currentUserId, getSavedItems, getUserEmail } from "@/lib/favorites";
import { formatPrice } from "@/lib/format";
import { num } from "@/lib/num";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Os meus favoritos",
  description: "Produtos guardados e alertas de preço.",
};

export default async function FavoritesPage() {
  const userId = await currentUserId();
  const items = userId ? await getSavedItems(userId) : [];
  const email = userId ? await getUserEmail(userId) : null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-bold tracking-tight text-slate-900">Os meus favoritos</h1>

      {items.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <p className="text-slate-500">Ainda não guardaste nenhum produto.</p>
          <Link href="/" className="mt-2 inline-block text-sm font-medium text-indigo-600 hover:underline">
            Explorar produtos
          </Link>
        </div>
      ) : (
        <>
          {/* Email para receber alertas */}
          <form
            action={setEmail}
            className="mt-6 flex flex-wrap items-end gap-2 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div className="flex-1">
              <label className="text-xs font-medium text-slate-500">
                Email para alertas de preço (opcional)
              </label>
              <input
                type="email"
                name="email"
                defaultValue={email ?? ""}
                placeholder="o-teu@email.pt"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
              />
            </div>
            <button
              type="submit"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
            >
              Guardar email
            </button>
          </form>

          <ul className="mt-6 space-y-3">
            {items.map((it) => {
              const cheapest = num(it.cheapest);
              const alert = num(it.priceAlert);
              const overall = num(it.overall);
              const triggered = alert !== null && cheapest !== null && cheapest <= alert;
              return (
                <li
                  key={it.savedId}
                  className="flex flex-wrap gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="h-20 w-20 shrink-0 overflow-hidden rounded-xl bg-slate-100">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={it.imageUrl ?? ""}
                      alt={it.canonicalName ?? "Produto"}
                      className="h-full w-full object-cover"
                    />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/produto/${it.slug}`}
                        className="font-semibold text-slate-900 hover:text-indigo-600"
                      >
                        {it.canonicalName}
                      </Link>
                      <div className="text-right">
                        <div className="font-bold tabular-nums text-slate-900">
                          {formatPrice(cheapest)}
                        </div>
                        {overall !== null && (
                          <div className="text-xs text-slate-400">Score {overall.toFixed(0)}/100</div>
                        )}
                      </div>
                    </div>

                    {triggered && (
                      <p className="mt-1 inline-block rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                        ✓ Alerta: já está abaixo de {formatPrice(alert)}
                      </p>
                    )}

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <form action={setPriceAlert} className="flex items-center gap-1">
                        <input type="hidden" name="productId" value={it.productId} />
                        <span className="text-xs text-slate-500">Alerta &lt;</span>
                        <input
                          type="number"
                          name="priceAlert"
                          step="0.01"
                          min="0"
                          defaultValue={alert ?? ""}
                          placeholder="€"
                          className="w-24 rounded-lg border border-slate-300 px-2 py-1 text-sm outline-none focus:border-indigo-400"
                        />
                        <button
                          type="submit"
                          className="rounded-lg bg-indigo-600 px-2 py-1 text-xs font-semibold text-white hover:bg-indigo-700"
                        >
                          Definir
                        </button>
                      </form>
                      <form action={removeFavorite}>
                        <input type="hidden" name="productId" value={it.productId} />
                        <button
                          type="submit"
                          className="rounded-lg px-2 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50"
                        >
                          Remover
                        </button>
                      </form>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-xs text-slate-400">
            Os alertas são verificados periodicamente (worker <code>check-alerts</code>); o envio por
            email entra quando ligarmos o fornecedor de email.
          </p>
        </>
      )}
    </div>
  );
}
