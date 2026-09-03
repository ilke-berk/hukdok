// @vitest-environment jsdom
// DeliveryInboxCard — yönetici teslim defteri: liste/rozet/sayaç, tara, yükle,
// kuru koş, raporlar (blob indirme) ve onaylı uygula. Backend sözleşmesi G108'de
// donduruldu (gorevler/gorev/G111.md); burada yalnız kartın o uçlara nasıl
// bağlandığı ve hata yollarının toast'a düştüğü sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

type Kids = { children?: unknown };

// Radix Dialog jsdom'da portal/odak katmanı için düzleştirilir: açıkken içerik
// kartın altında basılır, kapalıyken hiç basılmaz.
vi.mock("@/components/ui/dialog", () => {
    const duz = ({ children }: Kids) => <div>{children as never}</div>;
    return {
        Dialog: ({ open, children }: { open: boolean } & Kids) => (open ? <div data-dialog="open">{children as never}</div> : null),
        DialogContent: duz,
        DialogHeader: duz,
        DialogTitle: duz,
        DialogDescription: duz,
        DialogFooter: duz,
    };
});

import { DeliveryInboxCard, type Teslim } from "./DeliveryInboxCard";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const teslim = (over: Partial<Teslim> = {}): Teslim => ({
    id: 1,
    dosya_adi: "teslim_2026-09-01.xlsx",
    sha256: "abc",
    kaynak: "sharepoint",
    durum: "alindi",
    onceki_teslim_adi: null,
    zincir_tamam: null,
    okunan: null,
    islenen: null,
    atlanan: null,
    hata_sayisi: null,
    alan_degisikligi: null,
    kart_degisen: null,
    envanter_denk: null,
    kapi_karari: null,
    kapi_gerekcesi: null,
    cevap_yuklendi: null,
    uygulayan: null,
    hata_mesaji: null,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: null,
    done_at: null,
    ...over,
});

const ESIKLER = { hata_orani: 0.05, eslesmeyen_orani: 0.1, alan_degisikligi: 5000 };

const okJson = (payload: unknown, status = 200) => ({ ok: true, status, json: async () => payload });
const failJson = (status: number, payload: unknown = {}) => ({ ok: false, status, json: async () => payload });

const listeYaniti = (teslimler: Teslim[], etkin = true) => okJson({ teslimler, esikler: ESIKLER, etkin });

const isTeslimList = (url: string, o?: RequestInit) =>
    url.startsWith("/api/admin/aktarim/teslimler?") && (!o?.method || o.method === "GET");

