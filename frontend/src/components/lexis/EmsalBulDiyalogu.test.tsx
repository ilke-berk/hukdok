// @vitest-environment jsdom
// EmsalBulDiyalogu (G264) — dört adım uçtan uca: kaynak (kart belgesi yalnız pdf/docx/udf · dosya) → belge özeti
// + maske dökümü + model rozeti (sahte / Gemini onay kutusu, K4) → ilerleme (info / warning) → gerekçeli liste
// (puan, doğrulanmış alıntı, aynı kart, Kararı aç) → "Taslağa ekle" (K28) ve "İnceleme paketini indir" (404 → pasif).
// Örnek kip sentetik akışla (servis yok); Gemini / failed / iptal yolları gerçek kipte sahte servisle.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const servisMock = vi.hoisted(() => ({
  emsalBelgeKarttan: vi.fn(),
  emsalBelgeYukle: vi.fn(),
  emsalDurum: vi.fn(),
  emsalAra: vi.fn(),
  emsalSonuc: vi.fn(),
  emsalIndir: vi.fn(),
  kararGetir: vi.fn(),
}));
vi.mock("@/lib/lexisServis", () => servisMock);

import { EmsalBulDiyalogu } from "./EmsalBulDiyalogu";
import { EmsalKararListesi } from "./EmsalKararListesi";
import { LexisApiError, ORNEK_EMSAL_DURUMU, ORNEK_PAKET_YOK, lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla, veriKipiAyarla } from "@/lib/lexisApi";
import { ORNEK_DOSYALAR, ORNEK_EMSAL_OKUMALARI } from "@/lib/lexisOrnekVeri";
import { gosterilecekOneriler, type EmsalAkisOlayi, type EmsalBelge, type EmsalDurumu, type EmsalOnerisi, type LexisBelge } from "@/types/lexis";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;

