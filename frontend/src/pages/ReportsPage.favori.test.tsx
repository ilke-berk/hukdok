// @vitest-environment jsdom
// ReportsPage favori önerisi (G144, plan §6.2): başarılı export (manuel Excel/CSV ve asistan `indir_*`)
// sonrasında taslak hiçbir kayıtlı şablonla birebir aynı değilse araç çubuğunun altında kart çıkar;
// önerilen ad "<Kaynak> · <filtreler>" (`sablonAdiOner`); ad düzenlenebilir, Enter/Ekle → `POST /templates`
// {ad, aciklama:"", tanim, paylasimli:false} → şablon çubukta seçili + toast "Favorilere eklendi";
// "Şimdi değil"/× → aynı tanım için sayfa ömründe bir daha sorulmaz; kayıtlı tanımda kart çıkmaz ve çubukta
// "★ Kayıtlı: <ad>"; "☆ Favorilere ekle" bağlantısı indirme yapmadan kartı açar (reddi geçersiz kılar);
// tanım değişince kart kapanır; kart yalnız Rapor sekmesinde; kayıt hatasında toast + kart açık kalır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

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
import { OP_BY_TIP, type FiltreKontrolu, type KatalogKolon, type KolonTipi } from "@/lib/reports";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

class ResizeObserverStub {
    observe() { /* jsdom */ }
    unobserve() { /* jsdom */ }
    disconnect() { /* jsdom */ }
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = function () { /* jsdom */ };

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
                kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar"] }),
                kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
            ],
            hizli_filtreler: [{ alan: "opening_date", alternatifler: [] }, { alan: "status", alternatifler: [] }],
            kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no", "subject"] }],
        },
        {
            anahtar: "muvekkiller",
            etiket: "Müvekkiller",
            aciklama: "",
            varsayilan_kolonlar: ["name"],
            kolonlar: [
                kolon({ anahtar: "name", etiket: "Ad", tip: "metin" }),
                kolon({ anahtar: "city", etiket: "Şehir", tip: "metin", grup: "İletişim" }),
            ],
            hizli_filtreler: [{ alan: "city", alternatifler: [] }],
            kolon_setleri: [{ ad: "Temel", kolonlar: ["name"] }],
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
    sayfa_boyu: 10,
};

const VARSAYILAN_TANIM = { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] };
const KENDI_SABLON = {
    id: 1, ad: "Benim şablonum", aciklama: "Derdest davalar", paylasimli: false,
    olusturan: "admin@lexis.com.tr",
    tanim: { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "status"], filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }], siralama: [{ alan: "opening_date", yon: "desc" }] },
    created_at: "2026-09-06T10:00:00Z", updated_at: "2026-09-06T10:00:00Z",
};
/** Varsayılan taslakla BİREBİR aynı tanımlı (başkasının paylaşımlı) şablon — "kayıtlı" senaryosu. */
const VARSAYILANI_KAYDEDEN = {
    id: 5, ad: "Temel dava listesi", aciklama: null, paylasimli: true,
    olusturan: "baskasi@lexis.com.tr",
    tanim: VARSAYILAN_TANIM,
    created_at: "2026-09-05T10:00:00Z", updated_at: "2026-09-05T10:00:00Z",
};
const ASISTAN_TANIMI = {
    veri_kaynagi: "davalar",
    kolonlar: ["tracking_no", "status", "opening_date"],
    filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }],
    siralama: [{ alan: "opening_date", yon: "desc" }],
};

const okJson = (payload: unknown, status = 200) => ({ ok: true, status, json: async () => payload });
const failJson = (status: number, payload: unknown) => ({ ok: false, status, json: async () => payload });
const okBlob = (headers: Record<string, string>) => ({
    ok: true,
    status: 200,
    headers: { get: (k: string) => headers[k] ?? null },
    blob: async () => new Blob(["x"]),
});
const ayarlar = (acik: boolean) => okJson({ settings: [{ key: "rapor_asistani", value: acik, default: false, label: "Rapor asistanı", description: "", updated_by: null, updated_at: null }] });

/** NDJSON satırlarını tek tek chunk olarak veren sahte akış yanıtı. */
function akis(olaylar: unknown[]) {
    const encoder = new TextEncoder();
    const chunks = olaylar.map(o => encoder.encode(JSON.stringify(o) + "\n"));
    let i = 0;
    return {
        ok: true,
        status: 200,
        body: {
            getReader: () => ({
                read: async () => (i < chunks.length ? { value: chunks[i++], done: false } : { value: undefined, done: true }),
                cancel: async () => undefined,
            }),
        },
    };
}

