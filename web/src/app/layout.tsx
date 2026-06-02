import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "DECIFRA — Comparador de produtos com confiança verificável",
    template: "%s · DECIFRA",
  },
  description:
    "Fichas explicadas, preço multi-loja e reviews agregadas com fonte citada e selo de confiança. Sem opacidade.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-PT" className={`${geistSans.variable} ${geistMono.variable} h-full`}>
      <body className="flex min-h-full flex-col font-sans">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}

function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-indigo-600 font-mono text-sm font-bold text-white">
            D
          </span>
          <span className="text-lg font-bold tracking-tight text-slate-900">DECIFRA</span>
        </Link>
        <form action="/" className="ml-2 hidden flex-1 sm:block">
          <input
            type="search"
            name="q"
            placeholder="Procurar produto (ex.: Sony WH-1000XM5, SSD NVMe)…"
            className="w-full rounded-full border border-slate-300 bg-slate-50 px-4 py-2 text-sm text-slate-800 outline-none placeholder:text-slate-400 focus:border-indigo-400 focus:bg-white focus:ring-2 focus:ring-indigo-100"
          />
        </form>
        <nav className="ml-auto flex items-center gap-4 text-sm font-medium text-slate-600">
          <Link href="/" className="hover:text-slate-900">
            Produtos
          </Link>
          <Link href="/finder" className="hover:text-slate-900">
            Finder
          </Link>
          <Link href="/tops" className="hover:text-slate-900">
            Tops
          </Link>
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">
            MVP v1
          </span>
        </nav>
      </div>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto max-w-6xl px-4 py-8 text-sm text-slate-500">
        <p className="font-semibold text-slate-700">DECIFRA</p>
        <p className="mt-1 max-w-2xl">
          Camada universal: ficha explicada, preço multi-loja e reviews agregadas, sempre com fonte
          citada e selo de confiança. A IA explica e normaliza — nunca é a fonte primária dos números.
        </p>
        <p className="mt-3 text-xs text-slate-400">
          Divulgação: alguns links para lojas são de afiliado. Podemos receber comissão sem custo
          adicional para ti. Nunca republicamos o texto das reviews — ligamos à fonte original.
        </p>
      </div>
    </footer>
  );
}
