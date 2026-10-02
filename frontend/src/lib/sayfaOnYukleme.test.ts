import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ON_YUKLENEBILIR_YOLLAR } from "./sayfaOnYukleme";

// Faz 4 bekçisi: önden yükleme haritası App.tsx'in lazy modülleriyle ve menü yollarıyla hizalı kalmalı —
// sayfa taşınır/yeniden adlandırılırsa önden yükleme sessizce boşa düşmesin.
const SRC_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const oku = (yol: string) => readFileSync(path.join(SRC_DIR, yol), "utf8");

describe("sayfaOnYukleme haritası", () => {
  const harita = oku("lib/sayfaOnYukleme.ts");
  const app = oku("App.tsx");
  const haritaModulleri = [...harita.matchAll(/import\("\.\.\/pages\/([^"]+)"\)/g)].map(m => m[1]);
  const lazyModuller = new Set([...app.matchAll(/import\("\.\/pages\/([^"]+)"\)/g)].map(m => m[1]));

  it("haritadaki her modül App.tsx'te lazy yüklenen bir sayfadır", () => {
    expect(haritaModulleri.length).toBeGreaterThan(0);
    for (const m of haritaModulleri) expect(lazyModuller.has(m), m).toBe(true);
  });

  it("menüdeki her yol (Yönetim dahil) önden yüklenebilir", () => {
    const sidebar = oku("components/shell/Sidebar.tsx");
    const menuYollari = [...sidebar.matchAll(/path: "([^"]+)"/g)].map(m => m[1]);
    expect(menuYollari.length).toBeGreaterThan(0);
    for (const y of menuYollari) expect(ON_YUKLENEBILIR_YOLLAR, y).toContain(y);
  });
});
