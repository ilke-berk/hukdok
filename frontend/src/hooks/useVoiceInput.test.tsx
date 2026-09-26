// @vitest-environment jsdom
// useVoiceInput (G217) — `MediaRecorder`, `getUserMedia` ve `apiClient` sahte: destek yokken `destekleniyor=false`,
// tür seçim sırası, izin reddi uyarısı, kayıt→durdur→çeviri→`onMetin`, boş metinde "Ses anlaşılamadı", 60 sn'de
// kendiliğinden durma (sahte zamanlayıcı), iptal/unmount'ta track.stop + bekleyen isteğin abort'u, 503 mesajı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    AZAMI_KAYIT_SN, IZIN_REDDI_MESAJI, SES_ANLASILAMADI_MESAJI, kayitTuruSec, metneEkle, sureEtiketi, useVoiceInput,
    type VoiceInput,
} from "./useVoiceInput";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

class SahteRecorder {
    static desteklenen = new Set(["audio/webm;codecs=opus"]);
    static isTypeSupported = (t: string) => SahteRecorder.desteklenen.has(t);
    static son: SahteRecorder | null = null;
    state: "inactive" | "recording" = "inactive";
    mimeType: string;
    ondataavailable: ((e: { data: Blob }) => void) | null = null;
    onstop: (() => void) | null = null;
    constructor(_stream: unknown, opts?: { mimeType?: string }) {
        this.mimeType = opts?.mimeType ?? "";
        SahteRecorder.son = this;
    }
    start() {
        this.state = "recording";
    }
    stop() {
        if (this.state === "inactive") return;
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["ses-verisi"], { type: this.mimeType }) });
        this.onstop?.();
    }
}

let track: { stop: ReturnType<typeof vi.fn> };
let getUserMedia: ReturnType<typeof vi.fn>;

function ortamiKur() {
    track = { stop: vi.fn() };
    getUserMedia = vi.fn(async () => ({ getTracks: () => [track] }));
    SahteRecorder.son = null;
    SahteRecorder.desteklenen = new Set(["audio/webm;codecs=opus"]);
    vi.stubGlobal("MediaRecorder", SahteRecorder);
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
}

function ortamiKaldir() {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, "mediaDevices");
}

const yanit = (status: number, body: unknown) =>
    ({ ok: status >= 200 && status < 300, status, json: async () => body }) as unknown as Response;

let root: Root | null = null;
let kap: HTMLDivElement | null = null;
let ses: VoiceInput;
let gelenler: string[];

function Kosum() {
    ses = useVoiceInput({ onMetin: m => gelenler.push(m) });
    return null;
}

function ciz() {
    kap = document.createElement("div");
    document.body.appendChild(kap);
    root = createRoot(kap);
    act(() => root!.render(<Kosum />));
}

async function bosalt() {
    for (let i = 0; i < 8; i++) {
        await act(async () => {
            await Promise.resolve();
        });
    }
}

beforeEach(() => {
    fetchMock.mockReset();
    gelenler = [];
});

afterEach(() => {
    if (root) act(() => root!.unmount());
    root = null;
    kap?.remove();
    kap = null;
    ortamiKaldir();
    vi.useRealTimers();
});

describe("saf yardımcılar", () => {
    it("metneEkle: sona boşlukla ekler, boş mevcut/yeni durumlarını doğru işler", () => {
        expect(metneEkle("", "merhaba")).toBe("merhaba");
        expect(metneEkle("   ", "merhaba")).toBe("merhaba");
        expect(metneEkle("dava", "açıldı mı")).toBe("dava açıldı mı");
        expect(metneEkle("dava ", "açıldı mı")).toBe("dava açıldı mı");
        expect(metneEkle("dava", "  ")).toBe("dava");
    });

    it("sureEtiketi 0:12 biçimi", () => {
        expect(sureEtiketi(0)).toBe("0:00");
        expect(sureEtiketi(12)).toBe("0:12");
        expect(sureEtiketi(60)).toBe("1:00");
    });

    it("kayitTuruSec: webm/opus → ogg → mp4 sırası", () => {
        ortamiKur();
        expect(kayitTuruSec()).toBe("audio/webm;codecs=opus");
        SahteRecorder.desteklenen = new Set(["audio/ogg;codecs=opus", "audio/mp4"]);
        expect(kayitTuruSec()).toBe("audio/ogg;codecs=opus");
        SahteRecorder.desteklenen = new Set(["audio/mp4"]);
        expect(kayitTuruSec()).toBe("audio/mp4");
        SahteRecorder.desteklenen = new Set();
        expect(kayitTuruSec()).toBe("");
    });
});

