// @vitest-environment jsdom
// Hata bildirimi (02.10.2026) — zil düğmesi, bildirim penceresi, açık bildirim şeridi. `apiClient`
// sahte (yol+yönteme göre yanıt); bileşenler lib/hataBildirimleri üzerinden gerçek eşlemeyle koşar.
// Kilitlenenler: sağlayıcısız düğme çizilmez, hedefe göre liste ucu, açık alan işareti, pencere
// doğrulaması + POST gövdesi + yeniden çekme, alıcı seçicisi (gruplar, ön-seçim, hatırlama, liste
// alınamazsa varsayılana düşme), kapatma (düzeltildi / değişiklik gerekmiyor + not), liste hatasında
// kartın bozulmaması, vurgu, HTML kaçışı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

import { AcikHataBildirimleri, HataBildirButonu, HataBildirimSaglayici } from "./HataBildirimi";
import { SON_ALICILAR_ANAHTARI, type HataAliciAdayi, type HataBildirimi, type HataHedefi } from "@/lib/hataBildirimleri";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const bildirim = (over: Partial<HataBildirimi> = {}): HataBildirimi => ({
    id: 5,
    case_id: 42,
    client_id: null,
    hedef_etiketi: "DR.A.KAYA-0001-HUK · 2024/55",
    link: "/cases/42?hata=5",
    alan: "esas_no",
    alan_etiketi: "Esas No",
    mevcut_deger: "2024/55",
    dogru_deger: "2024/65",
    aciklama: "Esas no yanlış girilmiş.",
    durum: "ACIK",
    alicilar: [{ email: "nurten@example.com", ad: "Nurten Meral" }],
    bildiren_ad: "Av. Ayşe Kaya",
    bildiren_email: "ayse@example.com",
    created_at: "2026-10-02T07:05:00Z",
    kapatan_ad: null,
    kapatan_email: null,
    kapatma_notu: null,
    kapatildi_at: null,
    ...over,
});

const ADAYLAR: HataAliciAdayi[] = [
    { email: "nurten@example.com", ad: "Nurten Meral", grup: "IDARI", varsayilan: true },
    { email: "murat@example.com", ad: "Murat Arslan", grup: "IDARI", varsayilan: false },
    { email: "serap@example.com", ad: "Serap Turgal", grup: "AVUKAT", varsayilan: false },
    { email: "ilke@lexisbio.example", ad: "İlke", grup: "YONETICI", varsayilan: false },
];

let sunucuListesi: HataBildirimi[] = [];
let listeYaniti: () => Response = () => jsonYanit(200, sunucuListesi);
let adayYaniti: () => Response = () => jsonYanit(200, ADAYLAR);
let postYaniti: (yol: string) => Response = () => jsonYanit(201, bildirim());
/** Sunucunun "bu davada doğrudan düzeltebileceğin alanlar" yanıtı (boş = yetkisiz). */
let dogrudanAlanlar: string[] = [];

const ADAY_UCU = "/api/hata-bildirimleri/alicilar";
const DOGRUDAN_UCU = "/api/hata-bildirimleri/dogrudan";
const cagrilar = (method: string) =>
    fetchMock.mock.calls.filter(([, o]) => ((o as RequestInit | undefined)?.method ?? "GET") === method);
/** Bildirim listesi çekimleri (alıcı adayı ve doğrudan düzeltme uçları hariç). */
const listeCagrilari = () =>
    cagrilar("GET").filter(([yol]) => yol !== ADAY_UCU && !String(yol).startsWith(DOGRUDAN_UCU));

