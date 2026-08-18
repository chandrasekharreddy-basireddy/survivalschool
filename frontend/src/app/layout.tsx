import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Self-hosted Inter (no external request → CSP-clean, no layout-shift). Exposed
// as --font-sans, which globals.css and the Tailwind font-sans token consume.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
});
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/lib/toast";
import { ThemeProvider, NO_FLASH_THEME_SCRIPT } from "@/lib/theme";
import { NavBar } from "@/components/NavBar";
import { AnalyticsTracker } from "@/components/AnalyticsTracker";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";

export const metadata: Metadata = {
  title: {
    default: "Survival School — Learn. Compete. Certify.",
    template: "%s · Survival School",
  },
  description:
    "Survival School is a competitive, MCQ-driven learning platform: courses, AI-conducted weekend exams, live leaderboards, and verifiable certificates.",
  applicationName: "Survival School",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Survival School",
  },
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    title: "Survival School",
    description: "Learn. Compete. Certify. A university learning platform built like a game.",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8f9fb" },
    { media: "(prefers-color-scheme: dark)", color: "#08090f" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <NavBar />
              <AnalyticsTracker />
              <ServiceWorkerRegister />
              <main className="safe-area-x">{children}</main>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
