// caseHizmetleri (G252) — G248 sözleşmesindeki yollar/gövdeler, müvekkile göre gruplama ve hata
// eşlemesi. `apiClient` sahte: yalnız çağrılan yol/gövde ve yanıt eşlemesi denetlenir.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    type CaseHizmeti,
    ayniKume,
    kumeyiYaz,
    listele,
    muvekkileGoreGrupla,
    tekilAdlar,
} from "./caseHizmetleri";

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const satir = (kismi: Partial<CaseHizmeti> & Pick<CaseHizmeti, "id" | "case_party_id" | "hizmet_turu">): CaseHizmeti => ({
    muvekkil_adi: null,
    kaynak: "elle",
    foy_id: null,
    sistem_no: null,
    ...kismi,
});

beforeEach(() => {
    fetchMock.mockReset();
});

describe("muvekkileGoreGrupla", () => {
    const MUVEKKILLER = [{ id: 11, name: "Dr. Ayşe Kaya" }, { id: 12, name: "Özel Şifa Hastanesi" }];

    it("satırları kartın müvekkil sırasıyla gruplar; föy ve elle ayrı durur", () => {
        const gruplar = muvekkileGoreGrupla(MUVEKKILLER, [
            satir({ id: 1, case_party_id: 12, hizmet_turu: "Danışmanlık" }),
            satir({ id: 2, case_party_id: 11, hizmet_turu: "Dava Takibi", kaynak: "foy", foy_id: 7, sistem_no: "S-100" }),
            satir({ id: 3, case_party_id: 11, hizmet_turu: "Lexis Rapor" }),
        ]);
        expect(gruplar.map(g => g.muvekkilAdi)).toEqual(["Dr. Ayşe Kaya", "Özel Şifa Hastanesi"]);
        expect(gruplar[0].foy.map(s => s.id)).toEqual([2]);
        expect(gruplar[0].elle.map(s => s.id)).toEqual([3]);
        expect(gruplar[1].foy).toEqual([]);
        expect(gruplar[1].elle.map(s => s.id)).toEqual([1]);
        expect(gruplar.every(g => !g.kartDisi)).toBe(true);
    });

    it("hizmeti olmayan müvekkil boş grupla gelir (\"Hizmet girilmemiş\" satırı için)", () => {
        const gruplar = muvekkileGoreGrupla(MUVEKKILLER, []);
        expect(gruplar).toHaveLength(2);
        expect(gruplar.every(g => g.foy.length === 0 && g.elle.length === 0)).toBe(true);
    });

    it("tarafı müvekkil listesinde olmayan satır kaybolmaz: sona kartDisi grubu eklenir", () => {
        const gruplar = muvekkileGoreGrupla(MUVEKKILLER, [
            satir({ id: 9, case_party_id: 99, hizmet_turu: "Danışmanlık", muvekkil_adi: "Eski Müvekkil" }),
            satir({ id: 10, case_party_id: 98, hizmet_turu: "Danışmanlık" }),
        ]);
        expect(gruplar.map(g => [g.casePartyId, g.muvekkilAdi, g.kartDisi])).toEqual([
            [11, "Dr. Ayşe Kaya", false],
            [12, "Özel Şifa Hastanesi", false],
            [99, "Eski Müvekkil", true],
            [98, "Taraf #98", true],
        ]);
    });
});

describe("küme yardımcıları", () => {
    it("ayniKume sıra ve tekrardan bağımsızdır", () => {
        expect(ayniKume(["A", "B"], ["B", "A"])).toBe(true);
        expect(ayniKume(["A", "A", "B"], ["B", "A"])).toBe(true);
        expect(ayniKume([], [])).toBe(true);
        expect(ayniKume(["A"], ["A", "B"])).toBe(false);
        expect(ayniKume(["A", "B"], ["A", "C"])).toBe(false);
        expect(ayniKume(["A"], [])).toBe(false);
    });

    it("tekilAdlar ilk görülme sırasını korur", () => {
        expect(tekilAdlar(["B", "A", "B", "C", "A"])).toEqual(["B", "A", "C"]);
    });
});

