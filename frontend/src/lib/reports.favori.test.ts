// lib/reports — `sablonAdiOner` (G144, plan §6.2): favori önerisi için ad — "<Kaynak etiketi> · <en fazla
// iki filtre özeti>", filtresiz "<Kaynak> · Temel"; arama filtresi girmez; 60 karakter tavanı; aynı ad varsa
// " (2)", " (3)" eki (büyük/küçük harf duyarsız, ek dahil tavan korunur).
import { describe, expect, it, vi } from "vitest";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import {
    OP_BY_TIP, SABLON_AD_ONERI_MAX, sablonAdiOner,
    type Filtre, type FiltreKontrolu, type HizliFiltre, type Katalog, type KatalogKolon, type KolonTipi, type RaporTanimi,
} from "./reports";

const KONTROL: Record<KolonTipi, FiltreKontrolu> = {
    metin: "metin_icerir", liste: "coklu_secim", tarih: "tarih_araligi", sayi: "sayi_araligi", para: "sayi_araligi", mantik: "mantik",
};
type KolonSahtesi = Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>;
function kolon(k: KolonSahtesi): KatalogKolon {
    const filtrelenebilir = k.filtrelenebilir ?? true;
    return {
        filtrelenebilir, siralanabilir: true, turetilmis: false, secenekler: null, grup: "Kimlik",
        kontrol: filtrelenebilir ? KONTROL[k.tip] : null,
        oplar: filtrelenebilir ? [...OP_BY_TIP[k.tip]] : [],
        oneriler: null, oneri_kesik: false,
        secenek_kaynagi: k.tip === "liste" ? "sabit" : null, secenek_etiketleri: null, secilebilir: true,
        ...k,
    };
}
const hf = (alan: string, ek: Partial<HizliFiltre> = {}): HizliFiltre =>
    ({ alan, alternatifler: [], sunum: "varsayilan", etiket: null, ...ek });

