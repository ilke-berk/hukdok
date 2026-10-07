// @vitest-environment jsdom
// SayfaIzgarasi + SayfaKarti + usePdfTezgah sayfa düzeni (G271). `lib/pdfAraclariApi` sahte (islem, onizlemeBlob),
// IntersectionObserver sahte (yalnız tetiklenen kartlar önizleme çeker), DndContext işleyicisi yakalanıp doğrudan çağrılır
// (AdminPage.listeler.test deseni). Kilitlenen davranışlar: 200 sayfada yalnız görünür kartların fetch'i; önizleme hatası
// ızgarayı durdurmaz; döndür + sil + sürükle → tek `sayfa_duzenle` gövdesi (silinen yok, sıra listedeki, dondur mod 360),
// çıktı seçilir ve girdinin yerel düzeni sıfırlanır; değişiklik yoksa Uygula kapalı; Sıfırla; tüm sayfalar silinemez;
// shift ile aralık seçimi → böl "seçili sayfalar" `[[1,3],[7,7]]`; saf yardımcılar.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import type { DndContextProps, DragEndEvent } from "@dnd-kit/core";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ islem: vi.fn(), onizlemeBlob: vi.fn() }));
vi.mock("@/lib/pdfAraclariApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pdfAraclariApi")>()),
  ...apiMock,
}));

const dnd = vi.hoisted(() => ({ props: null as DndContextProps | null }));
vi.mock("@dnd-kit/core", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@dnd-kit/core")>();
  const DndContext = (props: DndContextProps) => {
    dnd.props = props;
    return <actual.DndContext {...props} />;
  };
  return { ...actual, DndContext };
});

import { IslemPaneli } from "./IslemPaneli";
import { SayfaIzgarasi } from "./SayfaIzgarasi";
import {
  sayfaDegisikligiVar,
  sayfaDuzenleParametreleri,
  seciliSayfalardanAraliklar,
  usePdfTezgah,
  varsayilanSayfaDuzeni,
  type PdfTezgah,
} from "./usePdfTezgah";
import type { Dosya } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// ── sahte IntersectionObserver ───────────────────────────────────────────────
type Kayit = { el: Element; cb: IntersectionObserverCallback };
const gozcu = { kayitlar: [] as Kayit[] };
class SahteGozcu {
  private cb: IntersectionObserverCallback;
  constructor(cb: IntersectionObserverCallback) {
    this.cb = cb;
  }
  observe(el: Element) {
    gozcu.kayitlar.push({ el, cb: this.cb });
  }
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}
async function gorunurYap(no: number) {
  const kayit = gozcu.kayitlar.find((k) => k.el.getAttribute("data-sayfa-no") === String(no))!;
  expect(kayit, `sayfa ${no} gözlenmiyor`).toBeDefined();
  await act(async () => {
    kayit.cb([{ isIntersecting: true, target: kayit.el } as IntersectionObserverEntry], {} as IntersectionObserver);
  });
}

const dosyaNesnesi = (id: string, sayfa: number): Dosya => ({
  id,
  ad: `${id}.pdf`,
  sayfa,
  boyut: 1000,
  sayfalar: Array.from({ length: sayfa }, (_, i) => ({ no: i + 1, genislik: 595, yukseklik: 842 })),
});

let kap: HTMLDivElement;
let kok: Root;
let tezgah: PdfTezgah;

