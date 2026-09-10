// reportsChat (G135) — `/api/reports/chat` NDJSON okuyucusu: gövde §2.6 birebir (`mesajlar` ≤20 +
// `mevcut_tanim`), yarım satır tamponu, `complete`/`failed` SON olay, `complete` yok → hata,
// `failed` → AsistanFailedError (error_kod), 409 → AsistanKapaliError, 403 → yetki; anahtar okuyucu.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import type { AsistanMesaji, Katalog, RaporTanimi } from "./reports";
import {
    ASISTAN_AKIS_EKSIK, ASISTAN_KAPALI_MESAJI, ASISTAN_MESAJ_MAX, ASISTAN_YETKI_MESAJI,
    AsistanFailedError, AsistanKapaliError, AsistanYetkiError,
    chatReport, errorKodIpucu, gecmisiKirp, onayNiyeti, ornekIstemler, raporAsistaniAcikMi, sohbetGecmisi, tanimAyni, tanimAyrintisi,
    tanimOzeti,
} from "./reportsChat";

/** Ham chunk'ları (satır sınırına saygı göstermeden) veren sahte akış yanıtı. */
function streamResponse(chunks: string[], status = 200): Response {
    const encoder = new TextEncoder();
    const parcalar = chunks.map(c => encoder.encode(c));
    let i = 0;
    const cancel = vi.fn(async () => undefined);
    return {
        ok: status >= 200 && status < 300,
        status,
        statusText: "OK",
        body: {
            getReader: () => ({
                read: async () =>
                    i < parcalar.length
                        ? { value: parcalar[i++], done: false }
                        : { value: undefined, done: true },
                cancel,
            }),
        },
        json: async () => ({}),
    } as unknown as Response;
}

const satir = (o: unknown) => JSON.stringify(o) + "\n";

const TANIM: RaporTanimi = {
    veri_kaynagi: "davalar",
    kolonlar: ["tracking_no", "subject"],
    filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }],
    siralama: [{ alan: "opening_date", yon: "desc" }],
};

const MESAJ: AsistanMesaji = { rol: "user", icerik: "Derdest davaları listele" };

const govde = () => JSON.parse(fetchMock.mock.calls[0][1].body as string);

describe("chatReport — gövde ve HTTP durumları", () => {
    beforeEach(() => {
        fetchMock.mockReset();
    });

    it("POST /api/reports/chat gövdesi {mesajlar, mevcut_tanim} — plan §2.6 birebir", async () => {
        fetchMock.mockResolvedValue(streamResponse([satir({ status: "complete", cevap: "Hazır.", tanim: TANIM, eylem: null })]));

        await chatReport([MESAJ], TANIM);

        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/chat");
        expect(fetchMock.mock.calls[0][1].method).toBe("POST");
        const g = govde();
        expect(Object.keys(g).sort()).toEqual(["mesajlar", "mevcut_tanim"]);
        expect(g.mesajlar).toEqual([{ rol: "user", icerik: "Derdest davaları listele" }]);
        expect(g.mevcut_tanim).toEqual(TANIM);
    });

    it("mevcut tanım yoksa `mevcut_tanim: null` gider (alan atlanmaz)", async () => {
        fetchMock.mockResolvedValue(streamResponse([satir({ status: "complete", cevap: "?", tanim: null, eylem: null })]));

        await chatReport([MESAJ], null);

        expect(govde()).toHaveProperty("mevcut_tanim", null);
    });

    it("sohbet geçmişinden en fazla 20 mesaj gönderilir — en yeniler (K6)", async () => {
        fetchMock.mockResolvedValue(streamResponse([satir({ status: "complete", cevap: "ok", tanim: null, eylem: null })]));
        const uzun: AsistanMesaji[] = Array.from({ length: 27 }, (_, i) => ({
            rol: i % 2 === 0 ? "user" : "assistant",
            icerik: `m${i}`,
        }));

        await chatReport(uzun, null);

        const g = govde();
        expect(g.mesajlar).toHaveLength(ASISTAN_MESAJ_MAX);
        expect(g.mesajlar[0].icerik).toBe("m7");
        expect(g.mesajlar[19].icerik).toBe("m26");
    });

    it("409 → AsistanKapaliError (anahtar kapalı, K8)", async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: "rapor_asistani kapalı" }) });

        const p = chatReport([MESAJ], null);
        await expect(p).rejects.toBeInstanceOf(AsistanKapaliError);
        await expect(p).rejects.toThrow(ASISTAN_KAPALI_MESAJI);
    });

    it("403 → AsistanYetkiError (yönetici uyarısı)", async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: "admin gerekli" }) });

        const p = chatReport([MESAJ], null);
        await expect(p).rejects.toBeInstanceOf(AsistanYetkiError);
        await expect(p).rejects.toThrow(ASISTAN_YETKI_MESAJI);
    });

    it("diğer HTTP hataları raporHatasiCevir ile okunur mesaja çevrilir", async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail: "bakım" }) });

        await expect(chatReport([MESAJ], null)).rejects.toThrow("bakım");
    });
});

