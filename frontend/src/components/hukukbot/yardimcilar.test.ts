// /hukukbot yardımcıları (G205): sıralama (sabitlenenler üstte, sonra en yeni), başlık üretimi,
// `/ask` geçmişi (akan/hatalı/boş mesaj girmez), hata → Türkçe metin (429 daima sabit Türkçe), iptal tanıma.
import { describe, expect, it, vi } from "vitest";

// hukukbotApi → lib/api → msalConfig `window` ister; yalnız hata sınıfları/sabitler kullanılır.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
  HUKUKBOT_GENEL_HATA,
  HUKUKBOT_HIZ_MESAJI,
  HUKUKBOT_YETKI_MESAJI,
  HukukbotApiError,
  HukukbotHizSiniriError,
  HukukbotYetkiError,
} from "@/lib/hukukbotApi";
import type { HukukbotOturumOzeti } from "@/types/hukukbot";
import {
  BASLIK_UZUNLUGU,
  KAYIT_BULUNAMADI,
  YENI_SOHBET_BASLIGI,
  baslikUret,
  ekranMesajlari,
  gecmisUret,
  hataMetni,
  iptalMi,
  kaynakHukdokId,
  oturumlariSirala,
  type EkranMesaji,
} from "./yardimcilar";

describe("kaynakHukdokId", () => {
  const k = (hukdok_id?: unknown, metadata?: Record<string, unknown> | null) =>
    ({ file_display_name: "x", filename: "x.pdf", text_preview: "", hukdok_id, metadata }) as never;
  it("hukbot alanı öncelikli; eski mesajda metadata.hukdok_id'ye düşer; store dize/float verebilir", () => {
    expect(kaynakHukdokId(k(14743))).toBe(14743);
    expect(kaynakHukdokId(k(null, { hukdok_id: "501" }))).toBe(501);
    expect(kaynakHukdokId(k(undefined, { hukdok_id: 7.0 }))).toBe(7);
    expect(kaynakHukdokId(k(3, { hukdok_id: 9 }))).toBe(3);
  });
  it("geçersizse null → eski /download yolu", () => {
    expect(kaynakHukdokId(k())).toBeNull();
    expect(kaynakHukdokId(k(null, null))).toBeNull();
    expect(kaynakHukdokId(k(0))).toBeNull();
    expect(kaynakHukdokId(k(-2))).toBeNull();
    expect(kaynakHukdokId(k("abc"))).toBeNull();
    expect(kaynakHukdokId(k(""))).toBeNull();
    expect(kaynakHukdokId(k(true))).toBeNull();
  });
});

const oturum = (id: string, created_at: string, is_pinned = false): HukukbotOturumOzeti => ({
  id,
  title: id,
  created_at,
  is_pinned,
});

describe("oturumlariSirala", () => {
  it("sabitlenenler üstte, her grupta en yeni önce; girdi değişmez", () => {
    const girdi = [
      oturum("eski", "2026-09-01T10:00:00Z"),
      oturum("sabit-eski", "2026-08-01T10:00:00Z", true),
      oturum("yeni", "2026-09-20T10:00:00Z"),
      oturum("sabit-yeni", "2026-09-10T10:00:00Z", true),
    ];
    const kopya = [...girdi];
    expect(oturumlariSirala(girdi).map((o) => o.id)).toEqual(["sabit-yeni", "sabit-eski", "yeni", "eski"]);
    expect(girdi).toEqual(kopya);
  });
});

describe("baslikUret", () => {
  it("boşlukları sadeleştirir, 50 karakterde keser; boşsa varsayılan", () => {
    expect(baslikUret("  kira   tespit\n davası ")).toBe("kira tespit davası");
    expect(baslikUret("a".repeat(80))).toHaveLength(BASLIK_UZUNLUGU);
    expect(baslikUret("   ")).toBe(YENI_SOHBET_BASLIGI);
  });
});

describe("gecmisUret / ekranMesajlari", () => {
  it("akan, hatalı ve boş mesajlar geçmişe girmez; yalnız role+content gider", () => {
    const mesajlar: EkranMesaji[] = [
      { anahtar: "1", role: "user", content: "soru 1" },
      { anahtar: "2", role: "model", content: "cevap 1", sources: [] },
      { anahtar: "3", role: "user", content: "soru 2" },
      { anahtar: "4", role: "model", content: "yarım", hata: "hata" },
      { anahtar: "5", role: "model", content: "", akiyor: true },
      { anahtar: "6", role: "model", content: "akıyor", akiyor: true },
    ];
    expect(gecmisUret(mesajlar)).toEqual([
      { role: "user", content: "soru 1" },
      { role: "model", content: "cevap 1" },
      { role: "user", content: "soru 2" },
    ]);
  });

  it("sunucu mesajlarını anahtarlı ekran modeline çevirir", () => {
    const e = ekranMesajlari([
      { role: "user", content: "s" },
      { role: "model", content: "c", sources: [{ file_display_name: "A", filename: "a.pdf", text_preview: "" }] },
    ]);
    expect(e.map((m) => m.anahtar)).toEqual(["sunucu-0", "sunucu-1"]);
    expect(e[1].sources?.[0].filename).toBe("a.pdf");
    expect(e[0].sources).toBeNull();
  });
});

describe("hataMetni / iptalMi", () => {
  it("429 sunucu metni ne olursa olsun sabit Türkçe metin", () => {
    expect(hataMetni(new HukukbotHizSiniriError("Rate limit exceeded"))).toBe(HUKUKBOT_HIZ_MESAJI);
  });

  it("401, 404, diğer HTTP ve bilinmeyen hatalar Türkçe", () => {
    expect(hataMetni(new HukukbotYetkiError())).toBe(HUKUKBOT_YETKI_MESAJI);
    expect(hataMetni(new HukukbotApiError(404, "Not Found"))).toBe(KAYIT_BULUNAMADI);
    expect(hataMetni(new HukukbotApiError(500, "Internal Server Error"))).toBe(`${HUKUKBOT_GENEL_HATA} (HTTP 500)`);
    expect(hataMetni(new TypeError("Failed to fetch"))).toBe(HUKUKBOT_GENEL_HATA);
  });

  it("AbortError iptal sayılır, diğerleri sayılmaz", () => {
    expect(iptalMi(new DOMException("x", "AbortError"))).toBe(true);
    expect(iptalMi(new Error("x"))).toBe(false);
    expect(iptalMi(null)).toBe(false);
  });
});
