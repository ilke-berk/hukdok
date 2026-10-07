// @vitest-environment jsdom
// SayfaGorunumu + KarartmaKatmani + NotKatmani + usePdfTezgah çizim durumu (G272). `lib/pdfAraclariApi` sahte (islem,
// onizlemeBlob); overlay genişliği `getBoundingClientRect` sahtesiyle verilir (ölçek 0,5 → 1190 px, ölçek 2 → 297,5 px;
// sayfa 595×842 pt). Kilitlenen davranışlar: kip düğmesi büyük görünümü açar (1200 px önizleme, touch-action none);
// sürüklenen piksel dikdörtgeni → `karart` gövdesinde doğru puan değerleri (iki ölçek), birden çok sayfada birikir, onay
// kutusu olmadan istek GİTMEZ, tek istek → çıktı seçilir + liste temizlenir + aynı sayfada kalınır; küçük alan yok
// sayılır; kırpma; not: tıkla → kutu → metin sınırı (≤ 2.000) → `not` isteği; klavye ←/→; karttan büyüt; dosya değişince
// ızgaraya dönüş; önizleme hatası çizimi durdurmaz.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ islem: vi.fn(), onizlemeBlob: vi.fn() }));
vi.mock("@/lib/pdfAraclariApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pdfAraclariApi")>()),
  ...apiMock,
}));

import { IslemPaneli } from "./IslemPaneli";
import { KARARTMA_ONAY_METNI, KarartmaListesi } from "./KarartmaKatmani";
import { BUYUK_ONIZLEME_GENISLIK, SayfaGorunumu } from "./SayfaGorunumu";
import { SayfaIzgarasi } from "./SayfaIzgarasi";
import { notMetniGecerli, usePdfTezgah, type PdfTezgah } from "./usePdfTezgah";
import type { Dosya, IslemIstegi } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const dosyaNesnesi = (id: string, sayfa: number, genislik = 595, yukseklik = 842): Dosya => ({
  id,
  ad: `${id}.pdf`,
  sayfa,
  boyut: 1000,
  sayfalar: Array.from({ length: sayfa }, (_, i) => ({ no: i + 1, genislik, yukseklik })),
});

let kap: HTMLDivElement;
let kok: Root;
let tezgah: PdfTezgah;

/** BelgeTezgahiPage'in orta yuvası + karartma listesi + işlem paneli (sayfa ile aynı bağlama). */
function Harness() {
  const t = usePdfTezgah();
  tezgah = t;
  return (
    <div>
      <span data-testid="secili">{t.seciliId ?? ""}</span>
      <span data-testid="hata">{t.hata ?? ""}</span>
      <section data-slot="sayfalar">
        {t.secili && t.buyukSayfa !== null ? (
          <SayfaGorunumu
            key={t.secili.id}
            dosya={t.secili}
            sayfaNo={t.buyukSayfa}
            cizimKipi={t.cizimKipi}
            karartmaAlanlari={t.karartmaAlanlari}
            mesgul={t.surenIslem !== null}
            onIzgara={t.izgarayaDon}
            onSayfaGit={t.buyukSayfayaGit}
            onKip={t.cizimKipiniAyarla}
            onKarartmaEkle={t.karartmaEkle}
            onNotEkle={t.notEkle}
          />
        ) : (
          t.secili &&
          t.sayfaDuzeni && (
            <SayfaIzgarasi
              key={t.secili.id}
              dosya={t.secili}
              duzen={t.sayfaDuzeni}
              degisiklikVar={t.sayfaDegisikligi}
              uygulaniyor={false}
              onTasi={t.sayfaTasi}
              onDondur={t.sayfaDondur}
              onSil={t.sayfaSilToggle}
              onSec={t.sayfaSec}
              onHepsiniSec={t.sayfalariSec}
              onSifirla={t.sayfaDuzeniniSifirla}
              onUygula={() => undefined}
              onBuyut={t.sayfayiBuyut}
            />
          )
        )}
      </section>
      {t.secili && (t.karartmaAlanlari.length > 0 || t.cizimKipi === "karart") && (
        <KarartmaListesi
          key={t.secili.id}
          alanlar={t.karartmaAlanlari}
          mesgul={t.surenIslem !== null}
          onSil={t.karartmaSil}
          onTemizle={t.karartmalariTemizle}
          onKarart={() => void t.karartmayiUygula()}
        />
      )}
      <IslemPaneli
        secili={t.secili}
        isaretliler={[]}
        surenIslem={t.surenIslem}
        indiriliyor={false}
        onIslem={() => undefined}
        onIndir={() => undefined}
        cizimKipi={t.cizimKipi}
        onCizimKipi={t.cizimKipiniAyarla}
        karartmaSayisi={t.karartmaAlanlari.length}
      />
    </div>
  );
}

