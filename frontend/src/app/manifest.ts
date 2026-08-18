import type { MetadataRoute } from "next";

// Installable app metadata. Paired with the build-generated service worker
// (src/app/sw.ts, see docs/PWA.md) for offline app-shell caching and real Web
// Push (docs/PUSH_NOTIFICATIONS.md). Maskable + any-purpose icons are provided
// so Android/Chrome install prompts render a crisp adaptive icon.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Survival School",
    short_name: "Survival",
    description:
      "Learn. Compete. Certify. Courses, AI-conducted weekend exams, live leaderboards, and verifiable certificates.",
    id: "/",
    start_url: "/dashboard",
    scope: "/",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#08090f",
    theme_color: "#08090f",
    categories: ["education", "productivity"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Dashboard", url: "/dashboard" },
      { name: "Courses", url: "/courses" },
      { name: "Leaderboard", url: "/leaderboard" },
    ],
  };
}