describe("useVoiceInput", () => {
    it("navigator.mediaDevices / MediaRecorder yoksa destekleniyor=false ve baslat hiçbir şey yapmaz", async () => {
        ciz();
        expect(ses.destekleniyor).toBe(false);
        await act(async () => {
            await ses.baslat();
        });
        expect(ses.durum).toBe("bosta");
    });

    it("MediaRecorder var ama mediaDevices yoksa da desteklenmez", () => {
        vi.stubGlobal("MediaRecorder", SahteRecorder);
        ciz();
        expect(ses.destekleniyor).toBe(false);
    });

    it("izin reddi → durum hata + 'Mikrofon izni verilmedi'", async () => {
        ortamiKur();
        getUserMedia.mockRejectedValue(new DOMException("hayır", "NotAllowedError"));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
        expect(ses.durum).toBe("hata");
        expect(ses.uyari).toBe(IZIN_REDDI_MESAJI);
        expect(SahteRecorder.son).toBeNull();
    });

    it("kayıt → durdur → çeviri → onMetin(trim'li metin); track'ler durur; tür webm/opus", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: " müvekkil kimdi " }));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        expect(ses.durum).toBe("kayitta");
        expect(SahteRecorder.son?.mimeType).toBe("audio/webm;codecs=opus");

        await act(async () => {
            ses.durdur();
        });
        await bosalt();

        expect(track.stop).toHaveBeenCalled();
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/transcribe");
        expect(((fetchMock.mock.calls[0][1] as RequestInit).body as FormData).get("ses")).toBeInstanceOf(Blob);
        expect(gelenler).toEqual(["müvekkil kimdi"]);
        expect(ses.durum).toBe("bosta");
        expect(ses.uyari).toBeNull();
    });

    it("çeviri sürerken durum 'cevriliyor'", async () => {
        ortamiKur();
        let coz: (r: Response) => void = () => {};
        fetchMock.mockReturnValue(new Promise<Response>(r => { coz = r; }));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        await act(async () => {
            ses.durdur();
        });
        expect(ses.durum).toBe("cevriliyor");
        await act(async () => {
            coz(yanit(200, { metin: "tamam" }));
        });
        await bosalt();
        expect(ses.durum).toBe("bosta");
        expect(gelenler).toEqual(["tamam"]);
    });

    it("boş metin → 'Ses anlaşılamadı' bilgisi, onMetin('')", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "" }));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        await act(async () => {
            ses.durdur();
        });
        await bosalt();
        expect(ses.uyari).toBe(SES_ANLASILAMADI_MESAJI);
        expect(ses.durum).toBe("bosta");
        expect(gelenler).toEqual([""]);
    });

    it("503 → durum hata + sunucunun Türkçe mesajı", async () => {
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(503, { detail: "Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin." }));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        await act(async () => {
            ses.durdur();
        });
        await bosalt();
        expect(ses.durum).toBe("hata");
        expect(ses.uyari).toBe("Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin.");
        expect(gelenler).toEqual([]);
    });

    it(`${AZAMI_KAYIT_SN} sn'de kendiliğinden durur, sayaç saniye sayar`, async () => {
        vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
        ortamiKur();
        fetchMock.mockResolvedValue(yanit(200, { metin: "uzun konuşma" }));
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        act(() => {
            vi.advanceTimersByTime(12_000);
        });
        expect(ses.gecenSn).toBe(12);
        expect(ses.durum).toBe("kayitta");
        expect(fetchMock).not.toHaveBeenCalled();

        act(() => {
            vi.advanceTimersByTime((AZAMI_KAYIT_SN - 12) * 1000);
        });
        await bosalt();
        expect(SahteRecorder.son?.state).toBe("inactive");
        expect(track.stop).toHaveBeenCalled();
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(gelenler).toEqual(["uzun konuşma"]);
    });

    it("kayıt sırasında unmount → track.stop, istek atılmaz", async () => {
        ortamiKur();
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        act(() => root!.unmount());
        root = null;
        await bosalt();
        expect(track.stop).toHaveBeenCalled();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("çeviri beklerken unmount → bekleyen istek abort edilir, onMetin çağrılmaz", async () => {
        ortamiKur();
        let sinyal: AbortSignal | undefined;
        let coz: (r: Response) => void = () => {};
        fetchMock.mockImplementation((_yol: string, secenek: RequestInit) => {
            sinyal = secenek.signal ?? undefined;
            return new Promise<Response>(r => { coz = r; });
        });
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        await act(async () => {
            ses.durdur();
        });
        expect(sinyal?.aborted).toBe(false);
        act(() => root!.unmount());
        root = null;
        expect(sinyal?.aborted).toBe(true);
        coz(yanit(200, { metin: "geç geldi" }));
        await bosalt();
        expect(gelenler).toEqual([]);
    });

    it("izin beklenirken unmount → gelen akışın track'leri hemen durdurulur", async () => {
        ortamiKur();
        let akisVer: (s: unknown) => void = () => {};
        getUserMedia.mockReturnValue(new Promise(r => { akisVer = r; }));
        ciz();
        let bekleyen: Promise<void> = Promise.resolve();
        act(() => {
            bekleyen = ses.baslat();
        });
        expect(ses.durum).toBe("izin_isteniyor");
        act(() => root!.unmount());
        root = null;
        akisVer({ getTracks: () => [track] });
        await bekleyen;
        expect(track.stop).toHaveBeenCalled();
        expect(SahteRecorder.son).toBeNull();
    });

    it("iptal → track.stop, kayıt çöpe (istek yok), durum bosta", async () => {
        ortamiKur();
        ciz();
        await act(async () => {
            await ses.baslat();
        });
        await act(async () => {
            ses.iptal();
        });
        await bosalt();
        expect(track.stop).toHaveBeenCalled();
        expect(fetchMock).not.toHaveBeenCalled();
        expect(ses.durum).toBe("bosta");
    });
});