describe("chatReport — NDJSON akışı", () => {
    beforeEach(() => {
        fetchMock.mockReset();
    });

    it("yarım satırı tamponda tutar: chunk sınırı JSON'un ortasına düşse de olaylar doğru okunur", async () => {
        const tam = satir({ status: "info", message: "Rapor tanımı hazırlanıyor" })
            + satir({ status: "complete", cevap: "Tamam.", tanim: TANIM, eylem: "onizle" });
        // Keyfi yerlerden böl — satır sonuyla hizalı DEĞİL.
        const chunks = [tam.slice(0, 17), tam.slice(17, 63), tam.slice(63, 64), tam.slice(64)];
        fetchMock.mockResolvedValue(streamResponse(chunks));
        const onInfo = vi.fn();

        const sonuc = await chatReport([MESAJ], null, { onInfo });

        expect(onInfo).toHaveBeenCalledTimes(1);
        expect(onInfo).toHaveBeenCalledWith("Rapor tanımı hazırlanıyor");
        expect(sonuc).toEqual({ cevap: "Tamam.", tanim: TANIM, eylem: "onizle", uyarilar: [] });
    });

    it("warning olayları callback'e gider VE sonuçta sırayla toplanır", async () => {
        fetchMock.mockResolvedValue(streamResponse([
            satir({ status: "warning", message: "tanım doğrulanamadı, tanım=null ile devam" }),
            satir({ status: "warning", message: "ikinci uyarı" }),
            satir({ status: "complete", cevap: "Soru: hangi veri kaynağı?", tanim: null, eylem: null }),
        ]));
        const onWarning = vi.fn();

        const sonuc = await chatReport([MESAJ], null, { onWarning });

        expect(onWarning.mock.calls.map(c => c[0])).toEqual(["tanım doğrulanamadı, tanım=null ile devam", "ikinci uyarı"]);
        expect(sonuc.uyarilar).toEqual(["tanım doğrulanamadı, tanım=null ile devam", "ikinci uyarı"]);
        expect(sonuc.tanim).toBeNull();
    });

    it("complete SON olaydır: sonrasındaki satırlar okunmaz, okuyucu bırakılır (cancel)", async () => {
        const res = streamResponse([
            satir({ status: "complete", cevap: "A", tanim: null, eylem: null }),
            satir({ status: "complete", cevap: "B", tanim: TANIM, eylem: "indir_xlsx" }),
            satir({ status: "failed", error_ozet: "sonradan", error_kod: "analysis_error" }),
        ]);
        fetchMock.mockResolvedValue(res);

        const sonuc = await chatReport([MESAJ], null);

        expect(sonuc.cevap).toBe("A");
        expect(sonuc.tanim).toBeNull();
        const reader = (res.body as unknown as { getReader: () => { cancel: ReturnType<typeof vi.fn> } }).getReader();
        expect(reader.cancel).toHaveBeenCalled();
    });

    it("failed → AsistanFailedError: error_ozet mesaj, error_kod etiket; akış orada biter", async () => {
        fetchMock.mockResolvedValue(streamResponse([
            satir({ status: "info", message: "başlıyor" }),
            satir({ status: "failed", error_ozet: "Yapay zekâ servisi şu an yoğun.", error_kod: "gemini_saturated" }),
            satir({ status: "complete", cevap: "gelmemeli", tanim: TANIM, eylem: null }),
        ]));

        const p = chatReport([MESAJ], null);
        await expect(p).rejects.toBeInstanceOf(AsistanFailedError);
        await expect(p).rejects.toThrow("Yapay zekâ servisi şu an yoğun.");
        await p.catch((e: AsistanFailedError) => {
            expect(e.kod).toBe("gemini_saturated");
        });
    });

    it("failed özet/etiket eksikse varsayılan mesaj + analysis_error", async () => {
        fetchMock.mockResolvedValue(streamResponse([satir({ status: "failed" })]));

        await chatReport([MESAJ], null).catch((e: AsistanFailedError) => {
            expect(e).toBeInstanceOf(AsistanFailedError);
            expect(e.message).toBe("Asistan isteği tamamlanamadı.");
            expect(e.kod).toBe("analysis_error");
        });
    });

    it("complete gelmeden akış kapanırsa 'akış tamamlanmadı' hatası", async () => {
        fetchMock.mockResolvedValue(streamResponse([satir({ status: "info", message: "başladı" })]));

        await expect(chatReport([MESAJ], null)).rejects.toThrow(ASISTAN_AKIS_EKSIK);
    });

    it("boş akış (hiç satır yok) da 'akış tamamlanmadı' hatasıdır", async () => {
        fetchMock.mockResolvedValue(streamResponse([]));

        await expect(chatReport([MESAJ], null)).rejects.toThrow(ASISTAN_AKIS_EKSIK);
    });

    it("son satır yeni satırsız bitse de (tamponda kalan) complete işlenir", async () => {
        fetchMock.mockResolvedValue(streamResponse([JSON.stringify({ status: "complete", cevap: "son", tanim: null, eylem: null })]));

        const sonuc = await chatReport([MESAJ], null);

        expect(sonuc.cevap).toBe("son");
    });

    it("bozuk JSON satırı atlanır (uyarı loglanır), akış sürer", async () => {
        const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
        fetchMock.mockResolvedValue(streamResponse([
            "{bozuk\n",
            satir({ status: "complete", cevap: "ok", tanim: null, eylem: null }),
        ]));

        const sonuc = await chatReport([MESAJ], null);

        expect(sonuc.cevap).toBe("ok");
        expect(warn).toHaveBeenCalledTimes(1);
        warn.mockRestore();
    });
});

