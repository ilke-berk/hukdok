// @vitest-environment jsdom
// KarttanAlDiyalogu (G273): dava ara → kartın belge listesi (`getCase().documents`; `sharepoint_url` boş olan soluk ve
// seçilemez "arşivde yok") → çoklu seçim (seçim sırası) → "Tezgâha al" her belge için SIRAYLA `karttanAl` → `onDosyalar`
// + kapanış; "Al ve birleştir" → `onBirlestir` (≥ 2); bir belgenin hatası diğerlerini durdurmaz, satırda kalır, diyalog
// açık kalır. Dialog düz DOM, debounce kimlik.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ karttanAl: vi.fn() }));
vi.mock("@/lib/pdfAraclariApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pdfAraclariApi")>()),
  ...apiMock,
}));
const cases = vi.hoisted(() => ({ searchCases: vi.fn(), getCase: vi.fn() }));
vi.mock("@/hooks/useCases", () => ({ useCases: () => cases }));
vi.mock("@/hooks/useDebounce", () => ({ useDebounce: <T,>(v: T) => v }));
type Kids = { children?: ReactNode; className?: string; "data-testid"?: string };
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: Kids & { open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children, className, ...rest }: Kids) => (
    <div className={className} data-testid={rest["data-testid"]}>
      {children}
    </div>
  ),
  DialogHeader: ({ children }: Kids) => <div>{children}</div>,
  DialogTitle: ({ children }: Kids) => <div>{children}</div>,
  DialogDescription: ({ children }: Kids) => <div>{children}</div>,
  DialogFooter: ({ children }: Kids) => <div>{children}</div>,
}));

import { KarttanAlDiyalogu } from "./KarttanAlDiyalogu";
import { PdfAraclariApiError } from "@/lib/pdfAraclariApi";
import type { Dosya } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KART = { id: 7, tracking_no: "T-7", esas_no: "2026/1", court: "ATM", status: "DERDEST" };
const BELGELER = [
  { id: 101, original_filename: "tebligat.pdf", stored_filename: "tebligat-101.pdf", belge_turu_adi: "Tebligat", sharepoint_url: "https://sp/101" },
  { id: 102, original_filename: "bekleyen.pdf", stored_filename: "bekleyen-102.pdf", belge_turu_adi: "Dilekçe", sharepoint_url: null },
  { id: 103, original_filename: "karar.pdf", stored_filename: "karar-103.pdf", belge_turu_adi: "Karar", sharepoint_url: "https://sp/103", durum: "TASLAK" },
];
const dosya = (id: number): Dosya => ({ id: `d${id}`, ad: `belge-${id}.pdf`, sayfa: 1, boyut: 10, sayfalar: [{ no: 1, genislik: 595, yukseklik: 842 }] });

let kap: HTMLDivElement;
let kok: Root;
const onKapat = vi.fn();
const onDosyalar = vi.fn();
const onBirlestir = vi.fn();

