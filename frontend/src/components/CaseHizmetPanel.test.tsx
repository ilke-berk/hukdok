// @vitest-environment jsdom
// CaseHizmetPanel (G252) — dava kartının müvekkil × hizmet paneli. `apiClient` sahte (yol+yönteme
// göre yanıt), seçenek listesi sahte; panel lib/caseHizmetleri + gerçek HizmetSecici (Radix Popover
// + cmdk) ile koşar. Kilitlenenler: müvekkile göre gruplama, föy çipi kilitli (kilit simgesi, föy no ipucunda,
// kaldırma yok), çoklu seçim → TEK PUT gövdesi (föy adı gövdede yok), değişmeyen seçimde istek yok,
// seçimi kaldırıp uygulamak boş küme yazar, iki müvekkile FARKLI küme, toplu uygulama (müvekkil
// başına bir PUT + kısmi hata), 409/422 Türkçe metin, liste dışı damga, yetkisizde düğmeler yok,
// yazma sonrası YENİDEN ÇEKME + kart tazeleme.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
const configMock = vi.hoisted(() => ({ serviceTypes: [] as { code?: string; name: string }[] }));
vi.mock("@/hooks/useConfig", () => ({
    useConfigList: () => ({ data: configMock.serviceTypes, isLoading: false, isError: false, error: undefined }),
}));

import CaseHizmetPanel from "./CaseHizmetPanel";
import type { CaseHizmeti, HizmetMuvekkili } from "@/lib/caseHizmetleri";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
Element.prototype.scrollIntoView = function () { /* jsdom */ };
const globalWithRO = globalThis as { ResizeObserver?: unknown };
if (!globalWithRO.ResizeObserver) {
    globalWithRO.ResizeObserver = class {
        observe() {}
        unobserve() {}
        disconnect() {}
    };
}

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const SERVICE_TYPES = [
    { code: "TD", name: "Takip (doktor müvekkil)" },
    { code: "DN", name: "Danışmanlık" },
    { code: "LR", name: "Lexis Rapor" },
];
const DOKTOR: HizmetMuvekkili = { id: 11, name: "Dr. Ayşe Kaya" };
const HASTANE: HizmetMuvekkili = { id: 12, name: "Özel Şifa Hastanesi" };

const FOY_SATIRI: CaseHizmeti = {
    id: 1, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Takip (doktor müvekkil)",
    kaynak: "foy", foy_id: 70, sistem_no: "S-2024-100",
};
const ELLE_SATIRI: CaseHizmeti = {
    id: 2, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Danışmanlık",
    kaynak: "elle", foy_id: null, sistem_no: null,
};

/** Sunucu durumu: GET bu listeyi döner; PUT yanıtı test başına ayarlanır (taraf id'sine göre). */
let sunucu: CaseHizmeti[] = [];
let putYaniti: (partyId: number, adlar: string[]) => Response = () => jsonYanit(200, []);
let sonId = 100;

/** Varsayılan PUT: sunucu durumunu G248 kuralıyla günceller (elle küme = verilen; föy sabit). */
const kumeyiUygula = (partyId: number, adlar: string[]): Response => {
    const foyAdlari = new Set(sunucu.filter(s => s.case_party_id === partyId && s.kaynak === "foy").map(s => s.hizmet_turu));
    sunucu = [
        ...sunucu.filter(s => !(s.case_party_id === partyId && s.kaynak === "elle")),
        ...adlar.filter(ad => !foyAdlari.has(ad)).map(ad => ({
            id: ++sonId, case_party_id: partyId, muvekkil_adi: null, hizmet_turu: ad,
            kaynak: "elle" as const, foy_id: null, sistem_no: null,
        })),
    ];
    return jsonYanit(200, sunucu);
};

const cagrilar = (method: string) =>
    fetchMock.mock.calls.filter(([, o]) => ((o as RequestInit | undefined)?.method ?? "GET") === method);
const putlar = () => cagrilar("PUT").map(([yol, o]) => ({
    yol: yol as string,
    govde: JSON.parse((o as RequestInit).body as string) as { hizmet_turleri: string[] },
}));

