import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

// Fonte principal do site.
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FieldEye — Análise de futebol por vídeo",
  description:
    "Rastreamento de jogadores, velocidade, distância e heatmap a partir do seu próprio vídeo.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-ink text-fg">{children}</body>
    </html>
  );
}