async function ciz(ekstra: Partial<Parameters<typeof KarttanAlDiyalogu>[0]> = {}) {
  await act(async () => {
    kok.render(<KarttanAlDiyalogu acik onKapat={onKapat} onDosyalar={onDosyalar} onBirlestir={onBirlestir} {...ekstra} />);
  });
}
const dugme = (ad: string) => Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad)!;
const tikla = (el: HTMLElement | null | undefined) => {
  expect(el).toBeTruthy();
  return act(async () => el!.click());
};
async function yaz(el: HTMLInputElement, deger: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
const kutu = (ad: string) => kap.querySelector<HTMLInputElement>(`input[aria-label="Seç: ${ad}"]`)!;
const satir = (id: number) => kap.querySelector<HTMLLIElement>(`li[data-belge-id="${id}"]`)!;

async function kartSec() {
  await yaz(kap.querySelector<HTMLInputElement>('input[aria-label="Dava ara"]')!, "T-7");
  await tikla(kap.querySelector<HTMLButtonElement>('[role="listbox"] button'));
  expect(cases.getCase).toHaveBeenCalledWith(7);
  expect(kap.querySelector('[data-testid="kart-belgeleri"]')).not.toBeNull();
}

beforeEach(() => {
  apiMock.karttanAl.mockReset();
  apiMock.karttanAl.mockImplementation(async (id: number) => dosya(id));
  cases.searchCases.mockReset();
  cases.getCase.mockReset();
  cases.searchCases.mockResolvedValue([KART]);
  cases.getCase.mockResolvedValue({ ...KART, documents: BELGELER });
  onKapat.mockReset();
  onDosyalar.mockReset();
  onBirlestir.mockReset();
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("KarttanAlDiyalogu", () => {
  it("ara → kart → belgeler; URL'siz belge seçilemez ('arşivde yok'); seçim sırasıyla SIRALI karttanAl → onDosyalar + kapanış", async () => {
    await ciz();
    expect(kap.querySelector<HTMLDivElement>('[data-testid="karttan-al-diyalogu"]')!.className).toContain("theme-classic");
    expect(dugme("Tezgâha al").disabled).toBe(true);
    await kartSec();
    expect(kap.querySelectorAll('[data-testid="kart-belgeleri"] li').length).toBe(3);
    expect(kutu("bekleyen.pdf").disabled).toBe(true);
    expect(satir(102).textContent).toContain("arşivde yok");
    expect(satir(103).textContent).toContain("taslak");

    await tikla(kutu("karar.pdf"));
    await tikla(kutu("tebligat.pdf"));
    expect(kap.textContent).toContain("2 seçili");
    expect(satir(103).textContent).toContain("#1");
    expect(satir(101).textContent).toContain("#2");

    const sira: number[] = [];
    apiMock.karttanAl.mockImplementation(async (id: number) => {
      sira.push(id);
      return dosya(id);
    });
    await tikla(dugme("Tezgâha al"));
    expect(sira).toEqual([103, 101]);
    expect(onDosyalar).toHaveBeenCalledWith([dosya(103), dosya(101)]);
    expect(onBirlestir).not.toHaveBeenCalled();
    expect(onKapat).toHaveBeenCalledTimes(1);
  });

  it("'Al ve birleştir' ≥ 2 seçimde açık ve alınanları onBirlestir'e verir; tek seçimde kapalı", async () => {
    await ciz();
    await kartSec();
    await tikla(kutu("tebligat.pdf"));
    expect(dugme("Al ve birleştir").disabled).toBe(true);
    await tikla(kutu("karar.pdf"));
    expect(dugme("Al ve birleştir").disabled).toBe(false);
    await tikla(dugme("Al ve birleştir"));
    expect(apiMock.karttanAl.mock.calls.map((c) => c[0])).toEqual([101, 103]);
    expect(onDosyalar).toHaveBeenCalledWith([dosya(101), dosya(103)]);
    expect(onBirlestir).toHaveBeenCalledWith([dosya(101), dosya(103)]);
    expect(onKapat).toHaveBeenCalledTimes(1);
  });

  it("bir belgenin hatası diğerlerini durdurmaz: başarılılar listeye düşer, hata satırda, diyalog açık kalır", async () => {
    await ciz();
    await kartSec();
    await tikla(kutu("tebligat.pdf"));
    await tikla(kutu("karar.pdf"));
    apiMock.karttanAl.mockImplementation(async (id: number) => {
      if (id === 101) throw new PdfAraclariApiError(502, "Belge arşivden (SharePoint) alınamadı; daha sonra tekrar deneyin.");
      return dosya(id);
    });
    await tikla(dugme("Tezgâha al"));
    expect(apiMock.karttanAl).toHaveBeenCalledTimes(2);
    expect(onDosyalar).toHaveBeenCalledWith([dosya(103)]);
    expect(satir(101).textContent).toContain("SharePoint");
    expect(onKapat).not.toHaveBeenCalled();
    expect(kap.querySelector('[data-testid="karttan-al-diyalogu"]')).not.toBeNull();
  });

  it("kartta belge yoksa bilgi; kart seçimi kaldırılınca arama geri gelir", async () => {
    cases.getCase.mockResolvedValue({ ...KART, documents: [] });
    await ciz();
    await yaz(kap.querySelector<HTMLInputElement>('input[aria-label="Dava ara"]')!, "T-7");
    await tikla(kap.querySelector<HTMLButtonElement>('[role="listbox"] button'));
    expect(cases.getCase).toHaveBeenCalledWith(7);
    expect(kap.textContent).toContain("Kartta belge yok.");
    await tikla(kap.querySelector<HTMLButtonElement>('button[aria-label="Kart seçimini kaldır"]'));
    expect(kap.querySelector('input[aria-label="Dava ara"]')).not.toBeNull();
    expect(kap.querySelector('[data-testid="kart-belgeleri"]')).toBeNull();
  });
});
