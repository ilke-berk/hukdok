import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// G090 nöbetçisi: uygulama kaynağı çalışma zamanında UZAKTAN script YÜKLEMEZ.
// G090'da silinen pdf.js yükleyicisi (o güne kadar `frontend/src/lib/` altında
// duruyordu) tam olarak bunu yapıyordu: `document.head.appendChild(...)` ile
// üçüncü taraf bir CDN'den pdf.js çekiyordu, üstelik SRI (integrity) olmadan.
// Böyle bir script uygulamanın origin'inde, Azure AD token'ı tutan bir sayfada
// çalışır — CDN ya da DNS tarafındaki bir olay oturum çalmaya kadar giden bir
// yol açar.
//
// Dosya hiçbir yerden import edilmediği için bundle'a girmiyordu; yani açık
// değil, MAYIN'dı — biri "PDF'ten metin çıkarayım" diye import ettiği an canlı
// hale gelirdi. Bu nöbetçi mayının geri gömülmesini engeller. Tarayıcı tarafında
// gerçekten bir kütüphane gerekirse doğru yol npm bağımlılığıdır, CDN değil.
// Yan fayda: CSP'nin `script-src 'self'` kalabilmesi (G091).
//
// Denetim, sunucu adı LİSTESİ tutmaz — liste her zaman eksik kalır. Bunun
// yerine yapısal değişmezi doğrular: script etiketi enjeksiyonu ve uzak URL'in
// bir `src` alanına atanması. Böylece kural yarınki CDN için de geçerlidir.
//
// Kaynak METNİ üzerinden çalışır (G088'deki devServerBind nöbetçisiyle aynı
// desen): modüller import edilmez, dosyalar okunur.
const SRC_DIR = fileURLToPath(new URL("..", import.meta.url));
const SELF_PATH = fileURLToPath(import.meta.url);

const TARANAN_UZANTILAR = [".ts", ".tsx", ".js", ".jsx"];

// `document.createElement("script")` — çalışma zamanında script etiketi üretimi.
const SCRIPT_ENJEKSIYONU = /createElement\(\s*['"`]script['"`]\s*\)/;

// `script.src = "https://..."` ve `GlobalWorkerOptions.workerSrc = "https://..."`
// gibi uzak kaynak atamaları (büyük/küçük harf duyarsız: `src`, `workerSrc`).
const UZAK_KAYNAK_ATAMASI = /\.\w*src\s*=\s*['"`]https?:\/\//i;

function kaynakDosyalari(dizin: string): string[] {
  const sonuc: string[] = [];
  for (const girdi of readdirSync(dizin, { withFileTypes: true })) {
    const tamYol = path.join(dizin, girdi.name);
    if (girdi.isDirectory()) {
      sonuc.push(...kaynakDosyalari(tamYol));
      continue;
    }
    if (!TARANAN_UZANTILAR.includes(path.extname(girdi.name))) continue;
    // Bu dosya yasakladığı desenleri tanım gereği (regex olarak) içerir;
    // kendini taraması yanlış pozitif üretir.
    if (path.resolve(tamYol) === path.resolve(SELF_PATH)) continue;
    sonuc.push(tamYol);
  }
  return sonuc;
}

const DOSYALAR = kaynakDosyalari(SRC_DIR);

function ihlalEdenler(desen: RegExp): string[] {
  return DOSYALAR.filter((dosya) => desen.test(readFileSync(dosya, "utf8"))).map((dosya) =>
    path.relative(SRC_DIR, dosya).replace(/\\/g, "/"),
  );
}

describe("uzaktan script yükleme yasağı", () => {
  it("taramayı gerçekten koşturur (boş tarama sahte yeşil verir)", () => {
    expect(DOSYALAR.length).toBeGreaterThan(50);
  });

  it("hiçbir kaynak dosyası çalışma zamanında script etiketi enjekte etmez", () => {
    expect(ihlalEdenler(SCRIPT_ENJEKSIYONU)).toEqual([]);
  });

  it("hiçbir kaynak dosyası uzak bir URL'i src alanına atamaz", () => {
    expect(ihlalEdenler(UZAK_KAYNAK_ATAMASI)).toEqual([]);
  });
});
