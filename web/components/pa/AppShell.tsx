"use client";

import { usePathname } from "next/navigation";
import { AppSidebar } from "@/components/pa/AppSidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const landing = pathname === "/";
  return (
    <div className={`app-shell${landing ? " landing-mode" : ""}`}>
      <AppSidebar />
      <div className="workspace">{children}</div>
    </div>
  );
}
