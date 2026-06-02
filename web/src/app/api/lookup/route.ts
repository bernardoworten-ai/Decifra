/**
 * API pública de lookup para a extensão de browser e integrações.
 *   GET /api/lookup?ean=4548736132917
 *   GET /api/lookup?q=sony wh-1000xm5
 * CORS aberto (consumida a partir de páginas de lojas).
 */
import { lookupProduct } from "@/lib/lookup";
import { num } from "@/lib/num";

export const dynamic = "force-dynamic";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "*",
};

export function OPTIONS() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const ean = searchParams.get("ean")?.trim() || undefined;
  const q = searchParams.get("q")?.trim() || undefined;

  if (!ean && !q) {
    return Response.json({ error: "Indica ?ean= ou ?q=" }, { status: 400, headers: CORS });
  }

  const result = await lookupProduct({ ean, q });
  if (!result) {
    return Response.json({ found: false }, { headers: CORS });
  }

  const { product, cheapest } = result;
  return Response.json(
    {
      found: true,
      product: {
        slug: product.slug,
        brand: product.brand,
        canonicalName: product.canonicalName,
        imageUrl: product.imageUrl,
        overall: num(product.overall),
        confidence: num(product.confidence),
        url: `${origin}/produto/${product.slug}`,
        cheapest: cheapest
          ? { price: num(cheapest.price), currency: cheapest.currency, store: cheapest.store }
          : null,
      },
    },
    { headers: CORS },
  );
}
