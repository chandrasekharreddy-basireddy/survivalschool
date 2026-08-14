import type { MetadataRoute } from "next";

// Installable app metadata (name, theme colors, start URL). Paired with a
// real build-generated service worker (src/app/sw.ts, see docs/PWA.md) for
// offline app-shell caching and real Web Push (docs/PUSH_NOTIFICATIONS.md).
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Survival School",
    short_name: "Survival School",
    description: "Learn. Compete. Certify. A university learning platform built like a game.",
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#0b0f19",
    theme_color: "#5b5bff",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}
