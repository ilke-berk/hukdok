// @vitest-environment jsdom
// Lexis'in dört yan sekmesi örnek adaptörle: Geçmiş (koşu logu), Kütüphane (filtre + okuyucu + karar bankası),
// Kart bağı (K8: kartı insan seçer, seçim geri alınır), Şirketler (profil + kriter tablosu, kaydedilmemiş
// değişiklikte onay).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactElement } from "react";
import { createRoot, type Root } from "react-dom/client";

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const confirmMock = vi.hoisted(() => ({ fn: vi.fn(async (_opts: unknown) => true) }));
vi.mock("@/hooks/useConfirm", () => ({ useConfirm: () => confirmMock.fn }));

import { GecmisTablosu } from "./GecmisTablosu";
import { KartBagiListesi } from "./KartBagiListesi";
import { KutuphaneTarayici } from "./KutuphaneTarayici";
import { SirketProfilleri } from "./SirketProfilleri";
import { lexisApi, ornekDurumuSifirla, ornekGecikmeAyarla } from "@/lib/lexisApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;

async function bekle(tur = 8) {
  for (let i = 0; i < tur; i += 1) {
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
  }
}

async function ciz(oge: ReactElement) {
  await act(async () => {
    kok.render(oge);
  });
  await bekle();
}

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

async function yaz(el: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, deger: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
  await bekle();
}

const satirlar = (id: string) => Array.from(kap.querySelectorAll<HTMLElement>(`[data-testid="${id}"]`));
const etiketli = <T extends HTMLElement>(etiket: string) => kap.querySelector<T>(`[aria-label="${etiket}"]`)!;

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  confirmMock.fn.mockReset();
  confirmMock.fn.mockResolvedValue(true);
  Object.values(toastMocks).forEach((m) => m.mockReset());
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("GecmisTablosu", () => {
  it("koşuları en yeni üstte listeler; indirilen koşu işaretlidir", async () => {
    await ciz(<GecmisTablosu />);
    const kosular = satirlar("lexis-kosu");
    expect(kosular).toHaveLength(3);
    expect(kosular[0].textContent).toContain("AK-9002-DR.ORNEK2-HUK");
    expect(kosular[0].textContent).toContain("indirildi");
    expect(kosular[1].textContent).toContain("taslak");
  });

  it("yenileyince yeni koşu görünür", async () => {
    await ciz(<GecmisTablosu />);
    for await (const _olay of lexisApi.taslakYaz({ case_id: 9003, sirket: "QUICK", rapor_turu: "ANA", iskelet: "KISA", belge_idleri: [301], emsal_sha: [] })) {
      // akış sonuna dek tüketilir
    }
    await tikla(dugme("Geçmişi yenile"));
    const kosular = satirlar("lexis-kosu");
    expect(kosular).toHaveLength(4);
    expect(kosular[0].textContent).toContain("QUICK-9003-DR.ORNEK3-HUK");
  });
});

describe("KutuphaneTarayici", () => {
  it("raporları listeler; şirket filtresi ve metin araması daraltır", async () => {
    await ciz(<KutuphaneTarayici />);
    expect(satirlar("lexis-kutuphane-satiri")).toHaveLength(8);

    await yaz(etiketli<HTMLSelectElement>("Şirket"), "AK");
    expect(satirlar("lexis-kutuphane-satiri")).toHaveLength(2);

    await tikla(dugme("Filtreleri temizle"));
    expect(satirlar("lexis-kutuphane-satiri")).toHaveLength(8);

    await yaz(kap.querySelector<HTMLInputElement>('input[type="search"]')!, "gazlı bez");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 300));
    });
    await bekle();
    const kalan = satirlar("lexis-kutuphane-satiri");
    expect(kalan).toHaveLength(1);
    expect(kalan[0].textContent).toContain("Cisim Unutma");
  });

  it("uzmanlık seçenekleri kütüphaneden türetilir", async () => {
    await ciz(<KutuphaneTarayici />);
    const secenekler = Array.from(etiketli<HTMLSelectElement>("Uzmanlık").options).map((o) => o.textContent);
    expect(secenekler).toContain("Dermatoloji");
    expect(secenekler).toContain("Kadın Hastalıkları ve Doğum");
  });

  it("satır maskeli raporu okuyucuda açar", async () => {
    await ciz(<KutuphaneTarayici />);
    await tikla(dugme("9.2002", satirlar("lexis-kutuphane-satiri")[1]));
    const okuyucu = document.querySelector('[data-testid="lexis-emsal-okuyucu"]')!;
    expect(okuyucu.textContent).toContain("maskeli metin");
    expect(okuyucu.textContent).toContain("[HASTA], burun estetiği ameliyatından sonra");
    expect(okuyucu.textContent).toContain("2021/1500 E., 2021/9000 K.");
  });

  it("karar bankası kararları geçtiği raporlarla gösterir", async () => {
    await ciz(<KutuphaneTarayici />);
    await tikla(dugme("Karar bankası"));
    const banka = kap.querySelector('[data-testid="lexis-karar-bankasi"]')!;
    expect(banka.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(banka.textContent).toContain("Yargıtay 3. Hukuk Dairesi");
    await tikla(dugme("rapor 1", banka));
    expect(document.querySelector('[data-testid="lexis-emsal-okuyucu"]')).not.toBeNull();
  });
});