describe("DeliveryInboxCard", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
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
        await act(async () => {
            root!.render(<DeliveryInboxCard />);
        });
    }

    const butonlar = () => Array.from(container.querySelectorAll<HTMLButtonElement>("button"));
    const buton = (metin: string, kok: ParentNode = container) =>
        Array.from(kok.querySelectorAll<HTMLButtonElement>("button")).find(b => b.textContent?.trim().startsWith(metin)) ?? null;

    const tikla = async (el: Element) => {
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    };

    it("boş defterde 'Henüz teslim yok' basar ve limit=50 ile listeyi çeker", async () => {
        fetchMock.mockResolvedValue(listeYaniti([]));

        await render();

        expect(fetchMock).toHaveBeenCalledWith("/api/admin/aktarim/teslimler?limit=50");
        expect(container.textContent).toContain("Henüz teslim yok");
        expect(container.textContent).not.toContain("Otomasyon kapalı");
    });

    it("etkin=false ise sarı uyarı satırını gösterir", async () => {
        fetchMock.mockResolvedValue(listeYaniti([], false));

        await render();

        const uyari = container.querySelector("[role='status']");
        expect(uyari?.textContent).toContain("Otomasyon kapalı — Özellikler sekmesinden açın");
    });

    it("liste alınamazsa hata metni basar", async () => {
        fetchMock.mockResolvedValue(failJson(500));

        await render();

        expect(container.textContent).toContain("Teslim listesi alınamadı");
    });

    it("üç teslimi rozet tonu, sayaçlar ve izinli aksiyonlarla listeler", async () => {
        fetchMock.mockResolvedValue(listeYaniti([
            teslim({ id: 1, durum: "uygulandi", okunan: 100, islenen: 95, atlanan: 5, hata_sayisi: 0, alan_degisikligi: 1200, kart_degisen: 40, kapi_karari: "otomatik", kapi_gerekcesi: "eşikler altında", uygulayan: "yonetici@ofis.av.tr" }),
            teslim({ id: 2, durum: "inceleme_bekliyor", kaynak: "yukleme", okunan: 80, islenen: 60, atlanan: 20, hata_sayisi: 3, alan_degisikligi: 9000, kapi_karari: "inceleme", kapi_gerekcesi: "alan değişikliği eşiği aşıldı", envanter_denk: false }),
            teslim({ id: 3, durum: "basarisiz", hata_mesaji: "sütun eksik: DosyaNo", onceki_teslim_adi: "teslim_2026-08-25.xlsx", zincir_tamam: false }),
        ]));

        await render();

        const rozetler = Array.from(container.querySelectorAll<HTMLElement>("[data-tone]")).map(r => [r.dataset.tone, r.textContent]);
        expect(rozetler).toEqual([
            ["green", "Uygulandı"],
            ["amber", "İnceleme bekliyor"],
            ["red", "Başarısız"],
        ]);

        const sayaclar = Array.from(container.querySelectorAll("[data-testid='sayaclar']")).map(c => c.textContent);
        expect(sayaclar[0]).toContain("100 / 95 / 5 / 0");
        expect(sayaclar[1]).toContain("80 / 60 / 20 / 3");
        expect(sayaclar[1]).toContain("envanter denk değil");
        expect(sayaclar[2]).toContain("— / — / — / —");

        const alan = Array.from(container.querySelectorAll("[data-testid='alan-degisikligi']")).map(c => c.textContent);
        expect(alan[0]).toContain("1200");
        expect(alan[0]).toContain("40 kart");
        expect(alan[2]).toBe("—");

        // Kapı: karar metni + gerekçe tooltip (title)
        const kapi = container.querySelector("[title='alan değişikliği eşiği aşıldı']");
        expect(kapi?.textContent).toBe("İnceleme");

        expect(container.textContent).toContain("SharePoint");
        expect(container.textContent).toContain("Yükleme");
        expect(container.textContent).toContain("sütun eksik: DosyaNo");
        expect(container.textContent).toContain("zincir kopuk");
        expect(container.textContent).toContain("yonetici@ofis.av.tr");
        expect(container.textContent).toContain("Eşikler");

        // "Uygula" yalnız inceleme_bekliyor satırında; "Kuru koş" uygulanmış satırda yok.
        const satir = (id: number) => container.querySelector(`[data-teslim-id='${id}']`)!;
        expect(buton("Uygula", satir(1))).toBeNull();
        expect(buton("Uygula", satir(2))).not.toBeNull();
        expect(buton("Uygula", satir(3))).toBeNull();
        expect(buton("Kuru koş", satir(1))).toBeNull();
        expect(buton("Kuru koş", satir(2))).not.toBeNull();
        expect(buton("Kuru koş", satir(3))).not.toBeNull();
    });

    it("'Uygula' onay diyaloğunda gerekçeyi gösterir ve onayda { onay: true } ile POST atar", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/teslimler/2/uygula") return okJson({ id: 2, durum: "uygulaniyor" });
            if (isTeslimList(url, o)) return listeYaniti([
                teslim({ id: 2, durum: "inceleme_bekliyor", okunan: 80, islenen: 60, atlanan: 20, hata_sayisi: 3, kapi_karari: "inceleme", kapi_gerekcesi: "alan değişikliği eşiği aşıldı" }),
            ]);
            return failJson(404);
        });

        await render();
        expect(container.querySelector("[data-dialog='open']")).toBeNull();

        await tikla(buton("Uygula")!);

        const onay = container.querySelector("[data-testid='uygula-onay']");
        expect(onay).not.toBeNull();
        expect(onay!.textContent).toContain("teslim_2026-09-01.xlsx");
        expect(onay!.textContent).toContain("alan değişikliği eşiği aşıldı");
        expect(onay!.textContent).toContain("okunan 80");
        expect(onay!.textContent).toContain("hata 3");

        await tikla(buton("Onaylıyorum")!);

        const post = fetchMock.mock.calls.find(([u]) => u === "/api/admin/aktarim/teslimler/2/uygula");
        expect(post).toBeDefined();
        const opts = post![1] as RequestInit;
        expect(opts.method).toBe("POST");
        expect(JSON.parse(opts.body as string)).toEqual({ onay: true });
        expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining("Uygulama başlatıldı"));
        expect(container.querySelector("[data-dialog='open']")).toBeNull();
        // liste yenilenir
        expect(fetchMock.mock.calls.filter(([u, o]) => isTeslimList(u as string, o as RequestInit)).length).toBe(2);
    });

    it("uygula 409 dönerse 'Bu durumda uygulanamaz' toast'ı basar", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url.endsWith("/uygula")) return failJson(409, { detail: "durum uygun değil" });
            if (isTeslimList(url, o)) return listeYaniti([teslim({ id: 5, durum: "kuru_kosuldu" })]);
            return failJson(404);
        });

        await render();
        await tikla(buton("Uygula")!);
        await tikla(buton("Onaylıyorum")!);

        expect(toastMocks.error).toHaveBeenCalledWith("Bu durumda uygulanamaz");
        expect(toastMocks.success).not.toHaveBeenCalled();
    });

    it("'Şimdi tara' sonucunu toast'a yazar; `not` varsa metne ekler", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/tara") return okJson({ yeni: 2, yinelenen: 1, not: "1 dosya uzantı dışı" });
            if (isTeslimList(url, o)) return listeYaniti([]);
            return failJson(404);
        });

        await render();
        await tikla(buton("Şimdi tara")!);

        const taraCall = fetchMock.mock.calls.find(([u]) => u === "/api/admin/aktarim/tara");
        expect((taraCall![1] as RequestInit).method).toBe("POST");
        expect(toastMocks.success).toHaveBeenCalledTimes(1);
        const mesaj = toastMocks.success.mock.calls[0][0] as string;
        expect(mesaj).toContain("2 yeni, 1 yinelenen");
        expect(mesaj).toContain("1 dosya uzantı dışı");
    });

    it("'Şimdi tara' başarısızsa hata toast'ı basar", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/tara") return failJson(500, { detail: "SharePoint erişilemedi" });
            if (isTeslimList(url, o)) return listeYaniti([]);
            return failJson(404);
        });

        await render();
        await tikla(buton("Şimdi tara")!);

        expect(toastMocks.error).toHaveBeenCalledWith("SharePoint erişilemedi");
    });

    const dosyaSec = async (file: File) => {
        const input = container.querySelector<HTMLInputElement>("input[type='file']")!;
        expect(input.accept).toBe(".xlsx");
        Object.defineProperty(input, "files", { value: [file], configurable: true });
        await act(async () => {
            input.dispatchEvent(new Event("change", { bubbles: true }));
        });
    };

    it("dosya yükleme multipart `file` alanıyla POST atar ve listeyi yeniler", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/teslimler" && o?.method === "POST") return okJson({ id: 9, durum: "alindi" }, 201);
            if (isTeslimList(url, o)) return listeYaniti([]);
            return failJson(404);
        });

        await render();
        const file = new File(["x"], "teslim_2026-09-03.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
        await dosyaSec(file);

        const post = fetchMock.mock.calls.find(([u, o]) => u === "/api/admin/aktarim/teslimler" && (o as RequestInit)?.method === "POST");
        expect(post).toBeDefined();
        const body = (post![1] as RequestInit).body;
        expect(body).toBeInstanceOf(FormData);
        expect((body as FormData).get("file")).toBe(file);
        expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining("teslim_2026-09-03.xlsx"));
        expect(fetchMock.mock.calls.filter(([u, o]) => isTeslimList(u as string, o as RequestInit)).length).toBe(2);
    });

    it("yükleme 400 dönerse sunucu `detail`'ini toast'a yazar", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/teslimler" && o?.method === "POST") return failJson(400, { detail: "Yalnız .xlsx kabul edilir" });
            if (isTeslimList(url, o)) return listeYaniti([]);
            return failJson(404);
        });

        await render();
        await dosyaSec(new File(["x"], "teslim.csv"));

        expect(toastMocks.error).toHaveBeenCalledWith("Yalnız .xlsx kabul edilir");
        expect(toastMocks.success).not.toHaveBeenCalled();
    });

    it("'Raporlar' listeyi açar, tıklanan dosya blob yoluyla indirilir", async () => {
        const blob = new Blob(["rapor"], { type: "text/csv" });
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/teslimler/4/raporlar") return okJson({ dosyalar: [{ ad: "kuru-kosu.csv", boyut: 2048 }, { ad: "hatalar.txt", boyut: 12 }] });
            if (url === "/api/admin/aktarim/teslimler/4/raporlar/kuru-kosu.csv") return { ok: true, status: 200, blob: async () => blob };
            if (isTeslimList(url, o)) return listeYaniti([teslim({ id: 4, durum: "kuru_kosuldu" })]);
            return failJson(404);
        });
        const createObjectURL = vi.fn(() => "blob:rapor");
        const revokeObjectURL = vi.fn();
        Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, configurable: true });
        Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, configurable: true });
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

        try {
            await render();
            expect(container.querySelector("[data-rapor-satiri='4']")).toBeNull();

            await tikla(buton("Raporlar")!);

            const raporSatiri = container.querySelector("[data-rapor-satiri='4']");
            expect(raporSatiri).not.toBeNull();
            expect(raporSatiri!.textContent).toContain("kuru-kosu.csv");
            expect(raporSatiri!.textContent).toContain("2.0 KB");
            expect(raporSatiri!.textContent).toContain("hatalar.txt");

            await tikla(buton("kuru-kosu.csv", raporSatiri!)!);

            expect(fetchMock).toHaveBeenCalledWith("/api/admin/aktarim/teslimler/4/raporlar/kuru-kosu.csv");
            expect(createObjectURL).toHaveBeenCalledWith(blob);
            expect(clickSpy).toHaveBeenCalledTimes(1);
            expect(revokeObjectURL).toHaveBeenCalledWith("blob:rapor");
            expect(toastMocks.success).toHaveBeenCalledWith("İndirildi: kuru-kosu.csv");
        } finally {
            clickSpy.mockRestore();
        }
    });

    it("'Kuru koş' POST atar ve kapı kararını toast'a yazar; 409'da hata toast'ı", async () => {
        fetchMock.mockImplementation(async (url: string, o?: RequestInit) => {
            if (url === "/api/admin/aktarim/teslimler/6/kuru-kos") return okJson({ id: 6, durum: "inceleme_bekliyor", kapi_karari: "inceleme", kapi_gerekcesi: "hata oranı yüksek" });
            if (url === "/api/admin/aktarim/teslimler/7/kuru-kos") return failJson(409);
            if (isTeslimList(url, o)) return listeYaniti([teslim({ id: 6, durum: "dogrulandi" }), teslim({ id: 7, durum: "alindi" })]);
            return failJson(404);
        });

        await render();
        const satir = (id: number) => container.querySelector(`[data-teslim-id='${id}']`)!;

        await tikla(buton("Kuru koş", satir(6))!);
        const kos = fetchMock.mock.calls.find(([u]) => u === "/api/admin/aktarim/teslimler/6/kuru-kos");
        expect((kos![1] as RequestInit).method).toBe("POST");
        expect(toastMocks.success).toHaveBeenCalledWith(expect.stringContaining("hata oranı yüksek"));

        await tikla(buton("Kuru koş", satir(7))!);
        expect(toastMocks.error).toHaveBeenCalledWith("Bu durumda kuru koşulamaz");
    });

    it("tüm aksiyon butonları listede her zaman erişilebilir (Raporlar her satırda)", async () => {
        fetchMock.mockResolvedValue(listeYaniti([teslim({ id: 1, durum: "yinelenen" }), teslim({ id: 2, durum: "reddedildi" })]));

        await render();

        const raporButonlari = butonlar().filter(b => b.textContent?.trim() === "Raporlar");
        expect(raporButonlari).toHaveLength(2);
        expect(butonlar().some(b => b.textContent?.trim() === "Kuru koş")).toBe(false);
        expect(butonlar().some(b => b.textContent?.trim() === "Uygula")).toBe(false);
    });
});

