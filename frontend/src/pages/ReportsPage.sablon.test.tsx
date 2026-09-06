// @vitest-environment jsdom
// ReportsPage (G134) — şablonlar, Excel/CSV indirme ve İndirme geçmişi sekmesi: şablon kaydetme
// gövdesi + listede görünme; başkasının şablonunda Güncelle/Sil yok + paylaşımlı rozeti; export
// gövdesi §2.4 birebir + dosya adı Content-Disposition'dan; 413 mesajı; geçmiş satırları +
// dosya_mevcut=false pasif + 410; "Tanımı yükle" oluşturucu state'ini tümüyle değiştirir; ?tab=.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

// Onay diyaloğu: provider yerine context varsayılanı — her çağrı kaydedilir, cevap ayarlanabilir.
const confirmMock = vi.hoisted(() => ({ fn: vi.fn(async (_opts: unknown) => true) }));
vi.mock("@/hooks/useConfirm", async () => {
    const React = await import("react");
    return {
        ConfirmContext: React.createContext({ confirm: (opts: unknown) => confirmMock.fn(opts) }),
        useConfirm: () => confirmMock.fn,
    };
});

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

import ReportsPage from "./ReportsPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Radix Switch (diyalogdaki "Paylaşımlı") useSize ile ResizeObserver ister; jsdom'da yok.
class ResizeObserverStub {
    observe() { /* jsdom */ }
    unobserve() { /* jsdom */ }
    disconnect() { /* jsdom */ }
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;

const KATALOG = {
    veri_kaynaklari: [
        {
            anahtar: "davalar",
            etiket: "Davalar",
            aciklama: "Dava kartları",
            varsayilan_kolonlar: ["tracking_no", "subject"],
            kolonlar: [
                { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
                { anahtar: "subject", etiket: "Konu", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
                { anahtar: "status", etiket: "Durum", tip: "liste", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: ["Derdest", "Karar"] },
                { anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
            ],
        },
        {
            anahtar: "muvekkiller",
            etiket: "Müvekkiller",
            aciklama: "",
            varsayilan_kolonlar: ["name"],
            kolonlar: [
                { anahtar: "name", etiket: "Ad", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
                { anahtar: "city", etiket: "Şehir", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
            ],
        },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
};

const ONIZLEME = {
    kolonlar: [
        { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" },
        { anahtar: "subject", etiket: "Konu", tip: "metin" },
    ],
    satirlar: [{ tracking_no: "2025/12", subject: "Tazminat" }],
    toplam: 3,
    sayfa: 1,
    sayfa_boyu: 50,
};

const KENDI_SABLON = {
    id: 1, ad: "Benim şablonum", aciklama: "Derdest davalar", paylasimli: false,
    olusturan: "admin@lexis.com.tr",
    tanim: { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "status"], filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }], siralama: [{ alan: "opening_date", yon: "desc" }] },
    created_at: "2026-09-06T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
};
const BASKASININ_SABLONU = {
    id: 2, ad: "Ortak müvekkil listesi", aciklama: null, paylasimli: true,
    olusturan: "baskasi@lexis.com.tr",
    tanim: { veri_kaynagi: "muvekkiller", kolonlar: ["name", "city"], filtreler: [{ alan: "city", op: "contains", deger: "İstanbul" }], siralama: [] },
    created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z",
};

const KOSU_MEVCUT = {
    id: 11, sablon_id: 1, sablon_adi: "Benim şablonum", format: "xlsx", kaynak: "manuel", veri_kaynagi: "davalar",
    kolon_sayisi: 2, satir_sayisi: 1234, kullanici: "admin@lexis.com.tr", baslangic: "2026-09-06T08:30:00Z", sure_ms: 800,
    dosya_adi: "hukdok-rapor-davalar-20260906-1130.xlsx", dosya_boyutu: 12600, sha256: null, dosya_mevcut: true,
    tanim: KENDI_SABLON.tanim,
};
const KOSU_SILINMIS = {
    id: 10, sablon_id: null, sablon_adi: null, format: "csv", kaynak: "asistan", veri_kaynagi: "muvekkiller",
    kolon_sayisi: 2, satir_sayisi: 7, kullanici: "baskasi@lexis.com.tr", baslangic: "2026-08-01T08:30:00Z", sure_ms: null,
    dosya_adi: "hukdok-rapor-muvekkiller-20260801-1130.csv", dosya_boyutu: null, sha256: null, dosya_mevcut: false,
    tanim: BASKASININ_SABLONU.tanim,
};

const okJson = (payload: unknown, status = 200) => ({ ok: true, status, json: async () => payload });
const failJson = (status: number, payload: unknown) => ({ ok: false, status, json: async () => payload });
const okBlob = (headers: Record<string, string>) => ({
    ok: true,
    status: 200,
    headers: { get: (k: string) => headers[k] ?? null },
    blob: async () => new Blob(["x"]),
});

type Cagri = [string, RequestInit | undefined];
const cagrilar = (url: string, method?: string) =>
    (fetchMock.mock.calls as Cagri[]).filter(([u, o]) => u === url && (!method || (o?.method ?? "GET") === method));
const govde = (c: Cagri) => JSON.parse(c[1]!.body as string);

/** URL'yi gözlemleyen yardımcı — sekme değişimi `?tab=`'a yazılıyor mu? */
let sonKonum = "";
function KonumGozcusu() {
    const loc = useLocation();
    sonKonum = loc.pathname + loc.search;
    return null;
}

describe("ReportsPage şablon / indirme / geçmiş (G134)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let indirmeler: string[];

    beforeEach(() => {
        fetchMock.mockReset();
        toastMocks.success.mockReset();
        toastMocks.error.mockReset();
        confirmMock.fn.mockReset();
        confirmMock.fn.mockResolvedValue(true);
        indirmeler = [];
        (URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => "blob:sahte");
        (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
        vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
            indirmeler.push(this.download);
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
        vi.restoreAllMocks();
    });

    type SunucuAyari = {
        sablonlar?: unknown[];
        exportCevabi?: () => unknown;
        indirmeCevabi?: () => unknown;
    };

    function sunucuKur(ayar: SunucuAyari = {}) {
        const sablonlar = [...(ayar.sablonlar ?? [KENDI_SABLON, BASKASININ_SABLONU])];
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            const method = opts?.method ?? "GET";
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const g = JSON.parse(opts!.body as string);
                return okJson({ ...ONIZLEME, sayfa: g.sayfa, sayfa_boyu: g.sayfa_boyu });
            }
            // Kopya: gerçek sunucu JSON serileştirir, dizi referansı paylaşılmaz
            if (url === "/api/reports/templates" && method === "GET") return okJson([...sablonlar]);
            if (url === "/api/reports/templates" && method === "POST") {
                const g = JSON.parse(opts!.body as string);
                const yeni = { ...g, id: 99, olusturan: "admin@lexis.com.tr", created_at: "2026-09-06T12:00:00Z", updated_at: "2026-09-06T12:00:00Z" };
                sablonlar.unshift(yeni);
                return okJson(yeni, 201);
            }
            if (url === "/api/reports/export") {
                return ayar.exportCevabi
                    ? ayar.exportCevabi()
                    : okBlob({ "Content-Disposition": 'attachment; filename="hukdok-rapor-davalar-20260906-1405.xlsx"', "X-Rapor-Kosu-Id": "42" });
            }
            if (url.startsWith("/api/reports/runs?")) {
                return okJson({ toplam: 2, kosular: [KOSU_MEVCUT, KOSU_SILINMIS] });
            }
            if (/^\/api\/reports\/runs\/\d+\/download$/.test(url)) {
                return ayar.indirmeCevabi
                    ? ayar.indirmeCevabi()
                    : okBlob({ "Content-Disposition": 'attachment; filename="saklanan.xlsx"' });
            }
            throw new Error("beklenmeyen uç: " + method + " " + url);
        });
    }

    async function render(url = "/reports") {
        root = createRoot(container);
        await act(async () => {
            root!.render(
                <MemoryRouter initialEntries={[url]}>
                    <KonumGozcusu />
                    <ReportsPage />
                </MemoryRouter>,
            );
        });
        await act(async () => { await Promise.resolve(); });
        await act(async () => { await Promise.resolve(); });
    }

    const $ = <T extends Element>(sel: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    const butonBul = (metin: string, kok: ParentNode = container): HTMLButtonElement => {
        const b = Array.from(kok.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };
    const butonVar = (metin: string, kok: ParentNode = container) =>
        Array.from(kok.querySelectorAll("button")).some(x => x.textContent?.trim() === metin);
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };

    function sec(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }
    function yaz(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }
    async function tikla(el: Element) {
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        await act(async () => { await Promise.resolve(); });
        await act(async () => { await Promise.resolve(); });
    }
    /** Radix Tabs tetikleyicisi mousedown ile etkinleşir. */
    async function sekme(metin: string) {
        const t = Array.from(container.querySelectorAll("[role='tab']")).find(x => x.textContent?.trim() === metin);
        if (!t) throw new Error("sekme bulunamadı: " + metin);
        await act(async () => {
            t.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
        });
        await act(async () => { await Promise.resolve(); });
        await act(async () => { await Promise.resolve(); });
    }
    const aktifSekme = () => container.querySelector("[role='tab'][data-state='active']")?.textContent?.trim();
    const seciliKolonlar = () => Array.from(container.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));

    it("şablon kaydetme: diyalog gövdesi {ad, aciklama, tanim, paylasimli} gider; şablon seçimde ve listede görünür", async () => {
        sunucuKur();
        await render();

        // Şablonlar katalogdan SONRA istenir (G133 sözleşmesi: ilk istek katalog)
        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        expect(cagrilar("/api/reports/templates", "GET")).toHaveLength(1);

        await tikla(butonBul("Kaydet"));
        const ad = $<HTMLInputElement>("#sablon-ad", document.body);
        // Ad boşken Kaydet kapalı
        const kaydetDugmesi = butonBul("Kaydet", $("form", document.body));
        expect(kaydetDugmesi.disabled).toBe(true);
        yaz(ad, "  Yeni rapor  ");
        yaz($<HTMLTextAreaElement>("#sablon-aciklama", document.body), "açıklama");
        await tikla($("#sablon-paylasimli", document.body));
        expect(kaydetDugmesi.disabled).toBe(false);
        await tikla(kaydetDugmesi);

        const post = cagrilar("/api/reports/templates", "POST");
        expect(post).toHaveLength(1);
        const g = govde(post[0]);
        expect(Object.keys(g).sort()).toEqual(["aciklama", "ad", "paylasimli", "tanim"]);
        expect(g.ad).toBe("Yeni rapor");
        expect(g.aciklama).toBe("açıklama");
        expect(g.paylasimli).toBe(true);
        expect(g.tanim).toEqual({ veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] });

        // Diyalog kapandı, yeni şablon seçili ve seçenekte
        expect(document.body.querySelector("#sablon-ad")).toBeNull();
        const secim = $<HTMLSelectElement>("#rapor-sablon");
        expect(secim.value).toBe("99");
        expect(Array.from(secim.options).map(o => o.textContent)).toContain("Yeni rapor");
        expect(toastMocks.success).toHaveBeenCalledWith("Şablon kaydedildi: Yeni rapor");

        // Şablonlar sekmesinde tablo satırı
        await sekme("Şablonlar");
        const satirlar = Array.from(container.querySelectorAll("[data-testid='sablon-satiri']"));
        expect(satirlar.map(s => s.getAttribute("data-sablon-id"))).toEqual(["99", "1", "2"]);
        expect(satirlar[0].textContent).toContain("Yeni rapor");
        expect(satirlar[0].textContent).toContain("Siz");
    });

    it("başkasının paylaşımlı şablonunda Güncelle/Sil yok, sahibi rozeti görünür; kendi şablonunda var", async () => {
        sunucuKur();
        await render();
        const secim = $<HTMLSelectElement>("#rapor-sablon");
        expect(Array.from(secim.options).map(o => o.textContent)).toEqual([
            "Şablon seçiniz", "Benim şablonum", "Ortak müvekkil listesi · baskasi@lexis.com.tr",
        ]);

        sec(secim, "2");
        expect(butonVar("Güncelle")).toBe(false);
        expect(butonVar("Sil")).toBe(false);
        expect($("[data-testid='paylasimli-rozeti']").textContent).toContain("baskasi@lexis.com.tr");

        sec(secim, "1");
        expect(butonVar("Güncelle")).toBe(true);
        expect(butonVar("Sil")).toBe(true);
        expect(container.querySelector("[data-testid='paylasimli-rozeti']")).toBeNull();

        // Tablo: başkasının satırında düzenle/sil yok, yükle var
        await sekme("Şablonlar");
        const satirlar = Array.from(container.querySelectorAll("[data-testid='sablon-satiri']"));
        const baskasi = satirlar.find(s => s.getAttribute("data-sablon-id") === "2")!;
        expect(baskasi.querySelector("[aria-label='Ortak müvekkil listesi yükle']")).not.toBeNull();
        expect(baskasi.querySelector("[aria-label='Ortak müvekkil listesi düzenle']")).toBeNull();
        expect(baskasi.querySelector("[aria-label='Ortak müvekkil listesi sil']")).toBeNull();
        expect(baskasi.textContent).toContain("baskasi@lexis.com.tr");
        const kendi = satirlar.find(s => s.getAttribute("data-sablon-id") === "1")!;
        expect(kendi.querySelector("[aria-label='Benim şablonum düzenle']")).not.toBeNull();
        expect(kendi.querySelector("[aria-label='Benim şablonum sil']")).not.toBeNull();
    });

    it("Excel indir: gövde {tanim, format:xlsx, sablon_id:null, kaynak:manuel}; <a download> adı Content-Disposition'dan", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));

        const exp = cagrilar("/api/reports/export", "POST");
        expect(exp).toHaveLength(1);
        expect(govde(exp[0])).toEqual({
            tanim: { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] },
            format: "xlsx",
            sablon_id: null,
            kaynak: "manuel",
        });
        expect(indirmeler).toEqual(["hukdok-rapor-davalar-20260906-1405.xlsx"]);
        expect(toastMocks.success).toHaveBeenCalledWith("İndirildi: hukdok-rapor-davalar-20260906-1405.xlsx");
    });

    it("CSV indir yüklü şablonla: sablon_id yazılır, format csv; toast satır sayısını önizlemeden alır", async () => {
        sunucuKur();
        await render();
        const secim = $<HTMLSelectElement>("#rapor-sablon");
        sec(secim, "1");
        await tikla(butonBul("Yükle"));
        expect(seciliKolonlar()).toEqual(["tracking_no", "status"]);
        await tikla(butonBul("Önizle"));
        await tikla(butonBul("CSV indir"));

        const g = govde(cagrilar("/api/reports/export", "POST")[0]);
        expect(g.format).toBe("csv");
        expect(g.sablon_id).toBe(1);
        expect(g.kaynak).toBe("manuel");
        expect(g.tanim).toEqual(KENDI_SABLON.tanim);
        expect(toastMocks.success).toHaveBeenLastCalledWith("İndirildi: hukdok-rapor-davalar-20260906-1405.xlsx · 3 satır");
    });

    it("413 satır limiti: tavan mesajı + filtre daraltma önerisi; dosya indirilmez", async () => {
        sunucuKur({ exportCevabi: () => failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }) });
        await render();
        await tikla(butonBul("Excel indir"));
        expect(indirmeler).toEqual([]);
        expect(toastMocks.error).toHaveBeenCalledTimes(1);
        const [baslik, secenek] = toastMocks.error.mock.calls[0] as [string, { description: string }];
        expect(baslik).toContain("tavan");
        expect(secenek.description).toContain("120.000");
        expect(secenek.description).toContain("50.000");
        expect(secenek.description).toContain("Filtre daraltın");
    });

    it("İndirme geçmişi: satırlar kullanıcı/zaman/format/satır/dosya durumu; dosya_mevcut=false düğmesi pasif + ipucu; İndir dosya adı başlıktan", async () => {
        sunucuKur();
        await render();
        expect(cagrilar("/api/reports/runs?limit=50&offset=0")).toHaveLength(0);
        await sekme("İndirme geçmişi");
        expect(cagrilar("/api/reports/runs?limit=50&offset=0")).toHaveLength(1);
        expect(sonKonum).toBe("/reports?tab=gecmis");

        const satirlar = Array.from(container.querySelectorAll("[data-testid='kosu-satiri']"));
        expect(satirlar.map(s => s.getAttribute("data-kosu-id"))).toEqual(["11", "10"]);
        const mevcut = satirlar[0];
        expect(mevcut.textContent).toContain("admin@lexis.com.tr");
        expect(mevcut.textContent).toMatch(/\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}/);
        expect(mevcut.textContent).toContain("Excel");
        expect(mevcut.textContent).toContain("1.234");
        expect(mevcut.textContent).toContain("Benim şablonum");
        expect(mevcut.textContent).toContain("12,3 KB");
        expect(mevcut.querySelector("[data-testid='kaynak-rozeti']")!.textContent).toBe("Manuel");
        expect(byLabel<HTMLButtonElement>("Koşu 11 indir", mevcut).disabled).toBe(false);

        const silinmis = satirlar[1];
        expect(silinmis.textContent).toContain("CSV");
        expect(silinmis.textContent).toContain("—"); // şablon adı yok
        expect(silinmis.querySelector("[data-testid='kaynak-rozeti']")!.textContent).toBe("Asistan");
        expect(silinmis.querySelector("[data-testid='dosya-yok']")).not.toBeNull();
        const pasif = byLabel<HTMLButtonElement>("Koşu 10 indir", silinmis);
        expect(pasif.disabled).toBe(true);
        expect(pasif.title).toContain("Saklama süresi doldu");
        expect($("[data-testid='kosu-toplam-rozeti']").textContent).toContain("2");

        await tikla(byLabel("Koşu 11 indir", mevcut));
        expect(cagrilar("/api/reports/runs/11/download")).toHaveLength(1);
        expect(indirmeler).toEqual(["saklanan.xlsx"]);
        expect(toastMocks.success).toHaveBeenCalledWith("İndirildi: saklanan.xlsx");
    });

    it("410: saklama süresi dolmuş mesajı, satır pasifleşir; liste hatası boş liste değil", async () => {
        sunucuKur({ indirmeCevabi: () => failJson(410, { detail: "gone" }) });
        await render("/reports?tab=gecmis");
        expect(aktifSekme()).toBe("İndirme geçmişi");
        await tikla(byLabel("Koşu 11 indir"));
        expect(indirmeler).toEqual([]);
        const [, secenek] = toastMocks.error.mock.calls[0] as [string, { description: string }];
        expect(secenek.description).toContain("saklama süresi dolmuş");
        expect(byLabel<HTMLButtonElement>("Koşu 11 indir").disabled).toBe(true);
    });

    it("geçmiş listesi hatası DataErrorBanner (boş liste DEĞİL) + Tekrar dene", async () => {
        sunucuKur();
        await render();
        // Sıradaki istek (koşu listesi) 503 döner
        fetchMock.mockImplementationOnce(async () => failJson(503, { detail: "bakım" }));
        await sekme("İndirme geçmişi");
        expect($("[role='alert']").textContent).toContain("bakım");
        expect(container.querySelector("[data-testid='kosu-satiri']")).toBeNull();
        expect(container.textContent).not.toContain("Henüz indirme yok");

        sunucuKur();
        await tikla(butonBul("Tekrar dene"));
        expect(container.querySelectorAll("[data-testid='kosu-satiri']")).toHaveLength(2);
    });

    it("\"Tanımı yükle\": oluşturucu state'i tümüyle değişir (kaynak, kolonlar, filtre), Rapor sekmesine geçer; kaynak değişimi onay ister", async () => {
        sunucuKur();
        await render("/reports?tab=gecmis");
        // Koşu 10 muvekkiller kaynağı — mevcut taslak davalar → onay
        await tikla(byLabel("Koşu 10 tanımını yükle"));
        expect(confirmMock.fn).toHaveBeenCalledTimes(1);
        expect((confirmMock.fn.mock.calls[0] as unknown as [{ tone: string }])[0].tone).toBe("warning");
        expect(aktifSekme()).toBe("Rapor");
        expect(sonKonum).toBe("/reports");

        expect($<HTMLSelectElement>("#rapor-kaynak").value).toBe("muvekkiller");
        expect(seciliKolonlar()).toEqual(["name", "city"]);
        const filtreler = container.querySelectorAll("[data-testid='filtre-satiri']");
        expect(filtreler).toHaveLength(1);
        expect(byLabel<HTMLSelectElement>("Alan", filtreler[0]).value).toBe("city");
        expect(byLabel<HTMLSelectElement>("Operatör", filtreler[0]).value).toBe("contains");
        // Koşunun şablonu yok → seçim boş
        expect($<HTMLSelectElement>("#rapor-sablon").value).toBe("");

        // Önizle bu tanımla gider (state gerçekten değişti)
        await tikla(butonBul("Önizle"));
        expect(govde(cagrilar("/api/reports/preview", "POST")[0]).tanim).toEqual(BASKASININ_SABLONU.tanim);
    });

    it("şablon yükleme: onay reddedilirse state değişmez; aynı kaynakta onay sorulmaz", async () => {
        sunucuKur();
        await render();
        const secim = $<HTMLSelectElement>("#rapor-sablon");
        sec(secim, "2");
        confirmMock.fn.mockResolvedValueOnce(false);
        await tikla(butonBul("Yükle"));
        expect(confirmMock.fn).toHaveBeenCalledTimes(1);
        expect($<HTMLSelectElement>("#rapor-kaynak").value).toBe("davalar");
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);

        sec(secim, "1");
        await tikla(butonBul("Yükle"));
        expect(confirmMock.fn).toHaveBeenCalledTimes(1); // aynı kaynak → sorulmadı
        expect(seciliKolonlar()).toEqual(["tracking_no", "status"]);
        expect(container.querySelectorAll("[data-testid='siralama-satiri']")).toHaveLength(1);
        expect(toastMocks.success).toHaveBeenCalledWith("Şablon yüklendi: Benim şablonum");
    });

    it("Sil: onay sonrası DELETE /templates/{id}, listeden düşer, seçim temizlenir", async () => {
        sunucuKur();
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/templates/1" && opts?.method === "DELETE") return { ok: true, status: 204 };
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/templates") return okJson([KENDI_SABLON, BASKASININ_SABLONU]);
            throw new Error("beklenmeyen uç: " + url);
        });
        await render();
        const secim = $<HTMLSelectElement>("#rapor-sablon");
        sec(secim, "1");
        await tikla(butonBul("Sil"));
        expect((confirmMock.fn.mock.calls[0] as unknown as [{ tone: string }])[0].tone).toBe("destructive");
        expect(cagrilar("/api/reports/templates/1", "DELETE")).toHaveLength(1);
        expect(Array.from(secim.options).map(o => o.value)).toEqual(["", "2"]);
        expect(secim.value).toBe("");
        expect(toastMocks.success).toHaveBeenCalledWith("Şablon silindi: Benim şablonum");
    });

    it("Güncelle (çubuk): seçili şablonun tanımı taslakla PUT edilir (künye aynı)", async () => {
        sunucuKur();
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/templates/1" && opts?.method === "PUT") {
                return okJson({ ...KENDI_SABLON, ...JSON.parse(opts.body as string), updated_at: "2026-09-06T13:00:00Z" });
            }
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/templates") return okJson([KENDI_SABLON, BASKASININ_SABLONU]);
            throw new Error("beklenmeyen uç: " + url);
        });
        await render();
        sec($<HTMLSelectElement>("#rapor-sablon"), "1");
        await tikla(butonBul("Güncelle"));
        const put = cagrilar("/api/reports/templates/1", "PUT");
        expect(put).toHaveLength(1);
        expect(govde(put[0])).toEqual({
            ad: "Benim şablonum", aciklama: "Derdest davalar", paylasimli: false,
            tanim: { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] },
        });
        expect(toastMocks.success).toHaveBeenCalledWith("Şablon güncellendi: Benim şablonum");
    });

    it("?tab=sablonlar ile açılır; geçersiz ?tab= Rapor'a düşer", async () => {
        sunucuKur();
        await render("/reports?tab=sablonlar");
        expect(aktifSekme()).toBe("Şablonlar");
        expect(container.querySelectorAll("[data-testid='sablon-satiri']")).toHaveLength(2);
        act(() => root!.unmount());
        root = null;

        await render("/reports?tab=xyz");
        expect(aktifSekme()).toBe("Rapor");
    });
});
