/**
 * Refresh de preço live, SÓ on-demand (§3). Rate-limit por IP+produto (§10).
 *   POST /api/price/refresh?slug=sony-wh-1000xm5
 */
import { rateLimit } from "@/lib/cache";
import { refreshProductPrice } from "@/lib/priceLive";

export const dynamic = "force-dynamic";

const COOLDOWN_SECONDS = 30;

export async function POST(request: Request) {
  const slug = new URL(request.url).searchParams.get("slug")?.trim();
  if (!slug) {
    return Response.json({ ok: false, message: "slug em falta" }, { status: 400 });
  }

  const ip = (request.headers.get("x-forwarded-for") ?? "anon").split(",")[0].trim();
  const allowed = await rateLimit(`rl:price:${ip}:${slug}`, COOLDOWN_SECONDS);
  if (!allowed) {
    return Response.json(
      { ok: false, message: "Preço verificado há pouco. Tenta novamente daqui a instantes." },
      { status: 429 },
    );
  }

  const result = await refreshProductPrice(slug);
  if (!result.configured) {
    return Response.json({
      ok: false,
      message: "Preço live não configurado (faltam credenciais DataForSEO/Bright Data/SerpApi).",
    });
  }
  if (!result.found) {
    return Response.json({ ok: false, message: "Produto não encontrado." }, { status: 404 });
  }
  return Response.json({ ok: true, offers: result.offers, checkedAt: result.checkedAt });
}
