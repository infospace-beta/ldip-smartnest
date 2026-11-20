import Link from "next/link";
import type { Metadata } from "next";
import { AuthProvider } from "@/contexts/AuthContext";
import "@/styles/smartnest.css";
import "@/styles/onboarding.css";
import "@/styles/workflows.css";
import "@/styles/signin.css";

export const metadata: Metadata = {
  title: "SmartNest | Property Workspace",
  description: "Property operations, made clearer.",
  robots: {index:false,follow:false},
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/* Browser extensions may add attributes to html and body before hydration.
          Suppress only those root attributes; app content still reports mismatches. */}
      <body suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
        <footer className="legal-links" aria-label="Legal information"><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link><a href="mailto:ogonyogad@gmail.com">Contact</a></footer>
      </body>
    </html>
  );
}