describe("CaseHizmetPanel", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    const onDegisti = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        configMock.serviceTypes = SERVICE_TYPES;
        sunucu = [FOY_SATIRI, ELLE_SATIRI];
        putYaniti = kumeyiUygula;
        sonId = 100;
        fetchMock.mockImplementation(async (yol: string, o?: RequestInit) => {
            if ((o?.method ?? "GET") === "PUT") {
                const partyId = Number(yol.split("/").pop());
                const { hizmet_turleri } = JSON.parse(o!.body as string) as { hizmet_turleri: string[] };
                return putYaniti(partyId, hizmet_turleri);
            }
            return jsonYanit(200, sunucu);
        });
        container = document.createElement("div");
        document.body.appendChild(container);
    });

    afterEach(() => {
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
        document.body.innerHTML = "";
        vi.restoreAllMocks();
    });

    const bas = async (muvekkiller: HizmetMuvekkili[] = [DOKTOR], duzenlenebilir?: boolean) => {
        await act(async () => {
            root = createRoot(container);
            root.render(
                <CaseHizmetPanel caseId={42} muvekkiller={muvekkiller} duzenlenebilir={duzenlenebilir} onDegisti={onDegisti} />,
            );
        });
    };

    const q = <T extends Element = HTMLElement>(testId: string, kok: ParentNode = container) =>
        kok.querySelector<T>(`[data-testid="${testId}"]`);
    const qa = (testId: string, kok: ParentNode = container) =>
        Array.from(kok.querySelectorAll<HTMLElement>(`[data-testid="${testId}"]`));
    const satiri = (partyId: number) =>
        container.querySelector<HTMLElement>(`[data-testid="case-hizmet-muvekkil"][data-party-id="${partyId}"]`)!;
    const cipAdlari = (partyId: number, kaynak?: "foy" | "elle") =>
        qa("case-hizmet-cip", satiri(partyId))
            .filter(c => !kaynak || c.getAttribute("data-kaynak") === kaynak)
            .map(c => q("case-hizmet-cip-adi", c)!.textContent);
    const secenek = (ad: string) =>
        Array.from(document.body.querySelectorAll<HTMLElement>("[cmdk-item]")).find(el => el.getAttribute("data-hizmet") === ad) ?? null;

    const tikla = async (el: Element | null) => {
        expect(el).not.toBeNull();
        await act(async () => { (el as HTMLElement).click(); });
    };
    /** "Hizmet ekle" / "Hizmetleri düzenle" → seçici açık gelir (defaultOpen). */
    const duzenle = async (partyId: number) => {
        await tikla(q("case-hizmet-sec", satiri(partyId)));
        expect(q("case-hizmet-duzenle", satiri(partyId))).not.toBeNull();
        expect(document.body.querySelector("[cmdk-input]")).not.toBeNull();
    };
    const uygula = async (partyId: number) => {
        await tikla(q("case-hizmet-uygula", satiri(partyId)));
    };

    it("müvekkile göre gruplar: föy çipi kilit simgeli (paket yazısı yok, föy no ipucunda), elle çip ayrı; GET yolu doğru", async () => {
        sunucu = [
            FOY_SATIRI, ELLE_SATIRI,
            { id: 3, case_party_id: 12, muvekkil_adi: "Özel Şifa Hastanesi", hizmet_turu: "Lexis Rapor", kaynak: "elle", foy_id: null, sistem_no: null },
        ];
        await bas([DOKTOR, HASTANE]);

        expect(fetchMock.mock.calls[0][0]).toBe("/api/cases/42/hizmetler");
        expect(qa("case-hizmet-muvekkil-adi").map(e => e.textContent)).toEqual(["Dr. Ayşe Kaya", "Özel Şifa Hastanesi"]);
        expect(cipAdlari(11, "foy")).toEqual(["Takip (doktor müvekkil)"]);
        expect(cipAdlari(11, "elle")).toEqual(["Danışmanlık"]);
        expect(cipAdlari(12)).toEqual(["Lexis Rapor"]);

        const foyCipi = qa("case-hizmet-cip", satiri(11)).find(c => c.getAttribute("data-kaynak") === "foy")!;
        // 03.10: çipte "paket · föy no" yazısı YOK — yalnız kilit simgesi; föy numarası ipucunda.
        expect(q("case-hizmet-kilit", foyCipi)).not.toBeNull();
        expect(foyCipi.textContent).toBe("Takip (doktor müvekkil)");
        expect(foyCipi.getAttribute("title")).toContain("Föy S-2024-100");
        // Föy çipinde kaldırma düğmesi YOK; elle çipte kilit yok.
        expect(foyCipi.querySelector("button")).toBeNull();
        const elleCipi = qa("case-hizmet-cip", satiri(11)).find(c => c.getAttribute("data-kaynak") === "elle")!;
        expect(q("case-hizmet-kilit", elleCipi)).toBeNull();
        expect(container.textContent).not.toMatch(/paket/i);
    });

    it("aynı hizmeti taşıyan föyler TEK çipte toplanır: adet rozette, föy numaraları ipucunda; farklı hizmet ayrı çip", async () => {
        sunucu = [
            FOY_SATIRI,
            { ...FOY_SATIRI, id: 4, foy_id: 71, sistem_no: "S-2024-101" },
            { ...FOY_SATIRI, id: 5, foy_id: 72, sistem_no: "S-2024-102" },
            { ...FOY_SATIRI, id: 6, foy_id: 73, sistem_no: "S-2024-103", hizmet_turu: "Lexis Rapor" },
        ];
        await bas([DOKTOR]);

        // Dört föy satırı → iki çip (üç föylük hizmet tek çip + farklı hizmet ayrı çip).
        expect(cipAdlari(11, "foy")).toEqual(["Takip (doktor müvekkil)", "Lexis Rapor"]);
        const [toplu, tekil] = qa("case-hizmet-cip", satiri(11));
        expect(toplu.getAttribute("data-adet")).toBe("3");
        expect(toplu.textContent).toBe("Takip (doktor müvekkil)");
        expect(toplu.getAttribute("title")).toContain("Föy S-2024-100, S-2024-101, S-2024-102");
        expect(tekil.getAttribute("title")).toContain("Föy S-2024-103");
        // Başlıktaki sayı ekrandaki çip sayısıdır (satır sayısı 4 değil).
        expect(container.textContent).toContain("(2)");
        expect(container.textContent).not.toContain("(4)");
    });

    it("hizmeti olmayan müvekkil 'Hizmet girilmemiş' der", async () => {
        await bas([DOKTOR, HASTANE]);
        expect(q("case-hizmet-bos", satiri(11))).toBeNull();
        expect(q("case-hizmet-bos", satiri(12))!.textContent).toBe("Hizmet girilmemiş");
    });

    it("düğme etiketi işi söyler: elle hizmeti olmayan müvekkilde 'Hizmet ekle', olanda 'Hizmetleri düzenle'", async () => {
        // DOKTOR: föy + elle satır; HASTANE: hiç satır yok. Yalnız föy satırı olan da "ekle" görür.
        await bas([DOKTOR, HASTANE]);
        expect(q("case-hizmet-sec", satiri(11))!.textContent).toBe("Hizmetleri düzenle");
        expect(q("case-hizmet-sec", satiri(11))!.getAttribute("aria-label")).toBe("Dr. Ayşe Kaya için hizmetleri düzenle");
        expect(q("case-hizmet-sec", satiri(12))!.textContent).toBe("Hizmet ekle");
        expect(q("case-hizmet-sec", satiri(12))!.getAttribute("aria-label")).toBe("Özel Şifa Hastanesi için hizmet ekle");
    });

    it("müvekkil tarafı olmayan kartta bilgi metni çıkar; ekleme/toplu düğmesi yok", async () => {
        sunucu = [];
        await bas([]);
        expect(q("case-hizmet-muvekkil-yok")!.textContent).toBe("Bu kartta müvekkil tarafı yok");
        expect(q("case-hizmet-sec")).toBeNull();
        expect(q("case-hizmet-toplu-ac")).toBeNull();
        expect(container.querySelector("button")).toBeNull();
    });

    it("çoklu seçim: aynı müvekkile iki hizmet TEK PUT ile yazılır; föy adı kilitli ve gövdede yok", async () => {
        sunucu = [FOY_SATIRI];
        await bas();
        await duzenle(11);

        // Föy kaynaklı ad seçicide işaretli + kilitli.
        const kilitli = secenek("Takip (doktor müvekkil)")!;
        expect(kilitli.getAttribute("data-checked")).toBe("true");
        expect(kilitli.getAttribute("data-kilitli")).toBe("true");
        await tikla(kilitli);

        await tikla(secenek("Lexis Rapor"));
        await tikla(secenek("Danışmanlık"));
        await uygula(11);

        expect(putlar()).toEqual([
            { yol: "/api/cases/42/hizmetler/11", govde: { hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] } },
        ]);
        // Yazma sonrası liste YENİDEN çekilir (açılış + yazma sonrası = 2 GET) ve kart tazelenir.
        expect(cagrilar("GET")).toHaveLength(2);
        expect(onDegisti).toHaveBeenCalledTimes(1);
        expect(cipAdlari(11, "foy")).toEqual(["Takip (doktor müvekkil)"]);
        expect(cipAdlari(11, "elle")).toEqual(["Danışmanlık", "Lexis Rapor"]);
        expect(q("case-hizmet-duzenle")).toBeNull();
        expect(toastMock.error).not.toHaveBeenCalled();
    });

    it("seçim değişmediyse istek atılmaz (Uygula yalnız kapatır)", async () => {
        await bas();
        await duzenle(11);
        expect(secenek("Danışmanlık")!.getAttribute("data-checked")).toBe("true");
        await uygula(11);
        expect(cagrilar("PUT")).toHaveLength(0);
        expect(cagrilar("GET")).toHaveLength(1);
        expect(onDegisti).not.toHaveBeenCalled();
        expect(q("case-hizmet-duzenle")).toBeNull();

        // Seçip geri almak da "değişmedi"dir.
        await duzenle(11);
        await tikla(secenek("Lexis Rapor"));
        await tikla(secenek("Lexis Rapor"));
        await uygula(11);
        expect(cagrilar("PUT")).toHaveLength(0);
    });

    it("seçimi kaldırıp uygulamak elle satırı siler (boş küme PUT); föy çipi kalır", async () => {
        await bas();
        await duzenle(11);
        await tikla(secenek("Danışmanlık"));
        await uygula(11);

        expect(putlar()).toEqual([{ yol: "/api/cases/42/hizmetler/11", govde: { hizmet_turleri: [] } }]);
        expect(cipAdlari(11, "elle")).toEqual([]);
        expect(cipAdlari(11, "foy")).toEqual(["Takip (doktor müvekkil)"]);
    });

    it("Vazgeç taslağı atar, istek atılmaz", async () => {
        await bas();
        await duzenle(11);
        await tikla(secenek("Lexis Rapor"));
        await tikla(q("case-hizmet-vazgec", satiri(11)));
        expect(cagrilar("PUT")).toHaveLength(0);
        expect(q("case-hizmet-duzenle")).toBeNull();
        expect(cipAdlari(11, "elle")).toEqual(["Danışmanlık"]);
    });

    it("iki müvekkile FARKLI hizmet kümesi yazılır ve ayrı ayrı görünür (muhasebe ayrımı)", async () => {
        sunucu = [];
        await bas([DOKTOR, HASTANE]);

        await duzenle(11);
        await tikla(secenek("Takip (doktor müvekkil)"));
        await tikla(secenek("Danışmanlık"));
        await uygula(11);

        await duzenle(12);
        // İkinci müvekkilin seçicisi BOŞ açılır — birincinin seçimi sızmaz.
        expect(secenek("Danışmanlık")!.getAttribute("data-checked")).toBe("false");
        await tikla(secenek("Lexis Rapor"));
        await uygula(12);

        expect(putlar()).toEqual([
            { yol: "/api/cases/42/hizmetler/11", govde: { hizmet_turleri: ["Takip (doktor müvekkil)", "Danışmanlık"] } },
            { yol: "/api/cases/42/hizmetler/12", govde: { hizmet_turleri: ["Lexis Rapor"] } },
        ]);
        expect(cipAdlari(11)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
        expect(cipAdlari(12)).toEqual(["Lexis Rapor"]);
        expect(onDegisti).toHaveBeenCalledTimes(2);
    });

    it("toplu uygulama: 2+ müvekkilde görünür, her müvekkil için bir PUT atar", async () => {
        sunucu = [];
        await bas([DOKTOR, HASTANE]);
        await tikla(q("case-hizmet-toplu-ac"));
        expect(q("case-hizmet-toplu")).not.toBeNull();
        // Seçim yokken "Tümüne uygula" devre dışı (yanlışlıkla toplu silme olmaz).
        expect(q<HTMLButtonElement>("case-hizmet-toplu-uygula")!.disabled).toBe(true);

        await tikla(secenek("Danışmanlık"));
        await tikla(secenek("Lexis Rapor"));
        await tikla(q("case-hizmet-toplu-uygula"));

        expect(putlar()).toEqual([
            { yol: "/api/cases/42/hizmetler/11", govde: { hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] } },
            { yol: "/api/cases/42/hizmetler/12", govde: { hizmet_turleri: ["Danışmanlık", "Lexis Rapor"] } },
        ]);
        expect(cipAdlari(11)).toEqual(["Danışmanlık", "Lexis Rapor"]);
        expect(cipAdlari(12)).toEqual(["Danışmanlık", "Lexis Rapor"]);
        expect(q("case-hizmet-toplu")).toBeNull();
        expect(q("case-hizmet-toplu-hata")).toBeNull();
        expect(onDegisti).toHaveBeenCalledTimes(1);
    });

    it("tek müvekkilli kartta toplu uygulama düğmesi yok", async () => {
        await bas([DOKTOR]);
        expect(q("case-hizmet-toplu-ac")).toBeNull();
        expect(q("case-hizmet-sec")).not.toBeNull();
    });

    it("toplu uygulamada biri başarısız olursa hangisinin yazılamadığı gösterilir, yazılan geri alınmaz", async () => {
        sunucu = [];
        putYaniti = (partyId, adlar) =>
            partyId === 12
                ? jsonYanit(409, { detail: "Bu kayıt şu an toplu bir veri işleminde kullanılıyor; değişikliğiniz kaydedilmedi. Birkaç dakika sonra tekrar deneyin." })
                : kumeyiUygula(partyId, adlar);
        await bas([DOKTOR, HASTANE]);
        await tikla(q("case-hizmet-toplu-ac"));
        await tikla(secenek("Danışmanlık"));
        await tikla(q("case-hizmet-toplu-uygula"));

        expect(cagrilar("PUT")).toHaveLength(2);
        const hata = qa("case-hizmet-toplu-hata-satiri");
        expect(hata).toHaveLength(1);
        expect(hata[0].textContent).toContain("Özel Şifa Hastanesi");
        expect(hata[0].textContent).toContain("Birkaç dakika sonra tekrar deneyin.");
        expect(hata[0].textContent).not.toContain("Dr. Ayşe Kaya");
        // Yazılan müvekkil ekranda; yazılamayan boş kalır. Toplu seçici yeniden denemek için açık.
        expect(cipAdlari(11)).toEqual(["Danışmanlık"]);
        expect(q("case-hizmet-bos", satiri(12))).not.toBeNull();
        expect(q("case-hizmet-toplu")).not.toBeNull();
        expect(onDegisti).toHaveBeenCalledTimes(1);
    });

    it("422 yanıtı Türkçe sunucu metniyle gösterilir; düzenleme açık kalır, liste değişmez", async () => {
        putYaniti = () => jsonYanit(422, { detail: "Hizmet türü listede yok: \"Lexis Rapor\"." });
        await bas();
        await duzenle(11);
        await tikla(secenek("Lexis Rapor"));
        await uygula(11);

        expect(toastMock.error).toHaveBeenCalledWith("Hizmet türü listede yok: \"Lexis Rapor\".");
        expect(q("case-hizmet-duzenle", satiri(11))).not.toBeNull();
        expect(cagrilar("GET")).toHaveLength(1);
        expect(onDegisti).not.toHaveBeenCalled();
        expect(cipAdlari(11, "elle")).toEqual(["Danışmanlık"]);
    });

    it("409 yanıtı Türkçe metinle gösterilir (gövdesizse varsayılan metin)", async () => {
        putYaniti = () => new Response(null, { status: 409 });
        await bas();
        await duzenle(11);
        await tikla(secenek("Lexis Rapor"));
        await uygula(11);
        expect(toastMock.error).toHaveBeenCalledWith(
            "Bu kayıt şu an başka bir işlemde kullanılıyor; birkaç dakika sonra tekrar deneyin.",
        );
    });

    it("liste dışı (eski adlı) çip amber 'liste dışı' damgasıyla görünür; seçicide seçenek olarak sunulmaz", async () => {
        sunucu = [
            ELLE_SATIRI,
            { id: 8, case_party_id: 11, muvekkil_adi: "Dr. Ayşe Kaya", hizmet_turu: "Eski Hizmet Adı", kaynak: "elle", foy_id: null, sistem_no: null },
        ];
        await bas();
        const cipler = qa("case-hizmet-cip", satiri(11));
        const eski = cipler.find(c => q("case-hizmet-cip-adi", c)!.textContent === "Eski Hizmet Adı")!;
        const guncel = cipler.find(c => q("case-hizmet-cip-adi", c)!.textContent === "Danışmanlık")!;
        expect(eski.getAttribute("data-liste-disi")).toBe("true");
        expect(q("case-hizmet-liste-disi", eski)!.textContent).toBe("liste dışı");
        expect(eski.className).toContain("amber");
        expect(eski.getAttribute("title")).toBe("Bu değer kapalı listede yok — aktarımdan gelmiş olabilir");
        expect(guncel.getAttribute("data-liste-disi")).toBe("false");
        expect(q("case-hizmet-liste-disi", guncel)).toBeNull();
        expect(guncel.getAttribute("title")).toBeNull();

        await duzenle(11);
        expect(secenek("Eski Hizmet Adı")).toBeNull();
        expect(q("case-hizmet-dusecek", satiri(11))!.textContent).toContain("\"Eski Hizmet Adı\"");
        // Değişiklik yoksa liste dışı satır yüzünden istek ATILMAZ.
        await uygula(11);
        expect(cagrilar("PUT")).toHaveLength(0);
    });

    it("liste boşken (henüz gelmedi) hiçbir çipe 'liste dışı' damgası vurulmaz", async () => {
        configMock.serviceTypes = [];
        await bas();
        expect(qa("case-hizmet-liste-disi")).toHaveLength(0);
        expect(qa("case-hizmet-cip").every(c => c.getAttribute("data-liste-disi") === "false")).toBe(true);
    });

    it("yetkisiz kullanıcıda 'Hizmet ekle' ve toplu uygulama görünmez; çipler görünür", async () => {
        await bas([DOKTOR, HASTANE], false);
        expect(q("case-hizmet-sec")).toBeNull();
        expect(q("case-hizmet-toplu-ac")).toBeNull();
        expect(cipAdlari(11)).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
        expect(q("case-hizmet-bos", satiri(12))).not.toBeNull();
    });

    it("yükleme hatasında Türkçe mesaj gösterilir; düğmeler çıkmaz", async () => {
        fetchMock.mockImplementation(async () => new Response(null, { status: 500 }));
        await bas([DOKTOR, HASTANE]);
        expect(q("case-hizmet-error")!.textContent).toBe("Hizmetler yüklenemedi.");
        expect(q("case-hizmet-sec")).toBeNull();
        expect(q("case-hizmet-toplu-ac")).toBeNull();
    });
});
