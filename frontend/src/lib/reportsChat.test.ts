// reportsChat (G135) — `/api/reports/chat` NDJSON okuyucusu: gövde §2.6 birebir (`mesajlar` ≤20 +
// `mevcut_tanim`), yarım satır tamponu, `complete`/`failed` SON olay, `complete` yok → hata,
// `failed` → AsistanFailedError (error_kod), 409 → AsistanKapaliError, 403 → yetki; anahtar okuyucu.
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import type { AsistanMesaji, Katalog, KatalogKolon, KatalogVeriKaynagi, RaporTanimi } from "./reports";
import {
    ASISTAN_AKIS_EKSIK, ASISTAN_KAPALI_MESAJI, ASISTAN_MESAJ_MAX, ASISTAN_YETKI_MESAJI, DEGER_ADAY_MAX,
    AsistanFailedError, AsistanKapaliError, AsistanYetkiError,
    chatReport, degerAdaylari, degerAnahtari, degerEsle, errorKodIpucu, filtreDegeriDegistir, gecmisiKirp, kaydetNiyeti,
    listeNiyeti, onayNiyeti, ornekIstemler, raporAsistaniAcikMi, sohbetGecmisi, sonucSatiri,
    tanimAyni, tanimAyrintisi,
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

    it("kaydetNiyeti (G168): adlı/adsız kaydetme kalıpları; başka kelimeli mesaj null", () => {
        expect(kaydetNiyeti("bunu haftalık rapor olarak kaydet")).toEqual({ ad: "haftalık rapor" });
        expect(kaydetNiyeti("Nisan Davaları adıyla kaydet")).toEqual({ ad: "Nisan Davaları" });
        expect(kaydetNiyeti('"Derdest dosyalar" ismiyle şablona ekle.')).toEqual({ ad: "Derdest dosyalar" });
        expect(kaydetNiyeti("bu raporu aylık takip diye sakla")).toEqual({ ad: "aylık takip" });
        for (const m of ["kaydet", "Kaydet.", "bunu kaydet", "şablon olarak kaydet", "favorilere ekle", "şablona ekle", "bu raporu sakla", "hadi favorile"]) {
            expect(kaydetNiyeti(m), m).toEqual({ ad: null });
        }
        for (const m of ["", "telefonu kaydet", "kaydettikten sonra indir", "tamam", "müvekkil adını da ekle", "kaydetme"]) {
            expect(kaydetNiyeti(m), m).toBeNull();
        }
    });

    it("sonucSatiri (G168): sayı tr-TR; boşta filtreler sayılır ve gevşetme önerilir; filtresiz boş kaynak", () => {
        const tanim: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"],
            filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }, { alan: "opening_date", op: "gte", deger: "2026-04-01" }], siralama: [] };
        expect(sonucSatiri(tanim, 3216, KATALOG)).toBe("3.216 kayıt bulundu.");
        const bos = sonucSatiri(tanim, 0, KATALOG);
        expect(bos).toContain("Sonuç boş");
        expect(bos).toContain("• Durum · eşittir · Derdest");
        expect(bos).toContain("• Açılış Tarihi · ≥ (en az) · 01.04.2026");
        expect(bos).toContain("kaldır");
        expect(sonucSatiri({ ...tanim, filtreler: [] }, 0, KATALOG)).toBe("Sonuç boş: bu kaynakta hiç kayıt yok.");
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

    it("G174: her kaynakta bir 'hangi … var' örneği (liste balonunu keşfettirir); üçlü sayı korunur", () => {
        for (const k of ["davalar", "muvekkiller", "belgeler", "foyler"]) {
            const liste = ornekIstemler(k);
            expect(liste).toHaveLength(3);
            expect(liste.filter(o => /^hangi .+ var\??$/i.test(o)), k).toHaveLength(1);
        }
    });
});

// ---------------------------------------------------------------------------
// G174 — değer eşleme (katalog önerileri) + liste niyeti (Gemini'siz)
// ---------------------------------------------------------------------------

function K(k: Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>): KatalogKolon {
    return {
        filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null, grup: "", kontrol: null,
        oplar: [], oneriler: null, oneri_kesik: false, secenek_kaynagi: null, secenek_etiketleri: null, secilebilir: true,
        ...k,
    };
}

