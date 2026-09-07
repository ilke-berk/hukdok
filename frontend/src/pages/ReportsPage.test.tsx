// @vitest-environment jsdom
// ReportsPage (G133 → G139) — kaynak kartları + filtre şeridi + Kolonlar yan paneli + önizleme
// tablosunun sözleşmeye bağlanışı: sayfa DOLU açılır (katalog yüklenir, önizleme KENDİLİĞİNDEN
// varsayılan tanımla istenir; Önizle düğmesi/bayat rozeti/sol sütun yok), kolon/şerit/başlık-sıralaması
// plan §2.1 gövdesiyle /api/reports/preview'a gider, yazarken 600 ms tek istek, geçersiz tanımda istek
// yok, kart tıklaması kaynağı değiştirir ve eski satırlar ANINDA kaybolur, kolon setleri yan panelden
// seçimi değiştirir, boş sonuçta filtre kısayolu, 422 okunur mesaja döner, ağ hatası boş listeye
// DÖNMEZ (DataErrorBanner), sayfa değişimi son önizlenen tanımla `sayfa` gönderir; /reports yalnız
// yöneticiye açılır, Sidebar "Raporlar" yalnız yöneticide.
// Seçili kolonların birincil kanıtı: "Kolonlar (N)" düğme metni + /preview gövdesindeki `kolonlar`
// (yan panel Radix portal'ında açılır; panel içi `document.body` üzerinden okunur).
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

// cmdk (alan seçici / combobox) jsdom'da ResizeObserver + scrollIntoView ister.
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
                kolon({ anahtar: "il", etiket: "İl", tip: "metin", grup: "İletişim" }),
            ],
            hizli_filtreler: [{ alan: "il", alternatifler: [] }],
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
    sayfa_boyu: 50,
};

