import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Survival School — Learn. Compete. Certify.",
  description:
    "Survival School is a playful, competitive MCQ-driven learning platform for universities — courses, timed exams, leaderboards, and real certificates.",
  openGraph: {
    title: "Survival School",
    description: "Learn. Compete. Certify. A university learning platform built like a game.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <AuthProvider>
          <NavBar />
          <main className="min-h-screen">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
