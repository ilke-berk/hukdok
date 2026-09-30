// @vitest-environment jsdom
// OfisNoKodlariPanel (G241) — ofis no kod listelerinin yönetici yüzü: kategori
// kodları + sigorta şirketi kodları. Backend kuralları (çakışma, SG sabiti)
// test_ofis_no* testlerinde kilitli; burada panelin G235 uçlarına nasıl
// bağlandığı, kod alanının biçimlenmesi ve sunucu hatasının gösterimi sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

const adminMock = vi.hoisted(() => ({ value: true as boolean | null }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => adminMock.value }));

import { KOD_DEGISIKLIGI_UYARISI, OfisNoKodlariPanel } from "./OfisNoKodlariPanel";
import { anahtarlariAyir, kodBicimle, type KategoriKodu, type SigortaKodu } from "@/lib/ofisNoKodlari";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KATEGORILER: KategoriKodu[] = [
    { code: "DOKTOR", name: "Doktor", ofis_no_kodu: "DR", active: true },
    { code: "KURUM", name: "Kurum", ofis_no_kodu: "KR", active: true },
    { code: "YENI", name: "Yeni", ofis_no_kodu: null, active: true },
];
const SIGORTALAR: SigortaKodu[] = [
    { id: 1, kod: "AXA", ad: "Axa Sigorta", eslesme_anahtarlari: ["AXA"], aktif: true },
    { id: 2, kod: "KORU", ad: "Koru Sigorta", eslesme_anahtarlari: ["KORU"], aktif: false },
];

const okJson = (payload: unknown) => ({ ok: true, json: async () => payload });
const hata = (status: number, detail: unknown) => ({ ok: false, status, json: async () => ({ detail }) });

type Yanit = ReturnType<typeof okJson> | ReturnType<typeof hata>;

/** GET'ler sabit listeleri döner; yazma istekleri `yazma`'ya düşer (varsayılan: başarılı). */
function sunucu(yazma: (url: string, options: RequestInit) => Yanit = () => okJson({})) {
    fetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
        if (options?.method) return yazma(url, options);
        if (url === "/api/admin/kategori-kodlari") return okJson({ kategoriler: KATEGORILER });
        if (url === "/api/admin/sigorta-kodlari") return okJson({ kodlar: SIGORTALAR, varsayilan_kod: "SG" });
        throw new Error(`beklenmeyen GET: ${url}`);
    });
}

const yazmaCagrilari = () =>
    fetchMock.mock.calls
        .filter(([, o]) => (o as RequestInit | undefined)?.method)
        .map(([url, o]) => ({
            url: url as string,
            method: (o as RequestInit).method,
            body: JSON.parse((o as RequestInit).body as string),
        }));

