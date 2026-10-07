// @vitest-environment jsdom
// YeniBelgeDiyalogu (G285, K15): sabit kartla açılış (arama yok), tür seçince ad varsayılanı (tür + tarih; elle yazılan
// ad ezilmez), sunucu adının ön-izlemesi, müvekkil seçimi → `yeniBelge` gövdesi; başarıda `ms-word:` yönlendirmesi +
// 1,5 sn'de açılmazsa "Word Online'da aç" (`word_url`), toast + `onBasari`; 409 sunucu metni; kart yoksa dava arama
// (tezgâh yolu) + "Kartın taslaklarına git" bağlantısı. Dialog düz DOM, debounce kimlik.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ yeniBelge: vi.fn() }));
vi.mock("@/lib/belgeYasamApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/belgeYasamApi")>()),
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
}));

import { YeniBelgeDiyalogu } from "./YeniBelgeDiyalogu";
import { BelgeYasamApiError, WORD_ACILMA_BEKLEMESI_MS, tarayici } from "@/lib/belgeYasamApi";
import type { KartOzeti } from "@/types/pdfAraclari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KART: KartOzeti = {
  id: 7,
  tracking_no: "DR.M.OZTURK-0003-HUK",
  esas_no: "2026/15",
  parties: [
    { id: 11, party_type: "CLIENT", name: "Ayşe Yılmaz" },
    { id: 12, party_type: "OPPONENT", name: "Sigorta A.Ş." },
  ],
};
const YANIT = { document_id: 91, word_url: "https://sp/03_TASLAKLAR/a.docx", word_ac: "ms-word:ofe|u|https://sp/03_TASLAKLAR/a.docx" };

let kap: HTMLDivElement;
let kok: Root;
let git: ReturnType<typeof vi.spyOn>;
const onKapat = vi.fn();
const onBasari = vi.fn();

async function ciz(props: Partial<Parameters<typeof YeniBelgeDiyalogu>[0]> = {}) {
  await act(async () => {
    kok.render(
      <MemoryRouter>
        <YeniBelgeDiyalogu acik kart={KART} onKapat={onKapat} onBasari={onBasari} {...props} />
      </MemoryRouter>,
    );
  });
}

const dugme = (ad: string) => Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad)!;
const secimler = () => Array.from(kap.querySelectorAll<HTMLSelectElement>("select"));
const adKutusu = () => kap.querySelector<HTMLInputElement>('input[maxlength="255"]')!;
async function yaz(el: HTMLInputElement | HTMLSelectElement, deger: string) {
  const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
  await act(async () => {
    setter.call(el, deger);
    el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  config.data = [
    { code: "DILEKCE_______", name: "Cevap Dilekçesi" },
    { code: "TEBLIGAT______", name: "Tebligat" },
  ];
  git = vi.spyOn(tarayici, "git").mockImplementation(() => undefined);
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});

afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
  git.mockRestore();
  vi.useRealTimers();
});