const KATALOG: Katalog = {
    veri_kaynaklari: [
        {
            anahtar: "muvekkiller",
            etiket: "Müvekkiller",
            aciklama: "",
            varsayilan_kolonlar: ["name"],
            kolonlar: [
                kolon({ anahtar: "name", etiket: "Ad", tip: "metin" }),
                kolon({ anahtar: "city", etiket: "Şehir", tip: "metin" }),
                kolon({ anahtar: "profession", etiket: "Meslek", tip: "liste", secenekler: ["Doktor", "Avukat"] }),
                kolon({ anahtar: "client_type", etiket: "Müvekkil Tipi", tip: "liste", secenekler: ["Individual", "Company"],
                    secenek_etiketleri: { Individual: "Gerçek kişi", Company: "Tüzel kişi" } }),
                kolon({ anahtar: "dava_sayisi", etiket: "Dava Sayısı", tip: "sayi", turetilmis: true }),
                kolon({ anahtar: "email", etiket: "E-posta", tip: "metin" }),
                kolon({ anahtar: "created_at", etiket: "Kayıt Tarihi", tip: "tarih" }),
                kolon({ anahtar: "maddi", etiket: "Maddi", tip: "para" }),
                kolon({ anahtar: "aktif", etiket: "Aktif", tip: "mantik" }),
                // §5.2 sanal arama kolonu: yalnız filtre — ada GİRMEZ
                kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", secilebilir: false, siralanabilir: false }),
            ],
            hizli_filtreler: [
                hf("arama", { sunum: "arama" }),
                hf("dava_sayisi", { sunum: "var_yok", etiket: "Davası var" }),
                hf("email", { sunum: "bos_anahtari", etiket: "E-postası yok" }),
                hf("created_at"),
            ],
            kolon_setleri: [],
        },
        {
            anahtar: "davalar",
            etiket: "Davalar",
            aciklama: "",
            varsayilan_kolonlar: ["tracking_no"],
            kolonlar: [
                kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
                kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar"] }),
            ],
            hizli_filtreler: [hf("status")],
            kolon_setleri: [],
        },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
};

const tanim = (filtreler: Filtre[], veri_kaynagi = "muvekkiller"): RaporTanimi =>
    ({ veri_kaynagi, kolonlar: ["name"], filtreler, siralama: [] });

describe("sablonAdiOner — kaynak + en fazla iki filtre özeti", () => {
    it("filtre yoksa '<Kaynak> · Temel'; kaynak etiketi katalogdan, katalogda olmayan kaynakta anahtar", () => {
        expect(sablonAdiOner(tanim([]), KATALOG)).toBe("Müvekkiller · Temel");
        expect(sablonAdiOner(tanim([], "davalar"), KATALOG)).toBe("Davalar · Temel");
        expect(sablonAdiOner(tanim([], "bilinmeyen"), KATALOG)).toBe("bilinmeyen · Temel");
    });

    it("çoklu seçim değeri + metin araması: 'Müvekkiller · Doktor · Ankara' (metinde 'içerir' yok)", () => {
        const t = tanim([
            { alan: "profession", op: "eq", deger: "Doktor" },
            { alan: "city", op: "contains", deger: "Ankara" },
        ]);
        expect(sablonAdiOner(t, KATALOG)).toBe("Müvekkiller · Doktor · Ankara");
        // Tam eşitlik (eq) de yalnız metin
        expect(sablonAdiOner(tanim([{ alan: "city", op: "eq", deger: "İzmir" }]), KATALOG)).toBe("Müvekkiller · İzmir");
    });

    it("en fazla İKİ filtre özeti girer (tanım sırasıyla), üçüncü düşer", () => {
        const t = tanim([
            { alan: "profession", op: "eq", deger: "Doktor" },
            { alan: "city", op: "contains", deger: "Ankara" },
            { alan: "client_type", op: "eq", deger: "Individual" },
        ]);
        expect(sablonAdiOner(t, KATALOG)).toBe("Müvekkiller · Doktor · Ankara");
    });

    it("arama filtresi (sanal `secilebilir=false` kolon) özete girmez; katalogda olmayan alan da girmez", () => {
        const t = tanim([
            { alan: "arama", op: "contains", deger: "ahmet" },
            { alan: "city", op: "contains", deger: "Ankara" },
            { alan: "yok_boyle_alan", op: "eq", deger: "x" },
        ]);
        expect(sablonAdiOner(t, KATALOG)).toBe("Müvekkiller · Ankara");
        // Yalnız arama varsa → Temel
        expect(sablonAdiOner(tanim([{ alan: "arama", op: "contains", deger: "ahmet" }]), KATALOG)).toBe("Müvekkiller · Temel");
    });

    it("tarih aralığı aynı yılda yıl ('2025'); iki yıl '2024–2025'; tek uç kolon etiketiyle", () => {
        expect(sablonAdiOner(tanim([{ alan: "created_at", op: "between", deger: ["2025-01-01", "2025-12-31"] }]), KATALOG))
            .toBe("Müvekkiller · 2025");
        expect(sablonAdiOner(tanim([{ alan: "created_at", op: "between", deger: ["2024-06-01", "2025-05-31"] }]), KATALOG))
            .toBe("Müvekkiller · 2024–2025");
        expect(sablonAdiOner(tanim([{ alan: "created_at", op: "gte", deger: "2025-03-01" }]), KATALOG))
            .toBe("Müvekkiller · Kayıt Tarihi ≥ 01.03.2025");
    });

    it("var/yok ve boş anahtarı hızlı filtre etiketiyle, küçük harfle: 'davası var', 'e-postası yok'; eq 0 → '<etiket> yok'", () => {
        expect(sablonAdiOner(tanim([{ alan: "dava_sayisi", op: "gte", deger: 1 }]), KATALOG)).toBe("Müvekkiller · davası var");
        expect(sablonAdiOner(tanim([{ alan: "dava_sayisi", op: "eq", deger: 0 }]), KATALOG)).toBe("Müvekkiller · dava sayısı yok");
        expect(sablonAdiOner(tanim([{ alan: "email", op: "is_null" }]), KATALOG)).toBe("Müvekkiller · e-postası yok");
    });

    it("seçenek etiketi (§5.2) ham kod yerine; sayı/para ve mantık kolon etiketiyle; gelişmiş op etiketiyle", () => {
        expect(sablonAdiOner(tanim([{ alan: "client_type", op: "eq", deger: "Individual" }]), KATALOG)).toBe("Müvekkiller · Gerçek kişi");
        expect(sablonAdiOner(tanim([{ alan: "client_type", op: "in", deger: ["Individual", "Company"] }]), KATALOG))
            .toBe("Müvekkiller · Gerçek kişi, Tüzel kişi");
        expect(sablonAdiOner(tanim([{ alan: "maddi", op: "gte", deger: 1000 }]), KATALOG)).toBe("Müvekkiller · Maddi ≥ 1.000");
        expect(sablonAdiOner(tanim([{ alan: "aktif", op: "eq", deger: true }]), KATALOG)).toBe("Müvekkiller · Aktif");
        expect(sablonAdiOner(tanim([{ alan: "aktif", op: "eq", deger: false }]), KATALOG)).toBe("Müvekkiller · Aktif değil");
        expect(sablonAdiOner(tanim([{ alan: "profession", op: "ne", deger: "Doktor" }]), KATALOG)).toBe("Müvekkiller · Meslek eşit değil Doktor");
    });

    it("60 karakter tavanı: uzun özet '…' ile kısalır; tekrar ekiyle birlikte de tavanı aşmaz", () => {
        const uzun = "Çok uzun bir şehir adı ki altmış karakteri rahatça aşsın diye yazıldı";
        const ad = sablonAdiOner(tanim([{ alan: "city", op: "contains", deger: uzun }]), KATALOG);
        expect(ad.length).toBe(SABLON_AD_ONERI_MAX);
        expect(ad.length).toBe(60);
        expect(ad.startsWith("Müvekkiller · Çok uzun")).toBe(true);
        expect(ad.endsWith("…")).toBe(true);

        const ikinci = sablonAdiOner(tanim([{ alan: "city", op: "contains", deger: uzun }]), KATALOG, [ad]);
        expect(ikinci.length).toBeLessThanOrEqual(60);
        expect(ikinci.endsWith("… (2)")).toBe(true);
        expect(ikinci).not.toBe(ad);
    });

    it("aynı ad varsa ' (2)', ikisi de varsa ' (3)'; karşılaştırma büyük/küçük harf ve boşluk duyarsız", () => {
        const t = tanim([{ alan: "profession", op: "eq", deger: "Doktor" }]);
        expect(sablonAdiOner(t, KATALOG, ["Müvekkiller · Doktor"])).toBe("Müvekkiller · Doktor (2)");
        expect(sablonAdiOner(t, KATALOG, ["Müvekkiller · Doktor", "Müvekkiller · Doktor (2)"])).toBe("Müvekkiller · Doktor (3)");
        expect(sablonAdiOner(t, KATALOG, ["  MÜVEKKİLLER · DOKTOR "])).toBe("Müvekkiller · Doktor (2)");
        expect(sablonAdiOner(t, KATALOG, ["Başka ad"])).toBe("Müvekkiller · Doktor");
    });

    it("saf: girdileri değiştirmez", () => {
        const t = tanim([{ alan: "city", op: "contains", deger: "Ankara" }]);
        const kopya = JSON.parse(JSON.stringify(t));
        const adlar = ["Müvekkiller · Ankara"];
        sablonAdiOner(t, KATALOG, adlar);
        expect(t).toEqual(kopya);
        expect(adlar).toEqual(["Müvekkiller · Ankara"]);
    });
});
