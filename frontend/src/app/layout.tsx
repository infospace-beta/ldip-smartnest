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
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