describe("OfisNoKodlariPanel", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
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

    async function render() {
        root = createRoot(container);
        const client = new QueryClient();
        await act(async () => {
            root!.render(<QueryClientProvider client={client}><OfisNoKodlariPanel /></QueryClientProvider>);
        });
    }

    const alan = (etiket: string) => {
        const el = container.querySelector<HTMLInputElement>(`input[aria-label='${etiket}']`);
        if (!el) throw new Error(`alan yok: ${etiket}`);
        return el;
    };

    const dugme = (metinYaDaEtiket: string, kapsam: ParentNode = container) => {
        const el = Array.from(kapsam.querySelectorAll<HTMLButtonElement>("button")).find(
            b => b.getAttribute("aria-label") === metinYaDaEtiket || b.textContent?.trim() === metinYaDaEtiket);
        if (!el) throw new Error(`düğme yok: ${metinYaDaEtiket}`);
        return el;
    };

    const yaz = async (el: HTMLInputElement, deger: string) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        await act(async () => {
            setter.call(el, deger);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    };

    const tikla = async (el: Element) => {
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    };

    const satir = (testId: string) => container.querySelector<HTMLElement>(`[data-testid='${testId}']`)!;

    it("iki listeyi G235 uçlarından listeler, uyarıyı ve örnek numaraları gösterir", async () => {
        sunucu();

        await render();

        expect(fetchMock).toHaveBeenCalledWith("/api/admin/kategori-kodlari");
        expect(fetchMock).toHaveBeenCalledWith("/api/admin/sigorta-kodlari");
        expect(KOD_DEGISIKLIGI_UYARISI).toBe(
            "Kod değişikliği mevcut ofis numaralarını değiştirmez, yalnız yeni kartları etkiler.");
        expect(container.textContent).toContain(KOD_DEGISIKLIGI_UYARISI);
        // Her satırda örnek numara: kişi kategorisi, kurum kategorisi, sigorta şirketi.
        expect(satir("kategori-DOKTOR").textContent).toContain("DR.A.YILMAZ-0001-HUK");
        expect(satir("kategori-KURUM").textContent).toContain("KR.ENTHONE-0001-HUK");
        expect(satir("kategori-YENI").textContent).toContain("Kod tanımlı değil");
        expect(satir("sigorta-1").textContent).toContain("AXA-0001-DR.A.YILMAZ-HUK");
        expect(satir("sigorta-2").textContent).toContain("Pasif");
    });

    it("listede olmayan sigortacının SG kodu sabit satırdır, düzenlenemez", async () => {
        sunucu();

        await render();

        const sg = satir("sigorta-varsayilan");
        expect(sg.textContent).toContain("SG");
        expect(sg.textContent).toContain("SG-0001-DR.A.YILMAZ-HUK");
        expect(sg.querySelector("button")).toBeNull();
    });

    it("admin olmayan kullanıcıda bölüm görünmez ve uçlar çağrılmaz", async () => {
        adminMock.value = false;
        sunucu();

        await render();

        expect(container.textContent).toBe("");
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("adminlik henüz bilinmiyorken (null) de bölüm görünmez", async () => {
        adminMock.value = null;
        sunucu();

        await render();

        expect(container.textContent).toBe("");
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("kod alanı büyük ASCII harfe zorlanır ve 10 karakterde kesilir", async () => {
        sunucu();
        await render();

        await yaz(alan("Yeni sigorta kodu"), "güneş-1 sigortası");

        expect(alan("Yeni sigorta kodu").value).toBe("GUNESSIGOR");
        expect(kodBicimle("ışık")).toBe("ISIK");
        expect(kodBicimle("a1-b")).toBe("AB");
        expect(anahtarlariAyir("axa, aksa sigorta;AXA")).toEqual(["AXA", "AKSA", "SIGORTA"]);
    });

    it("boş ya da tek harfli kod sunucuya gitmeden reddedilir", async () => {
        sunucu();
        await render();

        await yaz(alan("Yeni sigorta şirketi adı"), "Güneş Sigorta");
        await tikla(dugme("Şirket ekle"));
        expect(container.querySelector("[role='alert']")?.textContent).toBe("Kod boş olamaz");

        await yaz(alan("Yeni sigorta kodu"), "g");
        await tikla(dugme("Şirket ekle"));
        expect(container.querySelector("[role='alert']")?.textContent).toBe("Kod en az 2 harf olmalı");
        expect(yazmaCagrilari()).toEqual([]);
    });

    it("yeni sigorta şirketi POST ile eklenir (eşleşme kelimeleri ASCII büyük harf)", async () => {
        sunucu();
        await render();

        await yaz(alan("Yeni sigorta kodu"), "gunes");
        await yaz(alan("Yeni sigorta şirketi adı"), " Güneş Sigorta ");
        await yaz(alan("Yeni sigorta eşleşme kelimeleri"), "güneş, gunes sigorta");
        await tikla(dugme("Şirket ekle"));

        expect(yazmaCagrilari()).toEqual([{
            url: "/api/admin/sigorta-kodlari",
            method: "POST",
            body: { kod: "GUNES", ad: "Güneş Sigorta", eslesme_anahtarlari: ["GUNES", "SIGORTA"] },
        }]);
        expect(toastMocks.success).toHaveBeenCalled();
        expect(alan("Yeni sigorta kodu").value).toBe("");
    });

    it("mükerrer kodda sunucunun 409 mesajı aynen gösterilir", async () => {
        sunucu(() => hata(409, "'AXA' kodu zaten kayıtlı"));
        await render();

        await yaz(alan("Yeni sigorta kodu"), "axa");
        await yaz(alan("Yeni sigorta şirketi adı"), "Axa İki");
        await tikla(dugme("Şirket ekle"));

        expect(container.querySelector("[role='alert']")?.textContent).toBe("'AXA' kodu zaten kayıtlı");
        expect(toastMocks.success).not.toHaveBeenCalled();
        // Form silinmez — kullanıcı kodu düzeltip yeniden dener.
        expect(alan("Yeni sigorta kodu").value).toBe("AXA");
    });

    it("sigorta satırı düzenlenir: PATCH kod + ad + eşleşme kelimeleri", async () => {
        sunucu();
        await render();

        await tikla(dugme("Axa Sigorta satırını düzenle"));
        await yaz(alan("Axa Sigorta kodu"), "aksa");
        expect(satir("sigorta-1").textContent).toContain("AKSA-0001-DR.A.YILMAZ-HUK");
        await yaz(alan("Axa Sigorta eşleşme kelimeleri"), "axa, aksa");
        await tikla(dugme("Kaydet", satir("sigorta-1")));

        expect(yazmaCagrilari()).toEqual([{
            url: "/api/admin/sigorta-kodlari/1",
            method: "PATCH",
            body: { kod: "AKSA", ad: "Axa Sigorta", eslesme_anahtarlari: ["AXA", "AKSA"] },
        }]);
    });

    it("sigorta satırı pasife alınır / yeniden etkinleştirilir (silme düğmesi yok)", async () => {
        sunucu();
        await render();

        await tikla(dugme("Axa Sigorta pasife al"));
        await tikla(dugme("Koru Sigorta etkinleştir"));

        expect(yazmaCagrilari()).toEqual([
            { url: "/api/admin/sigorta-kodlari/1", method: "PATCH", body: { aktif: false } },
            { url: "/api/admin/sigorta-kodlari/2", method: "PATCH", body: { aktif: true } },
        ]);
        expect(yazmaCagrilari().some(c => c.method === "DELETE")).toBe(false);
        expect(Array.from(container.querySelectorAll("button")).some(b => b.textContent?.trim() === "Sil")).toBe(false);
    });

    it("kategori kodu düzenlenir: PATCH /kategori-kodlari/{code}", async () => {
        sunucu();
        await render();

        await tikla(dugme("Doktor kodunu düzenle"));
        await yaz(alan("Doktor kodu"), "hkm");
        expect(satir("kategori-DOKTOR").textContent).toContain("HKM.A.YILMAZ-0001-HUK");
        await tikla(dugme("Kaydet", satir("kategori-DOKTOR")));

        expect(yazmaCagrilari()).toEqual([{
            url: "/api/admin/kategori-kodlari/DOKTOR",
            method: "PATCH",
            body: { ofis_no_kodu: "HKM" },
        }]);
        expect(toastMocks.success).toHaveBeenCalled();
    });

    it("diğer listeyle çakışan kategori kodunda sunucu mesajı gösterilir, satır düzenlemede kalır", async () => {
        sunucu(() => hata(409, "'AXA' bir sigorta şirketi kodu — kategori kodu olamaz"));
        await render();

        await tikla(dugme("Doktor kodunu düzenle"));
        await yaz(alan("Doktor kodu"), "axa");
        await tikla(dugme("Kaydet", satir("kategori-DOKTOR")));

        expect(container.querySelector("[role='alert']")?.textContent)
            .toBe("'AXA' bir sigorta şirketi kodu — kategori kodu olamaz");
        expect(alan("Doktor kodu").value).toBe("AXA");
    });

    it("sunucunun 422 biçim reddi okunur metne çevrilir", async () => {
        sunucu(() => hata(422, [{ loc: ["body", "ofis_no_kodu"], msg: "String should match pattern" }]));
        await render();

        await tikla(dugme("Doktor kodunu düzenle"));
        await yaz(alan("Doktor kodu"), "dx");
        await tikla(dugme("Kaydet", satir("kategori-DOKTOR")));

        expect(container.querySelector("[role='alert']")?.textContent).toBe("Kod 2-10 büyük ASCII harf olmalı");
    });

    it("yeni kategori kodu ile birlikte eklenir: önce kategori, sonra kodu", async () => {
        sunucu();
        await render();

        await yaz(alan("Yeni kategori adı"), "Diş Hekimi");
        await yaz(alan("Yeni kategori kodu"), "dh");
        await tikla(dugme("Kategori ekle"));

        expect(yazmaCagrilari()).toEqual([
            { url: "/api/config/client_categories", method: "POST", body: { code: "DIS-HEKIMI", name: "Diş Hekimi" } },
            { url: "/api/admin/kategori-kodlari/DIS-HEKIMI", method: "PATCH", body: { ofis_no_kodu: "DH" } },
        ]);
        expect(alan("Yeni kategori adı").value).toBe("");
    });

    it("yeni kategoride kod girilmeden kayıt açılmaz", async () => {
        sunucu();
        await render();

        await yaz(alan("Yeni kategori adı"), "Diş Hekimi");
        await tikla(dugme("Kategori ekle"));

        expect(container.querySelector("[role='alert']")?.textContent).toBe("Kod boş olamaz");
        expect(yazmaCagrilari()).toEqual([]);
    });

    it("kategori eklendi ama kodu çakıştıysa durum açıkça söylenir", async () => {
        sunucu((url) => url.startsWith("/api/admin/kategori-kodlari/")
            ? hata(409, "'SG' listede olmayan sigortacının sabit kodudur")
            : okJson({}));
        await render();

        await yaz(alan("Yeni kategori adı"), "Sigortacı");
        await yaz(alan("Yeni kategori kodu"), "sg");
        await tikla(dugme("Kategori ekle"));

        const uyari = container.querySelector("[role='alert']")?.textContent ?? "";
        expect(uyari).toContain("kategorisi eklendi ama kodu kaydedilemedi");
        expect(uyari).toContain("'SG' listede olmayan sigortacının sabit kodudur");
    });

    it("listeler alınamazsa hata metni gösterir", async () => {
        fetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

        await render();

        expect(container.textContent).toContain("alınamadı");
    });
});
