// @vitest-environment jsdom
// AssistantBar + mikrofon (G217) — `MediaRecorder`, `getUserMedia` ve `apiClient` sahte: destek yokken ve iskelet
// (`yukleniyor`) hâlinde düğme yok; kayıt → durdur → metin girdinin SONUNA eklenir, odak girdiye döner, asistana
// İSTEK GİTMEZ (yalnız `/api/transcribe`) ve tanım uygulanmaz; 503 → girdinin altında sunucu mesajı.
// Anahtar kapalıyken (rapor_asistani) sayfa AssistantBar'ı hiç çizmez — düğme o koşula bağlıdır (ReportsPage).
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import type { AsistanEylemi, Katalog, RaporTanimi } from "@/lib/reports";
import { AssistantBar } from "./AssistantBar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KATALOG = {
    veri_kaynaklari: [
        { anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: [], kolonlar: [], hizli_filtreler: [], kolon_setleri: [] },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
} as unknown as Katalog;
const MEVCUT: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["subject"], filtreler: [], siralama: [] };

class SahteRecorder {
    static isTypeSupported = (t: string) => t === "audio/webm;codecs=opus";
    state: "inactive" | "recording" = "inactive";
    mimeType: string;
    ondataavailable: ((e: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    constructor(_stream: unknown, opts?: { mimeType?: string }) {
        this.mimeType = opts?.mimeType ?? "";
    }
    start() {
        this.state = "recording";
    }
    stop() {
        if (this.state === "inactive") return;
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["ses"], { type: this.mimeType }) });
        this.onstop?.();
    }
}

let track: { stop: ReturnType<typeof vi.fn> };

function ortamiKur() {
    track = { stop: vi.fn() };
    vi.stubGlobal("MediaRecorder", SahteRecorder);
    Object.defineProperty(navigator, "mediaDevices", {
        value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [track] })) },
        configurable: true,
    });
}

const yanit = (status: number, body: unknown) =>
    ({ ok: status >= 200 && status < 300, status, json: async () => body }) as unknown as Response;

let root: Root | null = null;
let kap: HTMLDivElement;
let onTanimUygula: Mock<(t: RaporTanimi, e: AsistanEylemi | null) => Promise<boolean>>;

async function bosalt() {
    for (let i = 0; i < 8; i++) {
        await act(async () => {
            await Promise.resolve();
        });
    }
}
async function ciz(yukleniyor = false) {
    await act(async () => {
        root!.render(
            <AssistantBar
                yukleniyor={yukleniyor}
                katalog={KATALOG}
                veriKaynagi="davalar"
                mevcutTanim={MEVCUT}
                onKapali={vi.fn()}
                onTanimUygula={onTanimUygula}
                geriAlinabilir={false}
                onGeriAl={vi.fn()}
            />,
        );
    });
    await bosalt();
}
const girdi = () => kap.querySelector<HTMLTextAreaElement>("[aria-label='Asistana mesaj']")!;
const mic = () => kap.querySelector<HTMLButtonElement>("[data-testid='mic-button']");
async function tikla(el: Element) {
    await act(async () => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await bosalt();
}
function yaz(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), "value")!.set!;
    act(() => {
        setter.call(el, value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
    });
}

beforeEach(() => {
    sessionStorage.clear();   // 28.09 rapor çalışması sekme oturumunda — testler birbirine sızmasın
    fetchMock.mockReset();
    onTanimUygula = vi.fn(async (_t: RaporTanimi, _e: AsistanEylemi | null) => true);
    kap = document.createElement("div");
    document.body.appendChild(kap);
    root = createRoot(kap);
});
afterEach(() => {
    act(() => root!.unmount());
    root = null;
    kap.remove();
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "mediaDevices");
});

describe("AssistantBar mikrofon (G217)", () => {
    it("desteklenmeyen ortamda düğme yok", async () => {
        await ciz();
        expect(girdi()).not.toBeNull();
        expect(mic()).toBeNull();
    });

    it("iskelet (yukleniyor) hâlinde girdi de düğme de yok", async () => {
        ortamiKur();
        await ciz(true);
        expect(kap.querySelector("[aria-label='Asistana mesaj']")).toBeNull();
        expect(mic()).toBeNull();
    });

    it("kayıt → durdur → metin girdinin sonuna eklenir, odak girdide; asistana istek gitmez", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "derdest davaları listele" }));
        await ciz();
        yaz(girdi(), "Ankara");
        (document.activeElement as HTMLElement | null)?.blur();

        await tikla(mic()!);
        expect(mic()!.getAttribute("aria-pressed")).toBe("true");
        await tikla(mic()!);

        expect(girdi().value).toBe("Ankara derdest davaları listele");
        expect(document.activeElement).toBe(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/transcribe");
        expect(onTanimUygula).not.toHaveBeenCalled();
        expect(kap.querySelector("[data-testid='sohbet-asistan']")).toBeNull();
        expect(track.stop).toHaveBeenCalled();
    });

    it("503 → girdinin altında sunucu mesajı", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(503, { detail: "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin." }));
        await ciz();
        await tikla(mic()!);
        await tikla(mic()!);
        expect(kap.querySelector("[data-testid='mic-durum']")?.textContent).toBe(
            "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin.",
        );
        expect(girdi().value).toBe("");
    });
});
