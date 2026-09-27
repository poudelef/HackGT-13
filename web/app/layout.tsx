import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "ClearPath PA", description: "Prior authorization with a human at every gate." };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500&family=Source+Sans+3:wght@400;500&display=swap" rel="stylesheet" />
      </head>
      <body>
        <nav className="nav">
          <Link href="/" className="brand">ClearPath</Link>
          <Link href="/admin/policies">Policy library</Link>
          <Link href="/doctor">Order</Link>
          <Link href="/insurer">Insurer review</Link>
          <span className="muted" style={{ marginLeft: "auto" }}>A human decides every step</span>
        </nav>
        <div className="shell">{children}</div>
      </body>
    </html>
  );
}
