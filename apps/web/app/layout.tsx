import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lunar South Pole Mission Planner",
  description:
    "Terrain-aware lunar surface sunlight, geometric DTE, and solar input analysis using NASA/JPL data.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