describe("HataBildirimi", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    const onDuzelt = vi.fn();
    const onKapandi = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        sunucuListesi = [];
        listeYaniti = () => jsonYanit(200, sunucuListesi);
        adayYaniti = () => jsonYanit(200, ADAYLAR);
        postYaniti = () => jsonYanit(201, bildirim());
        dogrudanAlanlar = [];
        window.localStorage.clear();
        fetchMock.mockImplementation(async (yol: string, o?: RequestInit) => {
            if ((o?.method ?? "GET") === "POST") return postYaniti(yol);
            if (yol.startsWith(DOGRUDAN_UCU)) return jsonYanit(200, { alanlar: dogrudanAlanlar });
            return yol === ADAY_UCU ? adayYaniti() : listeYaniti();
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

    const bas = async (hedef: HataHedefi = { caseId: 42 }, vurgulananId: number | null = null) => {
        await act(async () => {
            root = createRoot(container);
            root.render(
                <HataBildirimSaglayici hedef={hedef}>
                    <HataBildirButonu metinli />
                    <AcikHataBildirimleri vurgulananId={vurgulananId} onDuzelt={onDuzelt} onKapandi={onKapandi} />
                    <span>Esas No<HataBildirButonu alan="esas_no" etiket="Esas No" deger="2024/55" /></span>
                    <span>Mahkeme<HataBildirButonu alan="court" etiket="Mahkeme" deger={null} /></span>
                </HataBildirimSaglayici>,
            );
        });
    };

    const zil = (alan: string) => container.querySelector<HTMLButtonElement>(`[data-testid="hata-bildir"][data-alan="${alan}"]`)!;
    const govdede = <T extends Element = HTMLElement>(testId: string) =>
        document.body.querySelector<T>(`[data-testid="${testId}"]`);
    const tikla = async (el: Element) => {
        await act(async () => {
            (el as HTMLElement).click();
        });
    };
    const aliciKutusu = (email: string) =>
        document.body.querySelector<HTMLButtonElement>(`[data-testid="hata-alici"][data-email="${email}"]`)!;
    const seciliAlicilar = () =>
        Array.from(document.body.querySelectorAll<HTMLElement>('[data-testid="hata-alici"][data-state="checked"]'))
            .map(k => k.dataset.email);
    const yaz = async (el: HTMLInputElement | HTMLTextAreaElement, deger: string) => {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
        await act(async () => {
            setter.call(el, deger);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    };

    it("sağlayıcı yokken düğme ve şerit hiç çizilmez", async () => {
        await act(async () => {
            root = createRoot(container);
            root.render(<><HataBildirButonu alan="esas_no" etiket="Esas No" deger="x" /><AcikHataBildirimleri /></>);
        });
        expect(container.innerHTML).toBe("");
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("hedefe göre liste ucu: dava → case_id, müvekkil → client_id", async () => {
        await bas({ caseId: 42 });
        expect(fetchMock.mock.calls[0][0]).toBe("/api/hata-bildirimleri?case_id=42");
        act(() => root!.unmount());
        root = null;
        fetchMock.mockClear();
        await bas({ clientId: 7 });
        expect(fetchMock.mock.calls[0][0]).toBe("/api/hata-bildirimleri?client_id=7");
    });

    it("açık bildirimi olan alanın zili işaretlenir; şerit bildirimi basar", async () => {
        sunucuListesi = [bildirim()];
        await bas();
        expect(zil("esas_no").dataset.acik).toBe("1");
        expect(zil("court").dataset.acik).toBe("0");
        const serit = govdede("acik-hata-bildirimleri")!;
        expect(serit.textContent).toContain("Açık hata bildirimleri (1)");
        const satir = govdede("hata-bildirimi-satiri")!;
        expect(satir.textContent).toContain("Esas No");
        expect(satir.textContent).toContain("Av. Ayşe Kaya");
        expect(satir.textContent).toContain("02.10.2026 10:05");
        expect(govdede("hata-deger-farki")!.textContent).toBe("Kayıtlı: 2024/55→ Doğrusu:2024/65");
        expect(govdede("hata-aciklama-metni")!.textContent).toBe("Esas no yanlış girilmiş.");
        expect(govdede("hata-kime")!.textContent).toBe("Gönderildi: Nurten Meral");
    });

    it("açık bildirim yokken şerit çizilmez", async () => {
        await bas();
        expect(govdede("acik-hata-bildirimleri")).toBeNull();
    });

    it("vurgulanan bildirim işaretlenir (zilden gelindi)", async () => {
        sunucuListesi = [bildirim({ id: 5 }), bildirim({ id: 6, alan: "court", alan_etiketi: "Mahkeme" })];
        await bas({ caseId: 42 }, 6);
        const satirlar = Array.from(document.body.querySelectorAll<HTMLElement>('[data-testid="hata-bildirimi-satiri"]'));
        expect(satirlar.map(s => s.dataset.vurgulu)).toEqual(["0", "1"]);
    });

    it("açıklama HTML olarak yorumlanmaz", async () => {
        sunucuListesi = [bildirim({ aciklama: '<img src=x onerror="alert(1)">' })];
        await bas();
        const metin = govdede("hata-aciklama-metni")!;
        expect(metin.querySelector("img")).toBeNull();
        expect(metin.textContent).toBe('<img src=x onerror="alert(1)">');
    });

    it("zil pencereyi kayıtlı değerle açar; boşken Bildir pasif; gönderim POST atar ve listeyi yeniden çeker", async () => {
        await bas();
        expect(govdede("hata-bildir-pencere")).toBeNull();
        await tikla(zil("esas_no"));
        expect(govdede("hata-bildir-pencere")).not.toBeNull();
        expect(govdede("hata-mevcut-deger")!.textContent).toBe("2024/55");
        const gonder = () => govdede<HTMLButtonElement>("hata-gonder")!;
        expect(gonder().disabled).toBe(true);

        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "  2024/65  ");
        expect(gonder().disabled).toBe(false);
        await yaz(govdede<HTMLTextAreaElement>("hata-aciklama")!, "Tensip zaptında böyle.");

        sunucuListesi = [bildirim()];
        await tikla(gonder());

        const [yol, secenek] = cagrilar("POST")[0];
        expect(yol).toBe("/api/hata-bildirimleri");
        expect(JSON.parse((secenek as RequestInit).body as string)).toEqual({
            case_id: 42,
            client_id: null,
            alan: "esas_no",
            alan_etiketi: "Esas No",
            mevcut_deger: "2024/55",
            dogru_deger: "2024/65",
            aciklama: "Tensip zaptında böyle.",
            alicilar: ["nurten@example.com"],
            dogrudan_duzelt: false,
        });
        expect(toastMock.success).toHaveBeenCalledWith("Hata bildirimi gönderildi", { description: "Gönderildi: Nurten Meral" });
        expect(govdede("hata-bildir-pencere")).toBeNull();
        expect(listeCagrilari()).toHaveLength(2);
        expect(zil("esas_no").dataset.acik).toBe("1");
    });

    it("boş alanın zili 'boş' gösterir ve mevcut değeri null yollar", async () => {
        await bas();
        await tikla(zil("court"));
        expect(govdede("hata-mevcut-deger")!.textContent).toBe("— (boş)");
        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "Ankara 3. Asliye Hukuk");
        await tikla(govdede("hata-gonder")!);
        const govde = JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string);
        expect(govde.mevcut_deger).toBeNull();
        expect(govde.aciklama).toBeNull();
    });

    it("genel bildirim: yalnız açıklama sorulur, alan anahtarı 'genel'", async () => {
        await bas({ clientId: 7 });
        await tikla(govdede("hata-bildir-genel")!);
        expect(govdede("hata-dogru-deger")).toBeNull();
        expect(govdede("hata-mevcut-deger")).toBeNull();
        await yaz(govdede<HTMLTextAreaElement>("hata-aciklama")!, "Bu müvekkil iki kez kayıtlı.");
        await tikla(govdede("hata-gonder")!);
        const govde = JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string);
        expect(govde).toMatchObject({ case_id: null, client_id: 7, alan: "genel", alan_etiketi: "Genel", dogru_deger: null });
    });

    it("gönderim hatasında toast, pencere ve taslak korunur", async () => {
        postYaniti = () => new Response(null, { status: 500 });
        await bas();
        await tikla(zil("esas_no"));
        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
        await tikla(govdede("hata-gonder")!);
        expect(toastMock.error).toHaveBeenCalledWith("Hata bildirimi gönderilemedi.");
        expect(govdede<HTMLInputElement>("hata-dogru-deger")!.value).toBe("2024/65");
        expect(listeCagrilari()).toHaveLength(1);
    });

    it("alıcı seçicisi: gruplar basılır, varsayılan ön-seçili; seçim aday sırasıyla gönderilir ve hatırlanır", async () => {
        await bas();
        await tikla(zil("esas_no"));
        const kutu = govdede("hata-alicilar")!;
        expect(kutu.textContent).toContain("İdari personel");
        expect(kutu.textContent).toContain("Avukatlar");
        expect(kutu.textContent).toContain("Yönetici");
        expect(seciliAlicilar()).toEqual(["nurten@example.com"]);

        await tikla(aliciKutusu("nurten@example.com"));
        await tikla(aliciKutusu("ilke@lexisbio.example"));
        await tikla(aliciKutusu("serap@example.com"));
        expect(seciliAlicilar()).toEqual(["serap@example.com", "ilke@lexisbio.example"]);

        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
        await tikla(govdede("hata-gonder")!);
        const govde = JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string);
        expect(govde.alicilar).toEqual(["serap@example.com", "ilke@lexisbio.example"]);
        expect(JSON.parse(window.localStorage.getItem(SON_ALICILAR_ANAHTARI)!)).toEqual(govde.alicilar);

        // Sonraki açılış: son seçim ön-seçili (varsayılan değil); aday listesi yeniden çekilmez.
        await tikla(zil("court"));
        expect(seciliAlicilar()).toEqual(["serap@example.com", "ilke@lexisbio.example"]);
        expect(cagrilar("GET").filter(([yol]) => yol === ADAY_UCU)).toHaveLength(1);
    });

    describe("doğrudan düzeltme (sorumlu avukat / yönetici)", () => {
        const onDuzeltildi = vi.fn();
        const basYetkili = async () => {
            dogrudanAlanlar = ["esas_no", "hukuk_no"];
            await act(async () => {
                root = createRoot(container);
                root.render(
                    <HataBildirimSaglayici hedef={{ caseId: 42 }} onDuzeltildi={onDuzeltildi}>
                        <span>Esas No<HataBildirButonu alan="esas_no" etiket="Esas No" deger="2024/55" /></span>
                        <span>Mahkeme<HataBildirButonu alan="court" etiket="Mahkeme" deger="Ankara 1. AHM" /></span>
                        <HataBildirButonu metinli />
                    </HataBildirimSaglayici>,
                );
            });
        };
        const dogrudanDugmesi = () => govdede<HTMLButtonElement>("hata-dogrudan");

        it("yetkisiz kullanıcıda 'Kendim düzelt' hiç çıkmaz", async () => {
            await bas();
            await tikla(zil("esas_no"));
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
            expect(fetchMock.mock.calls.some(([yol]) => yol === `${DOGRUDAN_UCU}?case_id=42`)).toBe(true);
            expect(dogrudanDugmesi()).toBeNull();
            expect(govdede("hata-dogrudan-ipucu")).toBeNull();
        });

        it("müvekkil kartında yetki hiç sorulmaz", async () => {
            await bas({ clientId: 7 });
            await tikla(zil("esas_no"));
            expect(fetchMock.mock.calls.some(([yol]) => String(yol).startsWith(DOGRUDAN_UCU))).toBe(false);
            expect(dogrudanDugmesi()).toBeNull();
        });

        it("yalnız izinli alanda çıkar; doğrusu boş ya da kayıtlı değerle aynıyken pasif", async () => {
            await basYetkili();
            await tikla(zil("court"));
            expect(dogrudanDugmesi()).toBeNull();           // mahkeme listeden seçilir, serbest metinle yazılmaz
            await tikla(govdede("hata-bildir-genel")!);
            expect(dogrudanDugmesi()).toBeNull();           // genel bildirimin alanı yok

            await tikla(zil("esas_no"));
            expect(govdede("hata-dogrudan-ipucu")).not.toBeNull();
            expect(dogrudanDugmesi()!.disabled).toBe(true);
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, " 2024/55 ");
            expect(dogrudanDugmesi()!.disabled).toBe(true);
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
            expect(dogrudanDugmesi()!.disabled).toBe(false);
        });

        it("'Kendim düzelt' önce sorar; Geri taslağı korur, istek gitmez", async () => {
            await basYetkili();
            await tikla(zil("esas_no"));
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
            await tikla(dogrudanDugmesi()!);

            const onay = govdede("hata-dogrudan-onay")!;
            expect(onay.textContent).toContain("Emin misiniz?");
            expect(onay.textContent).toContain("2024/55");
            expect(govdede("hata-dogrudan-yeni")!.textContent).toBe("2024/65");
            expect(govdede("hata-gonder")).toBeNull();      // onay adımında "Bildir" yok
            expect(cagrilar("POST")).toHaveLength(0);

            const geri = Array.from(document.body.querySelectorAll("button")).find(b => b.textContent === "Geri")!;
            await tikla(geri);
            expect(govdede("hata-dogrudan-onay")).toBeNull();
            expect(govdede<HTMLInputElement>("hata-dogru-deger")!.value).toBe("2024/65");
            expect(cagrilar("POST")).toHaveLength(0);
        });

        it("onaylanınca dogrudan_duzelt ile POST atar, alıcı göndermez, kartı tazeletir", async () => {
            postYaniti = () => jsonYanit(201, bildirim({ durum: "COZULDU", alicilar: [] }));
            await basYetkili();
            await tikla(zil("esas_no"));
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, " 2024/65 ");
            await tikla(dogrudanDugmesi()!);
            await tikla(govdede("hata-dogrudan-onayla")!);

            expect(JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string)).toEqual({
                case_id: 42,
                client_id: null,
                alan: "esas_no",
                alan_etiketi: "Esas No",
                mevcut_deger: "2024/55",
                dogru_deger: "2024/65",
                aciklama: null,
                alicilar: null,
                dogrudan_duzelt: true,
            });
            expect(toastMock.success).toHaveBeenCalledWith("Esas No düzeltildi", { description: "2024/55 → 2024/65" });
            expect(onDuzeltildi).toHaveBeenCalledTimes(1);
            expect(govdede("hata-bildir-pencere")).toBeNull();
            expect(window.localStorage.getItem(SON_ALICILAR_ANAHTARI)).toBeNull();
        });

        it("sunucu reddederse (ekran bayat) sunucunun mesajı gösterilir, forma dönülür", async () => {
            postYaniti = () => jsonYanit(409, { detail: "Kayıt bu arada değişmiş. Sayfayı yenileyip güncel değeri kontrol edin." });
            await basYetkili();
            await tikla(zil("esas_no"));
            await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
            await tikla(dogrudanDugmesi()!);
            await tikla(govdede("hata-dogrudan-onayla")!);

            expect(toastMock.error).toHaveBeenCalledWith("Kayıt bu arada değişmiş. Sayfayı yenileyip güncel değeri kontrol edin.");
            expect(onDuzeltildi).not.toHaveBeenCalled();
            expect(govdede("hata-dogrudan-onay")).toBeNull();
            expect(govdede<HTMLInputElement>("hata-dogru-deger")!.value).toBe("2024/65");
        });
    });

    it("hiç alıcı seçili değilken Bildir pasif ve uyarı görünür", async () => {
        await bas();
        await tikla(zil("esas_no"));
        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
        expect(govdede<HTMLButtonElement>("hata-gonder")!.disabled).toBe(false);
        await tikla(aliciKutusu("nurten@example.com"));
        expect(govdede("hata-alici-uyari")).not.toBeNull();
        expect(govdede<HTMLButtonElement>("hata-gonder")!.disabled).toBe(true);
    });

    it("hatırlanan alıcı artık aday değilse varsayılana düşülür", async () => {
        window.localStorage.setItem(SON_ALICILAR_ANAHTARI, JSON.stringify(["ayrilan@example.com"]));
        await bas();
        await tikla(zil("esas_no"));
        expect(seciliAlicilar()).toEqual(["nurten@example.com"]);
    });

    it("alıcı listesi alınamazsa bildirim yine gönderilir (alicilar=null → sunucu varsayılanı)", async () => {
        adayYaniti = () => new Response(null, { status: 500 });
        await bas();
        await tikla(zil("esas_no"));
        expect(govdede("hata-alici-hatasi")).not.toBeNull();
        await yaz(govdede<HTMLInputElement>("hata-dogru-deger")!, "2024/65");
        await tikla(govdede("hata-gonder")!);
        const govde = JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string);
        expect(govde.alicilar).toBeNull();
        expect(toastMock.error).not.toHaveBeenCalled();
    });

    it("Düzeltildi: kapat ucuna COZULDU atar, listeyi yeniden çeker, kartı tazeletir", async () => {
        sunucuListesi = [bildirim()];
        postYaniti = () => jsonYanit(200, bildirim({ durum: "COZULDU" }));
        await bas();
        sunucuListesi = [];
        await tikla(govdede("hata-cozuldu")!);
        const [yol, secenek] = cagrilar("POST")[0];
        expect(yol).toBe("/api/hata-bildirimleri/5/kapat");
        expect(JSON.parse((secenek as RequestInit).body as string)).toEqual({ sonuc: "COZULDU", kapatma_notu: null });
        expect(onKapandi).toHaveBeenCalledTimes(1);
        expect(govdede("acik-hata-bildirimleri")).toBeNull();
        expect(zil("esas_no").dataset.acik).toBe("0");
    });

    it("Değişiklik gerekmiyor: not sorar; vazgeçilirse istek gitmez, yazılırsa REDDEDILDI + not", async () => {
        sunucuListesi = [bildirim()];
        const soru = vi.spyOn(window, "prompt").mockReturnValue(null);
        await bas();
        await tikla(govdede("hata-gecersiz")!);
        expect(soru).toHaveBeenCalledTimes(1);
        expect(cagrilar("POST")).toHaveLength(0);

        soru.mockReturnValue("  Esas no doğru, UYAP'ta böyle.  ");
        await tikla(govdede("hata-gecersiz")!);
        expect(JSON.parse((cagrilar("POST")[0][1] as RequestInit).body as string)).toEqual({
            sonuc: "REDDEDILDI",
            kapatma_notu: "Esas no doğru, UYAP'ta böyle.",
        });
    });

    it("kapatmada 409 Türkçe hata verir ve bayat listeyi tazeler", async () => {
        sunucuListesi = [bildirim()];
        postYaniti = () => new Response(null, { status: 409 });
        await bas();
        sunucuListesi = [];
        await tikla(govdede("hata-cozuldu")!);
        expect(toastMock.error).toHaveBeenCalledWith("Bu hata bildirimi zaten kapatılmış.");
        expect(onKapandi).not.toHaveBeenCalled();
        expect(govdede("acik-hata-bildirimleri")).toBeNull();
    });

    it("Kaydı düzelt düğmesi sayfanın düzeltme yolunu çağırır", async () => {
        sunucuListesi = [bildirim()];
        await bas();
        const dugme = Array.from(document.body.querySelectorAll("button")).find(b => b.textContent?.includes("Kaydı düzelt"))!;
        await tikla(dugme);
        expect(onDuzelt).toHaveBeenCalledTimes(1);
    });

    it("liste yüklenemezse kart bozulmaz: ziller çalışır, şerit ve toast yok", async () => {
        listeYaniti = () => new Response(null, { status: 500 });
        await bas();
        expect(govdede("acik-hata-bildirimleri")).toBeNull();
        expect(toastMock.error).not.toHaveBeenCalled();
        expect(zil("esas_no").dataset.acik).toBe("0");
        await tikla(zil("esas_no"));
        expect(govdede("hata-bildir-pencere")).not.toBeNull();
    });

    it("zil, içinde durduğu tıklanabilir satırı tetiklemez", async () => {
        const disTiklama = vi.fn();
        await act(async () => {
            root = createRoot(container);
            root.render(
                <HataBildirimSaglayici hedef={{ caseId: 42 }}>
                    <div onClick={disTiklama}>
                        <HataBildirButonu alan="taraf:3" etiket="Taraf: Ali" deger="Ali" />
                    </div>
                </HataBildirimSaglayici>,
            );
        });
        await tikla(zil("taraf:3"));
        expect(disTiklama).not.toHaveBeenCalled();
        expect(govdede("hata-bildir-pencere")).not.toBeNull();
    });
});
