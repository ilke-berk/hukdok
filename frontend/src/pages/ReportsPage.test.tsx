// @vitest-environment jsdom
// ReportsPage (G133 → G139 → G175 sohbet öncelikli yerleşim) — Rapor sekmesi üç bloktur: asistan satırı
// (anahtar kapalıyken yerinde bilgi kartı) → tanım şeridi (TanimSeridi: kaynak rozeti · kolon çipleri · filtre
// çipleri · sıralama · Temizle) → sayaç satırı ("N kayıt" · kompakt şablon çubuğu · Excel/CSV) → önizleme tablosu.
// Sayfa DOLU açılır (katalog yüklenir, önizleme KENDİLİĞİNDEN varsayılan tanımla istenir; Önizle düğmesi /
// bayat rozeti / sol sütun / kaynak kartları / filtre şeridi / Kolonlar yan paneli YOK), şeritten kolon/filtre/
// başlık-sıralaması plan §2.1 gövdesiyle /api/reports/preview'a gider, yazarken 600 ms tek istek, geçersiz
// tanımda istek yok, kaynak rozeti menüsü kaynağı değiştirir ve eski satırlar ANINDA kaybolur, boş sonuçta
// filtre kısayolu, 422 okunur mesaja döner, ağ hatası boş listeye DÖNMEZ (DataErrorBanner), sayfa değişimi son
// önizlenen tanımla `sayfa` gönderir; /reports yalnız yöneticiye açılır, Sidebar "Raporlar" yalnız yöneticide.
// Seçili kolonların kanıtı: şeritteki kolon çipleri (`serit-kolon-<anahtar>`) + /preview gövdesindeki `kolonlar`.
// Şerit açılırları (kaynak menüsü, "+ Kolon", filtre düzenleyici) Radix portal'ında açılır — `document.body`den okunur.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

// Yönetici bayrağı: ProtectedAdminRoute + Sidebar aynı hook'u okur; test başına ayarlanır.
const adminMock = vi.hoisted(() => ({ value: true as boolean | null }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => adminMock.value }));

const msalMock = vi.hoisted(() => {
    const account = { username: "admin@lexis.com.tr", name: "Admin Kullanıcı" };
    return {
        useMsal: () => ({
            accounts: [account],
            inProgress: "none",
            instance: { getActiveAccount: () => account, logoutRedirect: async () => undefined },
        }),
    };
});
vi.mock("@azure/msal-react", () => msalMock);
vi.mock("@/hooks/useDashboardView", () => ({ useDashboardView: () => ({ view: "avukat", setView: () => undefined }) }));

import ReportsPage, { ONIZLEME_GECIKME_MS } from "./ReportsPage";
import { ProtectedAdminRoute } from "@/components/ProtectedAdminRoute";
import { Sidebar } from "@/components/shell/Sidebar";
import { OP_BY_TIP, type FiltreKontrolu, type KatalogKolon, type KolonTipi } from "@/lib/reports";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// cmdk (alan seçici / combobox) ve Radix popper jsdom'da ResizeObserver + scrollIntoView ister.
class ResizeObserverStub {
    observe() { /* jsdom */ }
    unobserve() { /* jsdom */ }
    disconnect() { /* jsdom */ }
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = function () { /* jsdom */ };

// §4.2 katalog şekli: tipten türetilen `kontrol`, tip tablosu kadar `oplar`.
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

const KATALOG = {
    veri_kaynaklari: [
        {
            anahtar: "davalar",
            etiket: "Davalar",
            aciklama: "Dava kartları",
            varsayilan_kolonlar: ["tracking_no", "subject"],
            kolonlar: [
                kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
                kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
                kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar"], grup: "Karar ve aşama" }),
                kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
                kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", grup: "Tutarlar" }),
                kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", filtrelenebilir: false, siralanabilir: false, turetilmis: true, grup: "Taraflar" }),
            ],
            hizli_filtreler: [
                { alan: "opening_date", alternatifler: [] },
                { alan: "status", alternatifler: [] },
                { alan: "subject", alternatifler: [] },
                { alan: "maddi_tazminat", alternatifler: [] },
            ],
            kolon_setleri: [
                { ad: "Temel", kolonlar: ["tracking_no", "subject"] },
                { ad: "Karar takibi", kolonlar: ["tracking_no", "status", "opening_date"] },
                { ad: "Tazminat", kolonlar: ["tracking_no", "maddi_tazminat"] },
            ],
        },
        {
            anahtar: "muvekkiller",
            etiket: "Müvekkiller",
            aciklama: "Cari kartlar",
            varsayilan_kolonlar: ["name"],
            kolonlar: [
                kolon({ anahtar: "name", etiket: "Ad", tip: "metin" }),
                // §5.2 sanal arama kolonu: yalnız filtre ("+ Kolon" listesinde yok), şeritte arama kutusu
                kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, siralanabilir: false, secilebilir: false, oplar: ["contains"] }),
                kolon({ anahtar: "il", etiket: "İl", tip: "metin", grup: "İletişim" }),
            ],
            hizli_filtreler: [
                { alan: "arama", alternatifler: [], sunum: "arama", etiket: null },
                { alan: "il", alternatifler: [], sunum: "varsayilan", etiket: null },
            ],
            kolon_setleri: [{ ad: "Temel", kolonlar: ["name"] }],
        },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
};