const MAHKEMELER = [
    "Ankara 3. Asliye Ticaret Mahkemesi",
    "Ankara 1. Asliye Hukuk Mahkemesi",
    "İstanbul 5. Asliye Ticaret Mahkemesi",
    "İzmir 2. Asliye Hukuk Mahkemesi",
    "Bursa 1. Asliye Ticaret Mahkemesi",
    "Adana 4. Asliye Hukuk Mahkemesi",
    "Antalya 1. Asliye Ticaret Mahkemesi",
    "Kayseri Sulh Hukuk Mahkemesi",
];

const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: [], kolon_setleri: [],
    hizli_filtreler: [{ alan: "responsible_lawyer_name", alternatifler: [], sunum: "varsayilan", etiket: "Sorumlu avukat" }],
    kolonlar: [
        K({ anahtar: "court", etiket: "Mahkeme", tip: "metin", oplar: ["eq", "ne", "contains", "in", "is_null", "not_null"], oneriler: MAHKEMELER }),
        K({ anahtar: "court_city", etiket: "Mahkeme İli", tip: "metin", oplar: ["contains", "in", "is_null", "not_null"], oneriler: ["Ankara", "İstanbul", "İzmir"], oneri_kesik: true }),
        K({ anahtar: "status", etiket: "Durum", tip: "liste", oplar: ["eq", "ne", "in", "is_null", "not_null"], secenekler: ["Derdest", "Karar"] }),
        K({ anahtar: "responsible_lawyer_name", etiket: "Avukat Adı", tip: "metin", oplar: ["contains", "in"], oneriler: ["Ayşe Yılmaz", "Mehmet Kaya"] }),
        K({ anahtar: "subject", etiket: "Konu", tip: "metin", oplar: ["eq", "contains"] }),          // öneri listesi YOK
        K({ anahtar: "bos_liste", etiket: "Boş Liste", tip: "metin", oplar: ["eq", "contains"], oneriler: [] }),
        K({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", oplar: ["eq", "gte", "lte", "between"] }),
        K({ anahtar: "tutar", etiket: "Tutar", tip: "para", oplar: ["eq", "between"] }),
        K({ anahtar: "aktif", etiket: "Aktif", tip: "mantik", oplar: ["eq"] }),
        K({ anahtar: "muvekkil.phone", etiket: "Müvekkil kartı · Telefon", tip: "metin", oplar: ["contains"], bag: "muvekkil" }),
    ],
};
const MUVEKKILLER: KatalogVeriKaynagi = {
    anahtar: "muvekkiller", etiket: "Müvekkiller", aciklama: "", varsayilan_kolonlar: [], kolon_setleri: [], hizli_filtreler: [],
    kolonlar: [
        K({ anahtar: "city", etiket: "Şehir", tip: "metin", oplar: ["contains", "in"], oneriler: ["İstanbul", "Ankara", "İzmir"] }),
        K({ anahtar: "client_type", etiket: "Müvekkil Türü", tip: "liste", oplar: ["eq", "in"], secenekler: ["Individual", "Company"], secenek_etiketleri: { Individual: "Gerçek kişi", Company: "Tüzel kişi" } }),
        K({ anahtar: "name", etiket: "Ad", tip: "metin", oplar: ["contains"] }),
    ],
};
const KATALOG_G174 = { veri_kaynaklari: [DAVALAR, MUVEKKILLER], limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 } } as Katalog;

const tanimla = (filtreler: RaporTanimi["filtreler"], veri_kaynagi = "davalar"): RaporTanimi =>
    ({ veri_kaynagi, kolonlar: ["court"], filtreler, siralama: [] });

