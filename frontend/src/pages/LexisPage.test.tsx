// @vitest-environment jsdom
// LexisPage — `/lexis` önizleme sayfası: beş sekme, seçili sekme URL'de (`?sekme=`), "Rapor yaz" sekme
// değişince bağlı kalır (yarım taslak kaybolmaz), örnek veri şeridi görünür, ☰ HUKDOK menüsünü açar.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/hooks/useConfirm", () => ({ useConfirm: () => async () => true }));

// Gerçek dava kipinde dosya bölgesi servise gider (`lexisServis.ts` → `apiClient`); burada sahtedir.
const servisMock = vi.hoisted(() => ({ davaAra: vi.fn(), dosyaGetir: vi.fn(), emsalOner: vi.fn() }));
vi.mock("@/lib/lexisServis", () => servisMock);

import LexisPage from "./LexisPage";
import { OdakModuContext } from "@/hooks/useOdakModu";
import { ornekDurumuSifirla, ornekGecikmeAyarla, veriKipi } from "@/lib/lexisApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let kap: HTMLDivElement;
let kok: Root;
let konum = "";
const odak = { setOdak: vi.fn(), menuyuAc: vi.fn() };

function KonumIzleyici() {
  const l = useLocation();
  konum = `${l.pathname}${l.search}`;
  return null;
}

async function ciz(adres = "/lexis") {
  await act(async () => {
    kok.render(
      <OdakModuContext.Provider value={{ odak: true, ...odak }}>
        <MemoryRouter initialEntries={[adres]}>
          <KonumIzleyici />
          <LexisPage />
        </MemoryRouter>
      </OdakModuContext.Provider>,
    );
  });
}

const sekme = (ad: string) => Array.from(kap.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find((b) => b.textContent === ad)!;
const gorunenGovdeler = () =>
  Array.from(kap.querySelectorAll<HTMLElement>('[role="tabpanel"]'))
    .filter((p) => !p.hidden)
    .map((p) => p.id);

beforeEach(() => {
  ornekDurumuSifirla();
  ornekGecikmeAyarla(0);
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
  odak.setOdak.mockClear();
  odak.menuyuAc.mockClear();
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("LexisPage", () => {
  it("beş sekmeyi çizer; varsayılan 'Rapor yaz' ve örnek veri şeridi görünür", async () => {
    await ciz();
    expect(Array.from(kap.querySelectorAll('[role="tab"]')).map((b) => b.textContent)).toEqual([
      "Rapor yaz",
      "Geçmiş",
      "Kütüphane",
      "Kart bağı",
      "Şirketler",
    ]);
    expect(sekme("Rapor yaz").getAttribute("aria-selected")).toBe("true");
    expect(gorunenGovdeler()).toEqual(["lexis-govde-yaz"]);
    expect(kap.querySelector('[data-testid="lexis-ornek-seridi"]')!.textContent).toContain("Örnek veri");
  });

  it("sekme tıklanınca URL'ye yazılır; 'Rapor yaz' gizlenir ama bağlı kalır", async () => {
    await ciz();
    await act(async () => sekme("Kütüphane").click());
    expect(konum).toBe("/lexis?sekme=kutuphane");
    expect(gorunenGovdeler()).toEqual(["lexis-govde-kutuphane"]);
    expect(kap.querySelector("#lexis-govde-yaz")).not.toBeNull();

    await act(async () => sekme("Rapor yaz").click());
    expect(konum).toBe("/lexis");
    expect(kap.querySelector("#lexis-govde-kutuphane")).toBeNull();
  });

  it("şeritteki düğme veri kipini URL'ye yazar; sekme değişimi kipi korur", async () => {
    servisMock.davaAra.mockResolvedValue([]);
    await ciz();
    const dugme = () => kap.querySelector<HTMLButtonElement>('[data-testid="lexis-kip-dugmesi"]')!;
    expect(dugme().textContent).toBe("Gerçek davalarla dene");
    expect(veriKipi()).toBe("ornek");

    await act(async () => dugme().click());
    expect(konum).toBe("/lexis?veri=gercek");
    expect(veriKipi()).toBe("gercek");
    expect(kap.querySelector('[data-testid="lexis-ornek-seridi"]')!.textContent).toContain("Gerçek dava");
    // dava listesi artık servisten (arama gecikmeli ve modül dinamik yüklenir)
    await act(async () => {
      await vi.waitFor(() => expect(servisMock.davaAra).toHaveBeenCalled(), { timeout: 3000 });
    });

    await act(async () => sekme("Kütüphane").click());
    expect(konum).toBe("/lexis?veri=gercek&sekme=kutuphane");
    await act(async () => dugme().click());
    expect(konum).toBe("/lexis?sekme=kutuphane");
    expect(veriKipi()).toBe("ornek");
  });

  it("URL'deki sekme açılır; tanınmayan değer varsayılana düşer", async () => {
    await ciz("/lexis?sekme=kart-bagi");
    expect(sekme("Kart bağı").getAttribute("aria-selected")).toBe("true");
    act(() => kok.unmount());
    kok = createRoot(kap);
    await ciz("/lexis?sekme=yok");
    expect(sekme("Rapor yaz").getAttribute("aria-selected")).toBe("true");
  });

  it("odak moduna girer ve ☰ HUKDOK menüsünü açar", async () => {
    await ciz();
    expect(odak.setOdak).toHaveBeenCalledWith(true);
    await act(async () => kap.querySelector<HTMLButtonElement>('[aria-label="HUKDOK menüsünü aç"]')!.click());
    expect(odak.menuyuAc).toHaveBeenCalledTimes(1);
  });
});
