import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width", initialScale: 1, viewportFit: "cover", themeColor: "#080b10",
};

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
