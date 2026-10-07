// @vitest-environment jsdom
// KartaBaglaDiyalogu (G273): dava arama (tuş vuruşu yolu, sahte `searchCases`), seçilen kartın tarafları `getCase`'ten,
// belge türü listesi (`useConfigList("doctypes")`, kod `_` pad'li gider), taraf / ad / yön / kayıt biçimi → `kartaBagla`
// gövdesi; `istek_kimligi` açılışta üretilir ve tekrar denemede AYNI kalır (409 sonrası), `reused: true` → "zaten bağlı";
// ön-seçili kart (`location.state.case`) ile arama kutusu yok; yeniden açılış yeni kimlik. Dialog düz DOM (Radix odak
// tuzağı), debounce kimlik.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ kartaBagla: vi.fn() }));
vi.mock("@/lib/pdfAraclariApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/pdfAraclariApi")>()),
  ...apiMock,
}));
const cases = vi.hoisted(() => ({ searchCases: vi.fn(), getCase: vi.fn() }));
vi.mock("@/hooks/useCases", () => ({ useCases: () => cases }));
const config = vi.hoisted(() => ({ data: [] as { code?: string; name: string }[], error: null as Error | null }));
vi.mock("@/hooks/useConfig", () => ({ useConfigList: () => config }));
vi.mock("@/hooks/useDebounce", () => ({ useDebounce: <T,>(v: T) => v }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
type Kids = { children?: ReactNode; className?: string; "data-testid"?: string };
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: Kids & { open: boolean }) => (open ? <div data-dialog-open="true">{children}</div> : null),
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

import { KartaBaglaDiyalogu, TASLAK_ACIKLAMASI } from "./KartaBaglaDiyalogu";
import { PdfAraclariApiError } from "@/lib/pdfAraclariApi";
import type { Dosya, KartOzeti, KartaBaglaIstegi } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const DOSYA: Dosya = { id: "u1", ad: "dilekce.pdf", sayfa: 3, boyut: 100, sayfalar: [{ no: 1, genislik: 595, yukseklik: 842 }] };
const KART: KartOzeti = { id: 7, tracking_no: "DR.M.OZTURK-0003-HUK", esas_no: "2026/15", court: "İstanbul 3. ATM", status: "DERDEST" };
const TARAFLAR = [
  { id: 11, party_type: "CLIENT", name: "Ayşe Yılmaz", role: "Davacı" },
  { id: 12, party_type: "OPPONENT", name: "Sigorta A.Ş.", role: "Davalı" },
];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

let kap: HTMLDivElement;
let kok: Root;
const onKapat = vi.fn();
const onBasari = vi.fn();

async function ciz(props: Partial<Parameters<typeof KartaBaglaDiyalogu>[0]> = {}) {
  await act(async () => {
    kok.render(
      <MemoryRouter>
        <KartaBaglaDiyalogu acik dosya={DOSYA} onKapat={onKapat} onBasari={onBasari} {...props} />
      </MemoryRouter>,
    );
  });
}

const dugme = (ad: string) => Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad)!;
const tikla = (el: HTMLElement | null | undefined) => {
  expect(el).toBeTruthy();
  return act(async () => el!.click());
};
async function yaz(el: HTMLInputElement | HTMLSelectElement, deger: string) {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}
const secim = (etiket: string) => Array.from(kap.querySelectorAll<HTMLLabelElement>("label")).find((l) => l.textContent?.trim().startsWith(etiket))!;
const sonIstek = () => apiMock.kartaBagla.mock.calls.at(-1)![0] as KartaBaglaIstegi;