async function ciz(dosyalar: Dosya[]) {
  await act(async () => {
    kok.render(<Harness />);
  });
  await act(async () => {
    tezgah.dosyaEkle(dosyalar);
  });
}

/** Overlay genişliği (px) → ölçek = 595 / genişlik. */
function olcekAyarla(genislik: number, yukseklik = (genislik * 842) / 595) {
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    return { left: 0, top: 0, right: genislik, bottom: yukseklik, width: genislik, height: yukseklik, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
  });
}

const dugme = (ad: string) =>
  Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim().replace(/\s*·.*$/, "") === ad)!;
const panelDugmesi = (ad: string) =>
  Array.from(kap.querySelectorAll<HTMLButtonElement>('[data-testid="islem-paneli"] button')).find((b) => b.textContent?.trim().startsWith(ad))!;
const gorunum = () => kap.querySelector<HTMLDivElement>('[data-testid="sayfa-gorunumu"]');
const katmanKutusu = () => kap.querySelector<HTMLDivElement>('[data-testid="cizim-katmani"]')!;
const karartmaSvg = () => kap.querySelector<SVGSVGElement>('[data-testid="karartma-katmani"]')!;
const notSvg = () => kap.querySelector<SVGSVGElement>('[data-testid="not-katmani"]')!;
const sayac = () => kap.querySelector('[data-testid="sayfa-sayaci"]')!.textContent;
const satirlar = () => Array.from(kap.querySelectorAll('[data-testid="karartma-satiri"]')).map((li) => li.textContent?.replace(/\s+/g, " ").trim());
const onay = () => kap.querySelector<HTMLInputElement>('[data-testid="karartma-onayi"]')!;
const tikla = (el: HTMLElement | null | undefined) => {
  expect(el).toBeTruthy();
  return act(async () => el!.click());
};
const isaret = (el: Element, tur: string, x: number, y: number) =>
  act(async () => {
    el.dispatchEvent(new PointerEvent(tur, { bubbles: true, cancelable: true, clientX: x, clientY: y, pointerId: 1, pointerType: "mouse", button: 0 }));
  });