function Harness() {
  const t = usePdfTezgah();
  tezgah = t;
  return (
    <div>
      <span data-testid="secili">{t.seciliId ?? ""}</span>
      <span data-testid="hata">{t.hata ?? ""}</span>
      {t.secili && t.sayfaDuzeni && (
        <SayfaIzgarasi
          key={t.secili.id}
          dosya={t.secili}
          duzen={t.sayfaDuzeni}
          degisiklikVar={t.sayfaDegisikligi}
          uygulaniyor={t.surenIslem === "sayfa_duzenle"}
          onTasi={t.sayfaTasi}
          onDondur={t.sayfaDondur}
          onSil={t.sayfaSilToggle}
          onSec={t.sayfaSec}
          onHepsiniSec={t.sayfalariSec}
          onSifirla={t.sayfaDuzeniniSifirla}
          onUygula={() => void t.sayfaDuzeniniUygula()}
        />
      )}
      <IslemPaneli
        secili={t.secili}
        isaretliler={t.isaretliDosyalar}
        surenIslem={t.surenIslem}
        indiriliyor={false}
        onIslem={(istek) => void t.islemKos(istek)}
        onIndir={() => undefined}
        seciliSayfalar={t.sayfaDuzeni?.secili ?? []}
        sayfaDegisikligi={t.sayfaDegisikligi}
        onSayfaDuzenle={() => void t.sayfaDuzeniniUygula()}
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

const dugme = (ad: string) =>
  Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad)!;
const kart = (no: number) => kap.querySelector<HTMLLIElement>(`li[data-sayfa-no="${no}"]`)!;
const kartSirasi = () => Array.from(kap.querySelectorAll<HTMLLIElement>("li[data-sayfa-no]")).map((li) => Number(li.dataset.sayfaNo));
const etiketli = (ad: string) => kap.querySelector<HTMLButtonElement | HTMLInputElement>(`[aria-label="${ad}"]`)!;
const tikla = (el: HTMLElement) => act(async () => el.click());
const surukle = (aktif: number, hedef: number) =>
  act(async () => {
    dnd.props!.onDragEnd?.({ active: { id: aktif }, over: { id: hedef } } as unknown as DragEndEvent);
  });

beforeEach(() => {
  gozcu.kayitlar = [];
  (globalThis as unknown as { IntersectionObserver: typeof SahteGozcu }).IntersectionObserver = SahteGozcu;
  Object.assign(URL, { createObjectURL: vi.fn(() => "blob:onizleme"), revokeObjectURL: vi.fn() });
  apiMock.islem.mockReset();
  apiMock.onizlemeBlob.mockReset();
  apiMock.onizlemeBlob.mockResolvedValue(new Blob([new Uint8Array([1])]));
  dnd.props = null;
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("yardımcılar", () => {
  it("seciliSayfalardanAraliklar: ardışık bloklar, sıra bağımsız, tekrarsız", () => {
    expect(seciliSayfalardanAraliklar([1, 2, 3, 7])).toEqual([[1, 3], [7, 7]]);
    expect(seciliSayfalardanAraliklar([7, 3, 2, 1, 2])).toEqual([[1, 3], [7, 7]]);
    expect(seciliSayfalardanAraliklar([])).toEqual([]);
    expect(seciliSayfalardanAraliklar([5])).toEqual([[5, 5]]);
  });

  it("sayfaDuzenleParametreleri: silinen yok, sıra listedeki, dondur yalnız 0 dışında", () => {
    const duzen = varsayilanSayfaDuzeni(dosyaNesnesi("x", 3));
    expect(sayfaDegisikligiVar(duzen)).toBe(false);
    duzen.sayfalar = [
      { no: 2, dondur: 180, silindi: false },
      { no: 3, dondur: 0, silindi: true },
      { no: 1, dondur: 0, silindi: false },
    ];
    expect(sayfaDegisikligiVar(duzen)).toBe(true);
    expect(sayfaDuzenleParametreleri(duzen)).toEqual({ sayfalar: [{ no: 2, dondur: 180 }, { no: 1 }] });
  });

  it("sayfaDegisikligiVar: yalnız döndürme ya da yalnız silme de değişikliktir", () => {
    const d = varsayilanSayfaDuzeni(dosyaNesnesi("x", 2));
    expect(sayfaDegisikligiVar({ ...d, sayfalar: [{ no: 1, dondur: 90, silindi: false }, d.sayfalar[1]] })).toBe(true);
    expect(sayfaDegisikligiVar({ ...d, sayfalar: [d.sayfalar[0], { no: 2, dondur: 0, silindi: true }] })).toBe(true);
    expect(sayfaDegisikligiVar({ ...d, secili: [1, 2] })).toBe(false); // seçim sunucuya gitmez
  });
});

describe("önizleme (tembel)", () => {
  it("200 sayfada kartlar role=listitem; yalnız görünür olanlar fetch eder, blob URL img'ye biner", async () => {
    await ciz([dosyaNesnesi("buyuk", 200)]);
    expect(kap.querySelectorAll('[role="list"] > li[role="listitem"]').length).toBe(200);
    expect(gozcu.kayitlar.length).toBe(200);
    expect(apiMock.onizlemeBlob).not.toHaveBeenCalled();
    for (const no of [1, 2, 3, 4, 5]) await gorunurYap(no);
    expect(apiMock.onizlemeBlob).toHaveBeenCalledTimes(5);
    expect(apiMock.onizlemeBlob.mock.calls.map((c) => c.slice(0, 3))).toEqual([1, 2, 3, 4, 5].map((no) => ["buyuk", no, 240]));
    expect(kart(1).dataset.onizleme).toBe("hazir");
    expect(kart(1).querySelector("img")!.getAttribute("src")).toBe("blob:onizleme");
    expect(kart(1).querySelector("img")!.getAttribute("loading")).toBe("lazy");
    expect(kart(6).dataset.onizleme).toBe("bekliyor");
    expect(kart(6).querySelector("img")).toBeNull();
  });

  it("önizleme hatası → kartta 'Önizleme yok', döndürme yine çalışır; kart kalkınca blob URL serbest bırakılır", async () => {
    apiMock.onizlemeBlob.mockRejectedValueOnce(new Error("404")).mockResolvedValue(new Blob([new Uint8Array([1])]));
    await ciz([dosyaNesnesi("d", 2)]);
    await gorunurYap(1);
    await gorunurYap(2);
    expect(kart(1).dataset.onizleme).toBe("hata");
    expect(kart(1).textContent).toContain("Önizleme yok");
    expect(kart(2).dataset.onizleme).toBe("hazir");
    await tikla(etiketli("Sayfa 1'i döndür"));
    expect(kart(1).getAttribute("aria-label")).toContain("90° döndürülmüş");
    await act(async () => {
      tezgah.listedenKaldir("d");
    });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:onizleme");
  });
});

describe("sayfa düzeni → sayfa_duzenle", () => {
  it("döndür + sil + sürükle → tek istek; çıktı seçilir, girdinin yerel düzeni sıfırlanır", async () => {
    await ciz([dosyaNesnesi("d1", 3)]);
    expect(dugme("Uygula").disabled).toBe(true);
    expect(dugme("Sayfa düzenle").disabled).toBe(true);

    await tikla(etiketli("Sayfa 2'i döndür"));
    await tikla(etiketli("Sayfa 2'i döndür")); // 180
    await tikla(etiketli("Sayfa 3'i sil"));
    expect(kart(3).dataset.silindi).toBe("true");
    expect(etiketli("Sayfa 3'i geri al")).toBeDefined();
    await surukle(1, 2); // 1'i 2'nin yerine → [2,1,3]
    expect(kartSirasi()).toEqual([2, 1, 3]);
    expect(kart(2).getAttribute("aria-label")).toContain("sıra 1");
    expect(dugme("Uygula").disabled).toBe(false);
    expect(dugme("Sayfa düzenle").disabled).toBe(false);

    apiMock.islem.mockResolvedValueOnce([dosyaNesnesi("d1_duzenlenmis", 2)]);
    await tikla(dugme("Uygula"));
    expect(apiMock.islem).toHaveBeenCalledTimes(1);
    expect(apiMock.islem.mock.calls[0][0]).toEqual({
      islem: "sayfa_duzenle",
      girdiler: ["d1"],
      parametreler: { sayfalar: [{ no: 2, dondur: 180 }, { no: 1 }] },
    });
    expect(kap.querySelector('[data-testid="secili"]')!.textContent).toBe("d1_duzenlenmis");
    expect(kartSirasi()).toEqual([1, 2]); // çıktının ızgarası
    expect(tezgah.dosyalar.map((d) => d.id)).toEqual(["d1", "d1_duzenlenmis"]); // girdi listede kalır (K2)

    await act(async () => {
      tezgah.sec("d1");
    });
    expect(kartSirasi()).toEqual([1, 2, 3]); // yerel düzen sıfırlandı
    expect(kart(3).dataset.silindi).toBeUndefined();
    expect(dugme("Uygula").disabled).toBe(true);
  });

  it("dört döndürme = 0 → değişiklik yok; Sıfırla geri alır", async () => {
    await ciz([dosyaNesnesi("d2", 2)]);
    for (let i = 0; i < 4; i++) await tikla(etiketli("Sayfa 1'i döndür"));
    expect(dugme("Uygula").disabled).toBe(true);
    await tikla(etiketli("Sayfa 2'i sil"));
    await surukle(2, 1);
    expect(kartSirasi()).toEqual([2, 1]);
    expect(dugme("Uygula").disabled).toBe(false);
    await tikla(dugme("Sıfırla"));
    expect(kartSirasi()).toEqual([1, 2]);
    expect(kart(2).dataset.silindi).toBeUndefined();
    expect(dugme("Uygula").disabled).toBe(true);
  });

  it("tüm sayfalar silinince uygula istek atmaz, hata yazar", async () => {
    await ciz([dosyaNesnesi("d3", 2)]);
    await tikla(etiketli("Sayfa 1'i sil"));
    await tikla(etiketli("Sayfa 2'i sil"));
    await tikla(dugme("Uygula"));
    expect(apiMock.islem).not.toHaveBeenCalled();
    expect(kap.querySelector('[data-testid="hata"]')!.textContent).toContain("Tüm sayfalar silinemez");
  });

  it("panelin 'Sayfa düzenle' düğmesi ızgaranın Uygula'sıyla aynı isteği atar", async () => {
    await ciz([dosyaNesnesi("d4", 2)]);
    await tikla(etiketli("Sayfa 1'i döndür"));
    apiMock.islem.mockResolvedValueOnce([]);
    await tikla(dugme("Sayfa düzenle"));
    expect(apiMock.islem.mock.calls[0][0]).toEqual({
      islem: "sayfa_duzenle",
      girdiler: ["d4"],
      parametreler: { sayfalar: [{ no: 1, dondur: 90 }, { no: 2 }] },
    });
  });
});

describe("seçim → böl", () => {
  it("tik + shift aralık → [1,2,3,7] → böl 'seçili sayfalar' [[1,3],[7,7]]; silinen sayfa seçimden düşer", async () => {
    await ciz([dosyaNesnesi("d5", 8)]);
    await tikla(etiketli("Sayfa 1'i seç"));
    await act(async () => {
      etiketli("Sayfa 3'i seç").dispatchEvent(new MouseEvent("click", { bubbles: true, shiftKey: true }));
    });
    await tikla(etiketli("Sayfa 7'i seç"));
    expect(tezgah.sayfaDuzeni!.secili.sort((a, b) => a - b)).toEqual([1, 2, 3, 7]);
    expect(kap.textContent).toContain("4 seçili");

    const radyolar = Array.from(kap.querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    await tikla(radyolar[2]); // Seçili sayfalar
    expect(kap.textContent).toContain("1-3, 7");
    apiMock.islem.mockResolvedValueOnce([]);
    await tikla(dugme("Böl"));
    expect(apiMock.islem.mock.calls[0][0]).toEqual({ islem: "bol", girdiler: ["d5"], parametreler: { araliklar: [[1, 3], [7, 7]] } });

    await tikla(etiketli("Sayfa 2'i sil"));
    expect(tezgah.sayfaDuzeni!.secili.sort((a, b) => a - b)).toEqual([1, 3, 7]);
    expect((etiketli("Sayfa 2'i seç") as HTMLInputElement).disabled).toBe(true);
  });

  it("Tümünü seç / Seçimi temizle; seçim yokken 'seçili sayfalar' kipinde Böl kapalı", async () => {
    await ciz([dosyaNesnesi("d6", 3)]);
    const radyolar = Array.from(kap.querySelectorAll<HTMLInputElement>('input[type="radio"]'));
    await tikla(radyolar[2]);
    expect(dugme("Böl").disabled).toBe(true);
    await tikla(dugme("Tümünü seç"));
    expect(tezgah.sayfaDuzeni!.secili).toEqual([1, 2, 3]);
    expect(dugme("Böl").disabled).toBe(false);
    await tikla(dugme("Seçimi temizle"));
    expect(tezgah.sayfaDuzeni!.secili).toEqual([]);
  });
});

describe("erişilebilirlik ve klavye", () => {
  it("kartlar role=listitem, Türkçe aria-label'lı döndür/sil/sürükle düğmeleri; klavye sensörü bağlı", async () => {
    await ciz([dosyaNesnesi("d7", 1)]);
    const li = kart(1);
    expect(li.getAttribute("role")).toBe("listitem");
    expect(li.querySelector('button[aria-label="Sayfa 1\'i döndür"]')).not.toBeNull();
    expect(li.querySelector('button[aria-label="Sayfa 1\'i sil"]')).not.toBeNull();
    const tutamac = li.querySelector<HTMLButtonElement>('button[aria-label="Sayfa 1\'i sürükle"]')!;
    expect(tutamac.getAttribute("aria-roledescription")).toBe("sortable"); // dnd-kit attributes (klavye: boşluk + ok)
    expect(dnd.props!.sensors!.length).toBe(2); // Pointer + Keyboard
  });
});
