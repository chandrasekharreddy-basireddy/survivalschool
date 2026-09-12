import type { Metadata, Viewport } from "next";
import { Inter, Lora } from "next/font/google";
import "./globals.css";

// Self-hosted Inter (no external request → CSP-clean, no layout-shift). Exposed
// as --font-sans, which globals.css and the Tailwind font-sans token consume.
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-inter",
});

// A quiet serif for the rare bit of copy that wants to read as written
// rather than as UI (e.g. the dashboard's daily quote) — exposed as
// --font-serif via globals.css, same self-hosting pattern as Inter above.
const lora = Lora({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500"],
  style: ["italic", "normal"],
  variable: "--font-lora",
});
import { AuthProvider } from "@/lib/auth-context";
import { ToastProvider } from "@/lib/toast";
import { ThemeProvider, NO_FLASH_THEME_SCRIPT } from "@/lib/theme";
import { WARM_BACKEND_SCRIPT } from "@/lib/warm";
import { Sidebar } from "@/components/Sidebar";
import { Footer } from "@/components/Footer";
import { AnalyticsTracker } from "@/components/AnalyticsTracker";
import { GoogleAnalytics } from "@/components/GoogleAnalytics";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://survivalschool.vercel.app"),
  title: {
    default: "Survival School — Learn. Compete. Certify.",
    template: "%s · Survival School",
  },
  description:
    "Survival School is a competitive, MCQ-driven learning platform: AI-conducted weekend exams, live elimination battles, leaderboards, and verifiable certificates.",
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
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${lora.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH_THEME_SCRIPT }} />
        <script dangerouslySetInnerHTML={{ __html: WARM_BACKEND_SCRIPT }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <div className="flex min-h-screen">
                <Sidebar />
                {/* min-w-0 keeps this column from being pushed wider than the
                    viewport by its own content (long tables, code blocks) —
                    a flex item's default min-width is its content's natural
                    width, not 0, which would otherwise force horizontal
                    scroll on the whole page instead of inside the content.
                    pt-14 on mobile makes room for Sidebar's mobile top bar,
                    which is `fixed` (so it can span full width without
                    becoming a sized-to-content flex item of the row this div
                    is also in) and so reserves no space of its own. */}
                <div className="flex min-w-0 flex-1 flex-col pt-14 lg:pt-0">
                  <AnalyticsTracker />
                  <GoogleAnalytics />
                  <ServiceWorkerRegister />
                  <main className="safe-area-x flex-1">{children}</main>
                  <Footer />
                </div>
              </div>
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
