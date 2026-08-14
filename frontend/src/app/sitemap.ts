import type { MetadataRoute } from "next";

// Only public, unauthenticated, non-per-user pages belong in a sitemap —
// dashboards, instructor tools, and anything behind auth are deliberately
// excluded (and blocked in robots.txt) since a crawler indexing them serves
// no one and every visit would just bounce to /login anyway.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://survivalschool.example.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const staticPaths = ["/", "/courses", "/leaderboard", "/certificates/verify", "/login", "/register"];
  const lastModified = new Date();
  return staticPaths.map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified,
    changeFrequency: path === "/" ? "weekly" : "daily",
    priority: path === "/" ? 1 : 0.6,
  }));
}
