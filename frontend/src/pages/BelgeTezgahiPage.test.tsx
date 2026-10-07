// @vitest-environment jsdom
// BelgeTezgahiPage (G270) — `lib/pdfAraclariApi` sahte (yukle/islem/indir), ayrıştırıcılar gerçek. Kilitlenen davranışlar:
// iskelet (yol çipleri, TTL satırı, boş `data-slot="sayfalar"` yuvası), çoklu yükleme SIRAYLA + hata satırı diğerlerini
// durdurmaz, iki dosya işaretle → birleştir → çıktı listede ve seçili (↑/↓ sırayı değiştirir), böl aralık ayrıştırma
// (geçersiz → düğme kapalı, her sayfa → her_n:1), sıkıştır/damga parametreleri, 503 mesajı, indirme, listeden kaldırma,
// yuva düğmeleri kapalı; rota lazy + menü yolu önden yüklenebilir (metin bekçisi).
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

const apiMock = vi.hoisted(() => ({ yukle: vi.fn(), islem: vi.fn(), indir: vi.fn(), onizlemeBlob: vi.fn() }));
vi.mock("@/lib/pdfAraclariApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pdfAraclariApi")>()),
  ...apiMock,
}));

import BelgeTezgahiPage from "./BelgeTezgahiPage";
import { PdfAraclariApiError } from "@/lib/pdfAraclariApi";
import type { Dosya, IslemIstegi } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;

const dosyaNesnesi = (ad: string, sayfa = 2): Dosya => ({
  id: `id-${ad}`,
  ad,
  sayfa,
  boyut: 2048,
  sayfalar: Array.from({ length: sayfa }, (_, i) => ({ no: i + 1, genislik: 595, yukseklik: 842 })),
});

async function ciz() {
  await act(async () => {
    kok.render(<BelgeTezgahiPage />);
  });
}

const dugme = (ad: string) =>
  Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad);
const indirDugmesi = () =>
  Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim().startsWith("İndir"))!;
const satirlar = () => Array.from(kap.querySelectorAll<HTMLLIElement>('[data-testid="dosya-listesi"] > li'));
const satirAdlari = () => satirlar().map((li) => li.getAttribute("data-dosya-id")!.replace(/^id-/, ""));
const seciliSatir = () => kap.querySelector<HTMLLIElement>('[data-testid="dosya-listesi"] > li[aria-current="true"]');
const onayKutusu = (ad: string) => kap.querySelector<HTMLInputElement>(`input[aria-label="Birleştirmeye ekle: ${ad}"]`)!;

