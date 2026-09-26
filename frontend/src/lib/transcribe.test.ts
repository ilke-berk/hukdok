// transcribe (G217) — G216 sözleşmesi: `POST /api/transcribe`, tek FormData alanı `ses` (türe uygun uzantılı dosya
// adı), `apiClient` üzerinden; 200 → trim'li metin; 413/415/422/503 ayrı Türkçe mesajlı `SesCeviriHatasi`.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import { SES_HATA_MESAJLARI, SES_MESGUL_MESAJI, SesCeviriHatasi, sesUzantisi, sesiYaziyaCevir } from "./transcribe";

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
    fetchMock.mockReset();
});

describe("sesUzantisi", () => {
    it("parametreleri atıp türe uygun uzantı verir", () => {
        expect(sesUzantisi("audio/webm;codecs=opus")).toBe("webm");
        expect(sesUzantisi("audio/ogg; codecs=opus")).toBe("ogg");
        expect(sesUzantisi("audio/mp4")).toBe("m4a");
        expect(sesUzantisi("audio/mpeg")).toBe("mp3");
        expect(sesUzantisi("audio/wav")).toBe("wav");
        expect(sesUzantisi("")).toBe("webm");
    });
});

describe("sesiYaziyaCevir", () => {
    it("POST /api/transcribe, FormData alanı `ses`, uzantılı dosya adı, signal iletilir; metin trim'lenir", async () => {
        fetchMock.mockResolvedValue(jsonYanit(200, { metin: "  dava açıldı mı  " }));
        const ctrl = new AbortController();
        const blob = new Blob(["abc"], { type: "audio/ogg;codecs=opus" });

        await expect(sesiYaziyaCevir(blob, ctrl.signal)).resolves.toBe("dava açıldı mı");

        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [yol, secenek] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(yol).toBe("/api/transcribe");
        expect(secenek.method).toBe("POST");
        expect(secenek.signal).toBe(ctrl.signal);
        expect(secenek.body).toBeInstanceOf(FormData);
        const form = secenek.body as FormData;
        expect([...form.keys()]).toEqual(["ses"]);
        const dosya = form.get("ses") as File;
        expect(dosya.name).toBe("kayit.ogg");
        expect(dosya.size).toBe(3);
    });

    it("konuşma yoksa boş string döner", async () => {
        fetchMock.mockResolvedValue(jsonYanit(200, { metin: "" }));
        await expect(sesiYaziyaCevir(new Blob(["x"], { type: "audio/webm" }))).resolves.toBe("");
    });

    it.each([413, 415, 422])("%i → ayrı Türkçe mesajlı hata", async (status) => {
        fetchMock.mockResolvedValue(jsonYanit(status, { detail: "x" }));
        await expect(sesiYaziyaCevir(new Blob(["x"], { type: "audio/webm" }))).rejects.toMatchObject({
            name: "SesCeviriHatasi",
            status,
            message: SES_HATA_MESAJLARI[status],
        });
    });

    it("413/415/422/503 mesajları birbirinden farklı", () => {
        const mesajlar = [413, 415, 422, 503].map(s => SES_HATA_MESAJLARI[s]);
        expect(new Set(mesajlar).size).toBe(4);
    });

    it("503 → sunucunun detail metni", async () => {
        fetchMock.mockResolvedValue(jsonYanit(503, { detail: SES_MESGUL_MESAJI }));
        const hata = await sesiYaziyaCevir(new Blob(["x"], { type: "audio/webm" })).catch(e => e);
        expect(hata).toBeInstanceOf(SesCeviriHatasi);
        expect(hata.status).toBe(503);
        expect(hata.message).toBe("Ses şu an yazıya çevrilemedi, lütfen tekrar deneyin.");
    });

    it("503 gövdesi okunamazsa da sabit mesaj", async () => {
        fetchMock.mockResolvedValue(new Response("bozuk", { status: 503 }));
        await expect(sesiYaziyaCevir(new Blob(["x"], { type: "audio/webm" }))).rejects.toMatchObject({
            status: 503,
            message: SES_MESGUL_MESAJI,
        });
    });

    it("çağıranın iptali (AbortError) aynen fırlar", async () => {
        const abort = new DOMException("iptal", "AbortError");
        fetchMock.mockRejectedValue(abort);
        await expect(sesiYaziyaCevir(new Blob(["x"], { type: "audio/webm" }))).rejects.toBe(abort);
    });
});
