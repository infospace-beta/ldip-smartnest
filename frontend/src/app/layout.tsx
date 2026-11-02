import type { Metadata } from "next";
import { AuthProvider } from "@/contexts/AuthContext";
import "@/styles/smartnest.css";

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
      </body>
    </html>
  );
}
