// @vitest-environment jsdom
// SoruKutusu + mikrofon (G217) — `MediaRecorder`, `getUserMedia` ve `apiClient` sahte: destek yokken düğme yok;
// kayıt → durdur → metin kutudaki metnin SONUNA (boşlukla) eklenir, odak kutuya döner, `onGonder` TETİKLENMEZ;
// boş metin → "Ses anlaşılamadı"; izin reddi → "Mikrofon izni verilmedi"; 503 → sunucu mesajı; yanıt akarken
// mikrofon başlatılamaz. Ses Hukukbot'a gitmez: tek istek HUKDOK `/api/transcribe`.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import { SoruKutusu } from "./SoruKutusu";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
let getUserMedia: ReturnType<typeof vi.fn>;

function ortamiKur() {
    track = { stop: vi.fn() };
    getUserMedia = vi.fn(async () => ({ getTracks: () => [track] }));
    vi.stubGlobal("MediaRecorder", SahteRecorder);
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
}

const yanit = (status: number, body: unknown) =>
    ({ ok: status >= 200 && status < 300, status, json: async () => body }) as unknown as Response;

let root: Root | null = null;
let kap: HTMLDivElement;
let onGonder: ReturnType<typeof vi.fn<(s: string) => void>>;
let onDurdur: ReturnType<typeof vi.fn<() => void>>;

function ciz(gonderiliyor = false) {
    act(() => root!.render(<SoruKutusu gonderiliyor={gonderiliyor} onGonder={onGonder} onDurdur={onDurdur} />));
}
const kutu = () => kap.querySelector<HTMLTextAreaElement>("[data-testid='hukukbot-soru']")!;
const mic = () => kap.querySelector<HTMLButtonElement>("[data-testid='mic-button']");
const durumSatiri = () => kap.querySelector("[data-testid='mic-durum']")?.textContent ?? null;

async function bosalt() {
    for (let i = 0; i < 8; i++) {
        await act(async () => {
            await Promise.resolve();
        });
    }
}
async function tikla(el: Element) {
    await act(async () => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await bosalt();
}
function yaz(el: HTMLTextAreaElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
    act(() => {
        setter.call(el, value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
    });
}
/** Mikrofonla bir tur: bas → (kayıt) → tekrar bas. */
async function konus() {
    await tikla(mic()!);
    expect(mic()!.getAttribute("aria-pressed")).toBe("true");
    await tikla(mic()!);
}

beforeEach(() => {
    fetchMock.mockReset();
    onGonder = vi.fn<(s: string) => void>();
    onDurdur = vi.fn<() => void>();
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

describe("SoruKutusu mikrofon (G217)", () => {
    it("desteklenmeyen ortamda mikrofon düğmesi görünmez", () => {
        ciz();
        expect(kutu()).not.toBeNull();
        expect(mic()).toBeNull();
    });

    it("kayıt → durdur → metin mevcut metnin sonuna eklenir, odak kutuda, gönderim tetiklenmez", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "davanın esas numarası nedir" }));
        ciz();
        yaz(kutu(), "Ankara 3. Asliye");
        (document.activeElement as HTMLElement | null)?.blur();

        await konus();

        expect(kutu().value).toBe("Ankara 3. Asliye davanın esas numarası nedir");
        expect(document.activeElement).toBe(kutu());
        expect(onGonder).not.toHaveBeenCalled();
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/transcribe");
        expect(track.stop).toHaveBeenCalled();
        expect(mic()!.getAttribute("aria-pressed")).toBe("false");
        expect(durumSatiri()).toBeNull();
    });

    it("boş kutuya gelen metin doğrudan yazılır", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "merhaba" }));
        ciz();
        await konus();
        expect(kutu().value).toBe("merhaba");
        expect(onGonder).not.toHaveBeenCalled();
    });

    it("boş metin → 'Ses anlaşılamadı', kutu değişmez, odak kutuya döner", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "" }));
        ciz();
        yaz(kutu(), "soru");
        await konus();
        expect(kutu().value).toBe("soru");
        expect(durumSatiri()).toBe("Ses anlaşılamadı");
        expect(document.activeElement).toBe(kutu());
        expect(onGonder).not.toHaveBeenCalled();
    });

    it("izin reddi → kutu altında 'Mikrofon izni verilmedi'", async () => {
        ortamiKur();
        getUserMedia.mockRejectedValue(new DOMException("hayır", "NotAllowedError"));
        ciz();
        await tikla(mic()!);
        expect(durumSatiri()).toBe("Mikrofon izni verilmedi");
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("503 → sunucunun Türkçe mesajı, kutu değişmez", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(503, { detail: "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin." }));
        ciz();
        await konus();
        expect(durumSatiri()).toBe("Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin.");
        expect(kutu().value).toBe("");
        expect(onGonder).not.toHaveBeenCalled();
    });

    it("yanıt akarken mikrofon başlatılamaz", () => {
        ortamiKur();
        ciz(true);
        expect(mic()!.disabled).toBe(true);
    });

    it("kayıt sürerken bileşen kalkarsa track.stop", async () => {
        ortamiKur();
        ciz();
        await tikla(mic()!);
        act(() => root!.unmount());
        root = createRoot(kap);
        expect(track.stop).toHaveBeenCalled();
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
