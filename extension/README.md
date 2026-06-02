# DECIFRA — Extensão de browser (MVP)

Quando estás na página de um produto numa loja, a extensão deteta o **EAN** (ou o
título) e mostra o **DECIFRA Score**, o **preço mais baixo** e o **link da ficha**.

## Como funciona
- `content.js` corre na página da loja e extrai o EAN (JSON-LD `gtin13`, microdata,
  ou texto "EAN: …") e o título.
- `popup.js` chama a API pública `GET /api/lookup?ean=…` (ou `?q=título`) e mostra o veredicto.
- A API (em `web/src/app/api/lookup/route.ts`) tem **CORS aberto**.

## Instalar (desenvolvimento)
1. Arranca a app web: `cd web && npm run dev` (fica em `http://localhost:3000`).
2. Em `chrome://extensions`, ativa o **Modo de programador**.
3. **Carregar sem compactar** → escolhe a pasta `extension/`.
4. Abre uma página de produto (ou usa a pesquisa do popup) e clica no ícone DECIFRA.

## Produção
- Em `popup.js`, muda `API_BASE` para o teu domínio (ex.: `https://decifra.pt`).
- Adiciona esse domínio a `host_permissions` no `manifest.json`.

> MVP: deteção por EAN/título e veredicto. Próximos passos: realçar alternativas
> mais baratas/melhor avaliadas na própria página, e ícones da extensão.
