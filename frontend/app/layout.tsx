import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BhoomiLens — Land-record reconciliation",
  description: "Evidence-first land-record consistency screening for India.",
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