describe("YeniBelgeDiyalogu", () => {
  it("sabit kart: arama yok, theme-classic; tür seçince ad varsayılanı + ön-izleme; taraf yalnız müvekkiller", async () => {
    await ciz();
    const kok_ = kap.querySelector('[data-testid="yeni-belge-diyalogu"]')!;
    expect(kok_.className).toContain("theme-classic");
    expect(kap.querySelector('input[aria-label="Dava ara"]')).toBeNull();
    expect(kap.querySelector('[data-testid="secili-kart"]')!.textContent).toContain("DR.M.OZTURK-0003-HUK");
    expect(kap.querySelector('button[aria-label="Kart seçimini kaldır"]')).toBeNull();
    expect(dugme("Oluştur ve Word'de aç").disabled).toBe(true);

    await yaz(secimler()[0], "DILEKCE_______");
    expect(adKutusu().value).toMatch(/^Cevap Dilekçesi \d{2}\.\d{2}\.\d{4}$/);
    expect(kap.querySelector('[data-testid="ad-onizleme"]')!.textContent).toMatch(/Cevap Dilekçesi \d{2}\.\d{2}\.\d{4}\.docx/);
    expect(Array.from(secimler()[1].options).map((o) => o.textContent)).toEqual(["Tüm dava", "Ayşe Yılmaz"]);
    expect(dugme("Oluştur ve Word'de aç").disabled).toBe(false);

    // elle yazılan ad tür değişince ezilmez; geçersiz ad düğmeyi kapatır
    await yaz(adKutusu(), "Bilirkişi itirazı");
    await yaz(secimler()[0], "TEBLIGAT______");
    expect(adKutusu().value).toBe("Bilirkişi itirazı");
    await yaz(adKutusu(), "///");
    expect(kap.querySelector('[data-testid="ad-onizleme"]')!.textContent).toContain("geçersiz");
    expect(dugme("Oluştur ve Word'de aç").disabled).toBe(true);
  });

  it("Oluştur → yeniBelge gövdesi; ms-word yönlendirmesi; 1,5 sn sonra Word Online yedeği; toast + onBasari", async () => {
    apiMock.yeniBelge.mockResolvedValue(YANIT);
    await ciz();
    await yaz(secimler()[0], "DILEKCE_______");
    await yaz(adKutusu(), "Cevap dilekçesi");
    await yaz(secimler()[1], "11");
    vi.useFakeTimers();
    await act(async () => dugme("Oluştur ve Word'de aç").click());
    expect(apiMock.yeniBelge).toHaveBeenCalledWith(7, { belge_turu_kodu: "DILEKCE_______", ad: "Cevap dilekçesi", case_party_id: 11 });
    expect(git).toHaveBeenCalledWith(YANIT.word_ac);
    expect(onBasari).toHaveBeenCalledWith(YANIT, KART);
    expect(toastMock.success).toHaveBeenCalledWith("Word taslağı açıldı", expect.anything());
    expect(kap.querySelector('[data-testid="yeni-belge-sonuc"]')!.textContent).toContain("belge #91");
    expect(kap.querySelector('[data-testid="word-online-yedek"]')).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(WORD_ACILMA_BEKLEMESI_MS);
    });
    const yedek = kap.querySelector<HTMLAnchorElement>('[data-testid="word-online-yedek"] a')!;
    expect(yedek.textContent).toContain("Word Online'da aç");
    expect(yedek.getAttribute("href")).toBe(YANIT.word_url);
    expect(yedek.getAttribute("target")).toBe("_blank");
    // kart içinden açılınca "karta git" bağlantısı yok
    expect(kap.querySelector('a[href^="/cases/"]')).toBeNull();
  });

  it("409 ad çakışması: sunucu metni gösterilir, form yerinde", async () => {
    apiMock.yeniBelge.mockRejectedValue(new BelgeYasamApiError(409, "Aynı adlı 20 taslak var; farklı bir ad verin.", "ad_cakismasi"));
    await ciz();
    await yaz(secimler()[0], "DILEKCE_______");
    await act(async () => dugme("Oluştur ve Word'de aç").click());
    expect(kap.querySelector('[role="alert"]')!.textContent).toContain("Aynı adlı 20 taslak var");
    expect(git).not.toHaveBeenCalled();
    expect(onBasari).not.toHaveBeenCalled();
  });

  it("kart yoksa (tezgâh): dava ara → seç → taraflar getCase'ten; sonuçta 'Kartın taslaklarına git'", async () => {
    cases.searchCases.mockResolvedValue([{ id: 7, tracking_no: "DR.M.OZTURK-0003-HUK" }]);
    cases.getCase.mockResolvedValue({ parties: KART.parties });
    apiMock.yeniBelge.mockResolvedValue(YANIT);
    await ciz({ kart: null, kartaGitBaglantisi: true });
    await yaz(kap.querySelector<HTMLInputElement>('input[aria-label="Dava ara"]')!, "OZTURK");
    expect(cases.searchCases).toHaveBeenCalledWith("OZTURK");
    await act(async () => kap.querySelector<HTMLButtonElement>('[role="option"] button')!.click());
    expect(cases.getCase).toHaveBeenCalledWith(7);
    expect(Array.from(secimler()[1].options).map((o) => o.textContent)).toEqual(["Tüm dava", "Ayşe Yılmaz"]);
    await yaz(secimler()[0], "TEBLIGAT______");
    await act(async () => dugme("Oluştur ve Word'de aç").click());
    expect(apiMock.yeniBelge).toHaveBeenCalledWith(7, expect.objectContaining({ belge_turu_kodu: "TEBLIGAT______", case_party_id: undefined }));
    expect(kap.querySelector('a[href="/cases/7?belgeler=taslak"]')).not.toBeNull();
  });
});
