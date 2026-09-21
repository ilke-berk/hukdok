import path from "path";
import { readFileSync } from "fs";
import { defineConfig } from "vitest/config";

// Ayrı config: vite.config.ts lovable-tagger gibi dev eklentileri yüklüyor,
// test koşusunun onlara ihtiyacı yok.
const pkg = JSON.parse(readFileSync(path.join(__dirname, "package.json"), "utf8")) as { version: string };

export default defineConfig({
  resolve: {
    alias: {
      "@": path.join(__dirname, "src"),
    },
  },
  test: {
    // Login rozetindeki okunur sürüm — vite.config.ts `define` ile aynı kaynak (package.json).
    env: { VITE_APP_RELEASE: pkg.version },
    environment: "node", // DOM gerektiren testler dosya başına @vitest-environment jsdom kullanır
    // Faz 4.4: .tsx da dahil — bileşen testleri (ör. ErrorBoundary) yalnız-.ts
    // deseninde SESSİZCE toplanmıyordu.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