describe("G174 — degerAnahtari / degerEsle / degerAdaylari / filtreDegeriDegistir", () => {
    it("degerAnahtari: trim + tr-TR küçük harf + NFD birleşik işaret temizliği; İ/i̇ (U+0307) ve ş/ç/ğ katlanır, iç boşluk tekil", () => {
        expect(degerAnahtari("  İstanbul  ")).toBe("istanbul");
        expect(degerAnahtari("İstanbul")).toBe("istanbul");              // i + U+0307
        expect(degerAnahtari("İSTANBUL")).toBe("istanbul");
        expect(degerAnahtari("Şişli   Çağlayan")).toBe("sisli caglayan");
        expect(degerAnahtari("ANKARA")).toBe("ankara");
        expect(degerAnahtari("")).toBe("");
    });

    it("contains: normalize değer bir önerinin ALT DİZESİ ise temiz (Ankara → 'Ankara 3. Asliye Ticaret'), büyük/küçük ve diakritik farkı sorun değil", () => {
        expect(degerEsle(tanimla([{ alan: "court", op: "contains", deger: "Ankara" }]), KATALOG_G174)).toEqual({ temiz: true, sorunlar: [] });
        expect(degerEsle(tanimla([{ alan: "court", op: "contains", deger: "asliye ticaret" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "court", op: "contains", deger: "İSTANBUL" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "court", op: "contains", deger: "İzmir" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "city", op: "contains", deger: "istanbul" }], "muvekkiller"), KATALOG_G174).temiz).toBe(true);
    });

    it("eq: birebir (normalize) eşleşme temiz; alt dize eq için YETMEZ → sorun, adaylar o öneriler", () => {
        expect(degerEsle(tanimla([{ alan: "court", op: "eq", deger: "ankara 3. asliye ticaret mahkemesi" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "court", op: "eq", deger: " İstanbul 5. Asliye Ticaret Mahkemesi " }]), KATALOG_G174).temiz).toBe(true);
        const s = degerEsle(tanimla([{ alan: "court", op: "eq", deger: "Ankara" }]), KATALOG_G174);
        expect(s.temiz).toBe(false);
        expect(s.sorunlar).toHaveLength(1);
        expect(s.sorunlar[0]).toMatchObject({ indeks: 0, alan: "court", deger: "Ankara", kesik: false });
        // Kesişim 1 (ankara) önce; "Antalya" yalnız 2 harf ortak önekle sonda
        expect(s.sorunlar[0].adaylar).toEqual([
            "Ankara 3. Asliye Ticaret Mahkemesi", "Ankara 1. Asliye Hukuk Mahkemesi", "Antalya 1. Asliye Ticaret Mahkemesi",
        ]);
    });

    it("hiç tutmayan değer → sorun; adaylar kelime kesişimine göre sıralı, en çok 5; kesik bayrağı kolondan; indeks tanımdaki sıra", () => {
        const tanim = tanimla([
            { alan: "status", op: "eq", deger: "Derdest" },                       // liste kolonu, öneri yok → temiz
            { alan: "court", op: "contains", deger: "Ankara Ticaret Dairesi" },  // tutmaz
            { alan: "court_city", op: "contains", deger: "Konya" },              // tutmaz, liste kesik, aday yok
        ]);
        const s = degerEsle(tanim, KATALOG_G174);
        expect(s.temiz).toBe(false);
        expect(s.sorunlar.map(x => [x.indeks, x.alan, x.deger, x.kesik])).toEqual([
            [1, "court", "Ankara Ticaret Dairesi", false],
            [2, "court_city", "Konya", true],
        ]);
        // Kesişim 2 (ankara+ticaret) önce, sonra kesişim 1'ler; ≤5
        expect(s.sorunlar[0].adaylar[0]).toBe("Ankara 3. Asliye Ticaret Mahkemesi");
        expect(s.sorunlar[0].adaylar.length).toBeLessThanOrEqual(DEGER_ADAY_MAX);
        expect(s.sorunlar[0].adaylar.length).toBe(5);
        expect(s.sorunlar[0].adaylar.slice(1)).toEqual(expect.arrayContaining(["Ankara 1. Asliye Hukuk Mahkemesi", "İstanbul 5. Asliye Ticaret Mahkemesi"]));
        expect(s.sorunlar[0].adaylar).not.toContain("Kayseri Sulh Hukuk Mahkemesi");
        expect(s.sorunlar[1].adaylar).toEqual([]);
    });

    it("öneri listesi olmayan / boş kolon, katalogda olmayan kolon, katalogda olmayan kaynak ve katalog=null daima temiz", () => {
        expect(degerEsle(tanimla([{ alan: "subject", op: "contains", deger: "zzz" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "bos_liste", op: "eq", deger: "zzz" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "yok_boyle", op: "eq", deger: "zzz" }]), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "court", op: "eq", deger: "zzz" }], "yok_kaynak"), KATALOG_G174).temiz).toBe(true);
        expect(degerEsle(tanimla([{ alan: "court", op: "eq", deger: "zzz" }]), null).temiz).toBe(true);
        expect(degerEsle(tanimla([]), KATALOG_G174).temiz).toBe(true);
    });

    it("in / between / ne / is_null / tarih / sayı / mantık filtreleri ve string olmayan değerler atlanır (temiz)", () => {
        const tanim = tanimla([
            { alan: "court", op: "in", deger: ["Yok Böyle Mahkeme", null] },
            { alan: "court", op: "ne", deger: "Yok Böyle Mahkeme" },
            { alan: "court", op: "not_null" },
            { alan: "court", op: "eq", deger: 42 },
            { alan: "opening_date", op: "between", deger: ["2026-01-01", "2026-12-31"] },
            { alan: "opening_date", op: "eq", deger: "2026-05-05" },
            { alan: "tutar", op: "eq", deger: 100 },
            { alan: "aktif", op: "eq", deger: true },
            { alan: "court", op: "contains", deger: "   " },                    // boş değer: eşleme dışı (geçerlilik kapısı ayrı)
        ]);
        expect(degerEsle(tanim, KATALOG_G174)).toEqual({ temiz: true, sorunlar: [] });
    });

    it("Türkçe İ/ı ve U+0307 normalize: 'İSTANBUL' / 'i̇stanbul' / 'istanbul' aynı; 'Işık' ile 'İşık' farklı kalır (tr-TR I → ı)", () => {
        for (const d of ["İSTANBUL", "i̇stanbul", "istanbul", "İstanbul"]) {
            expect(degerEsle(tanimla([{ alan: "city", op: "eq", deger: d }], "muvekkiller"), KATALOG_G174).temiz, d).toBe(true);
        }
        expect(degerAnahtari("Işık")).not.toBe(degerAnahtari("İşık"));
    });

    it("degerAdaylari: kelime kesişimi (çok → az), sonra ortak önek, sonra katalog sırası; kesişimsiz ve <2 ortak önekli öneri aday değil; tavan", () => {
        expect(degerAdaylari("Ankara Ticaret", MAHKEMELER)).toEqual([
            "Ankara 3. Asliye Ticaret Mahkemesi",           // ankara + ticaret (kesişim 2)
            "Ankara 1. Asliye Hukuk Mahkemesi",             // ankara (kesişim 1, önek 7)
            "Antalya 1. Asliye Ticaret Mahkemesi",          // ticaret (kesişim 1, önek "an" 2)
            "İstanbul 5. Asliye Ticaret Mahkemesi",         // ticaret (kesişim 1, önek 0, katalog sırası)
            "Bursa 1. Asliye Ticaret Mahkemesi",
        ]);
        // Yazım hatası: kesişim yok, ortak önek "ank" (3) → Ankara'lılar önce, "an" (2) → Antalya; "Kayseri" gibi öneksizler aday değil
        expect(degerAdaylari("Ankra", MAHKEMELER)).toEqual([
            "Ankara 3. Asliye Ticaret Mahkemesi", "Ankara 1. Asliye Hukuk Mahkemesi", "Antalya 1. Asliye Ticaret Mahkemesi",
        ]);
        expect(degerAdaylari("Zonguldak", MAHKEMELER)).toEqual([]);
        expect(degerAdaylari("", MAHKEMELER)).toEqual([]);
        expect(degerAdaylari("Mahkemesi", MAHKEMELER, 3)).toHaveLength(3);
        expect(degerAdaylari("Mahkemesi", MAHKEMELER)).toHaveLength(DEGER_ADAY_MAX);
    });

    it("filtreDegeriDegistir: aday katalog yazımıyla yazılır; kolonda eq izinliyse eq, yoksa contains; kolon bilinmiyorsa op kalır; yeni nesne, diğer filtreler aynen", () => {
        const tanim = tanimla([
            { alan: "status", op: "eq", deger: "Derdest" },
            { alan: "court", op: "contains", deger: "Ankra" },
            { alan: "court_city", op: "contains", deger: "Ank" },
        ]);
        const court = DAVALAR.kolonlar.find(k => k.anahtar === "court")!;
        const courtCity = DAVALAR.kolonlar.find(k => k.anahtar === "court_city")!;
        const y1 = filtreDegeriDegistir(tanim, 1, "Ankara 3. Asliye Ticaret Mahkemesi", court);
        expect(y1).not.toBe(tanim);
        expect(y1.filtreler[1]).toEqual({ alan: "court", op: "eq", deger: "Ankara 3. Asliye Ticaret Mahkemesi" });
        expect(y1.filtreler[0]).toBe(tanim.filtreler[0]);
        expect(tanim.filtreler[1].deger).toBe("Ankra");                                   // kaynak nesne değişmedi
        const y2 = filtreDegeriDegistir(tanim, 2, "Ankara", courtCity);
        expect(y2.filtreler[2]).toEqual({ alan: "court_city", op: "contains", deger: "Ankara" });
        const y3 = filtreDegeriDegistir(tanim, 1, "Ankara 1. Asliye Hukuk Mahkemesi", undefined);
        expect(y3.filtreler[1]).toEqual({ alan: "court", op: "contains", deger: "Ankara 1. Asliye Hukuk Mahkemesi" });
    });
});