async function surukleCiz(x0: number, y0: number, x1: number, y1: number) {
  const svg = karartmaSvg();
  await isaret(svg, "pointerdown", x0, y0);
  await isaret(svg, "pointermove", (x0 + x1) / 2, (y0 + y1) / 2);
  expect(svg.querySelector('[data-testid="karartma-taslagi"]'), "sürüklerken taslak çizilir").not.toBeNull();
  await isaret(svg, "pointerup", x1, y1);
}
const tus = (key: string, hedef: EventTarget = window) =>
  act(async () => {
    hedef.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
async function yaz(el: HTMLTextAreaElement, deger: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
const sonIstek = () => apiMock.islem.mock.calls.at(-1)![0] as IslemIstegi;

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:buyuk"), revokeObjectURL: vi.fn() });
  apiMock.islem.mockReset();
  apiMock.onizlemeBlob.mockReset();
  apiMock.onizlemeBlob.mockResolvedValue(new Blob([new Uint8Array([1])]));
  olcekAyarla(1190); // ölçek 0,5
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
  vi.restoreAllMocks();
});

describe("büyük görünüm", () => {
  it("panelin Karart düğmesi kipi açar → sayfa 1 büyük görünümde (1200 px önizleme), touch-action none; Izgara düğmesi geri döner, kip açık kalır", async () => {
    await ciz([dosyaNesnesi("d", 3)]);
    expect(gorunum()).toBeNull();
    expect(panelDugmesi("Karart").getAttribute("aria-pressed")).toBe("false");
    await tikla(panelDugmesi("Karart"));
    expect(gorunum()).not.toBeNull();
    expect(sayac()).toBe("Sayfa 1 / 3");
    expect(apiMock.onizlemeBlob).toHaveBeenLastCalledWith("d", 1, BUYUK_ONIZLEME_GENISLIK);
    expect(BUYUK_ONIZLEME_GENISLIK).toBe(1200);
    expect(gorunum()!.querySelector("img")!.getAttribute("src")).toBe("blob:buyuk");
    expect(katmanKutusu().style.touchAction).toBe("none");
    expect(karartmaSvg().dataset.aktif).toBe("true");
    expect(notSvg().dataset.aktif).toBeUndefined();
    expect(panelDugmesi("Karart").getAttribute("aria-pressed")).toBe("true");
    // kipi kapat → kaydırma serbest
    await tikla(kap.querySelector<HTMLButtonElement>('[data-testid="kip-karart"]'));
    expect(katmanKutusu().style.touchAction).toBe("auto");
    expect(karartmaSvg().dataset.aktif).toBeUndefined();
    await tikla(dugme("Izgara"));
    expect(gorunum()).toBeNull();
    expect(kap.querySelector('[data-testid="sayfa-izgarasi"]')).not.toBeNull();
  });

  it("karttaki 'büyüt' sayfayı açar (kip kapalı: overlay tıklamayı geçirir); önceki/sonraki + ←/→ sınırda durur; metin alanında ok tuşu yok sayılır", async () => {
    await ciz([dosyaNesnesi("d", 2)]);
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Sayfa 2\'i büyüt"]'));
    expect(sayac()).toBe("Sayfa 2 / 2");
    expect(karartmaSvg().classList.contains("pointer-events-none")).toBe(true);
    expect(notSvg().classList.contains("pointer-events-none")).toBe(true);
    const sonraki = kap.querySelector<HTMLButtonElement>('button[aria-label="Sonraki sayfa"]')!;
    expect(sonraki.disabled).toBe(true);
    await tus("ArrowRight");
    expect(sayac()).toBe("Sayfa 2 / 2");
    await tus("ArrowLeft");
    expect(sayac()).toBe("Sayfa 1 / 2");
    expect(apiMock.onizlemeBlob).toHaveBeenLastCalledWith("d", 1, 1200);
    expect(kap.querySelector<HTMLButtonElement>('button[aria-label="Önceki sayfa"]')!.disabled).toBe(true);
    await tus("ArrowLeft");
    expect(sayac()).toBe("Sayfa 1 / 2");
    await tikla(sonraki);
    expect(sayac()).toBe("Sayfa 2 / 2");
    // metin alanındaki ok tuşu sayfa değiştirmez
    const girdi = document.createElement("textarea");
    kap.appendChild(girdi);
    await tus("ArrowLeft", girdi);
    expect(sayac()).toBe("Sayfa 2 / 2");
  });

  it("başka dosya seçilince ızgaraya döner; listeden kaldırılınca da", async () => {
    await ciz([dosyaNesnesi("a", 2), dosyaNesnesi("b", 5)]);
    expect(tezgah.seciliId).toBe("a");
    await act(async () => tezgah.sayfayiBuyut(2));
    expect(sayac()).toBe("Sayfa 2 / 2");
    await act(async () => tezgah.sec("b"));
    expect(gorunum()).toBeNull();
    await act(async () => tezgah.sayfayiBuyut(4));
    expect(sayac()).toBe("Sayfa 4 / 5");
    await act(async () => tezgah.listedenKaldir("b"));
    expect(tezgah.seciliId).toBe("a");
    expect(gorunum()).toBeNull();
  });

  it("önizleme hatası → 'Önizleme yok'; çizim katmanı yine çalışır", async () => {
    await ciz([dosyaNesnesi("d", 1)]); // (ızgara kartı kendi önizlemesini çeker; büyük görünümünki ayrı istek)
    apiMock.onizlemeBlob.mockRejectedValueOnce(new Error("500"));
    await tikla(panelDugmesi("Karart"));
    expect(gorunum()!.textContent).toContain("Önizleme yok");
    await surukleCiz(100, 200, 300, 500);
    expect(satirlar()).toEqual(["s. 1 · 100×150 pt"]);
  });
});

