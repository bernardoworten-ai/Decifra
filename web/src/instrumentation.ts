/**
 * Observabilidade (§7): Sentry server-side, só se SENTRY_DSN existir (graceful).
 * Captura erros de routes/RSC via onRequestError. Sem DSN é no-op.
 */
export async function register() {
  if (process.env.SENTRY_DSN && process.env.NEXT_RUNTIME === "nodejs") {
    const Sentry = await import("@sentry/node");
    Sentry.init({
      dsn: process.env.SENTRY_DSN,
      tracesSampleRate: 0,
      environment: process.env.NODE_ENV,
    });
  }
}

export async function onRequestError(error: unknown) {
  if (!process.env.SENTRY_DSN || process.env.NEXT_RUNTIME !== "nodejs") return;
  const Sentry = await import("@sentry/node");
  Sentry.captureException(error);
}
