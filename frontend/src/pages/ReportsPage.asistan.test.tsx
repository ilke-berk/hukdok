// @vitest-environment jsdom
// ReportsPage (G135 → G138 → G143 → G167 → G174 otomatik uygulama: temiz tanım düğme beklemeden uygulanır; kart
// yalnız reddedilince / geri alınınca bekler; Onayla / İndir / yerel onay / liste balonu) — Asistan ÖN PLANDA: anahtar açıkken Rapor sekmesinin İLK öğesi
// AssistantBar (anahtar okunana dek iskelet; kapalı/409 → satırın yerinde `asistan-kapali-karti` bilgi kartı
// (G175), araç çubuğunda "Asistan" düğmesi yok; şerit + tablo çalışır); G175: kaynak/kolon şeritten (rozet menüsü,
// "+ Kolon", çip ×), liste balonu tıkı `onFiltreEkle` ile filtre ekler; gönderilen gövde `{mesajlar (≤20),
// mevcut_tanim}`; `complete`+`tanim` → tanım DÜĞME BEKLEMEDEN uygulanır, `/preview` asistan tanımıyla,
// toast "Rapor hazırlandı · N kayıt"; "Geri al" eski taslağı ve önizlemeyi geri getirir (tek adım; manuel
// değişiklik adımı düşürür); `eylem:"indir_xlsx"` → `/export` `kaynak:"asistan"` (K7); `eylem:"onizle"`;
// `tanim=null` (soru) → uygulama yok, balon var; `warning` şerit; `failed` error_kod ipucu (tanınmayan →
// analysis_error); örnek çipi girdiye yazar, ikinci tık gönderir, çipler kaynağa göre; Enter gönderir.
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
import { ornekIstemler } from "@/lib/reportsChat";

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
const ASISTAN_TANIMI = {
    veri_kaynagi: "davalar",
    kolonlar: ["tracking_no", "status", "opening_date"],
    filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }],
    siralama: [{ alan: "opening_date", yon: "desc" }],
};
const MUVEKKIL_TANIMI = {
    veri_kaynagi: "muvekkiller",
    kolonlar: ["name", "city"],
    filtreler: [{ alan: "city", op: "contains", deger: "İstanbul" }],
    siralama: [],
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

/** Elle çözülen akış — gönderim sırasında kilit testi için. */
function bekleyenAkis(olaylar: unknown[]) {
    let coz: () => void = () => undefined;
    const kapi = new Promise<void>(r => { coz = r; });
    const encoder = new TextEncoder();
    const chunks = olaylar.map(o => encoder.encode(JSON.stringify(o) + "\n"));
    let i = 0;
    const res = {
        ok: true,
        status: 200,
        body: {
            getReader: () => ({
                read: async () => {
                    await kapi;
                    return i < chunks.length ? { value: chunks[i++], done: false } : { value: undefined, done: true };
                },
                cancel: async () => undefined,
            }),
        },
    };
    return { res, coz: () => coz() };
}

type Cagri = [string, RequestInit | undefined];
const cagrilar = (url: string, method?: string) =>
    (fetchMock.mock.calls as Cagri[]).filter(([u, o]) => u === url && (!method || (o?.method ?? "GET") === method));
const govde = (c: Cagri) => JSON.parse(c[1]!.body as string);

describe("ReportsPage asistan satırı (G135/G138/G143/G167)", () => {
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
        anahtar?: boolean;
        /** `/api/admin/settings` ucu tümden patlasın (ağ hatası). */
        ayarHatasi?: boolean;
        /** Anahtar cevabı elle çözülür (iskelet testi). */
        ayarBekle?: Promise<unknown>;
        chat?: (govde: { mesajlar: unknown[]; mevcut_tanim: unknown }) => unknown;
        exportCevabi?: () => unknown;
        /** G168: önizleme toplamı (varsayılan ONIZLEME.toplam = 3); 0 → boş sonuç önerisi. */
        onizlemeToplam?: number;
    };

    function sunucuKur(ayar: SunucuAyari = {}) {
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            const method = opts?.method ?? "GET";
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const g = JSON.parse(opts!.body as string);
                const toplam = ayar.onizlemeToplam ?? ONIZLEME.toplam;
                return okJson({ ...ONIZLEME, satirlar: toplam === 0 ? [] : ONIZLEME.satirlar, toplam, sayfa: g.sayfa, sayfa_boyu: g.sayfa_boyu });
            }
            if (url === "/api/reports/templates" && method === "GET") return okJson([]);
            if (url === "/api/reports/templates" && method === "POST") {
                const g = JSON.parse(opts!.body as string);
                return okJson({ ...g, id: 99, olusturan: "admin@lexis.com.tr", created_at: "2026-09-10T20:00:00Z", updated_at: "2026-09-10T20:00:00Z" }, 201);
            }
            if (url === "/api/admin/settings") {
                if (ayar.ayarHatasi) throw new Error("ağ yok");
                if (ayar.ayarBekle) return ayar.ayarBekle;
                return ayarlar(ayar.anahtar ?? true);
            }
            if (url === "/api/reports/chat" && method === "POST") {
                const g = JSON.parse(opts!.body as string);
                return ayar.chat ? ayar.chat(g) : akis([{ status: "complete", cevap: "Hazır.", tanim: null, eylem: null }]);
            }
            if (url === "/api/reports/export") {
                return ayar.exportCevabi
                    ? ayar.exportCevabi()
                    : okBlob({ "Content-Disposition": 'attachment; filename="hukdok-rapor-davalar-20260906-1500.xlsx"', "X-Rapor-Kosu-Id": "77" });
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
    const butonVar = (metin: string, kok: ParentNode = container) =>
        Array.from(kok.querySelectorAll("button")).some(x => x.textContent?.trim() === metin);
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const satir = () => $("[data-testid='asistan-satiri']");
    const konusma = () => $("[data-testid='asistan-konusmasi']");
    const konusmaVar = () => container.querySelector("[data-testid='asistan-konusmasi']") !== null;
    const girdi = () => byLabel<HTMLInputElement>("Asistana mesaj");
    const cipMetinleri = () => Array.from(container.querySelectorAll("[data-testid='ornek-istem']")).map(c => c.textContent?.trim());
    const cipler = () => Array.from(container.querySelectorAll("[data-testid='filtre-cipi']")).map(c => c.textContent?.trim());
    const onizlemeler = () => cagrilar("/api/reports/preview", "POST");
    const sonOnizleme = () => govde(onizlemeler().at(-1)!);
    /** G175: kaynak şeritteki rozette (etiket → katalog anahtarı). */
    const seciliKaynak = () => {
        const etiket = container.querySelector("[data-testid='serit-kaynak']")?.textContent?.trim();
        return KATALOG.veri_kaynaklari.find(k => k.etiket === etiket)?.anahtar ?? null;
    };
    /**
     * G175: seçili kolonların kanıtı SON önizleme gövdesi (uygulanan tanım kendiliğinden önizlenir)
     * + şeritteki kolon çipleri (`serit-kolon-<anahtar>`, sıralı).
     */
    const seciliKolonlar = () => {
        const kolonlar = sonOnizleme().tanim.kolonlar as string[];
        const cipler = Array.from(container.querySelectorAll("[data-testid^='serit-kolon-']"))
            .filter(e => e.getAttribute("data-testid") !== "serit-kolon-ekle")
            .map(e => e.getAttribute("data-testid")!.replace("serit-kolon-", ""));
        expect(cipler).toEqual(kolonlar);
        return kolonlar;
    };
    /** Şerit "+ Kolon" (Radix Popover portal → document.body) → cmdk öğesi. */
    async function kolonEkle(anahtar: string) {
        await tikla($("[data-testid='serit-kolon-ekle']"));
        await tikla($(`[data-testid='kolon-secici'] [cmdk-item][data-kolon='${anahtar}']`, document.body));
    }
    /** Şerit kolon çipinin ×'i. */
    const kolonKaldir = (etiket: string) => tikla(byLabel(`${etiket} kolonunu kaldır`));
    /** Şerit kaynak rozeti menüsü (Radix DropdownMenu: pointerdown açar, öğe portal'da). */
    async function kaynakSec(anahtar: string) {
        await act(async () => {
            $("[data-testid='serit-kaynak']").dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
        });
        await bekle();
        await tikla($(`[role='menu'] [data-kaynak='${anahtar}']`, document.body));
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
    async function tus(el: Element, key: string, shiftKey = false) {
        await act(async () => {
            el.dispatchEvent(new KeyboardEvent("keydown", { key, shiftKey, bubbles: true, cancelable: true }));
        });
        await bekle(8);
    }

    /** Üst satırdan mesaj gönderir (Enter). */
    async function gonder(metin: string) {
        const g = girdi();
        yaz(g, metin);
        await tus(g, "Enter");
        await bekle(8);
    }

    // ---------------------------------------------------------------- anahtar kapısı

    it("anahtar kapalıyken asistan satırı, araç çubuğu düğmesi ve yan panel yok; manuel akış (otomatik önizleme) etkilenmez", async () => {
        sunucuKur({ anahtar: false });
        await render();

        expect(cagrilar("/api/admin/settings")).toHaveLength(1);
        // Sıra: katalog ilk istek (G133 sözleşmesi), anahtar sonra
        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        expect(butonVar("Asistan")).toBe(false);
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-iskelet']")).toBeNull();
        expect(container.querySelector("[aria-label='Asistana mesaj']")).toBeNull();
        expect(document.body.querySelector("[data-testid='asistan-paneli']")).toBeNull();
        // G175: Rapor sekmesinin ilk öğesi asistan satırının yerindeki bilgi kartı; şerit onun altında
        const kart = $("[data-testid='asistan-kapali-karti']");
        expect($("[data-testid='rapor-sekmesi']").firstElementChild).toBe(kart);
        expect(kart.textContent).toContain("Rapor asistanı kapalı");
        expect(kart.textContent).toContain("rapor_asistani");
        expect(Boolean(kart.compareDocumentPosition($("[data-testid='tanim-seridi']")) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);

        // Açılış önizlemesi geldi; kolon değişimi (şerit "+ Kolon") hemen yeniden önizler
        expect(onizlemeler()).toHaveLength(1);
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
        await kolonEkle("status");
        expect(onizlemeler()).toHaveLength(2);
        expect(sonOnizleme().tanim.kolonlar).toEqual(["tracking_no", "subject", "status"]);
    });

    it("anahtar okunamazsa (uç hatası) satır yine gizli, toast yok", async () => {
        sunucuKur({ ayarHatasi: true });
        await render();

        expect(butonVar("Asistan")).toBe(false);
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(toastMocks.error).not.toHaveBeenCalled();
        expect(seciliKaynak()).toBe("davalar");
    });

    it("anahtar okunana dek iskelet; açık gelince satır Rapor sekmesinin İLK öğesi, kartların üstünde", async () => {
        let coz: (v: unknown) => void = () => undefined;
        sunucuKur({ ayarBekle: new Promise(r => { coz = r; }) });
        await render();

        expect(container.querySelector("[data-testid='asistan-iskelet']")).not.toBeNull();
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        // İskelet manuel akışı bekletmez: açılış önizlemesi geldi
        expect(onizlemeler()).toHaveLength(1);

        await act(async () => { coz(ayarlar(true)); });
        await bekle(8);

        expect(container.querySelector("[data-testid='asistan-iskelet']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-kapali-karti']")).toBeNull();
        const sekme = $("[data-testid='rapor-sekmesi']");
        expect(sekme.firstElementChild?.getAttribute("data-testid")).toBe("asistan-satiri");
        const serit = $("[data-testid='tanim-seridi']");
        expect(Boolean(satir().compareDocumentPosition(serit) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
        // Eski araç çubuğu düğmesi ve yan panel yok; konuşma alanı gönderene dek kapalı
        expect(butonVar("Asistan")).toBe(false);
        expect(document.body.querySelector("[data-testid='asistan-paneli']")).toBeNull();
        expect(document.body.querySelector("[role='complementary']")).toBeNull();
        expect(konusmaVar()).toBe(false);
        expect(girdi().placeholder).toContain("Ne listelemek istiyorsunuz");
        expect(satir().textContent).toContain("veya aşağıdan seçin");
    });

    // ---------------------------------------------------------------- çipler + konuşma alanı

    it("örnek çipleri kaynağa göre (3); ilk tık girdiye yazar, aynı çipe ikinci tık gönderir; kart değişince çipler değişir", async () => {
        sunucuKur({ anahtar: true });
        await render();

        expect(cipMetinleri()).toEqual([...ornekIstemler("davalar")]);
        expect(cipMetinleri()).toHaveLength(3);
        const cip = container.querySelectorAll("[data-testid='ornek-istem']")[1];

        await tikla(cip);
        expect(girdi().value).toBe(cip.textContent);
        // Henüz gönderilmedi
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        expect(konusmaVar()).toBe(false);

        await tikla(cip);
        await bekle(8);
        const post = cagrilar("/api/reports/chat", "POST");
        expect(post).toHaveLength(1);
        expect(govde(post[0]).mesajlar).toEqual([{ rol: "user", icerik: cip.textContent }]);
        expect(konusmaVar()).toBe(true);
        expect(girdi().value).toBe("");

        // Şerit kaynak rozetinden Müvekkiller → müvekkil örnekleri
        await kaynakSec("muvekkiller");
        expect(cipMetinleri()).toEqual([...ornekIstemler("muvekkiller")]);
        expect(cipMetinleri()[0]).toContain("Ankara");
    });

    it("konuşma alanı: 'Konuşmayı kapat' alanı kapatır, satır kalır, geçmiş korunur; yeni mesaj yeniden açar", async () => {
        sunucuKur({ anahtar: true });
        await render();

        await gonder("merhaba");
        expect(konusma().querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(1);
        expect(konusma().querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(1);

        await tikla(byLabel("Konuşmayı kapat"));
        expect(konusmaVar()).toBe(false);
        expect(container.querySelector("[data-testid='asistan-satiri']")).not.toBeNull();

        await gonder("tekrar");
        expect(konusmaVar()).toBe(true);
        expect(konusma().querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(2);
        // Geçmiş sunucuya taşındı (K6: istemci taşır)
        const post = cagrilar("/api/reports/chat", "POST");
        expect(govde(post[1]).mesajlar).toEqual([
            { rol: "user", icerik: "merhaba" }, { rol: "assistant", icerik: "Hazır." }, { rol: "user", icerik: "tekrar" },
        ]);
    });

    // ---------------------------------------------------------------- gövde + otomatik uygulama + geri al

    it("Enter gönderir: gövde {mesajlar, mevcut_tanim}; complete+tanim → G174 DÜĞME BEKLEMEDEN uygulanır (kısa kart, oluşturucu + /preview + toast); 'Geri al' eski taslağı geri getirir ve kart okunur teyit kartına döner; 'Onayla ve uygula' yeniden uygular", async () => {
        sunucuKur({
            chat: () => akis([
                { status: "info", message: "Rapor tanımı hazırlanıyor" },
                { status: "complete", cevap: "Derdest davaları hazırladım.", tanim: ASISTAN_TANIMI, eylem: null },
            ]),
        });
        await render();
        // Açılış önizlemesi: referans
        expect(onizlemeler()).toHaveLength(1);

        await gonder("Derdest davaları listele");

        const post = cagrilar("/api/reports/chat", "POST");
        expect(post).toHaveLength(1);
        const g = govde(post[0]);
        expect(Object.keys(g).sort()).toEqual(["mesajlar", "mevcut_tanim"]);
        expect(g.mesajlar).toEqual([{ rol: "user", icerik: "Derdest davaları listele" }]);
        expect(g.mevcut_tanim).toEqual(VARSAYILAN_TANIM);

        const k = konusma();
        expect(k.querySelector("[data-testid='sohbet-kullanici']")?.textContent).toBe("Derdest davaları listele");
        const asistan = k.querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.textContent).toContain("Derdest davaları hazırladım.");

        // G174: UYGULANDI — oluşturucu değişti, önizleme asistan tanımıyla, toast satır sayısıyla; kart KISA (ayrıntı şeritte)
        const ozet = asistan.querySelector("[data-testid='tanim-ozeti']")!;
        expect(ozet.getAttribute("data-kisa")).toBe("true");
        expect(ozet.querySelector("dl")).toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")?.textContent).toContain("Uygulandı · Davalar · 3 kolon · 1 filtre");
        expect(asistan.querySelector("[data-testid='tanim-teyit-notu']")).toBeNull();
        expect(butonVar("Onayla ve uygula", asistan)).toBe(false);
        expect(butonVar("Excel indir", asistan)).toBe(true);
        expect(butonVar("CSV indir", asistan)).toBe(true);
        expect(seciliKaynak()).toBe("davalar");
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        // Filtre şeride çözüldü (status eq Derdest → çoklu seçim çipi); operatör seçici yok
        expect(cipler()).toEqual(["DurumDerdest"]);
        expect(container.querySelector("[aria-label='Operatör']")).toBeNull();
        expect(onizlemeler()).toHaveLength(2);
        expect(sonOnizleme()).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(toastMocks.success).toHaveBeenCalledWith("Rapor hazırlandı · 3 kayıt");
        // Girdi temizlendi, akış durumu bitince kilit kalktı; bekleyen tanım yok
        expect(girdi().value).toBe("");
        expect(girdi().disabled).toBe(false);
        expect(girdi().placeholder).not.toContain("Düzeltme");
        // Eylem yoktu: export yok
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);

        // Geri al: eski taslak + önizleme geri gelir; kart okunur TEYİT KARTINA döner (etiket/operatör/değer) + Onayla
        await tikla($("[data-testid='tanim-geri-al']", asistan));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(cipler()).toEqual([]);
        expect(onizlemeler()).toHaveLength(3);
        expect(sonOnizleme()).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 10 });
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        const ozet2 = asistan.querySelector("[data-testid='tanim-ozeti']")!;
        expect(ozet2.querySelector("[data-testid='tanim-kaynak']")?.textContent).toBe("Davalar");
        expect(Array.from(ozet2.querySelectorAll("[data-testid='tanim-kolonlar'] span")).map(x => x.textContent))
            .toEqual(["Ofis No", "Durum", "Açılış Tarihi"]);
        expect(Array.from(ozet2.querySelectorAll("[data-testid='tanim-filtreler'] li")).map(x => x.textContent))
            .toEqual(["Durum · eşittir · Derdest"]);
        expect(ozet2.querySelector("[data-testid='tanim-siralama']")?.textContent).toBe("Açılış Tarihi ↓");
        expect(ozet2.querySelector("[data-testid='tanim-teyit-notu']")?.textContent).toContain("onaylayın");
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);
        expect(girdi().placeholder).toContain("Düzeltme");

        // Yeniden onayla → yine rozet + Geri al
        await tikla(butonBul("Onayla ve uygula", asistan));
        await bekle(8);
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        expect(onizlemeler()).toHaveLength(4);
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        expect(girdi().placeholder).not.toContain("Düzeltme");
    });

    it("Geri al tek adımdır: manuel değişiklik (kolon paneli) adımı düşürür; 'Geri al' yalnız SON uygulanan balonda", async () => {
        let sayac = 0;
        sunucuKur({
            chat: () => {
                sayac += 1;
                return akis([{ status: "complete", cevap: `cevap ${sayac}`, tanim: sayac === 1 ? ASISTAN_TANIMI : MUVEKKIL_TANIMI, eylem: null }]);
            },
        });
        await render();

        await gonder("birinci");
        const [ilk] = Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(ilk.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();   // G174: hemen uygulandı
        expect(ilk.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();

        // Manuel değişiklik: şeritteki "Durum" çipi (asistan seçmişti) × ile çıkarılır → adım düşer
        await kolonKaldir("Durum");
        expect(seciliKolonlar()).toEqual(["tracking_no", "opening_date"]);
        expect(container.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(ilk.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();

        // İkinci uygulama (kaynak değişir; sayfa onayı SORULMAZ) → hemen uygulanır, Geri al yalnız ikinci balonda
        await gonder("ikinci");
        // [0] ilk kart · [1] G168 sonuç satırı ("3 kayıt bulundu.") · [2] ikinci kart · [3] ikinci sonuç satırı
        const balonlar = Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar).toHaveLength(4);
        expect(balonlar[1].textContent).toContain("kayıt bulundu");
        expect(balonlar[3].textContent).toContain("kayıt bulundu");
        expect(confirmMock.fn).not.toHaveBeenCalled();
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(balonlar[0].querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(balonlar[2].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();

        // Geri al: kaynak davalar'a, manuel değişiklik SONRASI taslağa (status çıkarılmış hali) döner
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(seciliKaynak()).toBe("davalar");
        expect(seciliKolonlar()).toEqual(["tracking_no", "opening_date"]);
        expect(container.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
    });

    it("tanim=null ve eylem yok (asistan soru sordu): uygulama yok, önizleme yok, balon var, Geri al yok", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Hangi yılı istiyorsunuz?", tanim: null, eylem: null }]),
        });
        await render();
        await gonder("davaları listele");

        const asistan = konusma().querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.textContent).toContain("Hangi yılı istiyorsunuz?");
        expect(asistan.querySelector("[data-testid='tanim-ozeti']")).toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(onizlemeler()).toHaveLength(1);
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(toastMocks.success).not.toHaveBeenCalled();
    });

    it("ikinci mesajda geçmiş taşınır (user, assistant, user); hata kayıtları geçmişe girmez; en fazla 20", async () => {
        let sayac = 0;
        sunucuKur({
            chat: () => {
                sayac += 1;
                if (sayac === 2) return akis([{ status: "failed", error_ozet: "Servis yoğun.", error_kod: "gemini_saturated" }]);
                return akis([{ status: "complete", cevap: `cevap ${sayac}`, tanim: null, eylem: null }]);
            },
        });
        await render();

        await gonder("birinci");
        await gonder("ikinci");
        await gonder("üçüncü");

        const post = cagrilar("/api/reports/chat", "POST");
        expect(post).toHaveLength(3);
        expect(govde(post[1]).mesajlar).toEqual([
            { rol: "user", icerik: "birinci" }, { rol: "assistant", icerik: "cevap 1" }, { rol: "user", icerik: "ikinci" },
        ]);
        // İkinci istek failed → geçmişte asistan kaydı yok
        expect(govde(post[2]).mesajlar).toEqual([
            { rol: "user", icerik: "birinci" }, { rol: "assistant", icerik: "cevap 1" },
            { rol: "user", icerik: "ikinci" }, { rol: "user", icerik: "üçüncü" },
        ]);

        // 20 tavanı: 9 mesaj daha → 22 kayıt > 20
        for (let i = 0; i < 9; i++) await gonder(`m${i}`);
        const son = cagrilar("/api/reports/chat", "POST").at(-1)!;
        expect(govde(son).mesajlar.length).toBeLessThanOrEqual(20);
        expect(govde(son).mesajlar.at(-1)).toEqual({ rol: "user", icerik: "m8" });
    });

    // ---------------------------------------------------------------- eylemler (K7)

    it("eylem indir_xlsx: G174 tanım uygulanır ve HEMEN indirilir — /export gövdesi {tanim, format:xlsx, sablon_id:null, kaynak:asistan}; dosya adı başlıktan; 'Excel indir' düğmesi kartta kalır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Excel hazırlanıyor.", tanim: ASISTAN_TANIMI, eylem: "indir_xlsx" }]),
        });
        await render();
        await gonder("Derdest davaları Excel indir");
        await bekle(8);

        const exp = cagrilar("/api/reports/export", "POST");
        expect(exp).toHaveLength(1);
        const g = govde(exp[0]);
        expect(Object.keys(g).sort()).toEqual(["format", "kaynak", "sablon_id", "tanim"]);
        expect(g).toEqual({ tanim: ASISTAN_TANIMI, format: "xlsx", sablon_id: null, kaynak: "asistan" });
        expect(indirmeler).toEqual(["hukdok-rapor-davalar-20260906-1500.xlsx"]);
        expect(toastMocks.success).toHaveBeenCalledWith("İndirildi: hukdok-rapor-davalar-20260906-1500.xlsx");
        // İndirme yolunda ikinci "hazırlandı" toast'ı yok (tek bildirim)
        expect(toastMocks.success).toHaveBeenCalledTimes(1);

        // Oluşturucu da değişti, kart "uygulandı" rozetinde, düğme yok, Geri al var
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        const asistan = konusma().querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(butonVar("Onayla ve uygula", asistan)).toBe(false);
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        // İndirme düğmeleri kalır (tekrar indirilebilir): ikinci tık ikinci export
        expect(butonVar("CSV indir", asistan)).toBe(true);
        await tikla(butonBul("Excel indir", asistan));
        await bekle(8);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(2);
        expect(indirmeler).toHaveLength(2);
    });

    it("eylem indir_csv → G174 hemen format csv ile /export; 413'te tavan mesajı, dosya inmez, tanım yine uygulanır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "CSV.", tanim: MUVEKKIL_TANIMI, eylem: "indir_csv" }]),
            exportCevabi: () => failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }),
        });
        await render();
        await gonder("müvekkilleri csv indir");
        await bekle(8);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(1);

        const g = govde(cagrilar("/api/reports/export", "POST")[0]);
        expect(g.format).toBe("csv");
        expect(g.kaynak).toBe("asistan");
        expect(indirmeler).toEqual([]);
        expect(toastMocks.error).toHaveBeenCalledWith("Rapor satır tavanını aşıyor", expect.objectContaining({ description: expect.stringContaining("limit") }));
        // Kaynak değişti (davalar → muvekkiller) — asistan uygulamasında onay SORULMAZ
        expect(confirmMock.fn).not.toHaveBeenCalled();
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(seciliKolonlar()).toEqual(["name", "city"]);
        // Filtre şeritte çip; gövdeye tık → düzenleyicide değer (G175)
        expect(cipler()).toEqual(["Şehiriçerir \"İstanbul\""]);
        await tikla(byLabel("Şehir filtresini düzenle"));
        expect(byLabel<HTMLInputElement>("Şehir içerir", document.body.querySelector("[data-testid='filtre-duzenleyici']")!).value).toBe("İstanbul");
    });

    it("YEREL / SÖZLE ONAY: ilk tanım G174 ile hemen uygulanır; Geri al sonrası 'tamam' YEREL yürür (Gemini'ye gitmez), kart rozet alır; onay dışı cümle Gemini'ye gider ve aynen dönen tanım + eylem uygulanır", async () => {
        let sayac = 0;
        sunucuKur({
            chat: () => {
                sayac += 1;
                return akis([{ status: "complete", cevap: sayac === 1 ? "Hazırladım." : "Uyguluyorum.", tanim: ASISTAN_TANIMI, eylem: "onizle" }]);
            },
        });
        await render();
        await gonder("derdest davaları göster");
        await bekle(8);
        // İlk cevap: değerler kataloğa uyuyor → hemen uygulandı; [0] kart · [1] G168 sonuç satırı
        expect(onizlemeler()).toHaveLength(2);
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        const balonlar = () => Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar()).toHaveLength(2);
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[1].textContent).toContain("3 kayıt bulundu.");

        // Geri al → kart bekleyen; "tamam": YEREL onay — /chat çağrısı YOK, bekleyen tanım uygulanır, kartın kendisi rozet alır
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        await gonder("tamam");
        await bekle(8);
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(1);
        // [2] yerel "Onaylandı" · [3] G168 sonuç satırı
        expect(balonlar()).toHaveLength(4);
        expect(balonlar()[2].textContent).toContain("Onaylandı");
        expect(balonlar()[3].textContent).toContain("3 kayıt bulundu.");
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[0].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);

        // Geri al → yeniden bekleyen; onay DIŞI cümle Gemini'ye gider (mevcut_tanim = bekleyen); aynı tanım + onizle → uygulanır
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        await gonder("bu şekilde devam edelim mi");
        await bekle(8);
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(2);
        expect(govde(cagrilar("/api/reports/chat", "POST")[1]).mevcut_tanim).toEqual(ASISTAN_TANIMI);
        // [4] Gemini kartı (uygulandı) · [5] sonuç satırı
        expect(balonlar()).toHaveLength(6);
        expect(balonlar()[4].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[5].textContent).toContain("3 kayıt bulundu.");
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);

        const prev = onizlemeler();
        expect(prev).toHaveLength(6); // açılış + otomatik + geri al + yerel onay + geri al + sözle onay
        expect(govde(prev[1])).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(govde(prev[2])).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 10 });
        expect(govde(prev[3])).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(govde(prev[4])).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 10 });
        expect(govde(prev[5])).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(toastMocks.success).toHaveBeenCalledWith("Rapor hazırlandı · 3 kayıt");
    });

    it("G168 sonuç satırı: otomatik uygulama sonrası önizleme gelince '3 kayıt bulundu.'; boş sonuçta filtre listesi + gevşetme önerisi", async () => {
        sunucuKur({ chat: () => akis([{ status: "complete", cevap: "Hazır.", tanim: ASISTAN_TANIMI, eylem: null }]) });
        await render();
        await gonder("derdest davalar");
        await bekle(8);
        const balonlar = () => Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar()).toHaveLength(2);
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[1].textContent).toContain("3 kayıt bulundu.");
        expect(toastMocks.success).toHaveBeenCalledWith("Rapor hazırlandı · 3 kayıt");

        // Boş sonuç
        act(() => root!.unmount()); root = null; container.remove();
        container = document.createElement("div"); document.body.appendChild(container);
        sunucuKur({ chat: () => akis([{ status: "complete", cevap: "Hazır.", tanim: ASISTAN_TANIMI, eylem: null }]), onizlemeToplam: 0 });
        await render();
        await gonder("derdest davalar");
        await bekle(8);
        const son = balonlar().at(-1)!;
        expect(son.textContent).toContain("Sonuç boş");
        expect(son.textContent).toContain("Durum · eşittir · Derdest");
    });

    it("G168 sohbetten şablon kaydı: 'bunu haftalık rapor olarak kaydet' → POST /templates {ad, tanim: bekleyen (geri alınmış kart)}, Gemini yok, toast; 'kaydet' → önerilen ad", async () => {
        sunucuKur({ chat: () => akis([{ status: "complete", cevap: "Hazır.", tanim: ASISTAN_TANIMI, eylem: null }]) });
        await render();
        await gonder("derdest davalar");
        await bekle(8);
        // G174: hemen uygulandı → Geri al ile kart bekleyene alınır; kaydetme bekleyen tanımı alır
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        await gonder("bunu haftalık rapor olarak kaydet");
        await bekle(8);
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(1);
        const post = cagrilar("/api/reports/templates", "POST");
        expect(post).toHaveLength(1);
        expect(govde(post[0])).toEqual({ ad: "haftalık rapor", aciklama: "", paylasimli: false, tanim: ASISTAN_TANIMI });
        expect(toastMocks.success).toHaveBeenCalledWith("Şablon kaydedildi", expect.objectContaining({ description: "haftalık rapor" }));
        const balonlar = () => Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar().at(-1)!.textContent).toContain('"haftalık rapor" adıyla şablonlara kaydedildi');
        // Kaydetmek uygulamak değildir: oluşturucu değişmedi, kart hâlâ onay bekliyor
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(butonVar("Onayla ve uygula", balonlar()[0])).toBe(true);

        await gonder("kaydet");
        await bekle(8);
        const ikinci = cagrilar("/api/reports/templates", "POST")[1];
        expect(govde(ikinci).ad).toBe("Davalar · Derdest");        // sablonAdiOner (filtreden)
        expect(govde(ikinci).tanim).toEqual(ASISTAN_TANIMI);
    });

    it("YEREL indirme: geri alınmış kart beklerken 'excel indir' Gemini'ye gitmez, /export xlsx kaynak:asistan; kart rozet alır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Hazır.", tanim: ASISTAN_TANIMI, eylem: null }]),
        });
        await render();
        await gonder("derdest davalar");
        await bekle(8);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        await tikla($("[data-testid='tanim-geri-al']"));                        // bekleyen = asistan tanımı

        await gonder("excel indir");
        await bekle(8);
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(1);
        const exp = cagrilar("/api/reports/export", "POST");
        expect(exp).toHaveLength(1);
        expect(govde(exp[0])).toEqual({ tanim: ASISTAN_TANIMI, format: "xlsx", sablon_id: null, kaynak: "asistan" });
        expect(indirmeler).toEqual(["hukdok-rapor-davalar-20260906-1500.xlsx"]);
        const balonlar = Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar[0].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar.at(-1)!.textContent).toContain("Excel indiriliyor");
    });

    it("G174/G175 liste balonu: 'hangi durumlar var' Gemini'ye GİTMEZ, katalogdan Durum değerleri (Derdest/Karar) listelenir; tık → `onFiltreEkle`: filtre şeride eklenir (eq), önizleme hemen, toast; ikinci değer aynı çipe (in)", async () => {
        sunucuKur();
        await render();
        expect(onizlemeler()).toHaveLength(1);
        await gonder("hangi durumlar var");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        const liste = konusma().querySelector("[data-testid='deger-listesi']")!;
        expect(liste.getAttribute("data-alan")).toBe("status");
        const secenekler = Array.from(liste.querySelectorAll("[role='option']"));
        expect(secenekler.map(s => s.getAttribute("data-deger"))).toEqual(["Derdest", "Karar"]);

        await tikla(secenekler[0]);
        // Girdiye yazılmaz; tanım şeridine çip düşer, önizleme filtreli gider, toast
        expect(girdi().value).toBe("");
        expect(onizlemeler()).toHaveLength(2);
        expect(sonOnizleme().tanim).toEqual({ ...VARSAYILAN_TANIM, filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }] });
        expect(cipler()).toEqual(["DurumDerdest"]);
        expect(toastMocks.success).toHaveBeenCalledWith("Filtre eklendi · Durum: Derdest");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);

        // Aynı alanın dolu çoklu seçimine ikinci değer eklenir (ayrı filtre değil): in [Derdest, Karar]
        await tikla(secenekler[1]);
        expect(onizlemeler()).toHaveLength(3);
        expect(sonOnizleme().tanim.filtreler).toEqual([{ alan: "status", op: "in", deger: ["Derdest", "Karar"] }]);
        expect(cipler()).toEqual(["DurumDerdest, Karar"]);
        // Şeritten × → filtre düşer, önizleme hemen filtresiz
        await tikla(byLabel("Durum filtresini kaldır"));
        expect(onizlemeler()).toHaveLength(4);
        expect(sonOnizleme().tanim).toEqual(VARSAYILAN_TANIM);
    });

    it("eylem onizle + tanim null: oluşturucudaki mevcut tanımla YENİDEN önizler (aynı tanım olsa da); Geri al yok", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Mevcut tanımı önizliyorum.", tanim: null, eylem: "onizle" }]),
        });
        await render();
        expect(onizlemeler()).toHaveLength(1);
        await gonder("bunu önizle");
        await bekle(8);

        const prev = onizlemeler();
        expect(prev).toHaveLength(2);
        expect(govde(prev[1]).tanim).toEqual(VARSAYILAN_TANIM);
        expect(konusma().querySelector("[data-testid='tanim-ozeti']")).toBeNull();
        expect(container.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
    });

    it("asistan tanımının veri kaynağı katalogda yoksa: otomatik uygulama denemesi toast'la reddedilir, kart anahtarı olduğu gibi gösterip BEKLER; Onayla → yine toast + oluşturucu değişmez; düğme kalır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "?", tanim: { ...ASISTAN_TANIMI, veri_kaynagi: "yok_boyle" }, eylem: null }]),
        });
        await render();
        await gonder("x");

        const asistan = konusma().querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.querySelector("[data-testid='tanim-kaynak']")?.textContent).toBe("yok_boyle");
        // G174: sayfa otomatik uygulamayı reddetti → toast bir kez, kart bekliyor (rozet yok, Onayla var)
        expect(toastMocks.error).toHaveBeenCalledTimes(1);
        expect(toastMocks.error).toHaveBeenCalledWith("Asistan tanımı uygulanamadı", expect.objectContaining({ description: expect.stringContaining("yok_boyle") }));
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);
        expect(girdi().placeholder).toContain("Düzeltme");

        await tikla(butonBul("Onayla ve uygula", asistan));
        expect(toastMocks.error).toHaveBeenCalledTimes(2);
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(onizlemeler()).toHaveLength(1);
        expect(toastMocks.success).not.toHaveBeenCalled();

        // İndirme düğmesi de aynı yoldan reddeder
        await tikla(butonBul("Excel indir", asistan));
        expect(toastMocks.error).toHaveBeenCalledTimes(3);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
    });

    // ---------------------------------------------------------------- warning / failed / 409 / 403

    it("warning olayları asistan mesajının altında sarı şerit olarak görünür", async () => {
        sunucuKur({
            chat: () => akis([
                { status: "warning", message: "Tanım doğrulanamadı, tanım=null ile devam" },
                { status: "complete", cevap: "Hangi veri kaynağını istiyorsunuz?", tanim: null, eylem: null },
            ]),
        });
        await render();
        await gonder("belirsiz istek");

        const seritler = konusma().querySelectorAll("[data-testid='sohbet-uyari']");
        expect(seritler).toHaveLength(1);
        expect(seritler[0].textContent).toContain("Tanım doğrulanamadı, tanım=null ile devam");
        expect(konusma().querySelector("[data-testid='tanim-ozeti']")).toBeNull();
        expect(butonVar("Oluşturucuya uygula")).toBe(false);
    });

    it("failed: error_ozet kırmızı kutu + error_kod ipucu (gemini_saturated → biraz sonra); tanınmayan etiket analysis_error gibi", async () => {
        let sayac = 0;
        sunucuKur({
            chat: () => {
                sayac += 1;
                return sayac === 1
                    ? akis([{ status: "failed", error_ozet: "Yapay zekâ servisi şu an yoğun.", error_kod: "gemini_saturated" }])
                    : akis([{ status: "failed", error_ozet: "Bilinmeyen sorun.", error_kod: "yepyeni_etiket" }]);
            },
        });
        await render();

        await gonder("ilk");
        let hatalar = konusma().querySelectorAll("[data-testid='sohbet-hata']");
        expect(hatalar).toHaveLength(1);
        expect(hatalar[0].querySelector("[role='alert']")).not.toBeNull();
        expect(hatalar[0].textContent).toContain("Yapay zekâ servisi şu an yoğun.");
        expect(hatalar[0].textContent).toContain("biraz sonra");
        // Girdi yeniden açık — tekrar denenebilir
        expect(girdi().disabled).toBe(false);

        await gonder("ikinci");
        hatalar = konusma().querySelectorAll("[data-testid='sohbet-hata']");
        expect(hatalar).toHaveLength(2);
        expect(hatalar[1].textContent).toContain("Bilinmeyen sorun.");
        expect(hatalar[1].textContent).toContain("Beklenmeyen bir hata oldu");
        expect(hatalar[1].textContent).toContain("yepyeni_etiket");
        // Hata toast'a gitmez — konuşmada okunur
        expect(toastMocks.error).not.toHaveBeenCalled();
    });

    it("409: satır ve konuşma kalkar, tek toast ile bildirilir; manuel akış çalışır", async () => {
        sunucuKur({ chat: () => failJson(409, { detail: "rapor_asistani kapalı" }) });
        await render();
        expect(container.querySelector("[data-testid='asistan-satiri']")).not.toBeNull();
        await gonder("merhaba");

        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-konusmasi']")).toBeNull();
        expect(container.querySelector("[aria-label='Asistana mesaj']")).toBeNull();
        expect(butonVar("Asistan")).toBe(false);
        expect(toastMocks.error).toHaveBeenCalledTimes(1);
        expect(toastMocks.error).toHaveBeenCalledWith("Rapor asistanı kapalı", expect.objectContaining({ description: expect.stringContaining("kapalı") }));
        // G175: satırın yerine bilgi kartı gelir
        expect($("[data-testid='rapor-sekmesi']").firstElementChild?.getAttribute("data-testid")).toBe("asistan-kapali-karti");

        // Manuel yol etkilenmez: kolon değişimi (şerit "+ Kolon") hemen önizler
        expect(onizlemeler()).toHaveLength(1);
        await kolonEkle("status");
        expect(onizlemeler()).toHaveLength(2);
    });

    it("403: yönetici uyarısı konuşmada; satır kalır (403 anahtar değil, yetki)", async () => {
        sunucuKur({ chat: () => failJson(403, { detail: "admin gerekli" }) });
        await render();
        await gonder("merhaba");

        const hata = konusma().querySelector("[data-testid='sohbet-hata']")!;
        expect(hata.textContent).toContain("yalnız yöneticilere");
        expect(container.querySelector("[data-testid='asistan-satiri']")).not.toBeNull();
        expect(girdi().disabled).toBe(false);
        expect(toastMocks.error).not.toHaveBeenCalled();
    });

    // ---------------------------------------------------------------- girdi davranışı

    it("boş mesaj gönderilmez (Enter/Gönder pasif); gönderim sırasında girdi, Gönder ve çipler kilitli, akış durumu; Sohbeti temizle", async () => {
        const bekleyen = bekleyenAkis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]);
        sunucuKur({ chat: () => bekleyen.res });
        await render();
        const g = girdi();

        // Boş → gönderilmez
        await tus(g, "Enter");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        expect(butonBul("Gönder").disabled).toBe(true);
        yaz(g, "   ");
        await tus(g, "Enter");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        expect(konusmaVar()).toBe(false);

        yaz(g, "satır 1");
        expect(butonBul("Gönder").disabled).toBe(false);

        // Gönder → akış bekliyor → kilitli
        await tus(g, "Enter");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(1);
        expect(g.disabled).toBe(true);
        expect(butonBul("Gönder").disabled).toBe(true);
        expect(Array.from(container.querySelectorAll<HTMLButtonElement>("[data-testid='ornek-istem']")).every(b => b.disabled)).toBe(true);
        expect(konusma().querySelector("[data-testid='akis-durumu']")).not.toBeNull();
        expect(byLabel<HTMLButtonElement>("Sohbeti temizle").disabled).toBe(true);

        await act(async () => { bekleyen.coz(); });
        await bekle(8);
        expect(g.disabled).toBe(false);
        expect(konusma().querySelector("[data-testid='akis-durumu']")).toBeNull();
        expect(konusma().querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(1);

        await tikla(byLabel("Sohbeti temizle"));
        expect(konusma().querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(0);
        expect(konusma().querySelector("[data-testid='asistan-bos']")).not.toBeNull();
    });
});
