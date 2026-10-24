import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [react(), VitePWA({
    registerType: "prompt",
    includeAssets: ["nexo-mark.svg", "icons/nexo-192.png", "icons/nexo-512.png", "icons/nexo-apple.png"],
    manifest: {
      id: "/", name: "Nexo · Análisis de fútbol", short_name: "Nexo",
      description: "Tu jornada, resultados y pronósticos con evidencia.",
      lang: "es-MX", start_url: "/", scope: "/", display: "standalone",
      background_color: "#F3F1EC", theme_color: "#F3F1EC",
      icons: [
        {src:"/icons/nexo-192.png",sizes:"192x192",type:"image/png",purpose:"any"},
        {src:"/icons/nexo-512.png",sizes:"512x512",type:"image/png",purpose:"any"},
        {src:"/icons/nexo-maskable.png",sizes:"512x512",type:"image/png",purpose:"maskable"}
      ],
      shortcuts: [{name:"En vivo",url:"/en-vivo"},{name:"Mis apuestas",url:"/mis-pronosticos"}]
    },
    workbox: {
      globPatterns: ["**/*.{js,css,html,png,svg,ico}"],
      navigateFallbackDenylist: [/^\/api\//],
      // Solo archivos estáticos. Nunca almacenar sesiones, API, momios ni resultados.
      runtimeCaching: [], cleanupOutdatedCaches: true
    }
  })],
  preview: { host: "127.0.0.1", port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
