/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // --- core theme tokens (now light, used by the project detail view) ---
        base: "#faf7f0",
        panel: "#ffffff",
        surface: "rgba(255,255,255,0.7)",
        emerald: "#10b981",
        blue: "#3b82f6",
        violet: "#8b5cf6",
        rose: "#f43f5e",
        amber: "#f59e0b",
        muted: "#64748b",
        ink: "#1f2a24",

        // --- new earthy palette (landing page + project card dashboard, light theme) ---
        silt: "#161209",       // dark scrim tone (hero overlay only)
        bark: "#241c12",       // dark scrim secondary tone
        canopy: "#2f4a3c",     // deep mangrove green (hero accents)
        moss: "#4f7a45",       // living green accent, tuned for contrast on white
        clay: "#c1682f",       // warm terracotta accent
        tide: "#4a7c82",       // teal, water/carbon accent
        forest: "#1f3327",     // near-black green — headings/body text on light bg
        forestmuted: "#5b6b5e",// muted body text on light bg
        sand: "#e9dfc7",       // warm off-white (kept for hero-on-photo contexts)
        sandmuted: "#b8ad93",  // muted warm text (kept for hero-on-photo contexts)
      },
      fontFamily: {
        display: ["Outfit", "sans-serif"],
        body: ["Plus Jakarta Sans", "sans-serif"],
      },
      backdropBlur: { xs: "2px" },
      keyframes: {
        fadeUp: {
          "0%": { opacity: 0, transform: "translateY(16px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        fadeIn: {
          "0%": { opacity: 0 },
          "100%": { opacity: 1 },
        },
      },
      animation: {
        fadeUp: "fadeUp 0.8s ease-out forwards",
        fadeIn: "fadeIn 1.2s ease-out forwards",
      },
    },
  },
  plugins: [],
};
