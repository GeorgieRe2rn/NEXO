/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#FF783E", ink: "#17212B", muted: "#8A98A6", canvas: "rgb(var(--canvas) / <alpha-value>)" },
        pitch: {
          950: "rgb(var(--canvas) / <alpha-value>)",
          900: "rgb(var(--surface) / <alpha-value>)",
          800: "rgb(var(--surface-alt) / <alpha-value>)",
          700: "rgb(var(--edge) / <alpha-value>)",
        },
        led: {
          DEFAULT: "rgb(var(--accent) / <alpha-value>)",
          dim: "#913510",
        },
        line: "rgb(var(--edge) / <alpha-value>)",
        amber: "rgb(var(--warning) / <alpha-value>)",
        paper: { DEFAULT: "rgb(var(--text) / <alpha-value>)" },
        mute: { DEFAULT: "rgb(var(--muted) / <alpha-value>)" },
        rust: { 400: "#ff8a65", 500: "#e85d04", 600: "#c4452d" },
        ink: {
          950: "#17212B", 900: "#21313D", 800: "#344550", 700: "#54636F", 600: "#73828D",
        },
      },
      fontFamily: {
        display: ['"Inter"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

