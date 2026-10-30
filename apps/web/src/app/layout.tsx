import "@fontsource/instrument-sans/400.css";
import "@fontsource/instrument-sans/500.css";
import "@fontsource/instrument-sans/600.css";
import "@fontsource/instrument-serif/400.css";
import "./globals.css";

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Launchpad",
  description:
    "Freshness-first job discovery for new-graduate software engineers.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
