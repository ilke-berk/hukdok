// @vitest-environment jsdom
// ReportsPage (G135) — Asistan paneli: anahtar kapısı (kapalı → düğme yok, manuel akış çalışır);
// gönderilen gövde `{mesajlar (≤20), mevcut_tanim}`; `complete`+`tanim` → "Oluşturucuya uygula"
// oluşturucu state'ini değiştirir (öncesinde değişmez) + bayat rozeti; `eylem:"indir_xlsx"` →
// otomatik uygulama + `/export` `kaynak:"asistan"`; `eylem:"onizle"` → önizleme; `warning` şerit;
// `failed` error_kod ipucu (tanınmayan → analysis_error); 409 → şerit + düğme pasif; Enter/Shift+Enter.
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

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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

describe("ReportsPage asistan paneli (G135)", () => {
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
    const panel = () => $("[data-testid='asistan-paneli']");
    const seciliKolonlar = () => Array.from(container.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));

    function yaz(el: HTMLTextAreaElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
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

    /** Paneli açıp mesaj gönderir (Enter). */
    async function gonder(metin: string) {
        const girdi = byLabel<HTMLTextAreaElement>("Asistana mesaj");
        yaz(girdi, metin);
        await tus(girdi, "Enter");
        await bekle(8);
    }

    // ---------------------------------------------------------------- anahtar kapısı

    it("anahtar kapalıyken Asistan düğmesi ve panel yok; manuel önizleme akışı etkilenmez", async () => {
        sunucuKur({ anahtar: false });
        await render();

        expect(cagrilar("/api/admin/settings")).toHaveLength(1);
        // Sıra: katalog ilk istek (G133 sözleşmesi), anahtar sonra
        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/catalog");
        expect(butonVar("Asistan")).toBe(false);
        expect(container.querySelector("[data-testid='asistan-paneli']")).toBeNull();

        await tikla(butonBul("Önizle"));
        expect(cagrilar("/api/reports/preview", "POST")).toHaveLength(1);
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
    });

    it("anahtar okunamazsa (uç hatası) panel yine gizli, toast yok", async () => {
        sunucuKur({ ayarHatasi: true });
        await render();

        expect(butonVar("Asistan")).toBe(false);
        expect(toastMocks.error).not.toHaveBeenCalled();
        expect(container.querySelector("#rapor-kaynak")).not.toBeNull();
    });

    it("anahtar açıkken düğme görünür; tıklayınca panel + 3 örnek istem; çip girdiye yazılır; kapat düğmesi", async () => {
        sunucuKur({ anahtar: true });
        await render();

        expect(container.querySelector("[data-testid='asistan-paneli']")).toBeNull();
        await tikla(butonBul("Asistan"));
        const p = panel();
        expect(p.getAttribute("aria-label")).toBe("Rapor asistanı");
        const cipler = p.querySelectorAll("[data-testid='ornek-istem']");
        expect(cipler).toHaveLength(3);

        await tikla(cipler[1]);
        expect(byLabel<HTMLTextAreaElement>("Asistana mesaj").value).toBe(cipler[1].textContent);
        // Henüz gönderilmedi
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);

        await tikla(byLabel("Asistanı kapat"));
        expect(container.querySelector("[data-testid='asistan-paneli']")).toBeNull();
    });

    // ---------------------------------------------------------------- gövde + uygula

    it("Enter gönderir: gövde {mesajlar, mevcut_tanim}; complete+tanim → özet kartı; uygula ANCAK düğmeyle; bayat rozeti", async () => {
        sunucuKur({
            chat: () => akis([
                { status: "info", message: "Rapor tanımı hazırlanıyor" },
                { status: "complete", cevap: "Derdest davaları hazırladım.", tanim: ASISTAN_TANIMI, eylem: null },
            ]),
        });
        await render();
        // Önce manuel önizleme: bayat rozeti için referans
        await tikla(butonBul("Önizle"));
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();

        await tikla(butonBul("Asistan"));
        await gonder("Derdest davaları listele");

        const post = cagrilar("/api/reports/chat", "POST");
        expect(post).toHaveLength(1);
        const g = govde(post[0]);
        expect(Object.keys(g).sort()).toEqual(["mesajlar", "mevcut_tanim"]);
        expect(g.mesajlar).toEqual([{ rol: "user", icerik: "Derdest davaları listele" }]);
        expect(g.mevcut_tanim).toEqual(VARSAYILAN_TANIM);

        const p = panel();
        expect(p.querySelector("[data-testid='sohbet-kullanici']")?.textContent).toBe("Derdest davaları listele");
        const asistan = p.querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.textContent).toContain("Derdest davaları hazırladım.");
        const ozet = asistan.querySelector("[data-testid='tanim-ozeti']")!;
        expect(ozet.textContent).toContain("Davalar");
        expect(ozet.textContent).toContain("3"); // kolon
        // Girdi temizlendi, akış durumu bitince kilit kalktı
        expect(byLabel<HTMLTextAreaElement>("Asistana mesaj").value).toBe("");
        expect(byLabel<HTMLTextAreaElement>("Asistana mesaj").disabled).toBe(false);

        // Uygulamadan ÖNCE oluşturucu değişmedi
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();

        await tikla(butonBul("Oluşturucuya uygula", asistan));

        expect($<HTMLSelectElement>("#rapor-kaynak").value).toBe("davalar");
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        const filtreler = container.querySelectorAll("[data-testid='filtre-satiri']");
        expect(filtreler).toHaveLength(1);
        expect(byLabel<HTMLSelectElement>("Alan", filtreler[0]).value).toBe("status");
        expect(container.querySelectorAll("[data-testid='siralama-satiri']")).toHaveLength(1);
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(butonVar("Oluşturucuya uygula", asistan)).toBe(false);
        expect(toastMocks.success).toHaveBeenCalledWith("Asistan tanımı oluşturucuya uygulandı");
        // Önizleme artık bayat
        expect(container.querySelector("[data-testid='bayat-rozeti']")).not.toBeNull();
        // Eylem yoktu: ne export ne yeni önizleme
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        expect(cagrilar("/api/reports/preview", "POST")).toHaveLength(1);
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
        await tikla(butonBul("Asistan"));

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

    it("eylem indir_xlsx: tanım OTOMATİK uygulanır + /export gövdesi {tanim, format:xlsx, sablon_id:null, kaynak:asistan}; dosya adı başlıktan", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Excel hazırlanıyor.", tanim: ASISTAN_TANIMI, eylem: "indir_xlsx" }]),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("Derdest davaları Excel indir");
        await bekle(8);

        const exp = cagrilar("/api/reports/export", "POST");
        expect(exp).toHaveLength(1);
        const g = govde(exp[0]);
        expect(Object.keys(g).sort()).toEqual(["format", "kaynak", "sablon_id", "tanim"]);
        expect(g).toEqual({ tanim: ASISTAN_TANIMI, format: "xlsx", sablon_id: null, kaynak: "asistan" });
        expect(indirmeler).toEqual(["hukdok-rapor-davalar-20260906-1500.xlsx"]);
        expect(toastMocks.success).toHaveBeenCalledWith("İndirildi: hukdok-rapor-davalar-20260906-1500.xlsx");

        // Oluşturucu da değişti, kart "uygulandı" rozetinde, düğme yok
        expect(seciliKolonlar()).toEqual(["tracking_no", "status", "opening_date"]);
        const asistan = panel().querySelector("[data-testid='sohbet-asistan']")!;
        expect(asistan.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(butonVar("Oluşturucuya uygula", asistan)).toBe(false);
        expect(asistan.textContent).toContain("Excel indirme");
    });

    it("eylem indir_csv → format csv; 413'te tavan mesajı, dosya inmez, tanım yine uygulanır", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "CSV.", tanim: MUVEKKIL_TANIMI, eylem: "indir_csv" }]),
            exportCevabi: () => failJson(413, { detail: { sebep: "satir_limiti", toplam: 120000, limit: 50000 } }),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("müvekkilleri csv indir");
        await bekle(8);

        const g = govde(cagrilar("/api/reports/export", "POST")[0]);
        expect(g.format).toBe("csv");
        expect(g.kaynak).toBe("asistan");
        expect(indirmeler).toEqual([]);
        expect(toastMocks.error).toHaveBeenCalledWith("Rapor satır tavanını aşıyor", expect.objectContaining({ description: expect.stringContaining("limit") }));
        // Kaynak değişti (davalar → muvekkiller) — asistan uygulamasında onay SORULMAZ
        expect(confirmMock.fn).not.toHaveBeenCalled();
        expect($<HTMLSelectElement>("#rapor-kaynak").value).toBe("muvekkiller");
        expect(seciliKolonlar()).toEqual(["name", "city"]);
    });

    it("eylem onizle: tanım uygulanır ve önizleme asistanın tanımıyla istenir; export yok", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Önizliyorum.", tanim: ASISTAN_TANIMI, eylem: "onizle" }]),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("önizle");
        await bekle(8);

        const prev = cagrilar("/api/reports/preview", "POST");
        expect(prev).toHaveLength(1);
        expect(govde(prev[0])).toEqual({ tanim: ASISTAN_TANIMI, sayfa: 1, sayfa_boyu: 50 });
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
        expect(cagrilar("/api/reports/export", "POST")).toHaveLength(0);
        // Önizlenen = taslak → bayat değil
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
    });

    it("eylem onizle + tanim null: oluşturucudaki mevcut tanımla önizler", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "Mevcut tanımı önizliyorum.", tanim: null, eylem: "onizle" }]),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("bunu önizle");
        await bekle(8);

        const prev = cagrilar("/api/reports/preview", "POST");
        expect(prev).toHaveLength(1);
        expect(govde(prev[0]).tanim).toEqual(VARSAYILAN_TANIM);
        expect(panel().querySelector("[data-testid='tanim-ozeti']")).toBeNull();
    });

    it("asistan tanımının veri kaynağı katalogda yoksa uygulanmaz: toast + oluşturucu değişmez", async () => {
        sunucuKur({
            chat: () => akis([{ status: "complete", cevap: "?", tanim: { ...ASISTAN_TANIMI, veri_kaynagi: "yok_boyle" }, eylem: null }]),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("x");
        const asistan = panel().querySelector("[data-testid='sohbet-asistan']")!;
        await tikla(butonBul("Oluşturucuya uygula", asistan));

        expect(toastMocks.error).toHaveBeenCalledWith("Asistan tanımı uygulanamadı", expect.objectContaining({ description: expect.stringContaining("yok_boyle") }));
        expect(seciliKolonlar()).toEqual(["tracking_no", "subject"]);
        expect(butonVar("Oluşturucuya uygula", asistan)).toBe(true);
    });

    // ---------------------------------------------------------------- warning / failed / 409

    it("warning olayları asistan mesajının altında sarı şerit olarak görünür", async () => {
        sunucuKur({
            chat: () => akis([
                { status: "warning", message: "Tanım doğrulanamadı, tanım=null ile devam" },
                { status: "complete", cevap: "Hangi veri kaynağını istiyorsunuz?", tanim: null, eylem: null },
            ]),
        });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("belirsiz istek");

        const seritler = panel().querySelectorAll("[data-testid='sohbet-uyari']");
        expect(seritler).toHaveLength(1);
        expect(seritler[0].textContent).toContain("Tanım doğrulanamadı, tanım=null ile devam");
        expect(panel().querySelector("[data-testid='tanim-ozeti']")).toBeNull();
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
        await tikla(butonBul("Asistan"));

        await gonder("ilk");
        let hatalar = panel().querySelectorAll("[data-testid='sohbet-hata']");
        expect(hatalar).toHaveLength(1);
        expect(hatalar[0].querySelector("[role='alert']")).not.toBeNull();
        expect(hatalar[0].textContent).toContain("Yapay zekâ servisi şu an yoğun.");
        expect(hatalar[0].textContent).toContain("biraz sonra");
        // Girdi yeniden açık — tekrar denenebilir
        expect(byLabel<HTMLTextAreaElement>("Asistana mesaj").disabled).toBe(false);

        await gonder("ikinci");
        hatalar = panel().querySelectorAll("[data-testid='sohbet-hata']");
        expect(hatalar).toHaveLength(2);
        expect(hatalar[1].textContent).toContain("Bilinmeyen sorun.");
        expect(hatalar[1].textContent).toContain("Beklenmeyen bir hata oldu");
        expect(hatalar[1].textContent).toContain("yepyeni_etiket");
        // Hata toast'a gitmez — panelde okunur
        expect(toastMocks.error).not.toHaveBeenCalled();
    });

    it("409: panelde okunur uyarı şeridi, girdi kilitli, başlık düğmesi pasif + ipucu; manuel akış çalışır", async () => {
        sunucuKur({ chat: () => failJson(409, { detail: "rapor_asistani kapalı" }) });
        await render();
        const dugme = butonBul("Asistan");
        expect(dugme.disabled).toBe(false);
        await tikla(dugme);
        await gonder("merhaba");

        const serit = panel().querySelector("[data-testid='asistan-kapali-seridi']")!;
        expect(serit.getAttribute("role")).toBe("alert");
        expect(serit.textContent).toContain("kapalı");
        expect(byLabel<HTMLTextAreaElement>("Asistana mesaj").disabled).toBe(true);
        expect(panel().querySelectorAll("[data-testid='sohbet-hata']")).toHaveLength(1);

        expect(butonBul("Asistan").disabled).toBe(true);
        expect(butonBul("Asistan").title).toContain("kapalı");

        // Manuel yol etkilenmez
        await tikla(butonBul("Önizle"));
        expect(cagrilar("/api/reports/preview", "POST")).toHaveLength(1);
    });

    it("403: yönetici uyarısı panelde", async () => {
        sunucuKur({ chat: () => failJson(403, { detail: "admin gerekli" }) });
        await render();
        await tikla(butonBul("Asistan"));
        await gonder("merhaba");

        const hata = panel().querySelector("[data-testid='sohbet-hata']")!;
        expect(hata.textContent).toContain("yalnız yöneticilere");
        expect(butonBul("Asistan").disabled).toBe(false); // 403 anahtar değil, yetki
    });

    // ---------------------------------------------------------------- girdi davranışı

    it("Shift+Enter göndermez; boş mesaj gönderilmez; gönderim sırasında girdi ve Gönder kilitli; Sohbeti temizle", async () => {
        const bekleyen = bekleyenAkis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]);
        sunucuKur({ chat: () => bekleyen.res });
        await render();
        await tikla(butonBul("Asistan"));
        const girdi = byLabel<HTMLTextAreaElement>("Asistana mesaj");

        // Boş → gönderilmez
        await tus(girdi, "Enter");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        expect(butonBul("Gönder").disabled).toBe(true);

        yaz(girdi, "satır 1");
        await tus(girdi, "Enter", true);
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(0);
        expect(girdi.value).toBe("satır 1");

        // Gönder → akış bekliyor → kilitli
        await tus(girdi, "Enter");
        expect(cagrilar("/api/reports/chat", "POST")).toHaveLength(1);
        expect(girdi.disabled).toBe(true);
        expect(butonBul("Gönder").disabled).toBe(true);
        expect(panel().querySelector("[data-testid='akis-durumu']")).not.toBeNull();
        expect(byLabel<HTMLButtonElement>("Sohbeti temizle").disabled).toBe(true);

        await act(async () => { bekleyen.coz(); });
        await bekle(8);
        expect(girdi.disabled).toBe(false);
        expect(panel().querySelector("[data-testid='akis-durumu']")).toBeNull();
        expect(panel().querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(1);

        await tikla(byLabel("Sohbeti temizle"));
        expect(panel().querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(0);
        expect(panel().querySelector("[data-testid='asistan-bos']")).not.toBeNull();
    });
});