describe("KartBagiListesi", () => {
  it("varsayılan süzgeç seçim bekleyenleri gösterir; sayılar duruma göredir", async () => {
    await ciz(<KartBagiListesi />);
    expect(satirlar("lexis-bag-satiri")).toHaveLength(3);
    const suzgecler = kap.querySelector('[data-testid="lexis-bag-suzgecleri"]')!.textContent;
    expect(suzgecler).toContain("Seçim bekleyen3");
    expect(suzgecler).toContain("Çok aday3");
    expect(suzgecler).toContain("Çelişki1");
    expect(suzgecler).toContain("Bağ yok1");
    expect(suzgecler).toContain("Tümü5");
  });

  it("kartı insan seçer: adaylar yan yana, seçim sonrası satır bekleyenlerden düşer ve geri alınabilir", async () => {
    await ciz(<KartBagiListesi />);
    await tikla(dugme("Kart seç", satirlar("lexis-bag-satiri")[0]));
    const diyalog = document.querySelector<HTMLElement>('[data-testid="lexis-kart-secim"]')!;
    const adaylar = Array.from(diyalog.querySelectorAll<HTMLElement>('[data-testid="lexis-aday-kart"]'));
    expect(adaylar).toHaveLength(2);
    expect(adaylar[0].textContent).toContain("Kart #8101");
    expect(diyalog.textContent).toContain("Sıralama öneridir; seçim sizindir.");

    await tikla(dugme("Bu kart", adaylar[1]));
    expect(toastMocks.success).toHaveBeenCalledWith("Rapor kart #8102'e bağlandı");
    expect(document.querySelector('[data-testid="lexis-kart-secim"]')).toBeNull();
    expect(satirlar("lexis-bag-satiri")).toHaveLength(2);

    await tikla(dugme("Tümü"));
    const ilk = satirlar("lexis-bag-satiri")[0];
    expect(ilk.textContent).toContain("Kart #8102");
    expect(ilk.textContent).toContain("insan seçimi");
    await tikla(dugme("Seçimi geri al", ilk));
    expect(satirlar("lexis-bag-satiri")[0].textContent).toContain("seçilmedi");
  });

  it("bağ yok satırında seçim düğmesi yoktur", async () => {
    await ciz(<KartBagiListesi />);
    await tikla(dugme("Bağ yok"));
    const [satir] = satirlar("lexis-bag-satiri");
    expect(satir.textContent).toContain("hiçbir anahtar karta götürmedi");
    expect(satir.querySelector("button")).toBeNull();
  });
});

describe("SirketProfilleri", () => {
  it("ilk şirketin profili açılır; değişiklik olmadan kaydet kapalıdır", async () => {
    await ciz(<SirketProfilleri />);
    expect(kap.querySelectorAll('nav[aria-label="Şirketler"] button')).toHaveLength(4);
    expect(kap.querySelector("form")!.getAttribute("aria-label")).toBe("Anadolu Sigorta profili");
    expect(kap.querySelector('[data-testid="lexis-kriter-tablosu"]')!.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(dugme("Kaydedildi").disabled).toBe(true);
  });

  it("kriter satırı eklenip kaydedilir", async () => {
    await ciz(<SirketProfilleri />);
    await tikla(dugme("Satır ekle"));
    expect(kap.querySelector('[data-testid="lexis-kriter-tablosu"]')!.querySelectorAll("tbody tr")).toHaveLength(4);
    await tikla(dugme("Kaydet"));
    expect(toastMocks.success).toHaveBeenCalledWith("Profil kaydedildi", expect.anything());
    expect((await lexisApi.profiller())[0].muallak_tablosu).toHaveLength(4);
    expect(dugme("Kaydedildi").disabled).toBe(true);
  });

  it("kaydedilmemiş değişiklik varken şirket değişimi onay ister", async () => {
    await ciz(<SirketProfilleri />);
    await tikla(dugme("Satır ekle"));

    confirmMock.fn.mockResolvedValueOnce(false);
    await tikla(dugme("Ak Sigorta"));
    expect(confirmMock.fn).toHaveBeenCalledTimes(1);
    expect(kap.querySelector("form")!.getAttribute("aria-label")).toBe("Anadolu Sigorta profili");

    await tikla(dugme("Ak Sigorta"));
    expect(kap.querySelector("form")!.getAttribute("aria-label")).toBe("Ak Sigorta profili");
    // Vazgeçilen değişiklik kaydedilmedi
    expect((await lexisApi.profiller())[0].muallak_tablosu).toHaveLength(3);
  });
});
