import { afterEach, describe, expect, it, vi } from "vitest";
import * as caseNumberUtils from "./caseNumberUtils";
import {
    YARGI_TURLERI,
    istekKimligiGecerli,
    ofisNoOnizlemeSorgusu,
    yeniIstekKimligi,
} from "./caseNumberUtils";

// =====================================================================
// G237 (insan onaylı test taşıma): bu dosya eskiden İSTEMCİ numara üreticisini
// (generateTrackingNumber / generateNameBlock / pickNameClient / bestCategoryCode /
// validateCaseNumber + kod haritaları) sabitliyordu. Üretici kalktı — numarayı
// sunucu verir (`backend/services/ofis_no.py`, karar 023). Her test yeni davranışa
// çevrildi: istemci HAM girdiyi (ad / kayıt id'si / yargı türü) önizleme ucuna
// iletir, kod TÜRETMEZ; kayıt isteği kimlik (UUID) taşır.
// =====================================================================

const sorgu = (girdi: Parameters<typeof ofisNoOnizlemeSorgusu>[0]) => ofisNoOnizlemeSorgusu(girdi);
const paramlar = (girdi: Parameters<typeof ofisNoOnizlemeSorgusu>[0]) =>
    new URLSearchParams(sorgu(girdi) ?? "");
const disaVerilenler = caseNumberUtils as Record<string, unknown>;

describe("ofisNoOnizlemeSorgusu — istemci numara ÜRETMEZ (eski: generateTrackingNumber)", () => {
    it("müvekkilsiz çağrıda yer tutucu numara yok: sorgu null (istek atılmaz)", () => {
        expect(sorgu({ clients: [] })).toBeNull();
    });

    it("kişi müvekkilin adı ham gider; isim bloğu istemcide kurulmaz", () => {
        const s = sorgu({ clients: [{ name: "İlke Berk Kutluk" }] });
        expect(new URLSearchParams(s ?? "").getAll("muvekkiller")).toEqual(["İlke Berk Kutluk"]);
        // Eski çıktı ".I_KUTLUK.." bloğunu taşırdı
        expect(decodeURIComponent(s ?? "")).not.toContain("I_KUTLUK");
    });

    it("kurum müvekkilde jenerik kelimeler ATILMAZ — ad olduğu gibi iletilir", () => {
        // Eski: "Sigorta"/"A.Ş." atılıp "S2.ANADOLU..." kurulurdu
        expect(paramlar({ clients: [{ name: "Anadolu Sigorta A.Ş." }] }).getAll("muvekkiller"))
            .toEqual(["Anadolu Sigorta A.Ş."]);
    });

    it("bilinen sigorta şirketinin özgül kodu istemcide türetilmez", () => {
        // Eski: AXA → "S3". Kod artık yalnız sunucunun yanıtındadır.
        expect([...paramlar({ clients: [{ name: "AXA Sigorta" }] }).keys()]).toEqual(["muvekkiller"]);
    });

    it("bilinmeyen sigorta için de kod (S0) üretilmez", () => {
        expect(sorgu({ clients: [{ name: "Bilinmedik Sigorta" }] })).toBe("muvekkiller=Bilinmedik+Sigorta");
    });

    it("kayıtlı müvekkil adıyla değil kayıt id'siyle gider (kategori kodu D2 türetilmez)", () => {
        const p = paramlar({
            clients: [{ name: "Ayşe Yılmaz" }],
            dbClients: [{ id: 41, name: "AYŞE YILMAZ" }],
        });
        expect(p.getAll("muvekkiller")).toEqual(["41"]);
        expect(p.toString()).not.toContain("A_YILMAZ");
    });

    it("yargı türü ham gider; sıra numarası istemciden gönderilmez", () => {
        const p = paramlar({ clients: [{ name: "Ali Veli" }], fileType: "İcra" });
        // Eski: blok4 "ICRAA", blok3 ".0012." istemcide kurulurdu
        expect(p.get("file_type")).toBe("İcra");
        expect([...p.keys()].sort()).toEqual(["file_type", "muvekkiller"]);
    });

    // Eski: bu 4 tür blok4 kodu (IDARE/TAHKM/VERGI/DANIS) üretirdi
    it.each([
        ["İdare", "IDARE"],
        ["Tahkim", "TAHKM"],
        ["Vergi", "VERGI"],
        ["Danışmanlık", "DANIS"],
    ])("%s türü AD olarak iletilir, %s kodu istemcide üretilmez", (processType, eskiKod) => {
        const p = paramlar({ clients: [{ name: "Ali Veli" }], fileType: processType });
        expect(p.get("file_type")).toBe(processType);
        expect(p.toString()).not.toContain(eskiKod);
    });

    it("hiçbir girdide eski beş bloklu numara biçimi çıkmaz", () => {
        const ESKI_BICIM = /[A-Z0-9]{2}\.[A-Z0-9_.]{10}\.[A-Z0-9]{4}\.[A-Z0-9]{5}\.[A-Z0-9]{5}/;
        const cases = [
            sorgu({ clients: [] }),
            sorgu({ clients: [{ name: "İlke Berk Kutluk" }], fileType: "Ceza" }),
            sorgu({ clients: [{ name: "AXA Sigorta" }] }),
        ];
        for (const c of cases) expect(ESKI_BICIM.test(decodeURIComponent(c ?? ""))).toBe(false);
    });
});

