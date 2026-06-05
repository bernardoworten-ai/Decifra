/** Aquece o servidor antes dos testes, para o 1.º goto não pagar o cold-start. */
async function globalSetup() {
  const base = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
  const deadline = Date.now() + 90_000;
  for (const path of ["/", "/api/lookup?q=warmup"]) {
    while (Date.now() < deadline) {
      try {
        const res = await fetch(base + path);
        await res.text(); // força o SSR completo
        if (res.ok) break;
      } catch {
        // servidor ainda a arrancar
      }
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
}

export default globalSetup;