describe("karartma", () => {
  it("ölçek 0,5: sürüklenen piksel dikdörtgeni → puan; iki sayfada birikir; onay olmadan istek gitmez; onay → tek `karart`; çıktı seçilir, liste temizlenir, aynı sayfada kalınır", async () => {
    await ciz([dosyaNesnesi("d", 3)]);
    await tikla(panelDugmesi("Karart"));
    expect(kap.querySelector('[data-testid="karartma-listesi"]')!.textContent).toContain("0 alan");

    await surukleCiz(100, 200, 300, 500); // → 50,100 → 150,250
    expect(satirlar()).toEqual(["s. 1 · 100×150 pt"]);
    expect(karartmaSvg().querySelectorAll('[data-testid="karartma-alani"]').length).toBe(1);
    expect(karartmaSvg().querySelector('[data-testid="karartma-taslagi"]')).toBeNull();
    const rect = karartmaSvg().querySelector('[data-testid="karartma-alani"]')!;
    expect([rect.getAttribute("x"), rect.getAttribute("y"), rect.getAttribute("width"), rect.getAttribute("height")]).toEqual(["50", "100", "100", "150"]);
    expect(karartmaSvg().getAttribute("viewBox")).toBe("0 0 595 842");
    expect(panelDugmesi("Karart").textContent).toContain("· 1");

    await tus("ArrowRight");
    expect(sayac()).toBe("Sayfa 2 / 3");
    expect(karartmaSvg().querySelectorAll('[data-testid="karartma-alani"]').length).toBe(0); // 1. sayfanın alanı burada çizilmez
    await surukleCiz(1190, 1684, 1000, 1400); // ters çizim, köşe → 595,842 ↔ 500,700
    expect(satirlar()).toEqual(["s. 1 · 100×150 pt", "s. 2 · 95×142 pt"]);
    expect(karartmaSvg().querySelectorAll('[data-testid="karartma-alani"]').length).toBe(1);

    // onay yok → Karart kapalı, tıklama istek atmaz
    const karartDugmesi = Array.from(kap.querySelectorAll<HTMLButtonElement>('[data-testid="karartma-listesi"] button')).find((b) => b.textContent?.trim() === "Karart")!;
    expect(onay().checked).toBe(false);
    expect(karartDugmesi.disabled).toBe(true);
    await tikla(karartDugmesi);
    expect(apiMock.islem).not.toHaveBeenCalled();
    expect(kap.textContent).toContain(KARARTMA_ONAY_METNI);

    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("d_karartilmis", 3)]);
    await tikla(onay());
    expect(karartDugmesi.disabled).toBe(false);
    await tikla(karartDugmesi);
    expect(apiMock.islem).toHaveBeenCalledTimes(1);
    expect(sonIstek()).toEqual({
      islem: "karart",
      girdiler: ["d"],
      parametreler: {
        alanlar: [
          { sayfa: 1, x0: 50, y0: 100, x1: 150, y1: 250 },
          { sayfa: 2, x0: 500, y0: 700, x1: 595, y1: 842 },
        ],
      },
    });
    expect(tezgah.seciliId).toBe("d_karartilmis");
    expect(sayac()).toBe("Sayfa 2 / 3"); // çıktıda aynı sayfa: metnin gittiği görülür
    expect(apiMock.onizlemeBlob).toHaveBeenLastCalledWith("d_karartilmis", 2, 1200);
    expect(tezgah.karartmaAlanlari).toEqual([]);
    expect(satirlar()).toEqual([]);
    expect(karartmaSvg().querySelectorAll('[data-testid="karartma-alani"]').length).toBe(0);
    // girdi dosyasının listesi de temizlendi (K2: girdi listede kalır)
    await act(async () => tezgah.sec("d"));
    expect(tezgah.karartmaAlanlari).toEqual([]);
  });

  it("ölçek 2 (297,5 px görüntü): piksel değerleri iki katı puan", async () => {
    olcekAyarla(297.5);
    await ciz([dosyaNesnesi("d", 1)]);
    await tikla(panelDugmesi("Karart"));
    await surukleCiz(10, 20, 60, 120); // → 20,40 → 120,240
    expect(satirlar()).toEqual(["s. 1 · 100×200 pt"]);
    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("c", 1)]);
    await tikla(onay());
    await tikla(Array.from(kap.querySelectorAll<HTMLButtonElement>('[data-testid="karartma-listesi"] button')).find((b) => b.textContent?.trim() === "Karart"));
    expect(sonIstek().parametreler).toEqual({ alanlar: [{ sayfa: 1, x0: 20, y0: 40, x1: 120, y1: 240 }] });
  });

  it("döndürülmüş sayfa (842×595 görünür): yalnız ölçek, ek dönüşüm yok", async () => {
    olcekAyarla(1684, 1190);
    await ciz([dosyaNesnesi("yan", 1, 842, 595)]);
    await tikla(panelDugmesi("Karart"));
    expect(karartmaSvg().getAttribute("viewBox")).toBe("0 0 842 595");
    await surukleCiz(200, 100, 400, 300);
    expect(tezgah.karartmaAlanlari).toEqual([{ sayfa: 1, x0: 100, y0: 50, x1: 200, y1: 150 }]);
  });

  it("4×4 pt altındaki alan yok sayılır; sayfa dışına taşan sürükleme kırpılır; satır silme ve tümünü kaldır", async () => {
    await ciz([dosyaNesnesi("d", 1)]);
    await tikla(panelDugmesi("Karart"));
    await surukleCiz(10, 10, 16, 40); // 3×15 pt → yok
    expect(satirlar()).toEqual([]);
    await surukleCiz(10, 10, 100, 17); // 45×3,5 pt → yok
    expect(satirlar()).toEqual([]);
    expect(tezgah.karartmaEkle({ sayfa: 1, x0: 0, y0: 0, x1: 3, y1: 3 })).toBe(false);
    await surukleCiz(-100, -100, 5000, 5000);
    expect(tezgah.karartmaAlanlari).toEqual([{ sayfa: 1, x0: 0, y0: 0, x1: 595, y1: 842 }]);
    await surukleCiz(20, 20, 60, 60);
    expect(satirlar().length).toBe(2);
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Alan 1\'i sil"]'));
    expect(tezgah.karartmaAlanlari).toEqual([{ sayfa: 1, x0: 10, y0: 10, x1: 30, y1: 30 }]);
    await tikla(dugme("Tümünü kaldır"));
    expect(tezgah.karartmaAlanlari).toEqual([]);
    expect(tezgah.karartmayiUygula && (await tezgah.karartmayiUygula())).toBeNull();
    expect(apiMock.islem).not.toHaveBeenCalled();
  });

  it("kip kapalıyken sürükleme alan eklemez; işlem sürerken de", async () => {
    await ciz([dosyaNesnesi("d", 1)]);
    await act(async () => tezgah.sayfayiBuyut(1));
    const svg = karartmaSvg();
    await isaret(svg, "pointerdown", 100, 100);
    await isaret(svg, "pointerup", 300, 300);
    expect(tezgah.karartmaAlanlari).toEqual([]);
  });
});

