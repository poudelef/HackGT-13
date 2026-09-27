import "./globals.css";
import type { Metadata } from "next";
import { AppShell } from "@/components/pa/AppShell";

export const metadata: Metadata = {
  title: "ClearPath",
  description: "Help clinicians cut prior-auth delay so patients reach therapy faster.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