describe("ofisNoOnizlemeSorgusu — müvekkil listesi (eski: generateNameBlock)", () => {
    it("boş / boşluktan ibaret müvekkil satırı sorguya girmez", () => {
        expect(sorgu({ clients: [{ name: "" }] })).toBeNull();
        expect(sorgu({ clients: [{ name: "   " }] })).toBeNull();
        expect(paramlar({ clients: [{ name: "" }, { name: " Ali Veli " }] }).getAll("muvekkiller"))
            .toEqual(["Ali Veli"]);
    });

    it("';' ile yazılan çoklu isim ayrı müvekkiller olarak gider", () => {
        const samples: Array<{ yazilan: string; beklenen: string[] }> = [
            { yazilan: "İlke Berk Kutluk; Mehmet Öz", beklenen: ["İlke Berk Kutluk", "Mehmet Öz"] },
            { yazilan: "Anadolu Sigorta A.Ş.;", beklenen: ["Anadolu Sigorta A.Ş."] },
            { yazilan: " Mehmet Öz ;  ; Ayşe Gül ", beklenen: ["Mehmet Öz", "Ayşe Gül"] },
        ];
        for (const s of samples) {
            expect(paramlar({ clients: [{ name: s.yazilan }] }).getAll("muvekkiller")).toEqual(s.beklenen);
        }
    });

    it("satırın kendi client_id'si varsa ad eşleşmesi aranmadan o id gider", () => {
        expect(paramlar({
            clients: [{ name: "İlke Berk Kutluk", client_id: 7 }],
            dbClients: [{ id: 99, name: "İlke Berk Kutluk" }],
        }).getAll("muvekkiller")).toEqual(["7"]);
    });
});

describe("müvekkil seçimi sunucudadır (eski: pickNameClient)", () => {
    it("istemci kişi/sigorta önceliği uygulamaz: form sırası korunur", () => {
        // Eski: Doktor, sigortanın önüne alınırdı
        expect(paramlar({ clients: [{ name: "AXA Sigorta" }, { name: "Mehmet Öz" }] }).getAll("muvekkiller"))
            .toEqual(["AXA Sigorta", "Mehmet Öz"]);
    });

    it("kategori sırası (Doktor > Sağlık Çalışanı > Hasta > Bireysel) istemcide kurulmaz", () => {
        const dortlu = [{ name: "B" }, { name: "H" }, { name: "S" }, { name: "D" }];
        expect(paramlar({ clients: dortlu }).getAll("muvekkiller")).toEqual(["B", "H", "S", "D"]);

        expect(paramlar({ clients: dortlu.slice(0, 3) }).getAll("muvekkiller")).toEqual(["B", "H", "S"]);
    });

    it("boş liste: seçilecek müvekkil yok, sorgu yok", () => {
        expect(sorgu({ clients: [], fileType: "Hukuk" })).toBeNull();
    });
});

describe("'Sigortalı' tarafı sunucuya iletilir (eski: bestCategoryCode)", () => {
    it("Sigortalı rolündeki taraf `sigortali` olarak gider", () => {
        const p = paramlar({
            clients: [{ name: "AXA Sigorta" }],
            otherParties: [{ name: "Emre Altunç", role: "Sigortalı" }],
        });
        expect(p.getAll("sigortali")).toEqual(["Emre Altunç"]);
    });

    it("başka roldeki taraflar gönderilmez", () => {
        const p = paramlar({
            clients: [{ name: "AXA Sigorta" }],
            otherParties: [{ name: "Hasta Kişi", role: "Davacı" }, { name: "Tanık Bir", role: "Tanık" }],
        });
        expect(p.has("sigortali")).toBe(false);
    });

    it("';' ile yazılan çoklu sigortalı ayrı ayrı gider", () => {
        expect(paramlar({
            clients: [{ name: "AXA Sigorta" }],
            otherParties: [{ name: "Emre Altunç; Ayşe Gül", role: "Sigortalı" }],
        }).getAll("sigortali")).toEqual(["Emre Altunç", "Ayşe Gül"]);
    });

    it("rol boşluklu yazılsa da tanınır; müvekkil yoksa sigortalı tek başına sorgu kurmaz", () => {
        expect(paramlar({
            clients: [{ name: "AXA Sigorta" }],
            otherParties: [{ name: "Emre Altunç", role: " Sigortalı " }],
        }).getAll("sigortali")).toEqual(["Emre Altunç"]);

        expect(sorgu({
            clients: [],
            otherParties: [{ name: "Emre Altunç", role: "Sigortalı" }],
        })).toBeNull();
    });

    it("taraf listesi boşsa `sigortali` parametresi hiç yok", () => {
        expect(paramlar({ clients: [{ name: "AXA Sigorta" }], otherParties: [] }).has("sigortali")).toBe(false);
    });
});