describe("errorKodIpucu — etiket uzayı açık", () => {
    it("bilinen etiketlere özgü ipucu; gemini_saturated 'biraz sonra' der", () => {
        expect(errorKodIpucu("gemini_saturated")).toContain("biraz sonra");
        expect(errorKodIpucu("schema_invalid")).not.toBe(errorKodIpucu("analysis_error"));
    });

    it("tanınmayan / boş etiket analysis_error gibi ele alınır", () => {
        expect(errorKodIpucu("yeni_etiket_2027")).toBe(errorKodIpucu("analysis_error"));
        expect(errorKodIpucu(undefined)).toBe(errorKodIpucu("analysis_error"));
        expect(errorKodIpucu(null)).toBe(errorKodIpucu("analysis_error"));
    });
});

describe("sohbetGecmisi / gecmisiKirp / tanimOzeti", () => {
    it("hata kayıtları ve boş içerik geçmişe girmez; en yeni 20 kalır", () => {
        const kayitlar = [
            { id: 1, rol: "user" as const, icerik: "soru" },
            { id: 2, rol: "assistant" as const, icerik: "", hata: { ozet: "x", kod: "analysis_error" } },
            { id: 3, rol: "user" as const, icerik: "tekrar" },
            { id: 4, rol: "assistant" as const, icerik: "cevap", tanim: TANIM },
        ];
        expect(sohbetGecmisi(kayitlar)).toEqual([
            { rol: "user", icerik: "soru" },
            { rol: "user", icerik: "tekrar" },
            { rol: "assistant", icerik: "cevap" },
        ]);

        const cok = Array.from({ length: 25 }, (_, i) => ({ rol: "user" as const, icerik: `m${i}` }));
        const kirpik = gecmisiKirp(cok);
        expect(kirpik).toHaveLength(20);
        expect(kirpik[0].icerik).toBe("m5");
        // Kısa liste kopyalanır, aynı referans dönmez
        const kisa = [MESAJ];
        expect(gecmisiKirp(kisa)).toEqual(kisa);
        expect(gecmisiKirp(kisa)).not.toBe(kisa);
    });

    it("tanimOzeti kaynak + sayılar", () => {
        expect(tanimOzeti(TANIM)).toEqual({ kaynak: "davalar", kolon: 2, filtre: 1, siralama: 1 });
    });
});

