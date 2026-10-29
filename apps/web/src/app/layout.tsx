import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export const metadata: Metadata = { title: { default: "ReleaseRadar", template: "%s · ReleaseRadar" }, description: "Build and deploy status across your GitHub repositories." };

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  await headers(); // opts every page into dynamic rendering so the per-request CSP nonce can be applied
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
