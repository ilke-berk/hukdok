import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// G088 nöbetçisi: vite dev sunucusu YALNIZ loopback'e bağlanmalı. Wildcard bind
// (tüm ağ arayüzleri) dev sunucusunu LAN'a açar; vite'in Windows'a özgü açıkları
// (server.fs.deny bypass, launch-editor NTLMv2 hash sızması) bu yüzden gerçek bir
// risktir. Açıkların kendisini kapatan iş ayrı (vite yükseltmesi, G089) — burada
// yalnız vektörün geri açılmadığını doğruluyoruz.
//
// Denetim kaynak METNİ üzerinden yapılır: vite.config.ts dev eklentisi
// (lovable-tagger) yüklediği için test koşusunda import edilmesi istenmiyor
// (bkz. vitest.config.ts şerhi).
const VITE_CONFIG_PATH = fileURLToPath(new URL("../../vite.config.ts", import.meta.url));
const source = readFileSync(VITE_CONFIG_PATH, "utf8");

describe("vite dev sunucusu bağlanma adresi", () => {
  it("host olarak 127.0.0.1 kullanır", () => {
    expect(source).toMatch(/host:\s*"127\.0\.0\.1"/);
  });

  it("wildcard bind adresi dosyanın hiçbir yerinde geçmez", () => {
    expect(source).not.toContain("0.0.0.0");
  });

  it("port ve strictPort ayarları korunur", () => {
    expect(source).toMatch(/port:\s*8000/);
    expect(source).toMatch(/strictPort:\s*true/);
  });

  it("backend proxy allowlist'i eksilmez", () => {
    const uclar = [
      "/api",
      "/process",
      "/confirm",
      "/preview-email-body",
      "/preview-client-email-body",
      "/refresh",
    ];
    for (const uc of uclar) {
      expect(source).toContain(`'${uc}': {`);
    }
  });
});