async function bekle(tur = 16) {
  for (let i = 0; i < tur; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

type Props = Parameters<typeof EmsalBulDiyalogu>[0];

async function ciz(props: Partial<Props> = {}) {
  const varsayilan: Props = { acik: true, caseId: 9004, belgeler: ORNEK_DOSYALAR[9004].belgeler, onKararAc: vi.fn(), onKapat: vi.fn() };
  await act(async () => {
    kok.render(<EmsalBulDiyalogu {...varsayilan} {...props} />);
  });
  await bekle();
}

const diyalog = () => document.querySelector<HTMLElement>('[data-testid="lexis-emsal-bul"]');
const test = <T extends HTMLElement = HTMLElement>(id: string) => document.querySelector<T>(`[data-testid="${id}"]`);
const oneriler = () => Array.from(document.querySelectorAll<HTMLElement>('[data-testid="lexis-emsal-oneri"]'));

function dugme(etiket: string, icinde: ParentNode = document.body): HTMLButtonElement {
  const d = Array.from(icinde.querySelectorAll<HTMLButtonElement>("button")).find(
    (b) => b.getAttribute("aria-label") === etiket || b.textContent?.trim() === etiket || b.textContent?.trim().startsWith(etiket),
  );
  if (!d) throw new Error(`düğme yok: ${etiket}`);
  return d;
}

async function tikla(el: HTMLElement) {
  await act(async () => {
    el.click();
  });
  await bekle();
}

/** `<input type="file">`'a dosya koyar (jsdom'da `files` salt okunur: tanımlanır) ve change olayı yayar. */
async function dosyaSec(dosya: File) {
  const girdi = document.querySelector<HTMLInputElement>('input[type="file"]')!;
  Object.defineProperty(girdi, "files", { value: [dosya], configurable: true });
  await act(async () => {
    girdi.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await bekle();
}

/** Örnek kipte belgeyi hazırlayıp aramayı sonuna kadar koşturur. */
async function sonucaGit() {
  await tikla(dugme("Belgeyi hazırla"));
  await tikla(dugme("Ara"));
  await bekle(24);
}

const BELGE: EmsalBelge = { sha256: "b".repeat(64), kaynak: "yukleme", bicim: "udf", boyut: 24_000, sayfa: null, metin_uzunluk: 6_200, bolumler: [{ tip: "iddia", baslik: "İDDİA", bas: 0, son: 6200 }], maske_dokumu: { bilinen: 0, kalip: 2, ogrenilen: 1 }, case_id: null, hukdok_belge_id: null, yukleme: "2026-10-07T20:00:00+00:00", mevcut: false, arsiv: "tamam", sharepoint_url: null };
const GEMINI: EmsalDurumu = { ...ORNEK_EMSAL_DURUMU, kip: "gemini", sorgu_modeli: "gemini-3.8-flash", okuyucu_modeli: "gemini-3.8-flash", gunluk_token: 500_000, kullanilan_token: 12_345 };

/**
 * Verilen olayları sırayla veren sahte akış; `beklet` verilirse ilk olaydan sonra iptal edilene dek bekler; `hata`
 * verilirse akış başlamadan fırlar (HTTP hatası deseni).
 */
function sahteAkis(olaylar: EmsalAkisOlayi[], beklet = false, hata: Error | null = null) {
  return async function* (_sha: string, secenekler: { signal?: AbortSignal } = {}) {
    if (hata) throw hata;
    for (const olay of olaylar) {
      yield olay;
      if (beklet) {
        await new Promise<void>((resolve) => {
          const signal = secenekler.signal;
          if (!signal) return;
          signal.addEventListener("abort", () => resolve(), { once: true });
        });
        if (secenekler.signal?.aborted) throw new DOMException("İstek iptal edildi.", "AbortError");
      }
    }
  };
}

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  Object.values(servisMock).forEach((m) => m.mockReset());
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
  veriKipiAyarla("ornek");
});

describe("EmsalBulDiyalogu — örnek kip (sentetik akış, servis yok)", () => {
  it("kaynak adımı yalnız pdf/docx/udf (ve uzantısız) kart belgelerini listeler; belge satırından açılınca o belge seçili gelir", async () => {
    const belgeler: LexisBelge[] = [
      ...ORNEK_DOSYALAR[9004].belgeler,
      { id: 498, ad: "tebligat.pdf", tur: "DIGER", tarih: "2025-01-01", ozet: null, sayfa: 2 },
      { id: 499, ad: "foto.jpg", tur: "DIGER", tarih: "2025-01-01", ozet: null, sayfa: null },
      { id: 497, ad: "eposta.eml", tur: "DIGER", tarih: "2025-01-01", ozet: null, sayfa: null },
    ];
    await ciz({ belgeler, baslangicBelgeId: 403 });
    const d = diyalog()!;
    expect(d.getAttribute("role")).toBe("dialog");
    expect(d.className).toContain("theme-classic");
    const radyolar = Array.from(d.querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    expect(radyolar).toHaveLength(ORNEK_DOSYALAR[9004].belgeler.length + 1); // + tebligat.pdf; jpg ve eml elendi
    expect(test("lexis-emsal-kaynak")!.textContent).not.toContain("foto.jpg");
    expect(test("lexis-emsal-kaynak")!.textContent).toContain("tebligat.pdf");
    expect(radyolar.filter((r) => r.checked)).toHaveLength(1);
    expect(radyolar.find((r) => r.checked)!.closest("label")!.textContent).toContain("Bilirkişi ek raporu");
    expect(d.querySelector('input[type="file"]')).not.toBeNull();
    expect(dugme("Belgeyi hazırla").disabled).toBe(false);
  });

  it("seçim yokken 'Belgeyi hazırla' pasiftir; dosya seçilince açılır ve radyo seçimi düşer", async () => {
    await ciz();
    expect(dugme("Belgeyi hazırla").disabled).toBe(true);
    await tikla(diyalog()!.querySelector<HTMLInputElement>('input[type="radio"]')!);
    expect(dugme("Belgeyi hazırla").disabled).toBe(false);
    await dosyaSec(new File(["%PDF-1.4"], "dilekce.pdf", { type: "application/pdf" }));
    expect(Array.from(diyalog()!.querySelectorAll<HTMLInputElement>('input[type="radio"]')).some((r) => r.checked)).toBe(false);
    expect(test("lexis-emsal-kaynak")!.textContent).toContain("dilekce.pdf");
  });

  it("belge özeti maske dökümü ve 'Sahte üretici' rozetiyle gelir; arama 3 info + 1 warning + complete ile biter; liste gerekçeli ve doğrulanmış alıntılı", async () => {
    const onKararAc = vi.fn();
    const onTaslagaEkle = vi.fn();
    const onKapat = vi.fn();
    await ciz({ baslangicBelgeId: 401, onKararAc, onTaslagaEkle, onKapat });
    await tikla(dugme("Belgeyi hazırla"));

    const belge = test("lexis-emsal-belge")!;
    expect(belge.textContent).toContain("Kart belgesi");
    expect(belge.textContent).toContain("PDF");
    expect(belge.textContent).toContain("bilinen 2 · kalıp 1 · öğrenilen 0");
    expect(belge.textContent).toContain("HUKDOK arşivinde");
    expect(test("lexis-emsal-model")!.textContent).toContain("Sahte üretici");
    expect(test("lexis-emsal-model")!.querySelector('input[type="checkbox"]')).toBeNull(); // Gemini onayı yok
    expect(dugme("Ara").disabled).toBe(false);

    // Akışın olayları doğrudan adaptörden: 3 info + 1 warning + complete (sözleşme kilidi).
    const olaylar: EmsalAkisOlayi[] = [];
    const kayit = await lexisApi.emsalBelgeKarttan(9004, 401);
    for await (const o of lexisApi.emsalAra(kayit.sha256)) olaylar.push(o);
    expect(olaylar.map((o) => o.status)).toEqual(["info", "info", "info", "warning", "complete"]);
    expect(olaylar.slice(0, 3).map((o) => (o.status === "info" ? o.asama : ""))).toEqual(["kunye", "aday", "okuma"]);
    expect(await lexisApi.emsalSonuc(kayit.sha256)).toMatchObject({ sha256: kayit.sha256, oneriler: expect.any(Array) });

    await tikla(dugme("Ara"));
    await bekle(24);
    const sonuc = test("lexis-emsal-sonuc")!;
    expect(test("lexis-emsal-sayilar")!.textContent).toContain("6 aday · 6 okundu · 1 düştü · 1 önbellekten · 5 model çağrısı");
    expect(test("lexis-emsal-kunye")!.textContent).toContain("Kadın Hastalıkları ve Doğum");
    expect(sonuc.textContent).toContain("1 uyarı");
    expect(test("lexis-emsal-uyarilar")!.textContent).toContain("aday düştü: alıntı kararda bulunamadı");

    const satirlar = oneriler();
    expect(satirlar).toHaveLength(ORNEK_EMSAL_OKUMALARI.length);
    expect(satirlar.map((s) => s.getAttribute("data-karar-id"))).toEqual(ORNEK_EMSAL_OKUMALARI.map((o) => String(o.id)));
    const ilk = satirlar[0];
    expect(ilk.textContent).toContain("91");
    expect(ilk.textContent).toContain("Adana 1. İdare Mahkemesi · 2023/404 E., 2025/118 K. · 12.03.2025");
    expect(ilk.textContent).toContain("Ret (esastan)");
    expect(ilk.textContent).toContain("aynı kart"); // belge 9004 kartından, karar 7001 aynı kartın kararı
    expect(ilk.textContent).toContain("Aynı uzmanlık ve aynı olay");
    expect(ilk.querySelector("blockquote")!.textContent).toContain("omuz takılmasının doğumun öngörülemeyen bir komplikasyonu olduğu");
    expect(ilk.querySelector("blockquote")!.textContent).toContain("kaynakta doğrulandı");
    expect(ilk.textContent).toContain("Fark: Belgenin kendi kartının kararı");
    expect(satirlar[1].textContent).not.toContain("aynı kart");
    expect(satirlar[2].querySelector('[aria-label="Denetim uyarıları"]')!.textContent).toContain("65.000,00 TL tutarı kararda geçmiyor");
    expect(satirlar[3].textContent).toContain("önbellekten");

    // "Kararı aç" yalnız kimliği verir (okuyucuyu çağıran açar).
    await tikla(dugme("Mersin 2. İdare Mahkemesi", satirlar[1]));
    expect(onKararAc).toHaveBeenCalledWith(7004);

    // Seçim → "Taslağa ekle (n)": seçilen öneriler çağırana gider, diyalog kapanır.
    expect(dugme("Taslağa ekle").disabled).toBe(true);
    await tikla(satirlar[1].querySelector<HTMLInputElement>('input[type="checkbox"]')!);
    await tikla(satirlar[2].querySelector<HTMLInputElement>('input[type="checkbox"]')!);
    expect(dugme("Taslağa ekle (2)").disabled).toBe(false);
    await tikla(dugme("Taslağa ekle (2)"));
    expect(onTaslagaEkle).toHaveBeenCalledTimes(1);
    const eklenen = onTaslagaEkle.mock.calls[0][0] as EmsalOnerisi[];
    expect(eklenen.map((o) => o.id)).toEqual([7004, 7005]);
    expect(eklenen[0]).toMatchObject({ mahkeme: "Mersin 2. İdare Mahkemesi", puan: 84 });
    expect(onKapat).toHaveBeenCalledTimes(1);
  });

  it("'İnceleme paketini indir' 404'te pasifleşir ve nedenini yazar (örnek kipte paket üretilmez)", async () => {
    await ciz({ baslangicBelgeId: 401 });
    await sonucaGit();
    const indir = dugme("İnceleme paketini indir");
    expect(indir.disabled).toBe(false);
    await tikla(indir);
    expect(dugme("İnceleme paketini indir").disabled).toBe(true);
    expect(test("lexis-emsal-indirme-notu")!.textContent).toBe(ORNEK_PAKET_YOK);
  });

  it("rafta (kart yok) yalnız dosya seçilir, 'Taslağa ekle' çizilmez; kartsız yüklemede maske yalnız kalıptan; taslakta olan karar kilitli gelir", async () => {
    await ciz({ caseId: null, belgeler: [], mevcutKararlar: new Set([7001]) });
    expect(diyalog()!.querySelector('input[type="radio"]')).toBeNull();
    expect(test("lexis-emsal-kaynak")!.textContent).not.toContain("Kart belgesi");
    await dosyaSec(new File(["PK"], "karar.udf"));
    await tikla(dugme("Belgeyi hazırla"));
    expect(test("lexis-emsal-belge")!.textContent).toContain("Yükleme");
    expect(test("lexis-emsal-belge")!.textContent).toContain("UDF");
    expect(test("lexis-emsal-belge")!.textContent).toContain("bilinen 0 · kalıp 3 · öğrenilen 1");
    await tikla(dugme("Ara"));
    await bekle(24);
    const satirlar = oneriler();
    expect(satirlar[0].textContent).not.toContain("aynı kart"); // kartsız belgede aynı kart yok
    expect(satirlar[0].textContent).toContain("taslakta");
    const kutu = satirlar[0].querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(kutu.checked).toBe(true);
    expect(kutu.disabled).toBe(true);
    expect(Array.from(document.querySelectorAll("button")).some((b) => b.textContent?.includes("Taslağa ekle"))).toBe(false);
  });

  it("desteklenmeyen dosya hazırlık hatası olarak görünür; kaynak adımında kalınır", async () => {
    await ciz({ caseId: null, belgeler: [] });
    await dosyaSec(new File(["x"], "foto.jpg"));
    await tikla(dugme("Belgeyi hazırla"));
    expect(test("lexis-emsal-hata")!.textContent).toBe("Yalnız PDF, DOCX ve UDF kabul edilir.");
    expect(test("lexis-emsal-kaynak")).not.toBeNull();
  });
});

describe("EmsalKararListesi — savunma", () => {
  it("alinti_dogrulandi=false ya da alıntısı boş öneri gösterilmez", async () => {
    const kayit = await lexisApi.emsalBelgeKarttan(9004, 401);
    let sonuc = null as Awaited<ReturnType<typeof lexisApi.emsalSonuc>> | null;
    for await (const o of lexisApi.emsalAra(kayit.sha256)) if (o.status === "complete") sonuc = o;
    const [a, b, c, ...kalan] = sonuc!.oneriler;
    const liste: EmsalOnerisi[] = [{ ...a, alinti_dogrulandi: false }, { ...b, alinti: "   " }, { ...c, alinti_dogrulandi: true }, ...kalan];
    expect(gosterilecekOneriler(liste).map((o) => o.id)).toEqual([c.id, ...kalan.map((o) => o.id)]);
    await act(async () => {
      kok.render(<EmsalKararListesi oneriler={liste} secili={new Set()} onSec={vi.fn()} onKararAc={vi.fn()} />);
    });
    await bekle(2);
    expect(kap.querySelectorAll('[data-testid="lexis-emsal-oneri"]')).toHaveLength(liste.length - 2);
    expect(kap.textContent).not.toContain(a.gerekce);
    expect(kap.textContent).toContain(c.gerekce);

    await act(async () => {
      kok.render(<EmsalKararListesi oneriler={[{ ...a, alinti_dogrulandi: false }]} secili={new Set()} onSec={vi.fn()} onKararAc={vi.fn()} />);
    });
    expect(kap.textContent).toContain("Denetimden geçen emsal önerisi yok");
  });
});

describe("EmsalBulDiyalogu — gerçek kip (sahte servis)", () => {
  beforeEach(() => {
    veriKipiAyarla("gercek");
    servisMock.emsalBelgeYukle.mockResolvedValue(BELGE);
  });

  it("Gemini kipinde 'Ara' onay kutusu işaretlenmeden pasiftir; ilerleme i/n ve uyarılar akıştan gelir; dosya yüklemesi servise gider", async () => {
    servisMock.emsalDurum.mockResolvedValue(GEMINI);
    const tamam: EmsalAkisOlayi = { status: "complete", sha256: BELGE.sha256, kunye: { uzmanlik: null, tibbi_islem: null, iddia: "", taraf_turu: null, yargi_yolu: "DIGER", sorgular: [] }, model: "gemini-3.8-flash", sorgu_modeli: "gemini-3.8-flash", oneriler: [], sayilar: { aday: 5, okunan: 5, dusen: 5, onbellek: 0, model_cagrisi: 6, token: 8000, saniye: 4 } };
    servisMock.emsalAra.mockImplementation(
      sahteAkis([
        { status: "info", asama: "okuma", ilerleme: [2, 5], belge_id: 11, kaynak: "model" },
        { status: "warning", asama: "okuma", belge_id: 12, message: "aday düştü: okuyucu yanıtı şemaya uymadı", error_kod: "schema_invalid" },
        tamam,
      ]),
    );
    await ciz({ caseId: null, belgeler: [] });
    await dosyaSec(new File(["PK"], "karar.udf"));
    await tikla(dugme("Belgeyi hazırla"));
    expect(servisMock.emsalBelgeYukle).toHaveBeenCalledTimes(1);
    expect((servisMock.emsalBelgeYukle.mock.calls[0][0] as File).name).toBe("karar.udf");
    expect(servisMock.emsalBelgeYukle.mock.calls[0][1]).toBeNull();

    const model = test("lexis-emsal-model")!;
    expect(model.textContent).toContain("Gemini — gönderim onayı gerekir");
    expect(model.textContent).toContain("gemini-3.8-flash");
    expect(model.textContent).toContain("12.345 / 500.000");
    expect(dugme("Ara").disabled).toBe(true);
    await tikla(model.querySelector<HTMLInputElement>('input[type="checkbox"]')!);
    expect(dugme("Ara").disabled).toBe(false);
    expect(servisMock.emsalAra).not.toHaveBeenCalled(); // onay tek başına göndermez

    await tikla(dugme("Ara"));
    expect(servisMock.emsalAra).toHaveBeenCalledTimes(1);
    expect(servisMock.emsalAra.mock.calls[0][0]).toBe(BELGE.sha256);
    await bekle(8);
    // Akış bitti: boş sonuç (hepsi denetimden düştü) ve uyarı listesi.
    expect(test("lexis-emsal-sonuc")!.textContent).toContain("Denetimden geçen emsal önerisi yok");
    expect(test("lexis-emsal-sayilar")!.textContent).toContain("5 aday · 5 okundu · 5 düştü · 6 model çağrısı");
    expect(test("lexis-emsal-uyarilar")!.textContent).toContain("okuyucu yanıtı şemaya uymadı");
  });

  it("ilerleme adımda i/n gösterilir; 'Durdur' akışı keser ve belge adımına döner (hata yok)", async () => {
    servisMock.emsalDurum.mockResolvedValue(ORNEK_EMSAL_DURUMU);
    servisMock.emsalAra.mockImplementation(sahteAkis([{ status: "info", asama: "okuma", ilerleme: [3, 7], mesaj: "Adaylar okunuyor" }], true));
    await ciz({ caseId: null, belgeler: [] });
    await dosyaSec(new File(["PK"], "karar.udf"));
    await tikla(dugme("Belgeyi hazırla"));
    await tikla(dugme("Ara"));
    const ilerleme = test("lexis-emsal-ilerleme")!;
    expect(ilerleme.getAttribute("role")).toBe("status");
    expect(ilerleme.textContent).toContain("3/7");
    expect(ilerleme.querySelector('[aria-current="step"]')!.textContent).toContain("Okuma");
    await tikla(dugme("Durdur"));
    expect(test("lexis-emsal-ilerleme")).toBeNull();
    expect(test("lexis-emsal-belge")).not.toBeNull();
    expect(test("lexis-emsal-hata")).toBeNull();
  });

  it("failed olayı ve akış başlamadan HTTP hatası (409) belge adımında görünür; hat kapalıysa 'Ara' pasiftir", async () => {
    servisMock.emsalDurum.mockResolvedValue(ORNEK_EMSAL_DURUMU);
    servisMock.emsalAra.mockImplementationOnce(sahteAkis([{ status: "info", asama: "kunye" }, { status: "failed", error_ozet: "Belgede aday bulunamadı.", error_kod: "aday_yok" }]));
    await ciz({ caseId: null, belgeler: [] });
    await dosyaSec(new File(["PK"], "karar.udf"));
    await tikla(dugme("Belgeyi hazırla"));
    await tikla(dugme("Ara"));
    expect(test("lexis-emsal-belge")).not.toBeNull();
    expect(test("lexis-emsal-hata")!.textContent).toBe("Belgede aday bulunamadı.");

    servisMock.emsalAra.mockImplementationOnce(sahteAkis([], false, new LexisApiError(409, "Bir emsal aramanız zaten sürüyor; bitmesini bekleyin.")));
    await tikla(dugme("Ara"));
    expect(test("lexis-emsal-hata")!.textContent).toBe("Bir emsal aramanız zaten sürüyor; bitmesini bekleyin.");

    // Hat kapalı: rozet + neden, "Ara" pasif.
    servisMock.emsalDurum.mockResolvedValue({ ...GEMINI, acik: false, neden: "anahtar_yok" });
    await tikla(dugme("Geri"));
    await tikla(dugme("Belgeyi hazırla"));
    expect(test("lexis-emsal-model")!.textContent).toContain("Hat kapalı");
    expect(test("lexis-emsal-model")!.textContent).toContain("GEMINI_API_KEY");
    expect(dugme("Ara").disabled).toBe(true);
  });

  it("hat durumu alınamazsa belge özeti yine gelir, 'Ara' pasif ve neden yazılı", async () => {
    servisMock.emsalDurum.mockRejectedValue(new LexisApiError(503, "Lexis veritabanına ulaşılamadı; biraz sonra tekrar deneyin."));
    await ciz({ caseId: null, belgeler: [] });
    await dosyaSec(new File(["PK"], "karar.udf"));
    await tikla(dugme("Belgeyi hazırla"));
    expect(test("lexis-emsal-belge")).not.toBeNull();
    expect(test("lexis-emsal-model")!.textContent).toContain("Durum alınamadı");
    expect(test("lexis-emsal-model")!.textContent).toContain("Lexis veritabanına ulaşılamadı");
    expect(dugme("Ara").disabled).toBe(true);
  });
});
