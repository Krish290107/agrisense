import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgriSense | Agricultural Price Forecasting",
  description:
    "Agricultural price forecasting and market decision support. A 14-day college project, beginning with a connected Next.js and FastAPI foundation.",
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
