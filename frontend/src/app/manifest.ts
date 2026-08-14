import type { MetadataRoute } from "next";

// A filled-in manifest (installable app metadata, theme colors) — not a full
// PWA (that's offline support / a service worker, tracked separately as a
// P2/nice-to-have, not implemented here). This alone gets "Add to Home
// Screen" and correct browser chrome theming working.
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