describe("G167 — tanimAyrintisi / tanimAyni", () => {
    const KATALOG = {
        veri_kaynaklari: [{
            anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: [], hizli_filtreler: [], kolon_setleri: [],
            kolonlar: [
                { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin", secenek_etiketleri: null },
                { anahtar: "status", etiket: "Durum", tip: "liste", secenek_etiketleri: null },
                { anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", secenek_etiketleri: null },
                { anahtar: "muvekkil.phone", etiket: "Müvekkil kartı · Telefon", tip: "metin", secenek_etiketleri: null },
                { anahtar: "muvekkil.client_type", etiket: "Müvekkil kartı · Müvekkil Türü", tip: "liste",
                  secenek_etiketleri: { Individual: "Gerçek kişi" } },
                { anahtar: "aktif", etiket: "Aktif", tip: "mantik", secenek_etiketleri: null },
                { anahtar: "tutar", etiket: "Tutar", tip: "para", secenek_etiketleri: null },
            ],
        }],
        limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
    } as unknown as Katalog;

    it("etiket · operatör · değer satırları; tarih dd.MM.yyyy; between 'a – b'; in virgüllü + (boş); mantık Evet; seçenek etiketi; bağlı kolon etiketi; bilinmeyen anahtar aynen", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "davalar",
            kolonlar: ["tracking_no", "muvekkil.phone", "bilinmeyen"],
            filtreler: [
                { alan: "opening_date", op: "between", deger: ["2026-04-01", "2026-08-31"] },
                { alan: "status", op: "in", deger: ["Derdest", null] },
                { alan: "muvekkil.phone", op: "is_null" },
                { alan: "muvekkil.client_type", op: "eq", deger: "Individual" },
                { alan: "aktif", op: "eq", deger: true },
                { alan: "tutar", op: "gte", deger: 150000 },
                { alan: "opening_date", op: "lte", deger: "2026-12-31" },
            ],
            siralama: [{ alan: "opening_date", yon: "desc" }, { alan: "tracking_no", yon: "asc" }],
        };
        expect(tanimAyrintisi(tanim, KATALOG)).toEqual({
            kaynak: "Davalar",
            kolonlar: ["Ofis No", "Müvekkil kartı · Telefon", "bilinmeyen"],
            filtreler: [
                "Açılış Tarihi · aralıkta · 01.04.2026 – 31.08.2026",
                "Durum · şunlardan biri · Derdest, (boş)",
                "Müvekkil kartı · Telefon · boş",
                "Müvekkil kartı · Müvekkil Türü · eşittir · Gerçek kişi",
                "Aktif · eşittir · Evet",
                "Tutar · ≥ (en az) · 150000",
                "Açılış Tarihi · ≤ (en çok) · 31.12.2026",
            ],
            siralama: ["Açılış Tarihi ↓", "Ofis No ↑"],
        });
        // Katalog yok / kaynak yok: anahtarlar aynen, kart boş kalmaz
        expect(tanimAyrintisi({ ...tanim, veri_kaynagi: "yok" }, null)).toMatchObject({ kaynak: "yok", kolonlar: ["tracking_no", "muvekkil.phone", "bilinmeyen"] });
        expect(tanimAyrintisi({ ...tanim, filtreler: [], siralama: [] }, KATALOG)).toMatchObject({ filtreler: [], siralama: [] });
    });

    it("onayNiyeti: kısa onay → onizle; indirme kelimeleri → format (varsayılan Excel); başka kelime → null", () => {
        for (const m of ["tamam", "Tamam.", "evet", "Evet, doğru", "onayla", "uygula", "tamam uygula", "olur böyle", "Doğru, hadi göster",
                         "tamamdır", "peki devam", "OK", "bu şekilde listele", "hazırla"]) {
            expect(onayNiyeti(m), m).toBe("onizle");
        }
        for (const m of ["indir", "excel indir", "Excel olarak ver", "tamam, excel", "xlsx indir", "tamam indir", "excel dosyası olarak kaydet"]) {
            expect(onayNiyeti(m), m).toBe("indir_xlsx");
        }
        for (const m of ["csv", "csv indir", "tamam csv olarak ver", "CSV formatında indir"]) {
            expect(onayNiyeti(m), m).toBe("indir_csv");
        }
        for (const m of ["", "   ", "tamam ama telefonu da ekle", "nisan değil mart", "evet ama mahkemeyi çıkar", "doğru mu?",
                         "tamam bir de müvekkil kategorisi olsun", "hangi kolonlar var", "tamam tamam tamam tamam tamam tamam tamam tamam tamam"]) {
            expect(onayNiyeti(m), m).toBeNull();
        }
    });

    it("tanimAyni: alan alan eşitlik; kolon sırası, filtre değeri ve yön farkı ayrımdır; null/undefined false", () => {
        const a: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["x", "y"], filtreler: [{ alan: "s", op: "eq", deger: "1" }], siralama: [{ alan: "x", yon: "asc" }] };
        expect(tanimAyni(a, JSON.parse(JSON.stringify(a)))).toBe(true);
        expect(tanimAyni(a, { ...a, kolonlar: ["y", "x"] })).toBe(false);
        expect(tanimAyni(a, { ...a, filtreler: [{ alan: "s", op: "eq", deger: "2" }] })).toBe(false);
        expect(tanimAyni(a, { ...a, siralama: [{ alan: "x", yon: "desc" }] })).toBe(false);
        expect(tanimAyni(a, { ...a, veri_kaynagi: "muvekkiller" })).toBe(false);
        expect(tanimAyni(a, null)).toBe(false);
        expect(tanimAyni(undefined, a)).toBe(false);
    });
});