async function yukleDosyalar(adlar: string[]) {
  const girdi = kap.querySelector<HTMLInputElement>('[data-testid="pdf-yukleyici-girdi"]')!;
  // MIME ada göre: `.pdf` → application/pdf, diğerleri boş (isValidFile uzantı/MIME'a bakar; `.exe` elenir)
  const dosyalar = adlar.map((ad) => new File([new Uint8Array([1, 2])], ad, { type: ad.endsWith(".pdf") ? "application/pdf" : "" }));
  Object.defineProperty(girdi, "files", { value: dosyalar, configurable: true });
  await act(async () => {
    girdi.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

async function yaz(el: HTMLInputElement, deger: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function tikla(el: HTMLElement | undefined) {
  expect(el).toBeDefined();
  await act(async () => {
    el!.click();
  });
}

beforeEach(() => {
  apiMock.yukle.mockReset();
  apiMock.islem.mockReset();
  apiMock.indir.mockReset();
  apiMock.yukle.mockImplementation(async (f: File) => dosyaNesnesi(f.name));
  apiMock.indir.mockResolvedValue(undefined);
  // G271: ızgara kartları önizleme çeker (jsdom'da IntersectionObserver yok → hemen); burada hata ("Önizleme yok") yeter
  apiMock.onizlemeBlob.mockReset();
  apiMock.onizlemeBlob.mockRejectedValue(new Error("test: önizleme yok"));
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("BelgeTezgahiPage iskelet", () => {
  it("yol çipleri, TTL satırı, boş sayfa yuvası, boş liste, indirme kapalı", async () => {
    await ciz();
    expect(kap.querySelector("h1")!.textContent).toBe("Belge tezgâhı");
    expect(kap.querySelector('[data-testid="yol-pdf"]')!.getAttribute("aria-current")).toBe("true");
    const word = kap.querySelector<HTMLButtonElement>('[data-testid="yol-word"]')!;
    expect(word.disabled).toBe(true);
    expect(word.textContent).toContain("sonraki sürüm");
    expect(kap.querySelector('[data-testid="ttl-bilgisi"]')!.textContent).toContain("1 saat");
    const yuva = kap.querySelector('section[data-slot="sayfalar"]')!;
    expect(yuva).not.toBeNull();
    expect(yuva.children.length).toBe(0);
    expect(kap.querySelector('[data-testid="dosya-listesi-bos"]')).not.toBeNull();
    expect(indirDugmesi().disabled).toBe(true);
    expect(kap.textContent).toContain("İşlem için soldan bir dosya seçin.");
  });

  it("karart / not dosya yokken kapalı; sayfa düzenle değişiklik olmadan kapalı (G271); dosya seçilince Karart büyük görünümü açar (G272)", async () => {
    await ciz();
    for (const ad of ["Karart", "Not"]) {
      const b = dugme(ad)!;
      expect(b.disabled, ad).toBe(true);
      expect(b.getAttribute("aria-pressed")).toBe("false");
    }
    expect(dugme("Sayfa düzenle")!.disabled).toBe(true);

    await yukleDosyalar(["z.pdf"]);
    expect(dugme("Karart")!.disabled).toBe(false);
    expect(dugme("Not")!.disabled).toBe(false);
    const yuva = kap.querySelector('section[data-slot="sayfalar"]')!;
    expect(yuva.querySelector('[data-testid="sayfa-gorunumu"]')).toBeNull();
    await tikla(dugme("Karart"));
    expect(dugme("Karart")!.getAttribute("aria-pressed")).toBe("true");
    expect(yuva.querySelector('[data-testid="sayfa-gorunumu"]')).not.toBeNull();
    expect(yuva.querySelector('[data-testid="sayfa-izgarasi"]')).toBeNull();
    expect(kap.querySelector('[data-testid="karartma-listesi"]')).not.toBeNull();
    expect(apiMock.onizlemeBlob).toHaveBeenLastCalledWith("id-z.pdf", 1, 1200);
    await tikla(Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === "Izgara"));
    expect(yuva.querySelector('[data-testid="sayfa-izgarasi"]')).not.toBeNull();
  });

  it("dosya seçilince orta yuvada sayfa ızgarası çizilir (G271)", async () => {
    await ciz();
    await yukleDosyalar(["z.pdf"]); // 2 sayfa
    const yuva = kap.querySelector('section[data-slot="sayfalar"]')!;
    expect(yuva.querySelector('[data-testid="sayfa-izgarasi"]')).not.toBeNull();
    expect(yuva.querySelectorAll('[role="listitem"]').length).toBe(2);
  });
});

describe("yükleme", () => {
  it("çoklu seçim sırayla ayrı ayrı yüklenir; her dosya listeye düşer, son yüklenen seçili", async () => {
    await ciz();
    const sira: string[] = [];
    apiMock.yukle.mockImplementation(async (f: File) => {
      sira.push(f.name);
      return dosyaNesnesi(f.name);
    });
    await yukleDosyalar(["a.pdf", "b.pdf"]);
    expect(apiMock.yukle).toHaveBeenCalledTimes(2);
    expect(sira).toEqual(["a.pdf", "b.pdf"]);
    expect(apiMock.yukle.mock.calls.every((c) => c[0] instanceof File && c.length === 1)).toBe(true); // tek dosya/istek
    expect(satirAdlari()).toEqual(["a.pdf", "b.pdf"]);
    expect(seciliSatir()!.getAttribute("data-dosya-id")).toBe("id-b.pdf");
    expect(kap.textContent).toContain("Seçili: b.pdf");
    const durumlar = Array.from(kap.querySelectorAll('[aria-label="Yükleme durumu"] li[data-durum]')).map((li) => li.getAttribute("data-durum"));
    expect(durumlar).toEqual(["tamam", "tamam"]);
  });

  it("bir dosya hata alınca satırda mesaj görünür, diğerleri devam eder", async () => {
    await ciz();
    apiMock.yukle.mockImplementation(async (f: File) => {
      if (f.name === "kotu.exe") throw new PdfAraclariApiError(415, "İzin verilmeyen dosya uzantısı: .exe", "uzanti");
      return dosyaNesnesi(f.name);
    });
    await yukleDosyalar(["kotu.exe", "iyi.pdf"]);
    expect(apiMock.yukle).toHaveBeenCalledTimes(1); // .exe istemcide elendi (ACCEPT/isValidFile)
    expect(kap.textContent).toContain("Desteklenmeyen format atlandı: kotu.exe");
    expect(satirAdlari()).toEqual(["iyi.pdf"]);

    apiMock.yukle.mockClear();
    apiMock.yukle.mockImplementation(async (f: File) => {
      if (f.name === "buyuk.pdf") throw new PdfAraclariApiError(413, "Dosya çok büyük. Maksimum 50MB.", "boyut");
      return dosyaNesnesi(f.name);
    });
    await yukleDosyalar(["buyuk.pdf", "kucuk.pdf"]);
    expect(apiMock.yukle).toHaveBeenCalledTimes(2);
    const hataSatiri = kap.querySelector('[aria-label="Yükleme durumu"] li[data-durum="hata"]')!;
    expect(hataSatiri.textContent).toContain("buyuk.pdf");
    expect(hataSatiri.textContent).toContain("Dosya çok büyük. Maksimum 50MB.");
    expect(satirAdlari()).toEqual(["iyi.pdf", "kucuk.pdf"]);
  });
});

describe("işlemler", () => {
  it("iki dosya işaretle → birleştir → çıktı listede ve seçili; ↓ sırayı değiştirir", async () => {
    await ciz();
    await yukleDosyalar(["a.pdf", "b.pdf"]);
    const birlestir = () => dugme("Birleştir")!;
    expect(birlestir().disabled).toBe(true);
    await tikla(onayKutusu("a.pdf"));
    expect(birlestir().disabled).toBe(true); // tek işaretli yetmez
    await tikla(onayKutusu("b.pdf"));
    expect(birlestir().disabled).toBe(false);

    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("birlestirilmis.pdf", 4)]);
    await tikla(birlestir());
    expect(apiMock.islem).toHaveBeenCalledTimes(1);
    expect(apiMock.islem.mock.calls[0][0]).toEqual({
      islem: "birlestir",
      girdiler: ["id-a.pdf", "id-b.pdf"],
      parametreler: {},
      cikti_adi: "birlestirilmis.pdf",
    });
    expect(satirAdlari()).toEqual(["a.pdf", "b.pdf", "birlestirilmis.pdf"]);
    expect(seciliSatir()!.getAttribute("data-dosya-id")).toBe("id-birlestirilmis.pdf");
    expect(kap.textContent).toContain("Seçili: birlestirilmis.pdf · 4 sayfa");

    // ↓ a.pdf'i aşağı taşı → birleştirme sırası [b, a]
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Aşağı taşı: a.pdf"]')!);
    expect(satirAdlari()).toEqual(["b.pdf", "a.pdf", "birlestirilmis.pdf"]);
    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("ikinci.pdf", 4)]);
    await tikla(birlestir());
    expect((apiMock.islem.mock.calls[1][0] as IslemIstegi).girdiler).toEqual(["id-b.pdf", "id-a.pdf"]);
  });

  it("böl: geçersiz aralık düğmeyi kapatır ve uyarır; geçerli aralık → araliklar; her sayfa → her_n:1", async () => {
    await ciz();
    await yukleDosyalar(["c.pdf"]); // 2 sayfa
    const bol = () => dugme("Böl")!;
    const aralik = kap.querySelector<HTMLInputElement>('input[aria-label="Böl aralıkları"]')!;
    expect(bol().disabled).toBe(true);
    await yaz(aralik, "1-5");
    expect(bol().disabled).toBe(true);
    expect(kap.querySelector('[role="alert"]')!.textContent).toContain("Aralık biçimi");
    await yaz(aralik, "1-1,2");
    expect(bol().disabled).toBe(false);
    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("c_1-1.pdf", 1), dosyaNesnesi("c_2-2.pdf", 1)]);
    await tikla(bol());
    expect(apiMock.islem.mock.calls[0][0]).toEqual({ islem: "bol", girdiler: ["id-c.pdf"], parametreler: { araliklar: [[1, 1], [2, 2]] } });
    expect(satirAdlari()).toEqual(["c.pdf", "c_1-1.pdf", "c_2-2.pdf"]);
    expect(seciliSatir()!.getAttribute("data-dosya-id")).toBe("id-c_1-1.pdf");

    // her sayfa ayrı: seçimi c.pdf'e geri al, radyoyu değiştir
    await tikla(Array.from(kap.querySelectorAll<HTMLButtonElement>('li[data-dosya-id="id-c.pdf"] button')).find((b) => b.title === "c.pdf"));
    const radyolar = Array.from(kap.querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    await tikla(radyolar[1]);
    expect(bol().disabled).toBe(false);
    apiMock.islem.mockResolvedValueOnce([]);
    await tikla(bol());
    expect(apiMock.islem.mock.calls[1][0]).toEqual({ islem: "bol", girdiler: ["id-c.pdf"], parametreler: { her_n: 1 } });
  });

  it("sıkıştır varsayılan 'ebook'; damga varsayılan parametreleri", async () => {
    await ciz();
    await yukleDosyalar(["d.pdf"]);
    apiMock.islem.mockResolvedValue([]);
    await tikla(dugme("Sıkıştır"));
    expect(apiMock.islem.mock.calls[0][0]).toEqual({ islem: "sikistir", girdiler: ["id-d.pdf"], parametreler: { seviye: "ebook" } });
    await tikla(dugme("Damgala"));
    expect(apiMock.islem.mock.calls[1][0]).toEqual({
      islem: "damga",
      girdiler: ["id-d.pdf"],
      parametreler: { metin: "ASLI GİBİDİR", konum: "sag-ust", sayfalar: "hepsi", punto: 12, renk: "#b00020" },
    });
  });

  it("503 → hata şeridi sunucu/istemci mesajını gösterir, kapatılır", async () => {
    await ciz();
    await yukleDosyalar(["e.pdf"]);
    apiMock.islem.mockRejectedValueOnce(new PdfAraclariApiError(503, "Sistem şu anda meşgul; birkaç dakika sonra tekrar deneyin.", "sistem_mesgul"));
    await tikla(dugme("Sıkıştır"));
    const serit = kap.querySelector('[data-testid="tezgah-hatasi"]')!;
    expect(serit.textContent).toContain("Sistem şu anda meşgul");
    expect(satirAdlari()).toEqual(["e.pdf"]); // çıktı yok
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Hatayı kapat"]')!);
    expect(kap.querySelector('[data-testid="tezgah-hatasi"]')).toBeNull();
  });

  it("indir seçili dosyayı sunucudan gelen adla indirir", async () => {
    await ciz();
    await yukleDosyalar(["f.pdf"]);
    expect(indirDugmesi().textContent).toContain("İndir: f.pdf");
    await tikla(indirDugmesi());
    expect(apiMock.indir).toHaveBeenCalledWith("id-f.pdf", "f.pdf");
  });

  it("listeden kaldır yalnız istemcide; seçim kalan dosyaya geçer", async () => {
    await ciz();
    await yukleDosyalar(["g.pdf", "h.pdf"]);
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Listeden kaldır: h.pdf"]')!);
    expect(satirAdlari()).toEqual(["g.pdf"]);
    expect(seciliSatir()!.getAttribute("data-dosya-id")).toBe("id-g.pdf");
    expect(apiMock.islem).not.toHaveBeenCalled();
  });
});

describe("rota ve menü bekçisi", () => {
  const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const oku = (p: string) => readFileSync(path.join(SRC, p), "utf8");

  it("App.tsx rotayı lazy (importWithReload) bağlar; kabuk altında, yönetici kısıtı yok", () => {
    const app = oku("App.tsx");
    expect(app).toMatch(/const BelgeTezgahiPage = lazy\(\(\) => importWithReload\(\(\) => import\("\.\/pages\/BelgeTezgahiPage"\)\)\);/);
    expect(app).toContain('<Route path="/belge-tezgahi" element={<BelgeTezgahiPage />} />');
    expect(app).not.toMatch(/ProtectedAdminRoute>\s*<BelgeTezgahiPage/);
  });

  it("menü yolu önden yüklenebilir (sayfaOnYukleme haritası)", () => {
    expect(oku("lib/sayfaOnYukleme.ts")).toContain('"/belge-tezgahi": [() => import("../pages/BelgeTezgahiPage")]');
  });
});
