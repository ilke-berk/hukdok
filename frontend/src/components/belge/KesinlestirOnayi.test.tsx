// @vitest-environment jsdom
// KesinlestirOnayi + YeniSurumTaslagiOnayi (G285, K14): onay metni birebir, `istek_kimligi` açılışta üretilir (UUID v4)
// ve hata sonrası tekrar denemede AYNI kalır, yeniden açılış yeni kimlik; 503 → meşgul metni, 409 `zaten_kesin` →
// "zaten kesin" metni + `onZatenKesin`; başarıda toast + `onBasari`. Yeni sürüm onayı `yeniSurumTaslagi`'ni çağırır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));
const apiMock = vi.hoisted(() => ({ kesinlestir: vi.fn(), yeniSurumTaslagi: vi.fn() }));
vi.mock("@/lib/belgeYasamApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/belgeYasamApi")>()),
  ...apiMock,
}));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
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
}));

import { KESINLESTIR_METNI, KesinlestirOnayi, MESGUL_METNI, YeniSurumTaslagiOnayi, ZATEN_KESIN_METNI } from "./KesinlestirOnayi";
import { BelgeYasamApiError } from "@/lib/belgeYasamApi";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const BELGE = { id: 5, ad: "Cevap dilekçesi.docx" };

let kap: HTMLDivElement;
let kok: Root;
const onKapat = vi.fn();
const onBasari = vi.fn();
const onZatenKesin = vi.fn();

async function ciz(acik = true) {
  await act(async () => {
    kok.render(<KesinlestirOnayi acik={acik} belge={BELGE} onKapat={onKapat} onBasari={onBasari} onZatenKesin={onZatenKesin} />);
  });
}
const dugme = (ad: string) => Array.from(kap.querySelectorAll<HTMLButtonElement>("button")).find((b) => b.textContent?.trim() === ad)!;

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

describe("KesinlestirOnayi", () => {
  it("onay metni birebir + theme-classic + belge adı", async () => {
    await ciz();
    const kok_ = kap.querySelector('[data-testid="kesinlestir-onayi"]')!;
    expect(kok_.className).toContain("theme-classic");
    expect(kap.querySelector('[data-testid="kesinlestir-metni"]')!.textContent).toBe(KESINLESTIR_METNI);
    expect(kap.querySelector('[data-testid="kesinlestir-metni"] strong')!.textContent).toBe("giden");
    expect(kok_.textContent).toContain("Cevap dilekçesi.docx");
  });

  it("503 → meşgul metni; tekrar deneme AYNI istek_kimligi; başarı → toast + onBasari", async () => {
    apiMock.kesinlestir.mockRejectedValueOnce(new BelgeYasamApiError(503, "x", "sistem_mesgul"));
    apiMock.kesinlestir.mockResolvedValueOnce({ document_id: 5, reused: true });
    await ciz();
    await act(async () => dugme("Kesinleştir").click());
    expect(kap.querySelector('[role="alert"]')!.textContent).toBe(MESGUL_METNI);
    const ilk = apiMock.kesinlestir.mock.calls[0];
    expect(ilk[0]).toBe(5);
    expect(ilk[1]).toMatch(UUID);
    await act(async () => dugme("Kesinleştir").click());
    expect(apiMock.kesinlestir.mock.calls[1][1]).toBe(ilk[1]);
    expect(onBasari).toHaveBeenCalledWith({ document_id: 5, reused: true });
    expect(toastMock.success).toHaveBeenCalledWith("Belge zaten bu istekle kesinleşmişti", expect.anything());
  });

  it("409 zaten_kesin → metin + onZatenKesin; diğer 409 sunucu metni", async () => {
    apiMock.kesinlestir.mockRejectedValueOnce(new BelgeYasamApiError(409, "Belge zaten kesinleşmiş.", "zaten_kesin"));
    await ciz();
    await act(async () => dugme("Kesinleştir").click());
    expect(kap.querySelector('[role="alert"]')!.textContent).toBe(ZATEN_KESIN_METNI);
    expect(onZatenKesin).toHaveBeenCalledTimes(1);
    expect(onBasari).not.toHaveBeenCalled();
    apiMock.kesinlestir.mockRejectedValueOnce(new BelgeYasamApiError(409, "Bu işlem sunucuda halen sürüyor.", "suruyor"));
    await act(async () => dugme("Kesinleştir").click());
    expect(kap.querySelector('[role="alert"]')!.textContent).toBe("Bu işlem sunucuda halen sürüyor.");
    expect(onZatenKesin).toHaveBeenCalledTimes(1);
  });

  it("kapat → yeniden aç: yeni istek_kimligi", async () => {
    apiMock.kesinlestir.mockRejectedValue(new BelgeYasamApiError(503, "x"));
    await ciz();
    await act(async () => dugme("Kesinleştir").click());
    await ciz(false);
    await ciz(true);
    expect(kap.querySelector('[role="alert"]')).toBeNull();
    await act(async () => dugme("Kesinleştir").click());
    expect(apiMock.kesinlestir.mock.calls[1][1]).not.toBe(apiMock.kesinlestir.mock.calls[0][1]);
  });
});

describe("YeniSurumTaslagiOnayi", () => {
  it("onay → yeniSurumTaslagi(id, uuid) → onBasari", async () => {
    const y = { document_id: 9, reused: false, word_url: "https://sp/a-v2.docx", word_ac: "ms-word:x" };
    apiMock.yeniSurumTaslagi.mockResolvedValue(y);
    await act(async () => {
      kok.render(<YeniSurumTaslagiOnayi acik belge={BELGE} onKapat={onKapat} onBasari={onBasari} />);
    });
    expect(kap.querySelector('[data-testid="yeni-surum-onayi"]')!.className).toContain("theme-classic");
    await act(async () => dugme("Yeni taslak aç").click());
    expect(apiMock.yeniSurumTaslagi).toHaveBeenCalledWith(5, expect.stringMatching(UUID));
    expect(onBasari).toHaveBeenCalledWith(y);
    expect(toastMock.success).toHaveBeenCalledWith("Yeni sürüm taslağı açıldı", expect.anything());
  });
});