describe("not", () => {
  it("kip → tıkla → kutu; boş metin ve 2.001 karakter kapalı; metin → tek `not` isteği (puan koordinatı); çıktı seçilir, kutu kapanır", async () => {
    await ciz([dosyaNesnesi("d", 2)]);
    await tikla(panelDugmesi("Not"));
    expect(gorunum()).not.toBeNull();
    expect(notSvg().dataset.aktif).toBe("true");
    expect(karartmaSvg().dataset.aktif).toBeUndefined();
    expect(katmanKutusu().style.touchAction).toBe("none");
    expect(kap.querySelector('[data-testid="not-kutusu"]')).toBeNull();

    await isaret(notSvg(), "pointerdown", 100, 200); // → (50, 100) pt
    const kutu = kap.querySelector<HTMLDivElement>('[data-testid="not-kutusu"]')!;
    expect(kutu).not.toBeNull();
    expect(kutu.textContent).toContain("(50, 100)");
    expect(notSvg().querySelector('[data-testid="not-noktasi"]')!.getAttribute("transform")).toBe("translate(50 100)");
    const ekle = Array.from(kutu.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === "Notu ekle")!;
    const alan = kutu.querySelector("textarea")!;
    expect(ekle.disabled).toBe(true);
    await yaz(alan, "   ");
    expect(ekle.disabled).toBe(true);
    await yaz(alan, "x".repeat(2001));
    expect(ekle.disabled).toBe(true);
    expect(kutu.querySelector('[data-testid="not-sayac"]')!.textContent).toBe("2001 / 2000");
    await tikla(ekle);
    expect(apiMock.islem).not.toHaveBeenCalled();
    expect(notMetniGecerli("x".repeat(2000))).toBe(true);

    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("d_notlu", 2)]);
    await yaz(alan, "  Dikkat: tebliğ tarihi  ");
    expect(ekle.disabled).toBe(false);
    await tikla(ekle);
    expect(apiMock.islem).toHaveBeenCalledTimes(1);
    expect(sonIstek()).toEqual({ islem: "not", girdiler: ["d"], parametreler: { sayfa: 1, x: 50, y: 100, metin: "Dikkat: tebliğ tarihi" } });
    expect(tezgah.seciliId).toBe("d_notlu");
    expect(sayac()).toBe("Sayfa 1 / 2");
    expect(kap.querySelector('[data-testid="not-kutusu"]')).toBeNull();

    // zincir: ikinci not çıktıya eklenir
    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("d_notlu2", 2)]);
    await isaret(notSvg(), "pointerdown", 20, 20);
    await yaz(kap.querySelector("textarea")!, "İkinci");
    await tikla(Array.from(kap.querySelectorAll<HTMLButtonElement>('[data-testid="not-kutusu"] button')).find((b) => b.textContent?.trim() === "Notu ekle"));
    expect(sonIstek().girdiler).toEqual(["d_notlu"]);
    expect(tezgah.seciliId).toBe("d_notlu2");
  });

  it("sayfa değişince bekleyen nokta düşer; Vazgeç ve Escape kutuyu kapatır; tezgah.notEkle sınırları da uygular", async () => {
    await ciz([dosyaNesnesi("d", 2)]);
    await tikla(panelDugmesi("Not"));
    await isaret(notSvg(), "pointerdown", 100, 100);
    expect(kap.querySelector('[data-testid="not-kutusu"]')).not.toBeNull();
    await tus("ArrowRight");
    expect(sayac()).toBe("Sayfa 2 / 2");
    expect(kap.querySelector('[data-testid="not-kutusu"]')).toBeNull();
    await isaret(notSvg(), "pointerdown", 100, 100);
    await tikla(dugme("Vazgeç"));
    expect(kap.querySelector('[data-testid="not-kutusu"]')).toBeNull();
    await isaret(notSvg(), "pointerdown", 100, 100);
    await tus("Escape", kap.querySelector("textarea")!);
    expect(kap.querySelector('[data-testid="not-kutusu"]')).toBeNull();
    expect(await tezgah.notEkle({ sayfa: 1, x: 1, y: 1, metin: " " })).toBeNull();
    expect(await tezgah.notEkle({ sayfa: 1, x: 1, y: 1, metin: "y".repeat(2001) })).toBeNull();
    expect(apiMock.islem).not.toHaveBeenCalled();
  });
});