const MUVEKKIL_ONIZLEME = {
    kolonlar: [{ anahtar: "name", etiket: "Ad", tip: "metin" }],
    satirlar: [{ name: "Ayşe Yılmaz" }],
    toplam: 1,
    sayfa: 1,
    sayfa_boyu: 50,
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

describe("ReportsPage (G133/G138/G139)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        fetchMock.mockReset();
        toastMocks.error.mockReset();
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

    /** Varsayılan sunucu: katalog + önizleme; sayfa numarası gövdeden yankılanır, kaynağa göre satırlar. */
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

    const $ = <T extends Element>(sel: string): T => {
        const el = container.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    const byLabel = <T extends HTMLElement>(label: string, root: ParentNode = container): T => {
        const el = root.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const butonBul = (metin: string, root: ParentNode = container): HTMLButtonElement => {
        const b = Array.from(root.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
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
    function tikla(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    }
    async function tiklaVeBekle(el: Element) {
        tikla(el);
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
    const seritAlanlari = () =>
        Array.from(container.querySelectorAll("[data-testid='filtre-kontrolu']")).map(k => k.getAttribute("data-alan"));
    /** Kartlardaki seçili kaynak (`role=radio` + `aria-checked`). */
    const seciliKaynak = () => container.querySelector("[data-kaynak][aria-checked='true']")?.getAttribute("data-kaynak") ?? null;
    const kartlar = () => Array.from(container.querySelectorAll("[data-kaynak]"));
    const kolonDugmesi = () => $<HTMLButtonElement>("[data-testid='kolon-dugmesi']");
    /** Yan panel Radix portal'ında: gövdeden okunur. */
    const kolonPaneli = () => document.body.querySelector("[data-testid='kolon-paneli']");
    async function kolonPaneliAc(): Promise<ParentNode> {
        await tiklaVeBekle(kolonDugmesi());
        const p = kolonPaneli();
        if (!p) throw new Error("kolon paneli açılmadı");
        return p;
    }
    async function kolonPaneliKapat() {
        await tiklaVeBekle(byLabel("Paneli kapat", document.body));
        expect(kolonPaneli()).toBeNull();
    }
    const panelKolonlari = (p: ParentNode) => Array.from(p.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));

    it("sayfa DOLU açılır: katalog yüklenir, Davalar kartı seçili, önizleme KENDİLİĞİNDEN varsayılan tanımla istenir; sol sütun/Önizle/operatör/tip rozeti yok", async () => {
        sunucuKur();
        await render();

        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        // Kaynak kartları (radio grubu): katalog sırası, ilk kart seçili; eski select yok
        expect(kartlar().map(k => k.getAttribute("data-kaynak"))).toEqual(["davalar", "muvekkiller"]);
        expect(kartlar().map(k => k.getAttribute("role"))).toEqual(["radio", "radio"]);
        expect(seciliKaynak()).toBe("davalar");
        expect(kartlar()[0].textContent).toContain("Davalar");
        expect(kartlar()[0].textContent).toContain("Dava kartları");
        expect(container.querySelector("#rapor-kaynak")).toBeNull();

        // Kolonlar yalnız yan panelde: sayfada liste yok, düğme sayıyı taşır, panel kapalı
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (2)");
        expect(container.querySelector("[data-kolon]")).toBeNull();
        expect(kolonPaneli()).toBeNull();
        expect(container.textContent).not.toContain("Rapor Oluşturucu");

        // Otomatik önizleme: tek istek, varsayılan tanım, tablo dolu — kullanıcı hiçbir şeye basmadı
        expect(previewCagrilari()).toHaveLength(1);
        expect(sonPreviewGovdesi()).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 50 });
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
        expect($("[data-testid='toplam-rozeti']").textContent).toBe("120 kayıt · 4 kolon");

        // Şerit: kaynağın hızlı filtreleri sırayla; eski arayüz izleri yok
        expect(seritAlanlari()).toEqual(["opening_date", "status", "subject", "maddi_tazminat"]);
        expect(butonVar("Önizle")).toBe(false);
        expect(butonVar("Filtre ekle")).toBe(false);
        expect(butonVar("Sıralama ekle")).toBe(false);
        expect(container.querySelector("[aria-label='Operatör']")).toBeNull();
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(container.querySelector("[data-testid='guncelleniyor']")).toBeNull();

        // Sadeleştirme: kaynak açıklaması yalnız kartta (bir kez), tip rozeti hiçbir yerde yok
        expect(container.textContent?.split("Dava kartları")).toHaveLength(2);
        const p = await kolonPaneliAc();
        const panelMetni = (p as Element).textContent ?? "";
        expect(panelMetni).not.toContain("abc");
        expect(panelMetni).not.toContain("123");
        expect(panelMetni).not.toContain("Dava kartları");
        expect(container.textContent?.split("Dava kartları")).toHaveLength(2);
        await kolonPaneliKapat();
    });

    it("kart tıklaması kaynağı değiştirir (aria-checked), aynı karta yeniden basmak yeni istek üretmez", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        await tiklaVeBekle(kartlar()[0]); // zaten seçili
        expect(previewCagrilari()).toHaveLength(1);
        expect(seciliKaynak()).toBe("davalar");

        await tiklaVeBekle($("[data-kaynak='muvekkiller']"));
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(kartlar().map(k => k.getAttribute("aria-checked"))).toEqual(["false", "true"]);
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim).toEqual({ veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [], siralama: [] });
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (1)");
        expect(satirlar()).toEqual([["Ayşe Yılmaz"]]);
    });

    it("Kolonlar yan paneli: 3 hazır set + gruplar; set tıklaması seçimi değiştirir ve önizleme yenilenir; grup 'tümünü seç'; kapanınca ek istek yok", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        const p = await kolonPaneliAc();
        const setler = Array.from(p.querySelectorAll("[data-kolon-seti]"));
        expect(setler.map(s => s.getAttribute("data-kolon-seti"))).toEqual(["Temel", "Karar takibi", "Tazminat"]);
        expect(setler.map(s => s.getAttribute("aria-pressed"))).toEqual(["true", "false", "false"]);
        expect(Array.from(p.querySelectorAll("[data-kolon-grubu]")).map(g => g.getAttribute("data-kolon-grubu")))
            .toEqual(["Kimlik", "Karar ve aşama", "Tarihler", "Tutarlar", "Taraflar"]);
        expect(panelKolonlari(p)).toEqual(["tracking_no", "subject"]);

        // Set: seçim setle DEĞİŞİR (sıra setin sırası), önizleme hemen
        await tiklaVeBekle(setler[1]);
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "status", "opening_date"]);
        expect(panelKolonlari(p)).toEqual(["tracking_no", "status", "opening_date"]);
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (3)");
        expect(Array.from(p.querySelectorAll("[data-kolon-seti]")).map(s => s.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);

        // Grup başlığı: Tutarlar'ın tümü (maddi_tazminat) eklenir; ikinci tık grubu kaldırır
        await tiklaVeBekle(byLabel("Tutarlar tümünü seç", p));
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "status", "opening_date", "maddi_tazminat"]);
        await tiklaVeBekle(byLabel("Tutarlar tümünü seç", p));
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["tracking_no", "status", "opening_date"]);
        expect(previewCagrilari()).toHaveLength(4);

        await kolonPaneliKapat();
        expect(previewCagrilari()).toHaveLength(4);
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (3)");
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

        await tiklaVeBekle(byLabel("Durum seç"));
        await tiklaVeBekle(byLabel("Durum: Derdest"));
        expect(previewCagrilari()).toHaveLength(2);
        const bos = $("[data-testid='bos-sonuc']");
        expect(bos.textContent).toContain("Bu filtrelerle kayıt yok");
        expect(bos.textContent).toContain("filtreleri gevşetin");
        expect(container.querySelector("tbody")).toBeNull();

        await tiklaVeBekle(butonBul("Filtreleri temizle", bos));
        expect(previewCagrilari()).toHaveLength(3);
        expect(sonPreviewGovdesi().tanim).toEqual(VARSAYILAN_TANIM);
        expect(container.querySelector("[data-testid='bos-sonuc']")).toBeNull();
        expect(container.querySelector("[data-testid='filtre-cipi']")).toBeNull();
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    });

    it("kolon + şerit + başlık sıralaması gövdeyi §2.1 ile birebir gönderir (between dizi, in liste, sayı number); tablo biçimleri", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        // Kolon ekle (yan panel checkbox) ve sırayı değiştir (↓) — yapısal: her biri hemen önizlenir
        const p = await kolonPaneliAc();
        await tiklaVeBekle(byLabel<HTMLInputElement>("Açılış Tarihi", p));
        await tiklaVeBekle(byLabel<HTMLInputElement>("Maddi Tazminat", p));
        await tiklaVeBekle(byLabel<HTMLButtonElement>("Ofis No aşağı", p));
        expect(previewCagrilari()).toHaveLength(4);
        expect(sonPreviewGovdesi().tanim.kolonlar).toEqual(["subject", "tracking_no", "opening_date", "maddi_tazminat"]);
        await kolonPaneliKapat();

        // Durum in [Derdest, Karar] — checkbox'lı açılır, serbest metin yok
        await tiklaVeBekle(byLabel("Durum seç"));
        await tiklaVeBekle(byLabel("Durum: Derdest"));
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "eq", deger: "Derdest" }]);
        await tiklaVeBekle(byLabel("Durum: Karar"));
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "status", op: "in", deger: ["Derdest", "Karar"] }]);
        expect(previewCagrilari()).toHaveLength(6);

        // Açılış between: yazarken istek GİTMEZ, odak çıkışında gider
        yaz(byLabel<HTMLInputElement>("Açılış Tarihi başlangıç"), "2025-01-01");
        yaz(byLabel<HTMLInputElement>("Açılış Tarihi bitiş"), "2025-12-31");
        await bekle();
        expect(previewCagrilari()).toHaveLength(6);
        await odakCik(byLabel<HTMLInputElement>("Açılış Tarihi bitiş"));
        expect(previewCagrilari()).toHaveLength(7);

        // Maddi tazminat ≥ 1000 (sayı JSON number)
        yaz(byLabel<HTMLInputElement>("Maddi Tazminat en az"), "1000");
        await odakCik(byLabel<HTMLInputElement>("Maddi Tazminat en az"));
        expect(previewCagrilari()).toHaveLength(8);

        // Başlıktan sıralama: Açılış Tarihi → artan → azalan
        await tiklaVeBekle(byLabel("Açılış Tarihi sırala"));
        expect(sonPreviewGovdesi().tanim.siralama).toEqual([{ alan: "opening_date", yon: "asc" }]);
        await tiklaVeBekle(byLabel("Açılış Tarihi sırala"));
        expect(previewCagrilari()).toHaveLength(10);

        const [, opts] = previewCagrilari().at(-1)!;
        expect(opts!.method).toBe("POST");
        expect(sonPreviewGovdesi()).toEqual({
            tanim: {
                veri_kaynagi: "davalar",
                kolonlar: ["subject", "tracking_no", "opening_date", "maddi_tazminat"],
                filtreler: [
                    { alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] },
                    { alan: "status", op: "in", deger: ["Derdest", "Karar"] },
                    { alan: "maddi_tazminat", op: "gte", deger: 1000 },
                ],
                siralama: [{ alan: "opening_date", yon: "desc" }],
            },
            sayfa: 1,
            sayfa_boyu: 50,
        });
        expect($("th[aria-sort='descending']").textContent).toContain("Açılış Tarihi");

        // Tablo: başlık etiketle, tarih dd.MM.yyyy, para tr-TR, null "—"; toplam rozeti; etkin filtre çipleri
        const basliklar = Array.from(container.querySelectorAll("thead th button, thead th")).filter(e => e.tagName === "TH").map(th => th.textContent?.replace(/\d$/, ""));
        expect(basliklar).toEqual(["Ofis No", "Konu", "Açılış Tarihi", "Maddi Tazminat"]);
        expect(satirlar()).toEqual([
            ["2025/12", "Tazminat", "07.03.2025", "1.234,50"],
            ["2025/13", "—", "—", "—"],
        ]);
        expect($("[data-testid='toplam-rozeti']").textContent).toBe("120 kayıt · 4 kolon");
        expect(Array.from(container.querySelectorAll("[data-testid='filtre-cipi']")).map(c => c.getAttribute("data-alan")))
            .toEqual(["opening_date", "status", "maddi_tazminat"]);
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
    });

    it("yazarken tek istek gider: 600 ms gecikme, her tuşta yeniden başlar; süre dolunca son değerle contains", async () => {
        vi.useFakeTimers();
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        const konu = byLabel<HTMLInputElement>("Konu içerir");
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

    it("geçersiz tanımda istek gitmez: kolonlar temizlenince ipucu, kolon geri gelince hemen önizler; is_null değersiz gider", async () => {
        sunucuKur();
        await render();
        expect(previewCagrilari()).toHaveLength(1);

        let p = await kolonPaneliAc();
        await tiklaVeBekle(butonBul("Temizle", p)); // yan panel: kolon yok → geçersiz
        await kolonPaneliKapat();
        expect(previewCagrilari()).toHaveLength(1);
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (0)");
        // Son geçerli önizleme ekranda kalır, başlıkta "taslak eksik" ipucu; istek yok
        expect($("[data-testid='taslak-eksik']").textContent).toContain("en az bir kolon seçin");
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
        // Şerit değişikliği de geçersizken istek üretmez
        await tiklaVeBekle(byLabel("Açılış Tarihi boş olanlar"));
        expect(previewCagrilari()).toHaveLength(1);

        p = await kolonPaneliAc();
        await tiklaVeBekle(byLabel<HTMLInputElement>("Ofis No", p));
        await kolonPaneliKapat();
        expect(previewCagrilari()).toHaveLength(2);
        expect(container.querySelector("[data-testid='taslak-eksik']")).toBeNull();
        expect(sonPreviewGovdesi().tanim).toEqual({
            veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [{ alan: "opening_date", op: "is_null" }], siralama: [],
        });
        expect(byLabel<HTMLInputElement>("Açılış Tarihi başlangıç").disabled).toBe(true);
    });

    it("kart ile kaynak değişince eski kaynağın satırları ANINDA kaybolur, kolonlar/şerit yeni kaynağa döner, önizleme kendiliğinden yenilenir", async () => {
        sunucuKur();
        await render();
        expect(satirlar()).toHaveLength(2);
        yaz(byLabel<HTMLInputElement>("Konu içerir"), "x"); // bekleyen gecikmeli değişiklik

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
        tikla($("[data-kaynak='muvekkiller']"));
        await bekle(1);

        expect(seciliKaynak()).toBe("muvekkiller");
        expect(container.querySelector("tbody")).toBeNull();
        expect(container.textContent).not.toContain("2025/12");
        expect(container.textContent).toContain("Önizleme alınıyor");
        expect(kolonDugmesi().textContent?.trim()).toBe("Kolonlar (1)");
        expect(seritAlanlari()).toEqual(["il"]);
        expect(container.querySelector("[data-testid='filtre-cipi']")).toBeNull();
        // Yeni kaynak hemen istendi (bekleyen "x" filtresi eski kaynakla gitmedi)
        expect(previewCagrilari()).toHaveLength(2);
        expect(sonPreviewGovdesi().tanim).toEqual({ veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [], siralama: [] });

        await act(async () => { coz!(); });
        await bekle();
        expect(satirlar()).toEqual([["Ayşe Yılmaz"]]);
        expect($("[data-testid='toplam-rozeti']").textContent).toBe("1 kayıt · 1 kolon");
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
        vi.useFakeTimers();
        sunucuKur();
        await render();
        expect(container.textContent).toContain("1 / 3");

        // Taslağı yazarak değiştir (600 ms bekliyor) — sayfa değişimi yine önizlenen tanımla gitmeli
        yaz(byLabel<HTMLInputElement>("Konu içerir"), "Taz");
        await tiklaVeBekle(butonBul("İleri"));
        expect(previewCagrilari()).toHaveLength(2);
        const govde = sonPreviewGovdesi();
        expect(govde.sayfa).toBe(2);
        expect(govde.tanim).toEqual(VARSAYILAN_TANIM);
        expect(container.textContent).toContain("2 / 3");
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
        expect(container.querySelector("[data-kaynak]")).toBeNull();
        expect(previewCagrilari()).toHaveLength(0);

        sunucuKur();
        await tiklaVeBekle(butonBul("Tekrar dene"));
        expect(seciliKaynak()).toBe("davalar");
        expect(previewCagrilari()).toHaveLength(1);
    });

    it("yerleşim: kartlar → şerit → araç çubuğu → tablo; sol sütun yok; kök mx-auto/max-w ile daraltılmaz; dar ekranda kartlar ve tablo kendi içinde kaydırır", async () => {
        sunucuKur();
        await render();
        const kok = container.firstElementChild as HTMLElement;
        expect(kok.className).not.toContain("mx-auto");
        expect(kok.className).not.toMatch(/max-w-/);
        expect(container.innerHTML).not.toContain("xl:grid-cols-[320px_1fr]");

        const kartlar = $("[data-testid='kaynak-kartlari']");
        const serit = $("[data-testid='filtre-seridi']");
        const cubuk = $("[data-testid='arac-cubugu']");
        const tablo = $("table");
        const onceGelir = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        expect(onceGelir(kartlar, serit)).toBe(true);
        expect(onceGelir(serit, cubuk)).toBe(true);
        expect(onceGelir(cubuk, tablo)).toBe(true);

        // Araç çubuğu: sol kolon düğmesi + şablon, sağ indirme (+ asistan anahtarla)
        expect(cubuk.querySelector("[data-testid='kolon-dugmesi']")).not.toBeNull();
        expect(cubuk.querySelector("#rapor-sablon")).not.toBeNull();
        expect(Array.from(cubuk.querySelectorAll("button")).map(b => b.textContent?.trim())).toEqual(
            expect.arrayContaining(["Excel indir", "CSV indir"]),
        );

        // Responsive: kartlar yatay kaydırır (lg altı), tablo kendi sarmalayıcısında kaydırır
        expect(kartlar.className).toContain("overflow-x-auto");
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
        expect(container.querySelector("[data-testid='kaynak-kartlari']")).not.toBeNull();
        expect(container.querySelector("[data-testid='anasayfa']")).toBeNull();

        act(() => root!.unmount());
        root = null;
        const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
        adminMock.value = false;
        await render(agac, "/reports");
        expect(container.querySelector("[data-testid='anasayfa']")).not.toBeNull();
        expect(container.querySelector("[data-testid='kaynak-kartlari']")).toBeNull();
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
