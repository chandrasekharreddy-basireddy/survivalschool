import type { Config } from "tailwindcss";

/** Every shade below resolves through a CSS custom property (see
 * globals.css :root / .dark), using Tailwind's documented
 * `rgb(var(--x) / <alpha-value>)` pattern. That means every existing
 * `bg-ink-900`, `border-ink-700`, `text-fg-muted`, etc. utility across the
 * whole app repaints automatically when `.dark` is toggled on <html> — no
 * per-page edits needed to support light/dark mode, and opacity modifiers
 * (`bg-ink-900/40`) keep working exactly as before. */
function withOpacity(cssVar: string) {
  return ({ opacityValue }: { opacityValue?: string }) =>
    opacityValue !== undefined ? `rgb(var(${cssVar}) / ${opacityValue})` : `rgb(var(${cssVar}))`;
}

// Tailwind's own shipped types don't model the documented "function value for
// CSS-variable-backed colors" pattern (they type colors as string-only), even
// though the runtime (used by every official Tailwind CSS-variable example)
// fully supports it. `config` is intentionally left untyped here and cast at
// the export instead of annotated at declaration, so TS structurally infers
// this object rather than rejecting the function values against the
// incomplete `Config` type.
const config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Squid Game-inspired red -- verified AA-compliant against both
        // white button text (500/600 as backgrounds) and the near-black
        // dark background (400 used for links/accents on dark surfaces):
        // 500 vs white = 5.2:1, 600 vs white = 6.69:1, 400 vs bg-0 = 5.66:1.
        brand: {
          50: "#fdecec",
          100: "#fad0d1",
          400: "#ff3b3f",
          500: "#d7181f",
          600: "#b8121a",
          700: "#8f0d13",
          900: "#4a0609",
        },
        // Backgrounds, panels, and borders — theme-aware.
        ink: {
          950: withOpacity("--bg-0"),
          900: withOpacity("--bg-1"),
          800: withOpacity("--bg-2"),
          700: withOpacity("--border-c"),
          600: withOpacity("--border-strong"),
        },
        // Foreground text — theme-aware. text-fg / text-fg-muted / text-fg-subtle.
        fg: {
          DEFAULT: withOpacity("--fg-0"),
          muted: withOpacity("--fg-1"),
          subtle: withOpacity("--fg-2"),
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl2: "1.25rem",
      },
      boxShadow: {
        soft: "0 1px 2px rgb(0 0 0 / 0.04), 0 8px 24px -8px rgb(0 0 0 / 0.10)",
        "soft-dark": "0 1px 2px rgb(0 0 0 / 0.3), 0 12px 32px -12px rgb(0 0 0 / 0.55)",
      },
    },
  },
  plugins: [],
};

export default config as unknown as Config;