describe("raporAsistaniAcikMi — anahtar kapısı (K8)", () => {
    beforeEach(() => {
        fetchMock.mockReset();
    });

    const ayarlar = (value: boolean) => ({
        ok: true, status: 200,
        json: async () => ({ settings: [
            { key: "client_notice_enabled", value: true },
            { key: "rapor_asistani", value },
        ] }),
    });

    it("GET /api/admin/settings → rapor_asistani değeri", async () => {
        fetchMock.mockResolvedValueOnce(ayarlar(true));
        expect(await raporAsistaniAcikMi()).toBe(true);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/settings");

        fetchMock.mockResolvedValueOnce(ayarlar(false));
        expect(await raporAsistaniAcikMi()).toBe(false);
    });

    it("kayıt yoksa, HTTP hatasında ya da ağ hatasında false (panel gizli, toast yok)", async () => {
        fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ settings: [{ key: "baska", value: true }] }) });
        expect(await raporAsistaniAcikMi()).toBe(false);

        fetchMock.mockResolvedValueOnce({ ok: false, status: 403, json: async () => ({ detail: "admin" }) });
        expect(await raporAsistaniAcikMi()).toBe(false);

        fetchMock.mockRejectedValueOnce(new Error("ağ"));
        expect(await raporAsistaniAcikMi()).toBe(false);

        fetchMock.mockResolvedValueOnce(undefined);
        expect(await raporAsistaniAcikMi()).toBe(false);
    });
});

describe("ornekIstemler (G143) — kaynağa göre örnek çipleri", () => {
    it("dört kaynağın her biri için 3 farklı örnek; davalar Excel + avukat, müvekkiller Ankara/doktor örneğini içerir", () => {
        for (const k of ["davalar", "muvekkiller", "belgeler", "foyler"]) {
            const liste = ornekIstemler(k);
            expect(liste).toHaveLength(3);
            expect(new Set(liste).size).toBe(3);
        }
        expect(ornekIstemler("davalar")).toContain("2025'te açılan derdest davaları avukat adıyla listele, Excel ver");
        expect(ornekIstemler("muvekkiller")).toContain("Ankara'daki doktor müvekkillerin telefon ve e-postasını göster");
        expect(ornekIstemler("davalar")).not.toEqual(ornekIstemler("muvekkiller"));
    });

    it("tanınmayan / boş / null kaynak genel listeye düşer; aynı kaynak aynı referansı döner (render kararlı)", () => {
        const genel = ornekIstemler(null);
        expect(genel).toHaveLength(3);
        expect(ornekIstemler("")).toBe(genel);
        expect(ornekIstemler(undefined)).toBe(genel);
        expect(ornekIstemler("yok_boyle")).toBe(genel);
        expect(ornekIstemler("davalar")).toBe(ornekIstemler("davalar"));
    });
});
