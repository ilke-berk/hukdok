// caseNotes (G215) — G214 sözleşmesindeki yollar/şekiller, sınır doğrulaması, TR tarih biçimi
// ve hata eşlemesi. `apiClient` sahte: yalnız çağrılan yol/gövde ve yanıt eşlemesi denetlenir.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    CaseNoteError,
    NOT_AZAMI_UZUNLUK,
    NOT_SAYAC_ESIGI,
    ekle,
    listele,
    notGecerliMi,
    notTarihi,
    sil,
    yazanEtiketi,
    type CaseNote,
} from "./caseNotes";

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const NOT: CaseNote = {
    id: 5,
    body: "Duruşma ertelendi",
    author_name: "Av. Ayşe Kaya",
    author_email: "ayse@example.com",
    created_at: "2026-09-26T07:05:00Z",
    can_delete: true,
};

beforeEach(() => {
    fetchMock.mockReset();
});

describe("listele", () => {
    it("GET /api/cases/{id}/notes çağırır ve diziyi döner", async () => {
        fetchMock.mockResolvedValue(jsonYanit(200, [NOT]));
        await expect(listele(42)).resolves.toEqual([NOT]);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/cases/42/notes");
        expect(fetchMock.mock.calls[0][1]).toBeUndefined();
    });

    it("404'te Türkçe mesajlı CaseNoteError fırlatır", async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 404 }));
        await expect(listele(42)).rejects.toMatchObject({
            name: "CaseNoteError",
            status: 404,
            message: "Dava bulunamadı.",
        });
    });
});

describe("ekle", () => {
    it("POST gövdesi {body} ve 201 yanıtındaki tek notu döner", async () => {
        fetchMock.mockResolvedValue(jsonYanit(201, NOT));
        await expect(ekle(42, "Duruşma ertelendi")).resolves.toEqual(NOT);
        const [yol, secenek] = fetchMock.mock.calls[0];
        expect(yol).toBe("/api/cases/42/notes");
        expect(secenek.method).toBe("POST");
        expect(JSON.parse(secenek.body as string)).toEqual({ body: "Duruşma ertelendi" });
    });

    it("422'de sınır mesajı verir", async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 422 }));
        const err = await ekle(42, "x").catch((e: unknown) => e);
        expect(err).toBeInstanceOf(CaseNoteError);
        expect((err as CaseNoteError).status).toBe(422);
        expect((err as CaseNoteError).message).toBe("Not boş olamaz ve en fazla 5000 karakter olabilir.");
    });
});

describe("sil", () => {
    it("DELETE /api/cases/{id}/notes/{noteId}; 204 başarıdır", async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
        await expect(sil(42, 5)).resolves.toBeUndefined();
        const [yol, secenek] = fetchMock.mock.calls[0];
        expect(yol).toBe("/api/cases/42/notes/5");
        expect(secenek.method).toBe("DELETE");
    });

    it("403'te yetki mesajı", async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 403 }));
        await expect(sil(42, 5)).rejects.toMatchObject({
            status: 403,
            message: "Bu notu silme yetkiniz yok (yalnız yazan ya da yönetici silebilir).",
        });
    });

    it("404'te bulunamadı mesajı", async () => {
        fetchMock.mockResolvedValue(new Response(null, { status: 404 }));
        await expect(sil(42, 5)).rejects.toMatchObject({
            status: 404,
            message: "Not bulunamadı; daha önce silinmiş olabilir.",
        });
    });
});

describe("notGecerliMi", () => {
    it("sınırlar: boş, yalnız boşluk, 1, 5000, 5001", () => {
        expect(NOT_AZAMI_UZUNLUK).toBe(5000);
        expect(NOT_SAYAC_ESIGI).toBe(4500);
        expect(notGecerliMi("")).toBe(false);
        expect(notGecerliMi("   \n\t ")).toBe(false);
        expect(notGecerliMi("a")).toBe(true);
        expect(notGecerliMi("a".repeat(5000))).toBe(true);
        expect(notGecerliMi("a".repeat(5001))).toBe(false);
        // trim sonrası sayılır (sunucu kuralıyla aynı)
        expect(notGecerliMi(`  ${"a".repeat(5000)}  `)).toBe(true);
    });
});

describe("yazanEtiketi", () => {
    it("ad varsa ad, yoksa e-posta", () => {
        expect(yazanEtiketi(NOT)).toBe("Av. Ayşe Kaya");
        expect(yazanEtiketi({ author_name: null, author_email: "x@y.z" })).toBe("x@y.z");
        expect(yazanEtiketi({ author_name: "  ", author_email: "x@y.z" })).toBe("x@y.z");
    });
});

describe("notTarihi", () => {
    it("UTC damgasını Türkiye saatiyle TR biçiminde basar", () => {
        // 07:05 UTC = 10:05 TR (UTC+3)
        expect(notTarihi("2026-09-26T07:05:00Z")).toBe("26.09.2026 10:05");
        // gün dönümü: 22:30 UTC = ertesi gün 01:30 TR
        expect(notTarihi("2026-01-31T22:30:00+00:00")).toBe("01.02.2026 01:30");
    });

    it("çözülemeyen değeri aynen döner", () => {
        expect(notTarihi("bozuk")).toBe("bozuk");
    });
});
