import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f0ff",
          100: "#e0e0ff",
          400: "#8b8bff",
          500: "#5b5bff",
          600: "#4444e6",
          700: "#3333b3",
          900: "#1a1a5c",
        },
        ink: {
          950: "#0b0f19",
          900: "#12172a",
          800: "#1a2036",
          700: "#232a45",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl2: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
