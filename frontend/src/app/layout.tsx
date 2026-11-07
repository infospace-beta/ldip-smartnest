import Link from "next/link";
import type { Metadata } from "next";
import { AuthProvider } from "@/contexts/AuthContext";
import "@/styles/smartnest.css";
import "@/styles/onboarding.css";
import "@/styles/workflows.css";

export const metadata: Metadata = {
  title: "SmartNest | Property Workspace",
  description: "Property operations, made clearer.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      {/* Browser extensions may add attributes to body before React hydrates.
          Keep suppression here so mismatches inside the app are still reported. */}
      <body suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
        <footer className="legal-links" aria-label="Legal information"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><a href="mailto:ogonyogad@gmail.com">Contact</a></footer>
      </body>
    </html>
  );
}