describe("G174 — listeNiyeti ('hangi X'ler var')", () => {
    it("olumlu kalıplar (8+): hangi … var / listesi / seçenekleri (neler) / değerleri / neler var / var mı → tek kolon", () => {
        const olumlu: [string, KatalogVeriKaynagi, string][] = [
            ["hangi durumlar var", DAVALAR, "status"],
            ["Hangi durumlar var?", DAVALAR, "status"],
            ["durum listesi", DAVALAR, "status"],
            ["durum listesini verir misin", DAVALAR, "status"],
            ["durum seçenekleri neler", DAVALAR, "status"],
            ["durum seçenekleri", DAVALAR, "status"],
            ["durum değerleri", DAVALAR, "status"],
            ["durumlar neler", DAVALAR, "status"],
            ["hangi avukatlar var", DAVALAR, "responsible_lawyer_name"],
            ["sistemde hangi avukatlar kayıtlı", DAVALAR, "responsible_lawyer_name"],
            ["hangi iller var", MUVEKKILLER, "city"],
            ["şehir listesi", MUVEKKILLER, "city"],
            ["hangi müvekkil türleri var", MUVEKKILLER, "client_type"],
            ["müvekkil türü seçenekleri nelerdir", MUVEKKILLER, "client_type"],
            ["şehirler var mı", MUVEKKILLER, "city"],
        ];
        for (const [m, kaynak, beklenen] of olumlu) {
            const sonuc = listeNiyeti(m, kaynak);
            expect(sonuc?.map(k => k.anahtar), m).toEqual([beklenen]);
        }
    });

    it("olumsuz (4+): eylem fiilli / onay / düzeltme mesajları ve eşleşmeyen konu null → Gemini'ye gider", () => {
        for (const m of [
            "mahkemeyi kaldır", "listele davaları", "tamam", "mahkeme kolonunu ekle", "durum filtresini sil",
            "derdest davaları listele", "hangi kolonlar var", "hangi konular var",        // konu: öneri listesi yok
            "", "   ", "Ankara'daki davaları göster",
        ]) {
            expect(listeNiyeti(m, DAVALAR), m).toBeNull();
        }
        expect(listeNiyeti("hangi durumlar var", null)).toBeNull();
        expect(listeNiyeti("hangi durumlar var", undefined)).toBeNull();
    });

    it("kolon çözümü: etiket, hızlı filtre etiketi ('Sorumlu avukat'), anahtar ve eşanlamlılar (il → şehir, mahkeme → court, tür → type)", () => {
        expect(listeNiyeti("hangi sorumlular var", DAVALAR)?.map(k => k.anahtar)).toEqual(["responsible_lawyer_name"]);
        expect(listeNiyeti("hangi lawyer var", DAVALAR)?.map(k => k.anahtar)).toEqual(["responsible_lawyer_name"]);
        expect(listeNiyeti("hangi city var", MUVEKKILLER)?.map(k => k.anahtar)).toEqual(["city"]);
        expect(listeNiyeti("hangi tipler var", MUVEKKILLER)?.map(k => k.anahtar)).toEqual(["client_type"]);
        expect(listeNiyeti("status değerleri", DAVALAR)?.map(k => k.anahtar)).toEqual(["status"]);
        // Bağlı kolon etiketi son parçasıyla ("Müvekkil kartı · Telefon" → telefon) ama öneri listesi yok → aday değil
        expect(listeNiyeti("hangi telefonlar var", DAVALAR)).toBeNull();
    });

    it("belirsizde adaylar: 'hangi mahkemeler var' hem Mahkeme hem Mahkeme İli'ne uyar (eşit puan) → iki aday; ek sözcük ayırır", () => {
        expect(listeNiyeti("hangi mahkemeler var", DAVALAR)?.map(k => k.anahtar)).toEqual(["court", "court_city"]);
        expect(listeNiyeti("mahkeme listesi", DAVALAR)?.map(k => k.anahtar)).toEqual(["court", "court_city"]);
        expect(listeNiyeti("hangi mahkeme illeri var", DAVALAR)?.map(k => k.anahtar)).toEqual(["court_city"]);
        expect(listeNiyeti("hangi iller var", DAVALAR)?.map(k => k.anahtar)).toEqual(["court_city"]);
    });
});
