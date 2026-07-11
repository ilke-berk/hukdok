import path from "path";
import { defineConfig } from "vitest/config";

// Ayrı config: vite.config.ts lovable-tagger gibi dev eklentileri yüklüyor,
// test koşusunun onlara ihtiyacı yok.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.join(__dirname, "src"),
    },
  },
  test: {
    environment: "node", // DOM gerektiren testler dosya başına @vitest-environment jsdom kullanır
    include: ["src/**/*.test.ts"],
  },
});
