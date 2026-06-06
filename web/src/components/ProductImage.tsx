/** Imagem de produto com fallback — evita <img src=""> e adia o carregamento. */
export function ProductImage({
  src,
  alt,
  className,
}: {
  src: string | null | undefined;
  alt: string;
  className?: string;
}) {
  if (!src) {
    return (
      <div className={`grid place-items-center bg-slate-100 text-slate-300 ${className ?? ""}`}>
        <span className="text-3xl font-bold">{(alt || "?").charAt(0).toUpperCase()}</span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={alt} loading="lazy" className={className} />
  );
}
