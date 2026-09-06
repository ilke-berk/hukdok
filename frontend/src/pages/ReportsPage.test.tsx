// @vitest-environment jsdom
// ReportsPage (G133) — Rapor Oluşturucu + önizleme tablosunun sözleşmeye bağlanışı:
// katalog yüklenir, kolon/filtre/sıralama seçimi plan §2.1 gövdesiyle /api/reports/preview'a
// gider, 422 okunur mesaja döner, ağ hatası boş listeye DÖNMEZ (DataErrorBanner), sayfa
// değişimi `sayfa` gönderir; /reports yalnız yöneticiye açılır, Sidebar "Raporlar" yalnız yöneticide.
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

import ReportsPage from "./ReportsPage";
import { ProtectedAdminRoute } from "@/components/ProtectedAdminRoute";
import { Sidebar } from "@/components/shell/Sidebar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
                { anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
                { anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", filtrelenebilir: false, siralanabilir: false, turetilmis: true, secenekler: null },
            ],
        },
        {
            anahtar: "muvekkiller",
            etiket: "Müvekkiller",
            aciklama: "",
            varsayilan_kolonlar: ["name"],
            kolonlar: [
                { anahtar: "name", etiket: "Ad", tip: "metin", filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null },
            ],
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

describe("ReportsPage (G133)", () => {
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
    });

    /** Varsayılan sunucu: katalog + önizleme; sayfa numarası gövdeden yankılanır. */
    function sunucuKur(onizleme: unknown = ONIZLEME) {
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const govde = JSON.parse(opts!.body as string);
                return okJson({ ...(onizleme as object), sayfa: govde.sayfa, sayfa_boyu: govde.sayfa_boyu });
            }
            throw new Error("beklenmeyen uç: " + url);
        });
    }

    async function render(element: React.ReactNode = <ReportsPage />, url = "/reports") {
        root = createRoot(container);
        await act(async () => {
            root!.render(<MemoryRouter initialEntries={[url]}>{element}</MemoryRouter>);
        });
        // katalog promise'i çözülsün
        await act(async () => { await Promise.resolve(); });
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
    const butonBul = (metin: string): HTMLButtonElement => {
        const b = Array.from(container.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };

    /** React controlled select'e kullanıcı seçimi: prototip setter + change (value tracker aşımı). */
    function sec(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }
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
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        await act(async () => { await Promise.resolve(); });
    }

    it("katalog yüklenir: kaynaklar listelenir, varsayılan kolonlar seçili gelir", async () => {
        sunucuKur();
        await render();

        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        const kaynak = $<HTMLSelectElement>("#rapor-kaynak");
        expect(Array.from(kaynak.options).map(o => o.textContent)).toEqual(["Davalar", "Müvekkiller"]);
        expect(kaynak.value).toBe("davalar");

        const secili = Array.from(container.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));
        expect(secili).toEqual(["tracking_no", "subject"]);
        // Önizle açık (kolon var), henüz istek yok
        expect(butonBul("Önizle").disabled).toBe(false);
        expect(previewCagrilari()).toHaveLength(0);
    });

    it("kolon seçimi + filtre + sıralama gövdeyi §2.1 ile birebir gönderir (between dizi, in liste)", async () => {
        sunucuKur();
        await render();

        // Kolon ekle (checkbox) ve sırayı değiştir (↓ düğmesi)
        tikla(byLabel<HTMLInputElement>("Açılış Tarihi"));
        tikla(byLabel<HTMLInputElement>("Maddi Tazminat"));
        tikla(byLabel<HTMLButtonElement>("Ofis No aşağı"));

        // Filtre 1: Durum in [Derdest, Karar]
        tikla(butonBul("Filtre ekle"));
        let satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        sec(byLabel<HTMLSelectElement>("Alan", satirlar[0]), "status");
        sec(byLabel<HTMLSelectElement>("Operatör", satirlar[0]), "in");
        satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        const cipler = Array.from(satirlar[0].querySelectorAll("[aria-pressed]")) as HTMLButtonElement[];
        expect(cipler.map(c => c.textContent)).toEqual(["Derdest", "Karar"]);
        tikla(cipler[0]);
        tikla(cipler[1]);

        // Filtre 2: Açılış between
        tikla(butonBul("Filtre ekle"));
        satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        sec(byLabel<HTMLSelectElement>("Alan", satirlar[1]), "opening_date");
        sec(byLabel<HTMLSelectElement>("Operatör", satirlar[1]), "between");
        satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        // Tek uç doluyken Önizle KAPALI
        yaz(byLabel<HTMLInputElement>("Başlangıç", satirlar[1]), "2025-01-01");
        expect(butonBul("Önizle").disabled).toBe(true);
        yaz(byLabel<HTMLInputElement>("Bitiş", satirlar[1]), "2025-12-31");

        // Filtre 3: Maddi tazminat ≥ 1000 (sayı JSON number)
        tikla(butonBul("Filtre ekle"));
        satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        sec(byLabel<HTMLSelectElement>("Alan", satirlar[2]), "maddi_tazminat");
        sec(byLabel<HTMLSelectElement>("Operatör", satirlar[2]), "gte");
        satirlar = container.querySelectorAll("[data-testid='filtre-satiri']");
        yaz(byLabel<HTMLInputElement>("Değer", satirlar[2]), "1000");

        // Sıralama: Açılış azalan
        tikla(butonBul("Sıralama ekle"));
        sec(byLabel<HTMLSelectElement>("Sıralama alanı 1"), "opening_date");
        sec(byLabel<HTMLSelectElement>("Sıralama yönü 1"), "desc");

        expect(butonBul("Önizle").disabled).toBe(false);
        await tiklaVeBekle(butonBul("Önizle"));

        expect(previewCagrilari()).toHaveLength(1);
        const [, opts] = previewCagrilari()[0];
        expect(opts!.method).toBe("POST");
        expect(sonPreviewGovdesi()).toEqual({
            tanim: {
                veri_kaynagi: "davalar",
                kolonlar: ["subject", "tracking_no", "opening_date", "maddi_tazminat"],
                filtreler: [
                    { alan: "status", op: "in", deger: ["Derdest", "Karar"] },
                    { alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] },
                    { alan: "maddi_tazminat", op: "gte", deger: 1000 },
                ],
                siralama: [{ alan: "opening_date", yon: "desc" }],
            },
            sayfa: 1,
            sayfa_boyu: 50,
        });

        // Tablo: başlık etiketle, tarih dd.MM.yyyy, para tr-TR, null "—"; toplam rozeti
        const basliklar = Array.from(container.querySelectorAll("thead th")).map(th => th.textContent);
        expect(basliklar).toEqual(["Ofis No", "Konu", "Açılış Tarihi", "Maddi Tazminat"]);
        const hucreler = Array.from(container.querySelectorAll("tbody tr")).map(tr =>
            Array.from(tr.querySelectorAll("td")).map(td => td.textContent));
        expect(hucreler).toEqual([
            ["2025/12", "Tazminat", "07.03.2025", "1.234,50"],
            ["2025/13", "—", "—", "—"],
        ]);
        expect($("[data-testid='toplam-rozeti']").textContent).toBe("Toplam 120 kayıt");
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
    });

    it("filtre alanında türetilmiş kolon YOK; op listesi kolon tipine göre §2.2'yi aşmaz", async () => {
        sunucuKur();
        await render();
        tikla(butonBul("Filtre ekle"));
        const satir = $("[data-testid='filtre-satiri']");
        const alanlar = Array.from(byLabel<HTMLSelectElement>("Alan", satir).options).map(o => o.value).filter(Boolean);
        expect(alanlar).toEqual(["tracking_no", "subject", "status", "opening_date", "maddi_tazminat"]);
        expect(alanlar).not.toContain("muvekkil_adlari");

        const oplar = () => Array.from(byLabel<HTMLSelectElement>("Operatör", $("[data-testid='filtre-satiri']")).options).map(o => o.value);
        sec(byLabel<HTMLSelectElement>("Alan", satir), "status");
        expect(oplar()).toEqual(["eq", "ne", "in", "is_null", "not_null"]);
        sec(byLabel<HTMLSelectElement>("Alan", $("[data-testid='filtre-satiri']")), "opening_date");
        expect(oplar()).toEqual(["eq", "gte", "lte", "between", "is_null", "not_null"]);
        sec(byLabel<HTMLSelectElement>("Alan", $("[data-testid='filtre-satiri']")), "tracking_no");
        expect(oplar()).toEqual(["eq", "ne", "contains", "in", "is_null", "not_null"]);

        // Sıralama alanında da türetilmiş yok
        tikla(butonBul("Sıralama ekle"));
        const siraAlanlari = Array.from(byLabel<HTMLSelectElement>("Sıralama alanı 1").options).map(o => o.value).filter(Boolean);
        expect(siraAlanlari).not.toContain("muvekkil_adlari");
    });

    it("is_null değer istemez ve gövdede `deger` anahtarı taşımaz; kolon yokken Önizle kapalı", async () => {
        sunucuKur();
        await render();
        tikla(butonBul("Filtre ekle"));
        sec(byLabel<HTMLSelectElement>("Alan", $("[data-testid='filtre-satiri']")), "opening_date");
        sec(byLabel<HTMLSelectElement>("Operatör", $("[data-testid='filtre-satiri']")), "is_null");
        expect(container.querySelector("[data-testid='filtre-satiri'] input")).toBeNull();
        expect(butonBul("Önizle").disabled).toBe(false);

        await tiklaVeBekle(butonBul("Önizle"));
        expect(sonPreviewGovdesi().tanim.filtreler).toEqual([{ alan: "opening_date", op: "is_null" }]);

        tikla(butonBul("Temizle"));
        expect(butonBul("Önizle").disabled).toBe(true);
        // Tanım değişti → bayat rozeti
        expect(container.querySelector("[data-testid='bayat-rozeti']")).not.toBeNull();
    });

    it("422 detail.alan/sebep kullanıcıya okunur mesaj olarak gösterilir", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            return failJson(422, { detail: { alan: "filtreler[0].op", sebep: "liste tipinde contains izinli değil" } });
        });
        await render();
        await tiklaVeBekle(butonBul("Önizle"));

        const uyari = $("[role='alert']");
        expect(uyari.textContent).toContain("Geçersiz rapor tanımı: filtreler[0].op — liste tipinde contains izinli değil");
        expect(container.querySelector("table")).toBeNull();
    });

    it("ağ hatasında tablo boş listeye DÖNMEZ: DataErrorBanner + Tekrar dene", async () => {
        fetchMock.mockImplementation(async (url: string) => {
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            throw new Error("Sunucuya ulaşılamadı.");
        });
        await render();
        await tiklaVeBekle(butonBul("Önizle"));

        const uyari = $("[role='alert']");
        expect(uyari.textContent).toContain("Sunucuya ulaşılamadı.");
        expect(uyari.textContent).toContain("kayıtlarınız silinmedi");
        expect(container.textContent).not.toContain("Bu kriterlere uyan kayıt yok");

        // Tekrar dene → sunucu düzeldi → tablo gelir, şerit kalkar
        sunucuKur();
        await tiklaVeBekle(butonBul("Tekrar dene"));
        expect(container.querySelector("[role='alert']")).toBeNull();
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    });

    it("sayfa değişimi `sayfa: 2` gönderir ve SON önizlenen tanımı kullanır (taslağı değil)", async () => {
        sunucuKur();
        await render();
        await tiklaVeBekle(butonBul("Önizle"));
        expect(container.textContent).toContain("1 / 3");

        // Taslağı değiştir (bayat) — sayfa değişimi yine eski tanımla gitmeli
        tikla(byLabel<HTMLInputElement>("Durum"));
        expect(container.querySelector("[data-testid='bayat-rozeti']")).not.toBeNull();

        await tiklaVeBekle(butonBul("İleri"));
        expect(previewCagrilari()).toHaveLength(2);
        const govde = sonPreviewGovdesi();
        expect(govde.sayfa).toBe(2);
        expect(govde.tanim.kolonlar).toEqual(["tracking_no", "subject"]);
        expect(container.textContent).toContain("2 / 3");
        expect(butonBul("Geri").disabled).toBe(false);
    });

    it("katalog hatası şerit + toast; Tekrar dene yeniden yükler", async () => {
        fetchMock.mockResolvedValueOnce(failJson(503, { detail: "bakım" }));
        await render();
        expect($("[role='alert']").textContent).toContain("bakım");
        expect(toastMocks.error).toHaveBeenCalledTimes(1);
        expect(container.querySelector("#rapor-kaynak")).toBeNull();

        sunucuKur();
        await tiklaVeBekle(butonBul("Tekrar dene"));
        expect(container.querySelector("#rapor-kaynak")).not.toBeNull();
    });

    it("kaynak değişince kolonlar o kaynağın varsayılanına döner, filtreler sıfırlanır", async () => {
        sunucuKur();
        await render();
        tikla(butonBul("Filtre ekle"));
        expect(container.querySelectorAll("[data-testid='filtre-satiri']")).toHaveLength(1);

        sec($<HTMLSelectElement>("#rapor-kaynak"), "muvekkiller");
        const secili = Array.from(container.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));
        expect(secili).toEqual(["name"]);
        expect(container.querySelectorAll("[data-testid='filtre-satiri']")).toHaveLength(0);

        await tiklaVeBekle(butonBul("Önizle"));
        expect(sonPreviewGovdesi().tanim.veri_kaynagi).toBe("muvekkiller");
    });

    it("tam genişlik kuralı: sayfa kökü mx-auto ile ortalanmaz; oluşturucu xl altında tek sütun", async () => {
        sunucuKur();
        await render();
        const kok = container.firstElementChild as HTMLElement;
        expect(kok.className).toContain("max-w-[1600px]");
        expect(kok.className).not.toContain("mx-auto");
        const bolum = $("section");
        expect(bolum.className).toContain("grid-cols-1");
        expect(bolum.className).toContain("xl:grid-cols-[320px_1fr]");
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
        expect(container.querySelector("#rapor-kaynak")).not.toBeNull();
        expect(container.querySelector("[data-testid='anasayfa']")).toBeNull();

        act(() => root!.unmount());
        root = null;
        const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
        adminMock.value = false;
        await render(agac, "/reports");
        expect(container.querySelector("[data-testid='anasayfa']")).not.toBeNull();
        expect(container.querySelector("#rapor-kaynak")).toBeNull();
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
