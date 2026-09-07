/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#6366f1",
          600: "#4f46e5",
          50: "#eef2ff",
        },
        navy: {
          DEFAULT: "#0b1220",
          900: "#070c16",
          800: "#12203a",
          700: "#1a2d4d",
          600: "#243a5e",
        },
        gold: {
          DEFAULT: "#c9a227",
          200: "#e8d5a3",
          50: "#f7f0dc",
        },
        ivory: "#f4efe4",
      },
      fontFamily: {
        display: ['Inter', "system-ui", "sans-serif"],
        suit: ['Inter', "system-ui", "sans-serif"],
        sans: ['Inter', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
