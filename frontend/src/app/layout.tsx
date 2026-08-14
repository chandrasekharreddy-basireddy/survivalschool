import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/lib/toast";
import { ThemeProvider, NO_FLASH_THEME_SCRIPT } from "@/lib/theme";
import { NavBar } from "@/components/NavBar";
import { AnalyticsTracker } from "@/components/AnalyticsTracker";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";

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
      <head>
        {/* Must run before first paint to avoid a flash of the wrong theme —
            see NO_FLASH_THEME_SCRIPT's own comment in lib/theme.tsx for why
            this can't just be a useEffect in ThemeProvider. */}
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <NavBar />
              <AnalyticsTracker />
              <ServiceWorkerRegister />
              <main className="min-h-screen">{children}</main>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
