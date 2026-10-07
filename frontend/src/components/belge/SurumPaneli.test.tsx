// @vitest-environment jsdom
// SurumPaneli (G285, K13): yükleniyor → liste (v1, v2 kesin, not, kısa sha) ya da boş durum; "Sürüm kaydet" notla
// `surumKaydet` → `degisti:false` "Dosya değişmemiş, not kaydedildi", `degisti:true` "Sürüm N kaydedildi"; liste yeniden
// çekilir, `onKaydedildi`; hata metni; salt okunur kipte form yok.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ surumler: vi.fn(), surumKaydet: vi.fn() }));
vi.mock("@/lib/belgeYasamApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/belgeYasamApi")>()),
  ...apiMock,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import { DEGISMEDI_METNI, SurumPaneli } from "./SurumPaneli";
import { BelgeYasamApiError } from "@/lib/belgeYasamApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const S1 = { surum_no: 1, sha256: "aaaaaaaa11112222", not: "ilk taslak", olusturan_email: "av@x", olusturulma: "2026-10-08T09:00:00Z", kesin: false };
const S2 = { surum_no: 2, sha256: "bbbbbbbb33334444", not: null, olusturan_email: "av@x", olusturulma: "2026-10-08T10:00:00Z", kesin: true };

let kap: HTMLDivElement;
let kok: Root;
const onKaydedildi = vi.fn();

async function ciz(saltOkunur = false) {
  await act(async () => {
    kok.render(<SurumPaneli documentId={5} onKaydedildi={onKaydedildi} saltOkunur={saltOkunur} />);
  });
}
const dugme = () => Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.includes("Sürüm kaydet"))!;
async function notYaz(deger: string) {
  const ta = kap.querySelector<HTMLTextAreaElement>("textarea")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(ta, deger);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  kap = document.createElement("div");
  document.body.appendChild(kap);
  kok = createRoot(kap);
});
afterEach(() => {
  act(() => kok.unmount());
  kap.remove();
});

describe("SurumPaneli", () => {
  it("yükleniyor durumu, sonra liste (artan, kesin rozeti, not, kısa sha)", async () => {
    let coz!: (v: unknown) => void;
    apiMock.surumler.mockReturnValue(new Promise((r) => (coz = r)));
    await ciz();
    expect(kap.querySelector('[data-testid="surum-yukleniyor"]')).not.toBeNull();
    await act(async () => coz([S1, S2]));
    expect(apiMock.surumler).toHaveBeenCalledWith(5);
    const satirlar = Array.from(kap.querySelectorAll<HTMLLIElement>('[data-testid="surum-listesi"] > li'));
    expect(satirlar.map((li) => li.dataset.surum)).toEqual(["1", "2"]);
    expect(satirlar[0].textContent).toContain("v1");
    expect(satirlar[0].textContent).toContain("ilk taslak");
    expect(satirlar[0].textContent).toContain("aaaaaaaa");
    expect(satirlar[0].textContent).not.toContain("kesin");
    expect(satirlar[1].textContent).toContain("kesin");
  });

  it("boş durum", async () => {
    apiMock.surumler.mockResolvedValue([]);
    await ciz();
    expect(kap.querySelector('[data-testid="surum-bos"]')!.textContent).toContain("Henüz sürüm kaydedilmedi");
  });

  it("degisti:false → 'Dosya değişmemiş, not kaydedildi'; not gövdeye; liste yeniden çekilir + onKaydedildi", async () => {
    apiMock.surumler.mockResolvedValue([S1]);
    apiMock.surumKaydet.mockResolvedValue({ surum_no: 2, sha256: S1.sha256, degisti: false });
    await ciz();
    await notYaz("müvekkil onayı");
    await act(async () => dugme().click());
    expect(apiMock.surumKaydet).toHaveBeenCalledWith(5, "müvekkil onayı");
    expect(kap.querySelector('[data-testid="surum-bilgi"]')!.textContent).toContain(DEGISMEDI_METNI);
    expect(apiMock.surumler).toHaveBeenCalledTimes(2);
    expect(onKaydedildi).toHaveBeenCalledTimes(1);
    expect(kap.querySelector<HTMLTextAreaElement>("textarea")!.value).toBe("");
  });

  it("degisti:true → 'Sürüm N kaydedildi'; hata → sunucu metni", async () => {
    apiMock.surumler.mockResolvedValue([S1]);
    apiMock.surumKaydet.mockResolvedValueOnce({ surum_no: 2, sha256: "c", degisti: true });
    await ciz();
    await act(async () => dugme().click());
    expect(kap.querySelector('[data-testid="surum-bilgi"]')!.textContent).toContain("Sürüm 2 kaydedildi.");
    apiMock.surumKaydet.mockRejectedValueOnce(new BelgeYasamApiError(409, "Yalnız Word taslağının sürümü kaydedilir.", "taslak_degil"));
    await act(async () => dugme().click());
    expect(kap.querySelector('[role="alert"]')!.textContent).toContain("Yalnız Word taslağının sürümü kaydedilir.");
  });

  it("salt okunur: form yok", async () => {
    apiMock.surumler.mockResolvedValue([S1, S2]);
    await ciz(true);
    expect(kap.querySelector("textarea")).toBeNull();
    expect(dugme()).toBeUndefined();
  });
});
