// @vitest-environment jsdom
// ReportsPage (G135 → G138 → G143 → G167 teyit döngüsü: tanım kartta bekler; Onayla / İndir / sözle onay) — Asistan ÖN PLANDA: anahtar açıkken Rapor sekmesinin İLK öğesi
// AssistantBar (anahtar okunana dek iskelet; kapalı/409 → satır yok, araç çubuğunda "Asistan" düğmesi de
// yok, yan panel `Sheet` asistan için kullanılmaz; manuel akış çalışır); gönderilen gövde `{mesajlar (≤20),
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
    };

    function sunucuKur(ayar: SunucuAyari = {}) {
        fetchMock.mockImplementation(async (url: string, opts?: RequestInit) => {
            const method = opts?.method ?? "GET";
            if (url === "/api/reports/catalog") return okJson(KATALOG);
            if (url === "/api/reports/preview") {
                const g = JSON.parse(opts!.body as string);
                return okJson({ ...ONIZLEME, sayfa: g.sayfa, sayfa_boyu: g.sayfa_boyu });
            }
            if (url === "/api/reports/templates" && method === "GET") return okJson([]);
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
    /** G139: kaynak kartla seçilir (`role=radio` + `aria-checked`). */
    const seciliKaynak = () => container.querySelector("[data-kaynak][aria-checked='true']")?.getAttribute("data-kaynak") ?? null;
    /**
     * G139: kolon listesi ana ekranda durmaz — seçili kolonların kanıtı SON önizleme gövdesi
     * (uygulanan tanım kendiliğinden önizlenir) + "Kolonlar (N)" düğme metni.
     */
    const seciliKolonlar = () => {
        const kolonlar = sonOnizleme().tanim.kolonlar as string[];
        expect($("[data-testid='kolon-dugmesi']").textContent?.trim()).toBe(`Kolonlar (${kolonlar.length})`);
        return kolonlar;
    };
    /** Kolon checkbox'ları yan panelde (Radix portal → document.body); açıp paneli döndürür. */
    async function kolonPaneliAc(): Promise<ParentNode> {
        await tikla($("[data-testid='kolon-dugmesi']"));
        const p = document.body.querySelector("[data-testid='kolon-paneli']");
        if (!p) throw new Error("kolon paneli açılmadı");
        return p;
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
        // Rapor sekmesinin ilk öğesi kaynak kartları
        expect($("[data-testid='rapor-sekmesi']").firstElementChild?.getAttribute("data-testid")).toBe("kaynak-kartlari");

        // Açılış önizlemesi geldi; kolon değişimi (yan panel) hemen yeniden önizler
        expect(onizlemeler()).toHaveLength(1);
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
        await tikla(byLabel("Durum", await kolonPaneliAc()));
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
        const sekme = $("[data-testid='rapor-sekmesi']");
        expect(sekme.firstElementChild?.getAttribute("data-testid")).toBe("asistan-satiri");
        const kartlar = $("[data-testid='kaynak-kartlari']");
        expect(Boolean(satir().compareDocumentPosition(kartlar) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);
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

        // Müvekkiller kartı → müvekkil örnekleri
        await tikla($("[data-kaynak='muvekkiller']"));
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

    it("Enter gönderir: gövde {mesajlar, mevcut_tanim}; complete+tanim → TEYİT KARTI (okunur kolon/filtre/sıralama), UYGULANMAZ; 'Onayla ve uygula' → oluşturucu + /preview + toast; 'Geri al' eski taslağı geri getirir", async () => {
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
        // G167: teyit kartı OKUNUR — sayı değil etiket/operatör/değer
        const ozet = asistan.querySelector("[data-testid='tanim-ozeti']")!;
        expect(ozet.querySelector("[data-testid='tanim-kaynak']")?.textContent).toBe("Davalar");
        expect(Array.from(ozet.querySelectorAll("[data-testid='tanim-kolonlar'] span")).map(x => x.textContent))
            .toEqual(["Ofis No", "Durum", "Açılış Tarihi"]);
        expect(Array.from(ozet.querySelectorAll("[data-testid='tanim-filtreler'] li")).map(x => x.textContent))
            .toEqual(["Durum · eşittir · Derdest"]);
        expect(ozet.querySelector("[data-testid='tanim-siralama']")?.textContent).toBe("Açılış Tarihi ↓");
        expect(ozet.querySelector("[data-testid='tanim-teyit-notu']")?.textContent).toContain("onaylayın");
        // Girdi temizlendi, akış durumu bitince kilit kalktı; yer tutucu düzeltmeye çağırır
        expect(girdi().value).toBe("");
        expect(girdi().disabled).toBe(false);
        expect(girdi().placeholder).toContain("Düzeltme");

        // UYGULANMADI: oluşturucu ve önizleme aynı, toast yok, düğmeler bekliyor
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);
        expect(butonVar("Excel indir", asistan)).toBe(true);
        expect(butonVar("CSV indir", asistan)).toBe(true);
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(onizlemeler()).toHaveLength(1);
        expect(toastMocks.success).not.toHaveBeenCalled();

        // Onayla → oluşturucu değişti, önizleme asistan tanımıyla, toast satır sayısıyla
        await tikla(butonBul("Onayla ve uygula", asistan));
        await bekle(8);
        expect(butonVar("Onayla ve uygula", asistan)).toBe(false);
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-teyit-notu']")).toBeNull();
        expect(seciliKaynak()).toBe("davalar");
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        // Filtre şeride çözüldü (status eq Derdest → çoklu seçim çipi); operatör seçici yok
        expect(cipler()).toEqual(["DurumDerdest"]);
        expect(container.querySelector("[aria-label='Operatör']")).toBeNull();
        expect(onizlemeler()).toHaveLength(2);
        expect(sonOnizleme()).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(toastMocks.success).toHaveBeenCalledWith("Rapor hazırlandı · 3 kayıt");
        expect(girdi().placeholder).not.toContain("Düzeltme");
        // Eylem yoktu: export yok; indirme düğmeleri kartta KALIR
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        expect(butonVar("Excel indir", asistan)).toBe(true);

        // Geri al: eski taslak + önizleme geri gelir; bağlantı düşer, onay düğmesi geri gelir
        await tikla($("[data-testid='tanim-geri-al']", asistan));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(cipler()).toEqual([]);
        expect(onizlemeler()).toHaveLength(3);
        expect(sonOnizleme()).toEqual({ tanim: VARSAYILAN_TANIM, sayfa: 1, sayfa_boyu: 10 });
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);

        // Yeniden onayla → yine rozet + Geri al
        await tikla(butonBul("Onayla ve uygula", asistan));
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        expect(onizlemeler()).toHaveLength(4);
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
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
        expect(ilk.querySelector("[data-testid='tanim-geri-al']")).toBeNull();     // G167: onay bekliyor
        await tikla(butonBul("Onayla ve uygula", ilk));
        expect(ilk.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();

        // Manuel değişiklik: kolon panelinden "Durum" (asistan seçmişti) çıkarılır → adım düşer
        await tikla(byLabel("Durum", await kolonPaneliAc()));
        expect(seciliKolonlar()).toEqual(["tracking_no", "opening_date"]);
        expect(container.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(ilk.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();

        // İkinci uygulama (kaynak değişir; sayfa onayı SORULMAZ, kartın onayı yeter) → Geri al yalnız ikinci balonda
        await gonder("ikinci");
        const balonlar = Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar).toHaveLength(2);
        expect(seciliKaynak()).toBe("davalar");                                   // henüz uygulanmadı
        await tikla(butonBul("Onayla ve uygula", balonlar[1]));
        expect(confirmMock.fn).not.toHaveBeenCalled();
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(balonlar[0].querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(balonlar[1].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();

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

    it("eylem indir_xlsx: kart 'indirme önerdi' notuyla BEKLER; 'Excel indir' → tanım uygulanır + /export gövdesi {tanim, format:xlsx, sablon_id:null, kaynak:asistan}; dosya adı başlıktan", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Excel hazırlanıyor.", tanim: ASISTAN_TANIMI, eylem: "indir_xlsx" }]),
        });
        await render();
        await gonder("Derdest davaları Excel indir");
        await bekle(8);

        // G167: asistanın önerisi hemen yürümez — export yok, kart indirmeyi bekler
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        expect(indirmeler).toEqual([]);
        const kart = konusma().querySelector("[data-testid='sohbet-asistan']")!;
        expect(kart.querySelector("[data-testid='tanim-teyit-notu']")?.textContent).toContain("indirme önerdi");
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        await tikla(butonBul("Excel indir", kart));
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
        // İndirme düğmeleri kalır (tekrar indirilebilir)
        expect(butonVar("CSV indir", asistan)).toBe(true);
    });

    it("eylem indir_csv → 'CSV indir' tıklanınca format csv; 413'te tavan mesajı, dosya inmez, tanım yine uygulanır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "CSV.", tanim: MUVEKKIL_TANIMI, eylem: "indir_csv" }]),
            exportCevabi: () => failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }),
        });
        await render();
        await gonder("müvekkilleri csv indir");
        await bekle(8);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        await tikla(butonBul("CSV indir", konusma()));
        await bekle(8);

        const g = govde(cagrilar("/api/reports/export", "POST")[0]);
        expect(g.format).toBe("csv");
        expect(g.kaynak).toBe("asistan");
        expect(indirmeler).toEqual([]);
        expect(toastMocks.error).toHaveBeenCalledWith("Rapor satır tavanını aşıyor", expect.objectContaining({ description: expect.stringContaining("limit") }));
        // Kaynak değişti (davalar → muvekkiller) — asistan uygulamasında onay SORULMAZ
        expect(confirmMock.fn).not.toHaveBeenCalled();
        expect(seciliKaynak()).toBe("muvekkiller");
        expect(seciliKolonlar()).toEqual(["name", "city"]);
        expect(byLabel<HTMLInputElement>("Şehir içerir").value).toBe("İstanbul");
    });

    it("SÖZLE ONAY: ilk tanım kartta bekler (eylem onizle olsa da); ikinci cevap bekleyen tanımı AYNEN + onizle döndürünce hemen uygulanır ve önizlenir; export yok", async () => {
        let sayac = 0;
        sunucuKur({
            chat: () => {
                sayac += 1;
                return akis([{ status: "complete", cevap: sayac === 1 ? "Hazırladım, doğru mu?" : "Uyguluyorum.", tanim: ASISTAN_TANIMI, eylem: "onizle" }]);
            },
        });
        await render();
        await gonder("derdest davaları göster");
        await bekle(8);
        // İlk cevap: bekleyen tanım yoktu → kart bekler, uygulanmaz
        expect(onizlemeler()).toHaveLength(1);
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        const balonlar = () => Array.from(konusma().querySelectorAll("[data-testid='sohbet-asistan']"));
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).toBeNull();

        // "tamam": sunucuya mevcut_tanim = BEKLEYEN tanım gider; aynı tanım + eylem döner → sözle onay
        await gonder("tamam");
        await bekle(8);
        expect(govde(cagrilar("/api/reports/chat", "POST")[1]).mevcut_tanim).toEqual(ASISTAN_TANIMI);
        expect(balonlar()).toHaveLength(2);
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[1].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);

        const prev = onizlemeler();
        expect(prev).toHaveLength(2); // açılış + sözle onay
        expect(govde(prev[1])).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 10 });
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(toastMocks.success).toHaveBeenCalledWith("Rapor hazırlandı · 3 kayıt");
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

    it("asistan tanımının veri kaynağı katalogda yoksa: kart anahtarı olduğu gibi gösterir; Onayla → toast + oluşturucu değişmez; düğme kalır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "?", tanim: { ...ASISTAN_TANIMI, veri_kaynagi: "yok_boyle" }, eylem: null }]),
        });
        await render();
        await gonder("x");

        const asistan = konusma().querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.querySelector("[data-testid='tanim-kaynak']")?.textContent).toBe("yok_boyle");
        expect(toastMocks.error).not.toHaveBeenCalled();

        await tikla(butonBul("Onayla ve uygula", asistan));
        expect(toastMocks.error).toHaveBeenCalledWith("Asistan tanımı uygulanamadı", expect.objectContaining({ description: expect.stringContaining("yok_boyle") }));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(butonVar("Onayla ve uygula", asistan)).toBe(true);
        expect(asistan.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(onizlemeler()).toHaveLength(1);
        expect(toastMocks.success).not.toHaveBeenCalled();

        // İndirme düğmesi de aynı yoldan reddeder
        await tikla(butonBul("Excel indir", asistan));
        expect(toastMocks.error).toHaveBeenCalledTimes(2);
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
        expect($("[data-testid='rapor-sekmesi']").firstElementChild?.getAttribute("data-testid")).toBe("kaynak-kartlari");

        // Manuel yol etkilenmez: kolon değişimi (yan panel) hemen önizler
        expect(onizlemeler()).toHaveLength(1);
        await tikla(byLabel("Durum", await kolonPaneliAc()));
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