type Cagri = [string, RequestInit | undefined];
const cagrilar = (url: string, method?: string) =>
    (fetchMock.mock.calls as Cagri[]).filter(([u, o]) => u === url && (!method || (o?.method ?? "GET") === method));
const govde = (c: Cagri) => JSON.parse(c[1]!.body as string);

describe("ReportsPage favori önerisi (G144)", () => {
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
        /** Asistan anahtarı (varsayılan kapalı — manuel akış testleri asistan satırsız koşar). */
        anahtar?: boolean;
        chat?: () => unknown;
        exportCevabi?: () => unknown;
        kayitCevabi?: () => unknown;
    };

    function sunucuKur(ayar: SunucuAyari = {}) {
        const sablonlar = [...(ayar.sablonlar ?? [KENDI_SABLON])];
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            const method = opts?.method ?? "GET";
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const g = JSON.parse(opts!.body as string);
                return okJson({ ...ONIZLEME, sayfa: g.sayfa, sayfa_boyu: g.sayfa_boyu });
            }
            if (url === "/api/reports/templates" && method === "GET") return okJson([...sablonlar]);
            if (url === "/api/reports/templates" && method === "POST") {
                if (ayar.kayitCevabi) return ayar.kayitCevabi();
                const g = JSON.parse(opts!.body as string);
                const yeni = { ...g, id: 99, olusturan: "admin@lexis.com.tr", created_at: "2026-09-07T12:00:00Z", updated_at: "2026-09-07T12:00:00Z" };
                sablonlar.unshift(yeni);
                return okJson(yeni, 201);
            }
            if (url === "/api/admin/settings") return ayarlar(ayar.anahtar ?? false);
            if (url === "/api/reports/chat" && method === "POST") {
                return ayar.chat ? ayar.chat() : akis([{ status: "complete", cevap: "Hazır.", tanim: null, eylem: null }]);
            }
            if (url === "/api/reports/export") {
                return ayar.exportCevabi
                    ? ayar.exportCevabi()
                    : okBlob({ "Content-Disposition": 'attachment; filename="hukdok-rapor-davalar-20260907-1405.xlsx"', "X-Rapor-Kosu-Id": "42" });
            }
            throw new Error("beklenmeyen uç: " + method + " " + url);
        });
    }

    async function bekle(tur = 4) {
        for (let i = 0; i < tur; i++) {
            await act(async () => { await Promise.resolve(); });
        }
    }

    async function render(url = "/reports") {
        root = createRoot(container);
        await act(async () => {
            root!.render(
                <MemoryRouter initialEntries={[url]}>
                    <ReportsPage />
                </MemoryRouter>,
            );
        });
        await bekle();
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
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const kart = () => container.querySelector("[data-testid='favori-onerisi']");
    const kartVar = () => kart() !== null;
    const adGirdisi = () => byLabel<HTMLInputElement>("Favori adı");
    const kayitliRozeti = () => container.querySelector("[data-testid='favori-kayitli']");
    const ekleBaglantisi = () => container.querySelector<HTMLButtonElement>("[data-testid='favori-ekle-baglantisi']");
    const secim = () => $<HTMLSelectElement>("#rapor-sablon");

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
    async function tikla(el: Element) {
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        await bekle();
    }
    async function tus(el: Element, key: string) {
        await act(async () => {
            el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
        });
        await bekle(8);
    }
    /** Radix Tabs tetikleyicisi mousedown ile etkinleşir. */
    async function sekme(metin: string) {
        const t = Array.from(container.querySelectorAll("[role='tab']")).find(x => x.textContent?.trim() === metin);
        if (!t) throw new Error("sekme bulunamadı: " + metin);
        await act(async () => {
            t.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, button: 0 }));
        });
        await bekle();
    }
    /** Asistan satırından mesaj gönderir (Enter). */
    async function gonder(metin: string) {
        const g = byLabel<HTMLInputElement>("Asistana mesaj");
        yaz(g, metin);
        await tus(g, "Enter");
        await bekle(8);
    }

    // ---------------------------------------------------------------- tetik + ad önerisi

    it("kayıtsız tanımla Excel indirme sonrası kart çıkar: 'Bu formatı favorilere … adıyla ekleyeyim mi?', ad 'Davalar · Temel'; indirmeden önce kart yok", async () => {
        sunucuKur();
        await render();
        expect(kartVar()).toBe(false);
        // Çubukta kalıcı bağlantı var (taslak kayıtlı değil), "Kayıtlı" rozeti yok
        expect(ekleBaglantisi()).not.toBeNull();
        expect(ekleBaglantisi()!.textContent?.trim()).toBe("Favorilere ekle");
        expect(kayitliRozeti()).toBeNull();

        await tikla(butonBul("Excel indir"));
        expect(indirmeler).toEqual(["hukdok-rapor-davalar-20260907-1405.xlsx"]);
        expect(kartVar()).toBe(true);
        expect(kart()!.textContent).toContain("Bu formatı favorilere");
        expect(kart()!.textContent).toContain("adıyla ekleyeyim mi?");
        expect(adGirdisi().value).toBe("Davalar · Temel");
        // Kart sayaç satırının (şablon + indirme) ALTINDA, tablonun üstünde (G175)
        const cubuk = $("[data-testid='sayac-satiri']");
        const tablo = $("table");
        const onceGelir = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        expect(onceGelir(cubuk, kart()!)).toBe(true);
        expect(onceGelir(kart()!, tablo)).toBe(true);
        // Kart açılırken şablon yazılmaz, toast yalnız indirme
        expect(cagrilar("/api/reports/templates", "POST")).toHaveLength(0);
        expect(toastMocks.success).toHaveBeenCalledTimes(1);
    });

    it("Ekle → POST /templates {ad, aciklama:'', tanim, paylasimli:false}; şablon çubukta seçili, kart kapanır, toast 'Favorilere eklendi', rozet '★ Kayıtlı'", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(true);

        await tikla(butonBul("Ekle"));
        const post = cagrilar("/api/reports/templates", "POST");
        expect(post).toHaveLength(1);
        const g = govde(post[0]);
        expect(Object.keys(g).sort()).toEqual(["aciklama", "ad", "paylasimli", "tanim"]);
        expect(g).toEqual({ ad: "Davalar · Temel", aciklama: "", paylasimli: false, tanim: VARSAYILAN_TANIM });

        expect(kartVar()).toBe(false);
        expect(secim().value).toBe("99");
        expect(Array.from(secim().options).map(o => o.textContent)).toContain("Davalar · Temel");
        expect(toastMocks.success).toHaveBeenCalledWith("Favorilere eklendi", { description: "Davalar · Temel" });
        // Artık kayıtlı: bağlantı yerine rozet
        expect(ekleBaglantisi()).toBeNull();
        expect(kayitliRozeti()!.textContent).toContain("Kayıtlı: Davalar · Temel");
    });

    it("ad düzenlenebilir; Enter = Ekle (düzenlenen adla); boş ad ile Ekle kapalı", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("CSV indir"));
        const girdi = adGirdisi();
        yaz(girdi, "   ");
        expect(butonBul("Ekle").disabled).toBe(true);
        yaz(girdi, "  Dava listem  ");
        expect(butonBul("Ekle").disabled).toBe(false);
        await tus(girdi, "Enter");

        const post = cagrilar("/api/reports/templates", "POST");
        expect(post).toHaveLength(1);
        expect(govde(post[0]).ad).toBe("Dava listem");
        expect(kartVar()).toBe(false);
        expect(kayitliRozeti()!.textContent).toContain("Dava listem");
    });

    it("'Şimdi değil' → kart kapanır, aynı tanımla ikinci indirmede SORULMAZ; '☆ Favorilere ekle' yine açar", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(true);
        await tikla(butonBul("Şimdi değil"));
        expect(kartVar()).toBe(false);
        expect(cagrilar("/api/reports/templates", "POST")).toHaveLength(0);

        await tikla(butonBul("Excel indir"));
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(2);
        expect(kartVar()).toBe(false);

        // Kalıcı bağlantı reddi geçersiz kılar — indirme yapmadan
        await tikla(ekleBaglantisi()!);
        expect(kartVar()).toBe(true);
        expect(adGirdisi().value).toBe("Davalar · Temel");
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(2);
    });

    it("× de ret sayılır: sonraki indirmede sorulmaz", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));
        await tikla(byLabel("Öneriyi kapat"));
        expect(kartVar()).toBe(false);
        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(false);
    });

    it("kayıtlı tanımla indirme sonrası kart ÇIKMAZ; çubukta '★ Kayıtlı: <ad>' (seçili olmasa da), bağlantı yok", async () => {
        // Varsayılan taslak, başkasının paylaşımlı şablonuyla birebir aynı
        sunucuKur({ sablonlar: [KENDI_SABLON, VARSAYILANI_KAYDEDEN] });
        await render();
        expect(secim().value).toBe("");
        expect(kayitliRozeti()!.textContent).toContain("Kayıtlı: Temel dava listesi");
        expect(ekleBaglantisi()).toBeNull();

        await tikla(butonBul("Excel indir"));
        expect(indirmeler).toHaveLength(1);
        expect(kartVar()).toBe(false);

        // Kendi şablonu yüklenince de kayıtlı (tanım şeride çözülüp geri derlenir — birebir aynı)
        sec(secim(), "1");
        await tikla(butonBul("Yükle"));
        expect(kayitliRozeti()!.textContent).toContain("Kayıtlı: Benim şablonum");
        await tikla(butonBul("CSV indir"));
        expect(kartVar()).toBe(false);
    });

    it("tanım değişince kart kapanır (şerit kaynak rozeti); yeni tanımda indirme yeniden sorar, ad yeni kaynağa göre", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(true);

        // G175: kaynak şeritteki rozet menüsünden (Radix DropdownMenu: pointerdown açar, öğe portal'da)
        await act(async () => {
            $("[data-testid='serit-kaynak']").dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
        });
        await bekle();
        await tikla($("[role='menu'] [data-kaynak='muvekkiller']", document.body));
        expect(kartVar()).toBe(false);

        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(true);
        expect(adGirdisi().value).toBe("Müvekkiller · Temel");
    });

    it("kart yalnız Rapor sekmesinde: Şablonlar sekmesinde görünmez, dönünce (tanım aynı) yine görünür", async () => {
        sunucuKur();
        await render();
        await tikla(butonBul("Excel indir"));
        expect(kartVar()).toBe(true);
        await sekme("Şablonlar");
        expect(kartVar()).toBe(false);
        await sekme("Rapor");
        expect(kartVar()).toBe(true);
    });

    it("aynı ad kayıtlıysa öneri ' (2)' ekiyle gelir", async () => {
        sunucuKur({ sablonlar: [{ ...KENDI_SABLON, ad: "Davalar · Temel" }] });
        await render();
        await tikla(butonBul("Excel indir"));
        expect(adGirdisi().value).toBe("Davalar · Temel (2)");
    });

    it("kayıt hatası: toast + kart AÇIK kalır (ad düzeltilip yeniden denenebilir); şablon listesi değişmez", async () => {
        sunucuKur({ kayitCevabi: () => failJson(422, { detail: { alan: "ad", sebep: "cok_uzun" } }) });
        await render();
        await tikla(butonBul("Excel indir"));
        await tikla(butonBul("Ekle"));
        expect(toastMocks.error).toHaveBeenCalledWith("Şablon kaydedilemedi.", { description: "Geçersiz rapor tanımı: ad — cok_uzun" });
        expect(kartVar()).toBe(true);
        expect(butonBul("Ekle").disabled).toBe(false);
        expect(Array.from(secim().options).map(o => o.value)).toEqual(["", "1"]);
        expect(kayitliRozeti()).toBeNull();
    });

    // ---------------------------------------------------------------- asistan yolu

    it("asistan `indir_xlsx` sonrası da kart çıkar; ad filtreden: 'Davalar · Derdest'; Ekle asistanın tanımını kaydeder", async () => {
        sunucuKur({
            anahtar: true,
            chat: () => akis([{ status: "complete", cevap: "Excel hazırlanıyor.", tanim: ASISTAN_TANIMI, eylem: "indir_xlsx" }]),
        });
        await render();
        expect(kartVar()).toBe(false);
        await gonder("Derdest davaları Excel indir");
        await bekle(8);
        // G174: değerler kataloğa uyuyor → tanım düğme beklemeden uygulanır ve indirilir (G167 onay adımı kalktı)

        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(1);
        expect(kartVar()).toBe(true);
        expect(adGirdisi().value).toBe("Davalar · Derdest");

        await tikla(butonBul("Ekle"));
        const g = govde(cagrilar("/api/reports/templates", "POST")[0]);
        expect(g).toEqual({ ad: "Davalar · Derdest", aciklama: "", paylasimli: false, tanim: ASISTAN_TANIMI });
        expect(secim().value).toBe("99");
        expect(kartVar()).toBe(false);
    });

    it("asistan indirmesi 413 ile düşerse kart çıkmaz (başarılı export şart)", async () => {
        sunucuKur({
            anahtar: true,
            chat: () => akis([{ status: "complete", cevap: "Excel.", tanim: ASISTAN_TANIMI, eylem: "indir_xlsx" }]),
            exportCevabi: () => failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }),
        });
        await render();
        await gonder("Derdest davaları Excel indir");
        await bekle(8);
        await tikla(butonBul("Excel indir"));
        await bekle(8);
        expect(indirmeler).toEqual([]);
        expect(kartVar()).toBe(false);
    });
});
