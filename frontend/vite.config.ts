import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => ({
  envDir: "..",
  server: {
    // BILEREK localhost - GERI ALMA. Tum-arayuz bindi (wildcard adres)
    // dev sunucusunu aga acar; ayni Wi-Fi'daki herkes erisebilir (LAN vektoru).
    // Vite'in bilinen aciklarindan ikisi tam olarak Windows'a ozgudur
    // (server.fs.deny bypass, launch-editor NTLMv2 hash sizmasi) ve
    // gelistirme Windows'ta yapiliyor. Aciklarin kendisini kapatan is
    // G089 (vite yukseltmesi); burasi yalnizca vektoru daraltir.
    // Uzaktan erisim gerekiyorsa bu satiri degil, tek seferlik
    // `npm run dev -- --host` bayragini kullan.
    host: "127.0.0.1",
    port: 8000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
      '/process': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
      '/confirm': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
      // Bu ikisi eksikti: `npm run dev` altinda her iki e-posta govde onizlemesi
      // de SPA'ya dusup 404/HTML donuyordu. nginx.conf ile ayni allowlist.
      '/preview-email-body': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
      '/preview-client-email-body': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      },
      '/refresh': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  plugins: [
    react(),
    mode === 'development' &&
    componentTagger(),
  ].filter(Boolean),
  resolve: {
    alias: {
      "@": path.join(__dirname, "src"),
    },
  },
}));

