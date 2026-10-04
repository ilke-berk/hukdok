// @vitest-environment jsdom
// LexisPage — `/lexis` önizleme sayfası: beş sekme, seçili sekme URL'de (`?sekme=`), "Rapor yaz" sekme
// değişince bağlı kalır (yarım taslak kaybolmaz), örnek veri şeridi görünür, ☰ HukuDok menüsünü açar.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/hooks/useConfirm", () => ({ useConfirm: () => async () => true }));

import LexisPage from "./LexisPage";
import { OdakModuContext } from "@/hooks/useOdakModu";
import { ornekDurumuSifirla, ornekGecikmeAyarla } from "@/lib/lexisApi";

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

  it("URL'deki sekme açılır; tanınmayan değer varsayılana düşer", async () => {
    await ciz("/lexis?sekme=kart-bagi");
    expect(sekme("Kart bağı").getAttribute("aria-selected")).toBe("true");
    act(() => kok.unmount());
    kok = createRoot(kap);
    await ciz("/lexis?sekme=yok");
    expect(sekme("Rapor yaz").getAttribute("aria-selected")).toBe("true");
  });

  it("odak moduna girer ve ☰ HukuDok menüsünü açar", async () => {
    await ciz();
    expect(odak.setOdak).toHaveBeenCalledWith(true);
    await act(async () => kap.querySelector<HTMLButtonElement>('[aria-label="HukuDok menüsünü aç"]')!.click());
    expect(odak.menuyuAc).toHaveBeenCalledTimes(1);
  });
});
