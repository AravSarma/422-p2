/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Emerald palette chosen so text/buttons meet WCAG 2.1 AA (NFR-07):
        // emerald-800 on white ≈ 7.5:1, white on emerald-700 ≈ 5.5:1.
        brand: {
          50: "#ecfdf5",
          100: "#d1fae5",
          600: "#059669",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
        },
      },
    },
  },
  plugins: [],
};
