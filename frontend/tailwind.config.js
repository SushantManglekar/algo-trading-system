/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      boxShadow: {
        panel: "0 12px 35px rgba(15, 23, 42, 0.07)",
      },
    },
  },
  plugins: [],
};
