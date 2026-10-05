import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgriSense | Market Forecast Dashboard",
  description:
    "View Gujarat mandi price records and estimate the next reported market price using verified forecasting policies.",
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