beforeEach(() => {
  apiMock.kartaBagla.mockReset();
  cases.searchCases.mockReset();
  cases.getCase.mockReset();
  cases.searchCases.mockResolvedValue([KART]);
  cases.getCase.mockResolvedValue({ ...KART, parties: TARAFLAR });
  config.data = [
    { code: "TEBLIGAT______", name: "Tebligat" },
    { code: "KARAR_________", name: "Karar" },
    { name: "kodsuz" },
  ];
  config.error = null;
  onKapat.mockReset();
  onBasari.mockReset();
  toastMock.success.mockReset();
  toastMock.info.mockReset();
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("KartaBaglaDiyalogu", () => {
  it("ara → seç → tür/taraf/ad/yön/taslak → gövde doğru (kod pad'li, istek_kimligi UUID); sonuç paneli + karta bağlantı + toast", async () => {
    await ciz();
    const diyalog = kap.querySelector<HTMLDivElement>('[data-testid="karta-bagla-diyalogu"]')!;
    expect(diyalog.className).toContain("theme-classic");
    expect(dugme("Karta bağla").disabled).toBe(true);

    await yaz(kap.querySelector<HTMLInputElement>('input[aria-label="Dava ara"]')!, "öztürk");
    expect(cases.searchCases).toHaveBeenCalledWith("öztürk");
    const sonuc = kap.querySelector<HTMLButtonElement>('[role="listbox"] button')!;
    expect(sonuc.textContent).toContain("DR.M.OZTURK-0003-HUK");
    await tikla(sonuc);
    expect(kap.querySelector('[data-testid="secili-kart"]')!.textContent).toContain("DR.M.OZTURK-0003-HUK");
    expect(cases.getCase).toHaveBeenCalledWith(7); // taraflar karttan
    expect(kap.querySelector('[data-testid="secili-kart"]')!.textContent).toContain("Ayşe Yılmaz");

    const turSecici = kap.querySelector<HTMLSelectElement>('select[id$="-tur"]')!;
    expect(Array.from(turSecici.options).map((o) => o.value)).toEqual(["", "TEBLIGAT______", "KARAR_________"]); // kodsuz satır yok
    expect(dugme("Karta bağla").disabled).toBe(true); // tür seçilmedi
    await yaz(turSecici, "TEBLIGAT______");
    expect(dugme("Karta bağla").disabled).toBe(false);

    const tarafSecici = kap.querySelector<HTMLSelectElement>('select[id$="-taraf"]')!;
    expect(Array.from(tarafSecici.options).map((o) => o.textContent)).toEqual(["Tüm dava", "Ayşe Yılmaz"]); // yalnız CLIENT
    await yaz(tarafSecici, "11");

    const adGirdisi = kap.querySelector<HTMLInputElement>('input[id$="-ad"]')!;
    expect(adGirdisi.value).toBe("dilekce.pdf");
    await yaz(adGirdisi, "  tebligat-ek.pdf ");
    await tikla(secim("Giden").querySelector("input"));
    await tikla(secim("Taslak olarak kaydet").querySelector("input"));
    expect(kap.textContent).toContain(TASLAK_ACIKLAMASI);
    expect(dugme("Taslak kaydet")).toBeDefined();

    apiMock.kartaBagla.mockResolvedValueOnce({ document_id: 321, reused: false });
    await tikla(dugme("Taslak kaydet"));
    expect(apiMock.kartaBagla).toHaveBeenCalledTimes(1);
    const istek = sonIstek();
    expect(istek.istek_kimligi).toMatch(UUID);
    expect(istek).toEqual({
      id: "u1",
      case_id: 7,
      belge_turu_kodu: "TEBLIGAT______",
      dosya_adi: "tebligat-ek.pdf",
      case_party_id: 11,
      istek_kimligi: istek.istek_kimligi,
      yon: "GIDEN",
      durum: "TASLAK",
    });
    const sonucPaneli = kap.querySelector('[data-testid="karta-bagla-sonuc"]')!;
    expect(sonucPaneli.textContent).toContain("Taslak olarak kaydedildi");
    expect(sonucPaneli.textContent).toContain("#321");
    expect(sonucPaneli.querySelector('a[href="/cases/7"]')!.textContent).toContain("Karta git");
    expect(toastMock.success).toHaveBeenCalledTimes(1);
    expect(onBasari).toHaveBeenCalledWith({ document_id: 321, reused: false }, expect.objectContaining({ id: 7 }));
  });

  it("409 → hata şeridi; tekrar tıklama AYNI istek_kimligi; reused:true → 'zaten bağlı' + toast.info", async () => {
    await ciz({ onSecilenKart: { ...KART, parties: TARAFLAR } });
    expect(kap.querySelector('input[aria-label="Dava ara"]')).toBeNull(); // ön-seçili: arama yok
    expect(cases.getCase).not.toHaveBeenCalled(); // taraflar state'ten geldi
    await yaz(kap.querySelector<HTMLSelectElement>('select[id$="-tur"]')!, "KARAR_________");

    apiMock.kartaBagla.mockRejectedValueOnce(new PdfAraclariApiError(409, "Kayıt şu anda kilitli; birkaç dakika sonra tekrar deneyin."));
    await tikla(dugme("Karta bağla"));
    expect(kap.querySelector('[role="alert"]')!.textContent).toContain("kilitli");
    expect(kap.querySelector('[data-testid="karta-bagla-sonuc"]')).toBeNull();

    apiMock.kartaBagla.mockResolvedValueOnce({ document_id: 99, reused: true });
    await tikla(dugme("Karta bağla"));
    expect(apiMock.kartaBagla).toHaveBeenCalledTimes(2);
    const [ilk, ikinci] = apiMock.kartaBagla.mock.calls.map((c) => (c[0] as KartaBaglaIstegi).istek_kimligi);
    expect(ilk).toMatch(UUID);
    expect(ikinci).toBe(ilk);
    expect((apiMock.kartaBagla.mock.calls[1][0] as KartaBaglaIstegi)).toMatchObject({ yon: "GELEN", durum: "KESIN", case_party_id: undefined, dosya_adi: "dilekce.pdf" });
    expect(kap.querySelector('[data-testid="karta-bagla-sonuc"]')!.textContent).toContain("zaten bağlıydı");
    expect(toastMock.info).toHaveBeenCalledTimes(1);
    expect(toastMock.success).not.toHaveBeenCalled();
  });

  it("yeniden açılış yeni kimlik üretir; dosya yokken düğme kapalı; 503 mesajı", async () => {
    await ciz({ onSecilenKart: KART });
    await yaz(kap.querySelector<HTMLSelectElement>('select[id$="-tur"]')!, "KARAR_________");
    apiMock.kartaBagla.mockRejectedValueOnce(new PdfAraclariApiError(503, "Sistem şu anda meşgul; birkaç dakika sonra tekrar deneyin."));
    await tikla(dugme("Karta bağla"));
    expect(kap.querySelector('[role="alert"]')!.textContent).toContain("meşgul");
    const ilkKimlik = sonIstek().istek_kimligi;

    await ciz({ onSecilenKart: KART, acik: false });
    expect(kap.querySelector('[data-testid="karta-bagla-diyalogu"]')).toBeNull();
    await ciz({ onSecilenKart: KART });
    await yaz(kap.querySelector<HTMLSelectElement>('select[id$="-tur"]')!, "KARAR_________");
    apiMock.kartaBagla.mockResolvedValueOnce({ document_id: 1, reused: false });
    await tikla(dugme("Karta bağla"));
    expect(sonIstek().istek_kimligi).not.toBe(ilkKimlik);

    await ciz({ onSecilenKart: KART, dosya: null });
    expect(kap.textContent).toContain("Önce soldan bir dosya seçin.");
    expect(dugme("Karta bağla").disabled).toBe(true);
  });

  it("belge türü listesi hatası uyarı basar; 'Sonuç bulunamadı'", async () => {
    config.error = new Error("liste yok");
    config.data = [];
    cases.searchCases.mockResolvedValue([]);
    await ciz();
    expect(kap.textContent).toContain("Belge türü listesi alınamadı.");
    await yaz(kap.querySelector<HTMLInputElement>('input[aria-label="Dava ara"]')!, "zzz");
    expect(kap.querySelector('[role="listbox"]')!.textContent).toContain("Sonuç bulunamadı");
  });
});
