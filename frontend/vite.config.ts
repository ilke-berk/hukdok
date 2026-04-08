import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import { componentTagger } from "lovable-tagger";

export default defineConfig(({ mode }) => ({
  envDir: "..",
  server: {
    host: "0.0.0.0",
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