describe("istekKimligiGecerli (eski: validateCaseNumber)", () => {
    it("UUID biçimi kabul edilir", () => {
        expect(istekKimligiGecerli("3f2b8c1e-9d4a-4f6b-8a2c-1e5d7f9b0c3a")).toBe(true);
    });

    it("UUID olmayan değerler reddedilir (eski ofis numarası dahil)", () => {
        expect(istekKimligiGecerli("")).toBe(false);
        expect(istekKimligiGecerli("D1.I_KUTLUK...0007.CEZAA.00000")).toBe(false); // eski numara kimlik değildir
        expect(istekKimligiGecerli(undefined)).toBe(false);
        expect(istekKimligiGecerli("3f2b8c1e-9d4a-4f6b-8a2c")).toBe(false);         // eksik blok
    });
});

describe("yeniIstekKimligi — kayıt isteğinin kimliği (eski: B1 kodu ile çağrı, G223)", () => {
    afterEach(() => vi.unstubAllGlobals());

    const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

    it("geçerli bir UUID v4 üretir, her çağrıda farklı", () => {
        const a = yeniIstekKimligi();
        expect(istekKimligiGecerli(a)).toBe(true);
        expect(a).toMatch(V4);
        expect(a).toHaveLength(36);
        expect(yeniIstekKimligi()).not.toBe(a);
    });

    it("randomUUID yoksa (güvenli bağlam dışı) getRandomValues ile v4 kurar", () => {
        vi.stubGlobal("crypto", {
            getRandomValues: (dizi: Uint8Array) => { dizi.fill(0xab); return dizi; },
        });
        expect(yeniIstekKimligi()).toBe("abababab-abab-4bab-abab-abababababab");
        expect(yeniIstekKimligi()).toMatch(V4);
    });

    // Eski `cagriBicimi` yardımcısının yerine: crypto'suz ortamda üretim
    const cryptosuzUret = () => {
        vi.stubGlobal("crypto", undefined);
        return yeniIstekKimligi();
    };

    it("crypto hiç yoksa da biçimi geçerli bir kimlik döner", () => {
        expect(cryptosuzUret()).toMatch(V4);
    });

    it("yargı türü listesi AD listesidir: İdare var, eski 'İdari Yargı' yok", () => {
        expect(YARGI_TURLERI.filter(t => t === "İdare" || t === "İdari Yargı")).toEqual(["İdare"]);
    });

    it("yargı türü listesi tekildir ve sihirbazın dokuz türünü taşır", () => {
        expect(new Set(YARGI_TURLERI).size).toBe(YARGI_TURLERI.length);
        expect([...YARGI_TURLERI]).toEqual([
            "Hukuk", "Ceza", "İcra", "Arabuluculuk", "Savcılık", "İdare", "Tahkim", "Vergi", "Danışmanlık",
        ]);
    });
});

describe("kaldırılan üretici modülden dışa verilmez (eski: sigorta kodu ASCII, G223)", () => {
    it("numara ve isim bloğu üreticileri yok", () => {
        expect("generateTrackingNumber" in disaVerilenler).toBe(false);
        expect("generateNameBlock" in disaVerilenler).toBe(false);
    });

    it("müvekkil seçici ve kategori kodu çözücü yok", () => {
        expect("pickNameClient" in disaVerilenler).toBe(false);
        expect("bestCategoryCode" in disaVerilenler).toBe(false);
    });

    it("istemci biçim doğrulayıcısı yok (biçimi sunucu bilir)", () => {
        expect("validateCaseNumber" in disaVerilenler).toBe(false);
    });

    it("kod haritaları yok — kanonik kaynak backend/services/ofis_no.py", () => {
        for (const harita of ["CATEGORY_MAP", "INSURANCE_CODES", "PROCESS_MAP", "B1_CODES"]) {
            expect(harita in disaVerilenler).toBe(false);
        }
    });
});
