/** Formatação para pt-PT (preço, datas, frescura). */

const priceFmt = new Intl.NumberFormat("pt-PT", {
  style: "currency",
  currency: "EUR",
});

export function formatPrice(value: number | null, currency = "EUR"): string {
  if (value === null) return "—";
  if (currency === "EUR") return priceFmt.format(value);
  return new Intl.NumberFormat("pt-PT", { style: "currency", currency }).format(value);
}

const dateFmt = new Intl.DateTimeFormat("pt-PT", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatDate(date: Date | string | null): string {
  if (!date) return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  return dateFmt.format(d);
}

/** "verificado há 2 dias" — frescura relativa, em português. */
export function freshness(date: Date | string | null): string {
  if (!date) return "frescura desconhecida";
  const d = typeof date === "string" ? new Date(date) : date;
  const diffMs = Date.now() - d.getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "verificado agora mesmo";
  if (minutes < 60) return `verificado há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `verificado há ${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 30) return `verificado há ${days} ${days === 1 ? "dia" : "dias"}`;
  return `verificado a ${formatDate(d)}`;
}

export function formatRating(value: number | null): string {
  if (value === null) return "—";
  return value.toFixed(1).replace(".", ",");
}