describe("listele", () => {
    it("GET /api/cases/{id}/hizmetler çağırır ve diziyi döner", async () => {
        const liste = [satir({ id: 1, case_party_id: 11, hizmet_turu: "Dava Takibi" })];
        fetchMock.mockResolvedValue(jsonYanit(200, liste));
        await expect(listele(42)).resolves.toEqual(liste);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/cases/42/hizmetler");
        expect(fetchMock.mock.calls[0][1]).toBeUndefined();
    });

    it("404 ve diğer hatalarda Türkçe mesajlı CaseHizmetError fırlatır", async () => {
        fetchMock.mockResolvedValueOnce(new Response(null, { status: 404 }));
        await expect(listele(42)).rejects.toMatchObject({ name: "CaseHizmetError", status: 404, message: "Dava bulunamadı." });
        fetchMock.mockResolvedValueOnce(new Response(null, { status: 500 }));
        await expect(listele(42)).rejects.toMatchObject({ name: "CaseHizmetError", status: 500, message: "Hizmetler yüklenemedi." });
    });
});

describe("kumeyiYaz", () => {
    it("PUT /api/cases/{id}/hizmetler/{case_party_id} gövdesi {hizmet_turleri}; güncel listeyi döner", async () => {
        const guncel = [
            satir({ id: 5, case_party_id: 11, hizmet_turu: "Danışmanlık" }),
            satir({ id: 6, case_party_id: 11, hizmet_turu: "Dava Takibi" }),
        ];
        fetchMock.mockResolvedValue(jsonYanit(200, guncel));
        await expect(kumeyiYaz(42, 11, ["Dava Takibi", "Danışmanlık"])).resolves.toEqual(guncel);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [yol, secenek] = fetchMock.mock.calls[0];
        expect(yol).toBe("/api/cases/42/hizmetler/11");
        expect(secenek.method).toBe("PUT");
        expect(JSON.parse(secenek.body)).toEqual({ hizmet_turleri: ["Dava Takibi", "Danışmanlık"] });
    });

    it("boş küme de gönderilir (elle satırların tamamı silinir)", async () => {
        fetchMock.mockResolvedValue(jsonYanit(200, []));
        await kumeyiYaz(42, 11, []);
        expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ hizmet_turleri: [] });
    });

    it("422'de sunucunun Türkçe detail metni gösterilir", async () => {
        fetchMock.mockResolvedValue(jsonYanit(422, { detail: "Hizmet türü listede yok: \"Eski Hizmet\"." }));
        await expect(kumeyiYaz(42, 11, ["Eski Hizmet"])).rejects.toMatchObject({
            name: "CaseHizmetError",
            status: 422,
            message: "Hizmet türü listede yok: \"Eski Hizmet\".",
        });
    });

    it("422 doğrulama dizisi (string olmayan detail) → Türkçe varsayılan metin", async () => {
        fetchMock.mockResolvedValue(jsonYanit(422, { detail: [{ loc: ["body", "hizmet_turleri"], msg: "field required" }] }));
        await expect(kumeyiYaz(42, 11, [])).rejects.toMatchObject({
            status: 422,
            message: "Seçilen hizmet kaydedilemedi: hizmet türü listede yok ya da taraf bu kartın müvekkili değil.",
        });
    });

    it("409'da sunucu metni; gövde yoksa Türkçe varsayılan", async () => {
        fetchMock.mockResolvedValueOnce(jsonYanit(409, {
            detail: "Bu kayıt şu an toplu bir veri işleminde kullanılıyor; değişikliğiniz kaydedilmedi. Birkaç dakika sonra tekrar deneyin.",
        }));
        await expect(kumeyiYaz(42, 11, ["Dava Takibi"])).rejects.toMatchObject({
            status: 409,
            message: "Bu kayıt şu an toplu bir veri işleminde kullanılıyor; değişikliğiniz kaydedilmedi. Birkaç dakika sonra tekrar deneyin.",
        });
        fetchMock.mockResolvedValueOnce(new Response(null, { status: 409 }));
        await expect(kumeyiYaz(42, 11, ["Dava Takibi"])).rejects.toMatchObject({
            status: 409,
            message: "Bu kayıt şu an başka bir işlemde kullanılıyor; birkaç dakika sonra tekrar deneyin.",
        });
    });

    it("404 ve 500 Türkçe metne eşlenir (sunucu detail'i yok sayılır)", async () => {
        fetchMock.mockResolvedValueOnce(jsonYanit(404, { detail: "Dava bulunamadı" }));
        await expect(kumeyiYaz(42, 11, [])).rejects.toMatchObject({ status: 404, message: "Dava bulunamadı." });
        fetchMock.mockResolvedValueOnce(jsonYanit(500, { detail: "Internal Server Error" }));
        await expect(kumeyiYaz(42, 11, [])).rejects.toMatchObject({ status: 500, message: "Hizmetler kaydedilemedi." });
    });
});