const ONIZLEME = {
    kolonlar: [
        { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" },
        { anahtar: "subject", etiket: "Konu", tip: "metin" },
        { anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih" },
        { anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para" },
    ],
    satirlar: [
        { tracking_no: "2025/12", subject: "Tazminat", opening_date: "2025-03-07", maddi_tazminat: 1234.5 },
        { tracking_no: "2025/13", subject: null, opening_date: null, maddi_tazminat: null },
    ],
    toplam: 120,
    sayfa: 1,
    sayfa_boyu: 10,
};

const MUVEKKIL_ONIZLEME = {
    kolonlar: [{ anahtar: "name", etiket: "Ad", tip: "metin" }],
    satirlar: [{ name: "Ayşe Yılmaz" }],
    toplam: 1,
    sayfa: 1,
    sayfa_boyu: 10,
};

const VARSAYILAN_TANIM = { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] };

const okJson = (payload: unknown, status = 200) => ({ ok: true, status, json: async () => payload });
const failJson = (status: number, payload: unknown) => ({ ok: false, status, json: async () => payload });

type Cagri = [string, RequestInit | undefined];
const previewCagrilari = () =>
    (fetchMock.mock.calls as Cagri[]).filter(([url]) => url === "/api/reports/preview");
const sonPreviewGovdesi = () => {
    const cagrilar = previewCagrilari();
    const [, opts] = cagrilar[cagrilar.length - 1];
    return JSON.parse(opts!.body as string);
};

describe("ReportsPage (G133/G138/G175)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        fetchMock.mockReset();
        toastMocks.error.mockReset();
        toastMocks.success.mockReset();
        adminMock.value = true;
        container = document.createElement("div");
        document.body.appendChild(container);
    });

    afterEach(() => {
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
        vi.useRealTimers();
    });

    /** Varsayılan sunucu: katalog + önizleme; sayfa numarası gövdeden yankılanır, kaynağa göre satırlar. Anahtar KAPALI (ayar yok). */
    function sunucuKur(onizleme: unknown = ONIZLEME) {
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/templates") return okJson([]);
            if (url === "/api/admin/settings") return okJson({ settings: [] });
            if (url === "/api/reports/preview") {
                const govde = JSON.parse(opts!.body as string);
                const cevap = govde.tanim.veri_kaynagi === "muvekkiller" ? MUVEKKIL_ONIZLEME : onizleme;
                return okJson({ ...(cevap as object), sayfa: govde.sayfa, sayfa_boyu: govde.sayfa_boyu });
            }
            throw new Error("beklenmeyen uç: " + url);
        });
    }

    async function bekle(tur = 4) {
        for (let i = 0; i < tur; i++) {
            await act(async () => { await Promise.resolve(); });
        }
    }

    async function render(element: React.ReactNode = <ReportsPage />, url = "/reports") {
        root = createRoot(container);
        await act(async () => {
            root!.render(<MemoryRouter initialEntries={[url]}>{element}</MemoryRouter>);
        });
        // katalog + açılış önizlemesi çözülsün
        await bekle();
    }

    const $ = <T extends Element>(sel: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    /** Portal'da (document.body) açılan panel — `container` da gövdenin içindedir. */
    const $$ = <T extends Element>(sel: string): T => $(sel, document.body);
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = document.body): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const butonBul = (metin: string, kok: ParentNode = container): HTMLButtonElement => {
        const b = Array.from(kok.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };
    const butonVar = (metin: string) =>
        Array.from(container.querySelectorAll("button")).some(x => x.textContent?.trim() === metin);

    function yaz(el: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }
    function sec(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }
    function tikla(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    }
    async function tiklaVeBekle(el: Element) {
        tikla(el);
        await bekle();
    }
    /** Radix DropdownMenu tetikleyicisi pointerdown ile açılır (click ile değil). */
    async function bas(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
        });
        await bekle();
    }
    /** Odak çıkışı: gerçek focus()/blur() (React onBlur focusout dinler). */
    async function odakCik(el: HTMLElement) {
        act(() => { el.focus(); });
        act(() => { el.blur(); });
        await bekle();
    }
    const satirlar = () => Array.from(container.querySelectorAll("tbody tr")).map(tr =>
        Array.from(tr.querySelectorAll("td")).map(td => td.textContent));

    // ---- Şerit (G173/G175) yardımcıları ----
    const serit = () => $("[data-testid='tanim-seridi']");
    /** Kaynak rozetindeki etiket → katalog anahtarı. */
    const seciliKaynak = () => {
        const etiket = $("[data-testid='serit-kaynak']").textContent?.trim();
        return KATALOG.veri_kaynaklari.find(k => k.etiket === etiket)?.anahtar ?? null;
    };
    async function kaynakSec(anahtar: string) {
        await bas($("[data-testid='serit-kaynak']"));
        tikla($$(`[role='menu'] [data-kaynak='${anahtar}']`));
    }
    const kolonCipleri = () => Array.from(container.querySelectorAll("[data-testid^='serit-kolon-']"))
        .filter(e => e.getAttribute("data-testid") !== "serit-kolon-ekle")
        .map(e => e.getAttribute("data-testid")!.replace("serit-kolon-", ""));
    const kolonSecici = () => document.body.querySelector("[data-testid='kolon-secici']");
    async function kolonSeciciAc() {
        await tiklaVeBekle($("[data-testid='serit-kolon-ekle']"));
        const p = kolonSecici();
        if (!p) throw new Error("kolon seçici açılmadı");
        return p;
    }
    async function kolonEkle(anahtar: string) {
        const p = await kolonSeciciAc();
        await tiklaVeBekle($(`[cmdk-item][data-kolon='${anahtar}']`, p));
    }
    async function kolonKaldir(etiket: string) {
        await tiklaVeBekle(byLabel(`${etiket} kolonunu kaldır`, container));
    }
    const filtreCipleri = () => Array.from(container.querySelectorAll("[data-testid='filtre-cipi']")).map(c => c.getAttribute("data-alan"));
    const duzenleyici = (alan: string) => document.body.querySelector(`[data-testid='filtre-duzenleyici'][data-alan='${alan}']`);
    /** "+ Filtre" → alan → popover'daki düzenleyici (FilterControl). */
    async function filtreAc(alan: string): Promise<ParentNode> {
        await tiklaVeBekle($("[data-testid='serit-filtre-ekle'] button"));
        await tiklaVeBekle($(`[data-testid='alan-secici'] [cmdk-item][data-alan='${alan}']`));
        const p = duzenleyici(alan);
        if (!p) throw new Error("filtre düzenleyici açılmadı: " + alan);
        return p;
    }
    /** "+ Filtre" listesindeki alanlar (açar, okur, kapatır). */
    async function filtreAlanlari(): Promise<(string | null)[]> {
        await tiklaVeBekle($("[data-testid='serit-filtre-ekle'] button"));
        const alanlar = Array.from($("[data-testid='alan-secici']").querySelectorAll("[cmdk-item]")).map(i => i.getAttribute("data-alan"));
        await tiklaVeBekle($("[data-testid='serit-filtre-ekle'] button"));
        return alanlar;
    }
    /** Durum çoklu seçiminde bir seçeneği işaretler; düzenleyici/listbox zaten açıksa yeniden açmaz (toggle). */
    async function durumSec(secenek: string) {
        const p = duzenleyici("status") ?? await filtreAc("status");
        const ac = byLabel("Durum seç", p);
        if (ac.getAttribute("aria-expanded") !== "true") await tiklaVeBekle(ac);
        await tiklaVeBekle(byLabel(`Durum: ${secenek}`));
    }
    /** Dolu çipin gövdesinden düzenleyiciyi açar (zaten açıksa dokunmaz — gövde tıkı toggle'dır). */
    async function cipDuzenleyiciAc(alan: string, etiket: string): Promise<ParentNode> {
        if (!duzenleyici(alan)) await tiklaVeBekle(byLabel(`${etiket} filtresini düzenle`, container));
        const p = duzenleyici(alan);
        if (!p) throw new Error("çip düzenleyicisi açılmadı: " + alan);
        return p;
    }
    const onceGelir = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

    it("sayfa DOLU açılır: katalog yüklenir, şeritte Davalar + varsayılan kolonlar, önizleme KENDİLİĞİNDEN varsayılan tanımla istenir; kart/şerit/yan panel/Önizle/operatör yok", async () => {
        sunucuKur();
        await render();

        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        // Şerit: kaynak rozeti ilk kaynak, kolon çipleri varsayılan, filtre çipi yok (boş yuvalar görünmez)
        expect(seciliKaynak()).toBe("davalar");
        expect(kolonCipleri()).toEqual(["tracking_no", "subject"]);
        expect(filtreCipleri()).toEqual([]);
        expect(container.querySelector("[data-testid='serit-filtre-taslak']")).toBeNull();
        // "+ Filtre": filtrelenebilir alanlar grup sırasıyla; türetilmiş/filtrelenemez (muvekkil_adlari) yok
        expect(await filtreAlanlari()).toEqual(["tracking_no", "subject", "status", "opening_date", "maddi_tazminat"]);

        // Otomatik önizleme: tek istek, varsayılan tanım, tablo dolu — kullanıcı hiçbir şeye basmadı
        expect(previewCagrilari()).toHaveLength(1);
        expect(sonPreviewGovdesi()).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 10 });
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
        expect(container.querySelector("[data-testid='toplam-rozeti']")).toBeNull();   // 12.09: sayı tek yerde
        expect($("[data-testid='kayit-sayaci']").textContent).toBe("120 kayıt");

        // G175: eski arayüz izleri yok — kaynak kartları, filtre şeridi, Kolonlar düğmesi/paneli, araç çubuğu, eski select
        expect(container.querySelector("[data-testid='kaynak-kartlari']")).toBeNull();
        expect(container.querySelector("[role='radio']")).toBeNull();
        expect(container.querySelector("[data-testid='filtre-seridi']")).toBeNull();
        expect(container.querySelector("[data-testid='etkin-filtreler']")).toBeNull();
        expect(container.querySelector("[data-testid='kolon-dugmesi']")).toBeNull();
        expect(document.body.querySelector("[data-testid='kolon-paneli']")).toBeNull();
        expect(container.querySelector("[data-testid='arac-cubugu']")).toBeNull();
        expect(container.querySelector("#rapor-kaynak")).toBeNull();
        expect(container.textContent).not.toContain("Rapor Oluşturucu");
        expect(container.textContent).not.toContain("Kolonlar (");
        expect(butonVar("Önizle")).toBe(false);
        expect(butonVar("Filtre ekle")).toBe(false);
        expect(butonVar("Sıralama ekle")).toBe(false);
        expect(container.querySelector("[aria-label='Operatör']")).toBeNull();
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(container.querySelector("[data-testid='guncelleniyor']")).toBeNull();
        // Sadeleştirme: kaynak açıklaması yalnız rozet menüsünde (kapalı), tip rozeti yok
        expect(container.textContent).not.toContain("Dava kartları");
        expect(container.textContent).not.toContain("abc");
    });

    it("kaynak rozeti menüsü kaynağı değiştirir; aynı kaynağa yeniden basmak yeni istek üretmez", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        await bas($("[data-testid='serit-kaynak']"));
        const menu = $$("[role='menu']");
        expect(Array.from(menu.querySelectorAll("[data-kaynak]")).map(o => o.getAttribute("data-kaynak"))).toEqual(["davalar", "muvekkiller"]);
        expect(menu.textContent).toContain("Cari kartlar");   // açıklama yalnız menüde
        await tiklaVeBekle($$("[role='menu'] [data-kaynak='davalar']")); // zaten seçili
        expect(previewCagrilari()).toHaveLength(1);
        expect(seciliKaynak()).toBe("davalar");

        await kaynakSec("muvekkiller");
        await bekle();
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim).toEqual({ veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [], siralama: [] });
        expect(kolonCipleri()).toEqual(["name"]);
        expect(satirlar()).toEqual([["Ayşe Yılmaz"]]);
    });

    it("+ Kolon: hazır setler + gruplar (seçilmiş kolonlar listede yok); set ekler ve önizleme yenilenir; kolon × hemen önizler; tek kolon kalınca × kapalı", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        const p = await kolonSeciciAc();
        expect(Array.from(p.querySelectorAll("[cmdk-item][data-set]")).map(s => s.getAttribute("data-set"))).toEqual(["Temel", "Karar takibi", "Tazminat"]);
        expect(Array.from(p.querySelectorAll("[cmdk-group]:not([hidden]) [cmdk-group-heading]")).map(h => h.textContent))
            .toEqual(["Hazır setler", "Karar ve aşama", "Tarihler", "Tutarlar", "Taraflar"]);
        expect(Array.from(p.querySelectorAll("[cmdk-item][data-kolon]")).map(i => i.getAttribute("data-kolon")))
            .toEqual(["status", "opening_date", "maddi_tazminat", "muvekkil_adlari"]);
        expect((p as Element).textContent).not.toContain("abc");
        expect((p as Element).textContent).not.toContain("Dava kartları");

        // Set: eksik kolonlar EKLENİR (mevcutlar korunur, set sırası), önizleme hemen, seçici kapanır
        await tiklaVeBekle($("[cmdk-item][data-set='Karar takibi']", p));
        expect(kolonSecici()).toBeNull();
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "subject", "status", "opening_date"]);
        expect(kolonCipleri()).toEqual(["tracking_no", "subject", "status", "opening_date"]);

        // ×: yapısal — hemen önizlenir
        await kolonKaldir("Konu");
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "status", "opening_date"]);
        await kolonKaldir("Durum");
        await kolonKaldir("Açılış Tarihi");
        expect(previewCagrilari()).toHaveLength(5);
        expect(kolonCipleri()).toEqual(["tracking_no"]);
        const son = byLabel<HTMLButtonElement>("Ofis No kolonunu kaldır", container);
        expect(son.disabled).toBe(true);
        await tiklaVeBekle(son);
        expect(previewCagrilari()).toHaveLength(5);
    });

    it("boş sonuçta 'filtreleri gevşetin' + Filtreleri temizle kısayolu: şerit boşalır, önizleme filtresiz yenilenir", async () => {
        const bosCevap = { ...ONIZLEME, satirlar: [], toplam: 0 };
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/templates") return okJson([]);
            if (url === "/api/admin/settings") return okJson({ settings: [] });
            if (url === "/api/reports/preview") {
                const govde = JSON.parse(opts!.body as string);
                const cevap = govde.tanim.filtreler.length > 0 ? bosCevap : ONIZLEME;
                return okJson({ ...cevap, sayfa: govde.sayfa, sayfa_boyu: govde.sayfa_boyu });
            }
            throw new Error("beklenmeyen uç: " + url);
        });
        await render();
        expect(container.querySelector("[data-testid='bos-sonuc']")).toBeNull();

        await durumSec("Derdest");
        expect(previewCagrilari()).toHaveLength(2);
        expect(filtreCipleri()).toEqual(["status"]);
        expect($("[data-testid='kayit-sayaci']").textContent).toBe("0 kayıt");
        const bos = $("[data-testid='bos-sonuc']");
        expect(bos.textContent).toContain("Bu filtrelerle kayıt yok");
        expect(bos.textContent).toContain("filtreleri gevşetin");
        expect(container.querySelector("tbody")).toBeNull();

        await tiklaVeBekle(butonBul("Filtreleri temizle", bos));
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim).toEqual(VARSAYILAN_TANIM);
        expect(container.querySelector("[data-testid='bos-sonuc']")).toBeNull();
        expect(filtreCipleri()).toEqual([]);
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    });

    it("şeritten filtre kaldırınca (×) ve şerit Temizle ile önizleme HEMEN istenir", async () => {
        sunucuKur();
        await render();
        await durumSec("Derdest");
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "eq", deger: "Derdest" }]);

        // ×: hızlı yuva boşa döner, çip düşer, istek hemen filtresiz gider
        await tiklaVeBekle(byLabel("Durum filtresini kaldır", container));
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim).toEqual(VARSAYILAN_TANIM);
        expect(filtreCipleri()).toEqual([]);

        // Temizle: kolon eklenmiş + filtre + sıralama → varsayılana döner, tek istek
        await kolonEkle("status");
        await durumSec("Karar");
        await tiklaVeBekle(byLabel("Ofis No sırala", container));
        expect(previewCagrilari()).toHaveLength(6);
        const temizle = $<HTMLButtonElement>("[data-testid='serit-temizle']");
        expect(temizle.disabled).toBe(false);
        await tiklaVeBekle(temizle);
        expect(previewCagrilari()).toHaveLength(7);
        expect(sonPreviewGovdesi().tanim).toEqual(VARSAYILAN_TANIM);
        expect(kolonCipleri()).toEqual(["tracking_no", "subject"]);
        expect(filtreCipleri()).toEqual([]);
        expect(container.querySelector("[data-testid^='serit-siralama-']")).toBeNull();
        expect($<HTMLButtonElement>("[data-testid='serit-temizle']").disabled).toBe(true);
    });

    it("kolon + şerit + başlık sıralaması gövdeyi §2.1 ile birebir gönderir (between dizi, in liste, sayı number); tablo biçimleri", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        // Kolon ekle ("+ Kolon") — yapısal: her biri hemen önizlenir
        await kolonEkle("opening_date");
        await kolonEkle("maddi_tazminat");
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "subject", "opening_date", "maddi_tazminat"]);

        // Durum in [Derdest, Karar] — popover'da checkbox'lı açılır, serbest metin yok
        await durumSec("Derdest");
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "eq", deger: "Derdest" }]);
        await durumSec("Karar");
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "in", deger: ["Derdest", "Karar"] }]);
        expect(previewCagrilari()).toHaveLength(5);

        // Açılış between: yazarken istek GİTMEZ, odak çıkışında gider
        const acilis = await filtreAc("opening_date");
        yaz(byLabel<HTMLInputElement>("Açılış Tarihi başlangıç", acilis), "2025-01-01");
        yaz(byLabel<HTMLInputElement>("Açılış Tarihi bitiş", acilis), "2025-12-31");
        await bekle();
        expect(previewCagrilari()).toHaveLength(5);
        await odakCik(byLabel<HTMLInputElement>("Açılış Tarihi bitiş", acilis));
        expect(previewCagrilari()).toHaveLength(6);

        // Maddi tazminat ≥ 1000 (sayı JSON number)
        const maddi = await filtreAc("maddi_tazminat");
        yaz(byLabel<HTMLInputElement>("Maddi Tazminat en az", maddi), "1000");
        await odakCik(byLabel<HTMLInputElement>("Maddi Tazminat en az", maddi));
        expect(previewCagrilari()).toHaveLength(7);

        // Başlıktan sıralama: Açılış Tarihi → artan → azalan; şeritte sıralama çipi
        await tiklaVeBekle(byLabel("Açılış Tarihi sırala", container));
        expect(sonPreviewGovdesi().tanim.siralama).toEqual([{ alan: "opening_date", yon: "asc" }]);
        expect($("[data-testid='serit-siralama-opening_date']").getAttribute("data-yon")).toBe("asc");
        await tiklaVeBekle(byLabel("Açılış Tarihi sırala", container));
        expect(previewCagrilari()).toHaveLength(9);
        expect($("[data-testid='serit-siralama-opening_date']").getAttribute("data-yon")).toBe("desc");

        const [, opts] = previewCagrilari().at(-1)!;
        expect(opts!.method).toBe("POST");
        expect(sonPreviewGovdesi()).toEqual({
            tanim: {
                veri_kaynagi: "davalar",
                kolonlar: ["tracking_no", "subject", "opening_date", "maddi_tazminat"],
                filtreler: [
                    { alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] },
                    { alan: "status", op: "in", deger: ["Derdest", "Karar"] },
                    { alan: "maddi_tazminat", op: "gte", deger: 1000 },
                ],
                siralama: [{ alan: "opening_date", yon: "desc" }],
            },
            sayfa: 1,
            sayfa_boyu: 10,
        });
        expect($("th[aria-sort='descending']").textContent).toContain("Açılış Tarihi");

        // Tablo: başlık etiketle, tarih dd.MM.yyyy, para tr-TR, null "—"; toplam rozeti; etkin filtre çipleri şeritte
        const basliklar = Array.from(container.querySelectorAll("thead th button, thead th")).filter(e => e.tagName === "TH").map(th => th.textContent?.replace(/\d$/, ""));
        expect(basliklar).toEqual(["Ofis No", "Konu", "Açılış Tarihi", "Maddi Tazminat"]);
        expect(satirlar()).toEqual([
            ["2025/12", "Tazminat", "07.03.2025", "1.234,50"],
            ["2025/13", "—", "—", "—"],
        ]);
        expect($("[data-testid='kayit-sayaci']").textContent).toBe("120 kayıt");
        expect(filtreCipleri()).toEqual(["opening_date", "status", "maddi_tazminat"]);
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
    });

    it("yazarken tek istek gider: 600 ms gecikme, her tuşta yeniden başlar; süre dolunca son değerle contains", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);
        const p = await filtreAc("subject");
        vi.useFakeTimers();

        const konu = byLabel<HTMLInputElement>("Konu içerir", p);
        yaz(konu, "T");
        yaz(konu, "Ta");
        await act(async () => { vi.advanceTimersByTime(ONIZLEME_GECIKME_MS - 1); });
        yaz(konu, "Taz");
        await act(async () => { vi.advanceTimersByTime(ONIZLEME_GECIKME_MS - 1); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(1); // henüz yok — zamanlayıcı her tuşta sıfırlandı

        await act(async () => { vi.advanceTimersByTime(1); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "subject", op: "contains", deger: "Taz" }]);
        expect(container.querySelector("[data-testid='filtre-cipi'][data-alan='subject']")?.textContent).toContain("içerir \"Taz\"");

        // Aynı tanıma tekrar istek atılmaz
        await act(async () => { vi.advanceTimersByTime(5000); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(2);
    });

    it("geçersiz tanımda istek gitmez: gelişmiş çipin değeri silinince ipucu, değer gelince hemen önizler", async () => {
        sunucuKur();
        await render();
        await durumSec("Derdest");
        expect(previewCagrilari()).toHaveLength(2);

        // Çipin "…" menüsü → "eşit değil" (gelişmiş çip, değer taşınır → geçerli, hemen önizlenir)
        await tiklaVeBekle(byLabel("Durum filtre seçenekleri", container));
        await tiklaVeBekle(Array.from(byLabel("Durum gelişmiş", container).querySelectorAll("button")).find(b => b.textContent?.includes("eşit değil"))!);
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "ne", deger: "Derdest" }]);
        expect(container.querySelector("[data-testid='filtre-cipi'][data-alan='status']")?.getAttribute("data-gelismis")).toBe("true");

        // Düzenleyicide değer silinir → tanım geçersiz: istek YOK, son geçerli önizleme kalır, "taslak eksik" ipucu
        const panel = await cipDuzenleyiciAc("status", "Durum");
        sec(byLabel<HTMLSelectElement>("Durum değeri", panel), "");
        await bekle();
        expect(previewCagrilari()).toHaveLength(3);
        expect($("[data-testid='taslak-eksik']").textContent).toContain("filtreleri tamamlayın");
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
        // Geçersizken kolon değişikliği de istek üretmez
        await kolonEkle("opening_date");
        expect(previewCagrilari()).toHaveLength(3);

        sec(byLabel<HTMLSelectElement>("Durum değeri", panel), "Karar");
        await bekle();
        expect(previewCagrilari()).toHaveLength(4);
        expect(container.querySelector("[data-testid='taslak-eksik']")).toBeNull();
        expect(sonPreviewGovdesi().tanim).toEqual({
            veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject", "opening_date"],
            filtreler: [{ alan: "status", op: "ne", deger: "Karar" }], siralama: [],
        });
    });

    it("arama kutusu (§5.3): yazarken 600 ms tek istek, `arama contains`; × hemen filtresiz ister; `arama` + Kolon listesinde yok", async () => {
        sunucuKur();
        await render();
        await kaynakSec("muvekkiller");
        await bekle();
        expect(previewCagrilari()).toHaveLength(2);
        expect(await filtreAlanlari()).toEqual(["name", "arama", "il"]);

        const p = await filtreAc("arama");
        vi.useFakeTimers();
        const kutu = byLabel<HTMLInputElement>("Ara içerir", p);
        yaz(kutu, "A");
        yaz(kutu, "Ay");
        await act(async () => { vi.advanceTimersByTime(ONIZLEME_GECIKME_MS - 1); });
        yaz(kutu, "Ayşe");
        await act(async () => { vi.advanceTimersByTime(ONIZLEME_GECIKME_MS - 1); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(2); // zamanlayıcı her tuşta sıfırlandı
        await act(async () => { vi.advanceTimersByTime(1); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim).toEqual({
            veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [{ alan: "arama", op: "contains", deger: "Ayşe" }], siralama: [],
        });
        expect(container.querySelector("[data-testid='filtre-cipi'][data-alan='arama']")?.textContent).toContain("içerir \"Ayşe\"");

        await tiklaVeBekle(byLabel("Ara filtresini kaldır", container));
        expect(previewCagrilari()).toHaveLength(4);
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([]);
        expect(filtreCipleri()).toEqual([]);
        vi.useRealTimers();

        const secici = await kolonSeciciAc();
        expect(Array.from(secici.querySelectorAll("[cmdk-item][data-kolon]")).map(i => i.getAttribute("data-kolon"))).toEqual(["il"]);
    });

    it("kaynak değişince eski kaynağın satırları ANINDA kaybolur, kolonlar/şerit yeni kaynağa döner, önizleme kendiliğinden yenilenir", async () => {
        sunucuKur();
        await render();
        expect(satirlar()).toHaveLength(2);
        const p = await filtreAc("subject");
        yaz(byLabel<HTMLInputElement>("Konu içerir", p), "x"); // bekleyen gecikmeli değişiklik

        // Müvekkil önizlemesi elle çözülür: cevap gelmeden ekranda dava satırı KALMAMALI
        let coz: (() => void) | null = null;
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const govde = JSON.parse(opts!.body as string);
                await new Promise<void>(r => { coz = r; });
                return okJson({ ...MUVEKKIL_ONIZLEME, sayfa: govde.sayfa, sayfa_boyu: govde.sayfa_boyu });
            }
            throw new Error("beklenmeyen uç: " + url);
        });
        await kaynakSec("muvekkiller");
        await bekle(1);

        expect(seciliKaynak()).toBe("muvekkiller");
        expect(container.querySelector("tbody")).toBeNull();
        expect(container.textContent).not.toContain("2025/12");
        expect(container.textContent).toContain("Önizleme alınıyor");
        expect(kolonCipleri()).toEqual(["name"]);
        expect(filtreCipleri()).toEqual([]);
        expect(document.body.querySelector("[data-testid='filtre-duzenleyici']")).toBeNull();
        // Yeni kaynak hemen istendi (bekleyen "x" filtresi eski kaynakla gitmedi)
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim).toEqual({ veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [], siralama: [] });

        await act(async () => { coz!(); });
        await bekle();
        expect(satirlar()).toEqual([["Ayşe Yılmaz"]]);
        expect($("[data-testid='kayit-sayaci']").textContent).toBe("1 kayıt");
    });

    it("422 detail.alan/sebep kullanıcıya okunur mesaj olarak gösterilir", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            return failJson(422, { detail: { alan: "filtreler[0].op", sebep: "liste tipinde contains izinli değil" } });
        });
        await render();

        const uyari = $("[role='alert']");
        expect(uyari.textContent).toContain("Geçersiz rapor tanımı: filtreler[0].op — liste tipinde contains izinli değil");
        expect(container.querySelector("table")).toBeNull();
        expect($("[data-testid='kayit-sayaci']").textContent).toBe("— kayıt");
    });

    it("ağ hatasında tablo boş listeye DÖNMEZ: DataErrorBanner + Tekrar dene; hata döngüye girmez", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            throw new Error("Sunucuya ulaşılamadı.");
        });
        await render();
        await bekle();

        const uyari = $("[role='alert']");
        expect(uyari.textContent).toContain("Sunucuya ulaşılamadı.");
        expect(uyari.textContent).toContain("kayıtlarınız silinmedi");
        expect(container.textContent).not.toContain("Bu kriterlere uyan kayıt yok");
        expect(previewCagrilari()).toHaveLength(1); // aynı tanım yeniden denenmez

        // Tekrar dene → sunucu düzeldi → tablo gelir, şerit kalkar
        sunucuKur();
        await tiklaVeBekle(butonBul("Tekrar dene"));
        expect(container.querySelector("[role='alert']")).toBeNull();
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
        expect(previewCagrilari()).toHaveLength(2);
    });

    it("sayfa değişimi `sayfa: 2` gönderir ve SON önizlenen tanımı kullanır (bekleyen taslağı değil)", async () => {
        sunucuKur();
        await render();
        expect(container.textContent).toContain("1 / 12");   // 120 kayıt / örnek boyu 10
        const p = await filtreAc("subject");
        vi.useFakeTimers();

        // Taslağı yazarak değiştir (600 ms bekliyor) — sayfa değişimi yine önizlenen tanımla gitmeli
        yaz(byLabel<HTMLInputElement>("Konu içerir", p), "Taz");
        await tiklaVeBekle(butonBul("İleri"));
        expect(previewCagrilari()).toHaveLength(2);
        const govde = sonPreviewGovdesi();
        expect(govde.sayfa).toBe(2);
        expect(govde.tanim).toEqual(VARSAYILAN_TANIM);
        expect(container.textContent).toContain("2 / 12");
        expect(butonBul("Geri").disabled).toBe(false);

        // Süre dolunca taslak sayfa 1'den önizlenir
        await act(async () => { vi.advanceTimersByTime(ONIZLEME_GECIKME_MS); });
        await bekle();
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi()).toMatchObject({ sayfa: 1, tanim: { filtreler: [{ alan: "subject", op: "contains", deger: "Taz" }] } });
    });

    it("katalog hatası şerit + toast; Tekrar dene yeniden yükler ve önizler", async () => {
        fetchMock.mockResolvedValueOnce(failJson(503, { detail: "bakım" }));
        await render();
        expect($("[role='alert']").textContent).toContain("bakım");
        expect(toastMocks.error).toHaveBeenCalledTimes(1);
        expect(container.querySelector("[data-testid='tanim-seridi']")).toBeNull();
        expect(previewCagrilari()).toHaveLength(0);

        sunucuKur();
        await tiklaVeBekle(butonBul("Tekrar dene"));
        expect(seciliKaynak()).toBe("davalar");
        expect(previewCagrilari()).toHaveLength(1);
    });

    it("anahtar kapalı: asistan satırının yerinde bilgi kartı (sekmenin ilk öğesi); şerit ve tablo çalışır, şablon çubuğu ve indirme yerinde", async () => {
        sunucuKur();   // `/api/admin/settings` boş → anahtar kapalı
        await render();
        const kart = $("[data-testid='asistan-kapali-karti']");
        expect(kart.textContent).toContain("Rapor asistanı kapalı");
        expect(kart.textContent).toContain("rapor_asistani");
        expect($("[data-testid='rapor-sekmesi']").firstElementChild).toBe(kart);
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-iskelet']")).toBeNull();
        expect(container.querySelector("[aria-label='Asistana mesaj']")).toBeNull();

        // Şerit yedek kurucu: kolon ekle → hemen önizleme; filtre → önizleme
        expect(previewCagrilari()).toHaveLength(1);
        await kolonEkle("status");
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "subject", "status"]);
        await durumSec("Karar");
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "eq", deger: "Karar" }]);
        expect($("#rapor-sablon")).not.toBeNull();
        expect(butonVar("Excel indir")).toBe(true);
        expect(butonVar("CSV indir")).toBe(true);
    });

    it("yerleşim: asistan (kapalı kartı) → şerit → sayaç satırı → tablo; kart/şerit/araç çubuğu yok; kök mx-auto/max-w ile daraltılmaz; dar ekranda satırlar sarar, tablo kendi içinde kaydırır", async () => {
        sunucuKur();
        await render();
        const kok = container.firstElementChild as HTMLElement;
        expect(kok.className).not.toContain("mx-auto");
        expect(kok.className).not.toMatch(/max-w-/);
        expect(container.innerHTML).not.toContain("xl:grid-cols-[320px_1fr]");

        const sekme = $("[data-testid='rapor-sekmesi']");
        const asistan = $("[data-testid='asistan-kapali-karti']");
        const s = serit();
        const sayac = $("[data-testid='sayac-satiri']");
        const tablo = $("table");
        expect(sekme.firstElementChild).toBe(asistan);
        expect(onceGelir(asistan, s)).toBe(true);
        expect(onceGelir(s, sayac)).toBe(true);
        expect(onceGelir(sayac, tablo)).toBe(true);
        expect(container.querySelector("[data-testid='kaynak-kartlari']")).toBeNull();
        expect(container.querySelector("[data-testid='filtre-seridi']")).toBeNull();
        expect(container.querySelector("[data-testid='arac-cubugu']")).toBeNull();
        expect(container.querySelector("[data-testid='kolon-dugmesi']")).toBeNull();

        // Sayaç satırı: sayaç + kompakt şablon çubuğu + Excel/CSV; "Asistan" düğmesi yok
        expect(sayac.querySelector("[data-testid='kayit-sayaci']")?.textContent).toBe("120 kayıt");
        expect(sayac.querySelector("#rapor-sablon")).not.toBeNull();
        expect(sayac.querySelector("[data-testid='sablon-cubugu']")).not.toBeNull();
        const dugmeler = Array.from(sayac.querySelectorAll("button")).map(b => b.textContent?.trim());
        expect(dugmeler).toEqual(expect.arrayContaining(["Yükle", "Kaydet", "Excel indir", "CSV indir"]));
        expect(dugmeler).not.toContain("Asistan");

        // Responsive: şerit ve sayaç satırı sarar (lg altı), tablo kendi sarmalayıcısında kaydırır
        for (const satir of Array.from(s.children)) expect(satir.className).toContain("flex-wrap");   // şerit iki satır, her biri sarar
        expect(sayac.className).toContain("flex-wrap");
        expect(tablo.parentElement?.className).toContain("overflow-x-auto");
    });

    it("/reports yöneticiye açılır; yönetici değilse ana sayfaya yönlendirilir", async () => {
        sunucuKur();
        const agac = (
            <Routes>
                <Route path="/" element={<div data-testid="anasayfa" />} />
                <Route path="/reports" element={<ProtectedAdminRoute><ReportsPage /></ProtectedAdminRoute>} />
            </Routes>
        );
        await render(agac, "/reports");
        expect(container.querySelector("[data-testid='tanim-seridi']")).not.toBeNull();
        expect(container.querySelector("[data-testid='anasayfa']")).toBeNull();

        act(() => root!.unmount());
        root = null;
        const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
        adminMock.value = false;
        await render(agac, "/reports");
        expect(container.querySelector("[data-testid='anasayfa']")).not.toBeNull();
        expect(container.querySelector("[data-testid='tanim-seridi']")).toBeNull();
        warn.mockRestore();
    });

    it("Sidebar'da Raporlar yalnız yöneticide görünür ve Yönetim'den önce gelir", async () => {
        const etiketler = () =>
            Array.from(container.querySelectorAll("nav button")).map(b => b.textContent?.trim());

        adminMock.value = true;
        await render(<Sidebar open onClose={() => undefined} />, "/");
        const admin = etiketler();
        expect(admin).toContain("Raporlar");
        expect(admin.indexOf("Raporlar")).toBe(admin.indexOf("Yönetim") - 1);

        act(() => root!.unmount());
        root = null;
        adminMock.value = false;
        await render(<Sidebar open onClose={() => undefined} />, "/");
        expect(etiketler()).not.toContain("Raporlar");
        expect(etiketler()).not.toContain("Yönetim");
    });
});