describe("DeliveryInboxCard — mesai saati uyarısı", () => {
    // Europe/Istanbul UTC+3 (yaz saati yok): 09:00–18:00 TR = 06:00–15:00 UTC.
    // Sistem saati sabitlenir; tarayıcının yerel dilimi ne olursa olsun uyarı
    // Türkiye saatine göre çizilir.
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
        container = document.createElement("div");
        document.body.appendChild(container);
        fetchMock.mockResolvedValue(
            okJson({ teslimler: [teslim({ id: 2, durum: "inceleme_bekliyor" })], esikler: ESIKLER, etkin: true }),
        );
    });

    afterEach(() => {
        vi.useRealTimers();
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
    });

    async function diyalogAc(now: string) {
        vi.useFakeTimers({ now: new Date(now), toFake: ["Date"] });
        root = createRoot(container);
        await act(async () => {
            root!.render(<DeliveryInboxCard />);
        });
        const uygula = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(b => b.textContent?.trim() === "Uygula")!;
        await act(async () => {
            uygula.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        return container.querySelector("[data-testid='uygula-onay'] [role='alert']");
    }

    it("mesai içinde (14:30 TR) onay diyaloğunda ek uyarı satırı vardır", async () => {
        const uyari = await diyalogAc("2026-09-03T11:30:00Z");
        expect(uyari?.textContent).toContain("Mesai saatindesiniz");
    });

    it("sınırda 17:59 TR mesai içi, 18:00 TR mesai dışı", async () => {
        expect(await diyalogAc("2026-09-03T14:59:00Z")).not.toBeNull();
        act(() => root!.unmount());
        root = null;
        expect(await diyalogAc("2026-09-03T15:00:00Z")).toBeNull();
    });

    it("mesai dışında (00:00 TR) uyarı satırı yoktur", async () => {
        expect(await diyalogAc("2026-09-03T21:00:00Z")).toBeNull();
    });
});
