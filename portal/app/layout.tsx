import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Life Shield — Credit Repair Portal",
  description: "AI-powered credit repair platform. FCRA & CROA compliant.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f8f9fb]">{children}</body>
    </html>
  );
}
