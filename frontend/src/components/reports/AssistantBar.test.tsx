// @vitest-environment jsdom
// AssistantBar + AssistantThread (G143 → G167 → G174) — izole: iskelet (`yukleniyor`) girdi/istek üretmez; çipler
// `ornekIstemler(veriKaynagi)`; ilk tık girdiye yazar + odak, ikinci tık gönderir; `complete`+`tanim` →
// G174 OTOMATİK UYGULAMA (değerler kataloğa uyuyorsa düğme beklemeden `onTanimUygula(tanim, eylem ?? onizle)`),
// kısa "Uygulandı" kartı + Excel/CSV + Geri al; kataloğa uymayan metin değeri → kart BEKLER: sorun satırı + aday
// çipleri (tık → değer yazılır + uygulanır) + "Yine de uygula"; `onTanimUygula` false → kart beklemede (Onayla),
// Geri al yok; düzeltme bekleyen tanımı taşır; sözle onay (aynı tanım + eylem) ve yerel onay (`onayNiyeti`) korunur;
// "hangi durumlar var" → fetch'siz `DegerListesi` balonu (tık → `onFiltreEkle` ya da girdiye yazım), belirsizde
// "Hangisi?" çipleri; `geriAlinabilir` yalnız son uygulanan balonda "Geri al", tıklanınca `onGeriAl` + balon düğmeye
// döner; 409 → `onKapali`; "Konuşmayı kapat" geçmişi korur; Sohbeti temizle geri-al kimliğini de sıfırlar.
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import type { AsistanEylemi, Katalog, KatalogKolon, RaporTanimi } from "@/lib/reports";
import { ornekIstemler } from "@/lib/reportsChat";
import { AssistantBar } from "./AssistantBar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KATALOG = {
    veri_kaynaklari: [
        { anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: [], kolonlar: [], hizli_filtreler: [], kolon_setleri: [] },
        { anahtar: "muvekkiller", etiket: "Müvekkiller", aciklama: "", varsayilan_kolonlar: [], kolonlar: [], hizli_filtreler: [], kolon_setleri: [] },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
} as unknown as Katalog;

function K(k: Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>): KatalogKolon {
    return {
        filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null, grup: "", kontrol: null,
        oplar: [], oneriler: null, oneri_kesik: false, secenek_kaynagi: null, secenek_etiketleri: null, secilebilir: true,
        ...k,
    };
}
const MAHKEMELER = [
    "Ankara 3. Asliye Ticaret Mahkemesi", "Ankara 1. Asliye Hukuk Mahkemesi", "İstanbul 5. Asliye Ticaret Mahkemesi",
    "İzmir 2. Asliye Hukuk Mahkemesi", "Bursa 1. Asliye Ticaret Mahkemesi", "Adana 4. Asliye Hukuk Mahkemesi",
    "Antalya 1. Asliye Ticaret Mahkemesi", "Kayseri Sulh Hukuk Mahkemesi",
];
/** G174: öneri/seçenek listeli kolonlar — değer eşleme ve liste balonu testleri. */
const KATALOG_G174 = {
    veri_kaynaklari: [
        {
            anahtar: "davalar", etiket: "Davalar", aciklama: "", varsayilan_kolonlar: [], kolon_setleri: [], hizli_filtreler: [],
            kolonlar: [
                K({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin", oplar: ["eq", "contains"] }),
                K({ anahtar: "subject", etiket: "Konu", tip: "metin", oplar: ["eq", "contains"] }),
                K({ anahtar: "court", etiket: "Mahkeme", tip: "metin", oplar: ["eq", "ne", "contains", "in", "is_null", "not_null"], oneriler: MAHKEMELER }),
                K({ anahtar: "court_city", etiket: "Mahkeme İli", tip: "metin", oplar: ["contains", "in"], oneriler: ["Ankara", "İstanbul", "İzmir"], oneri_kesik: true }),
                K({ anahtar: "status", etiket: "Durum", tip: "liste", oplar: ["eq", "ne", "in"], secenekler: ["Derdest", "Karar"], secenek_sayilari: { Derdest: 1443, Karar: 0 } }),
            ],
        },
        {
            anahtar: "muvekkiller", etiket: "Müvekkiller", aciklama: "", varsayilan_kolonlar: [], kolon_setleri: [], hizli_filtreler: [],
            kolonlar: [K({ anahtar: "city", etiket: "Şehir", tip: "metin", oplar: ["contains", "in"], oneriler: ["İstanbul", "Ankara", "İzmir"] })],
        },
    ],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
} as Katalog;

const TANIM: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] };
const TANIM2: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] };
const TANIM2F: RaporTanimi = { ...TANIM2, filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }] };
const MEVCUT: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["subject"], filtreler: [], siralama: [] };
/** G174: mahkeme değeri kataloğa uymuyor (contains alt dize değil). */
const SORUNLU: RaporTanimi = {
    veri_kaynagi: "davalar", kolonlar: ["tracking_no", "court"], siralama: [],
    filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }, { alan: "court", op: "contains", deger: "Ankara Ticaret Dairesi" }],
};
/** G174: iki sorunlu filtre (mahkeme + kesik listeli il). */
const SORUNLU2: RaporTanimi = {
    ...SORUNLU,
    filtreler: [...SORUNLU.filtreler, { alan: "court_city", op: "contains", deger: "Ankra" }],
};

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

type Props = Partial<Parameters<typeof AssistantBar>[0]>;

describe("AssistantBar (G143/G167/G174)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let onTanimUygula: Mock<(t: RaporTanimi, e: AsistanEylemi | null) => Promise<boolean>>;
    let onKapali: Mock<() => void>;
    let onGeriAl: Mock<() => void>;

    beforeEach(() => {
        fetchMock.mockReset();
        onTanimUygula = vi.fn(async (_t: RaporTanimi, _e: AsistanEylemi | null) => true);
        onKapali = vi.fn<() => void>();
        onGeriAl = vi.fn<() => void>();
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

    async function bekle(tur = 8) {
        for (let i = 0; i < tur; i++) await act(async () => { await Promise.resolve(); });
    }

    function eleman(props: Props = {}) {
        return (
            <AssistantBar
                katalog={KATALOG}
                veriKaynagi="davalar"
                mevcutTanim={MEVCUT}
                onKapali={onKapali}
                onTanimUygula={onTanimUygula}
                geriAlinabilir={false}
                onGeriAl={onGeriAl}
                {...props}
            />
        );
    }
    async function render(props: Props = {}) {
        root = createRoot(container);
        await act(async () => { root!.render(eleman(props)); });
        await bekle(2);
    }
    async function yenidenRender(props: Props = {}) {
        await act(async () => { root!.render(eleman(props)); });
        await bekle(2);
    }

    const $ = <T extends Element>(sel: string): T => {
        const el = container.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    const girdi = () => $<HTMLInputElement>("[aria-label='Asistana mesaj']");
    const cipler = () => Array.from(container.querySelectorAll<HTMLButtonElement>("[data-testid='ornek-istem']"));
    const balonlar = () => Array.from(container.querySelectorAll("[data-testid='sohbet-asistan']"));
    const dugmeler = (kok: Element) => Array.from(kok.querySelectorAll("button")).map(x => x.textContent?.trim());
    const butonBulIcinde = (kok: ParentNode, metin: string) => {
        const b = Array.from(kok.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };
    function yaz(el: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }
    async function tikla(el: Element) {
        await act(async () => { el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })); });
        await bekle();
    }
    async function enter(el: Element) {
        await act(async () => { el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })); });
        await bekle();
    }
    async function gonder(metin: string) {
        yaz(girdi(), metin);
        await enter(girdi());
    }
    const sohbetGovdesi = () => JSON.parse((fetchMock.mock.calls.at(-1)![1] as RequestInit).body as string);

    it("iskelet: yukleniyor iken girdi, çip ve istek yok; aria-hidden", async () => {
        await render({ yukleniyor: true });
        expect(container.querySelector("[data-testid='asistan-iskelet']")?.getAttribute("aria-hidden")).toBe("true");
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(container.querySelector("[aria-label='Asistana mesaj']")).toBeNull();
        expect(cipler()).toHaveLength(0);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("mevcutVarsayilan (12.09): dokunulmamış varsayılan tanım sunucuya mevcut_tanim=null gider; bayrak yokken tanım gider", async () => {
        fetchMock.mockResolvedValue(akis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]));
        await render({ mevcutVarsayilan: true });
        await gonder("ofis no ve doktor adıyla derdest davalar");
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(sohbetGovdesi().mevcut_tanim).toBeNull();
        await yenidenRender({ mevcutVarsayilan: false });
        await gonder("telefonu da ekle");
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(sohbetGovdesi().mevcut_tanim).toEqual(MEVCUT);
    });

    it("çipler kaynağa göre; ilk tık girdiye yazar ve odaklar, aynı çipe ikinci tık gönderir (gövde mevcut_tanim ile)", async () => {
        fetchMock.mockResolvedValue(akis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]));
        await render({ veriKaynagi: "muvekkiller" });
        expect(cipler().map(c => c.textContent?.trim())).toEqual([...ornekIstemler("muvekkiller")]);

        const cip = cipler()[0];
        await tikla(cip);
        expect(girdi().value).toBe(cip.textContent);
        expect(document.activeElement).toBe(girdi());
        expect(fetchMock).not.toHaveBeenCalled();
        expect(container.querySelector("[data-testid='asistan-konusmasi']")).toBeNull();

        await tikla(cip);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe("/api/reports/chat");
        expect(sohbetGovdesi()).toEqual({ mesajlar: [{ rol: "user", icerik: cip.textContent }], mevcut_tanim: MEVCUT });
        expect(container.querySelector("[data-testid='asistan-konusmasi']")).not.toBeNull();
        expect(girdi().value).toBe("");

        // Kaynak değişince çipler değişir
        await yenidenRender({ veriKaynagi: "davalar" });
        expect(cipler().map(c => c.textContent?.trim())).toEqual([...ornekIstemler("davalar")]);
    });

    it("G174 OTOMATİK UYGULAMA: complete+tanim (temiz) → onTanimUygula(tanim, onizle) hemen, kısa 'Uygulandı' kartı (Onayla yok, Excel/CSV var); Geri al kartı onay bekleyene döndürür (dl kart + Onayla); Onayla → onTanimUygula(tanim, null); Excel indir → indir_xlsx", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: "onizle" }]));
        await render();
        await gonder("listele");

        // Düğme beklemeden uygulandı
        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        const balon = $("[data-testid='sohbet-asistan']");
        const kart = balon.querySelector("[data-testid='tanim-ozeti']")!;
        expect(kart.getAttribute("data-kisa")).toBe("true");
        expect(kart.querySelector("[data-testid='tanim-uygulandi']")?.textContent).toContain("Uygulandı · Davalar · 1 kolon · 0 filtre");
        expect(kart.querySelector("dl")).toBeNull();                              // ayrıntı şeritte, kart kısa
        expect(balon.querySelector("[data-testid='tanim-teyit-notu']")).toBeNull();
        expect(dugmeler(balon)).not.toContain("Onayla ve uygula");
        expect(dugmeler(balon)).toEqual(expect.arrayContaining(["Excel indir", "CSV indir"]));
        expect(girdi().placeholder).not.toContain("Düzeltme");
        // Sayfa henüz geri-al adımını vermedi → bağlantı yok
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).toBeNull();

        // Düzeltme: bekleyen yok → sunucuya mevcut_tanim = oluşturucudaki; yeni tanım da hemen uygulanır
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "güncelledim", tanim: TANIM2, eylem: null }]));
        await gonder("konuyu da ekle");
        expect(sohbetGovdesi().mevcut_tanim).toEqual(MEVCUT);
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, "onizle");
        const balon2 = balonlar()[1];
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")?.textContent).toContain("2 kolon");

        // Geri al → kart yeniden onay bekleyen (okunur dl kart + Onayla); yer tutucu düzeltmeye çağırır
        await yenidenRender({ geriAlinabilir: true });
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).toBeNull();   // yalnız SON uygulanan balonda
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(onGeriAl).toHaveBeenCalledTimes(1);
        expect(balon2.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balon2.querySelector("[data-testid='tanim-ozeti'] dl")).not.toBeNull();
        expect(Array.from(balon2.querySelectorAll("[data-testid='tanim-kolonlar'] span")).map(x => x.textContent)).toEqual(["tracking_no", "subject"]);
        expect(balon2.querySelector("[data-testid='tanim-teyit-notu']")?.textContent).toContain("onaylayın");
        expect(dugmeler(balon2)).toContain("Onayla ve uygula");
        expect(girdi().placeholder).toContain("Düzeltme");

        // Düzeltme mesajı BEKLEYEN tanımı taşır
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: null, eylem: null }]));
        await gonder("bu doğru mu");
        expect(sohbetGovdesi().mevcut_tanim).toEqual(TANIM2);

        // Onayla → onTanimUygula(TANIM2, null); kısa kart; bekleyen düşer
        await tikla(butonBulIcinde(balon2, "Onayla ve uygula"));
        expect(onTanimUygula).toHaveBeenCalledTimes(3);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, null);
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(dugmeler(balon2)).not.toContain("Onayla ve uygula");
        expect(girdi().placeholder).not.toContain("Düzeltme");

        // Karttan indirme: onTanimUygula(TANIM2, indir_xlsx) / indir_csv — uygulanmış kartta da durur
        await tikla(butonBulIcinde(balon2, "Excel indir"));
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, "indir_xlsx");
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        await tikla(butonBulIcinde(balon2, "CSV indir"));
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, "indir_csv");
    });

    it("eylem indir_xlsx ile gelen temiz tanım hemen indirilir: onTanimUygula(tanim, indir_xlsx); kart uygulandı", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "excel", tanim: TANIM, eylem: "indir_xlsx" }]));
        await render();
        await gonder("excel ver");
        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "indir_xlsx");
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(dugmeler(balonlar()[0])).not.toContain("Onayla ve uygula");
    });

    it("sözle onay + red: onTanimUygula false → kart bekler (Onayla), Geri al yok, bekleyen o tanım; aynı tanım + eylem tekrar → uygulanır; tanim=null + eylem → bekleyen (yoksa mevcut) tanımla eylem; soru → yalnız balon", async () => {
        const TANIM3: RaporTanimi = { ...MEVCUT, kolonlar: ["subject", "court"] };
        fetchMock
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "uyguluyorum", tanim: TANIM, eylem: "onizle" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "yeni", tanim: TANIM3, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "indiriyorum", tanim: null, eylem: "indir_csv" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "soru?", tanim: null, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "önizliyorum", tanim: null, eylem: "onizle" }]));
        await render({ geriAlinabilir: true });

        // Sayfa reddetti (kaynak katalogda yok vb.) → rozet yok, Onayla düğmesi, bekleyen = TANIM
        onTanimUygula.mockResolvedValueOnce(false);
        await gonder("bir");
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        expect(balonlar()[0].querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balonlar()[0].querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(dugmeler(balonlar()[0])).toContain("Onayla ve uygula");
        expect(girdi().placeholder).toContain("Düzeltme");

        // Onay dışı cümle Gemini'ye gider (mevcut_tanim = bekleyen); aynı tanım + eylem döner → uygulanır: rozet + Geri al
        await gonder("bu şekilde devam edelim mi");
        expect(sohbetGovdesi().mevcut_tanim).toEqual(TANIM);
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[1].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        expect(girdi().placeholder).not.toContain("Düzeltme");

        // Yeni tanım → hemen uygulanır; sonra tanımsız "indir" → bekleyen yok → oluşturucudaki tanımla indirme
        await gonder("başka");
        expect(onTanimUygula).toHaveBeenCalledTimes(3);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM3, "onizle");
        await gonder("bunu csv olarak da atar mısın");
        expect(onTanimUygula).toHaveBeenLastCalledWith(MEVCUT, "indir_csv");
        expect(balonlar()[3].querySelector("[data-testid='tanim-ozeti']")).toBeNull();

        // Soru: uygulama çağrısı YOK
        await gonder("?");
        expect(onTanimUygula).toHaveBeenCalledTimes(4);

        // Bekleyen yok → tanımsız "önizle" oluşturucudaki tanımla
        await gonder("önizleyebilir misin");
        expect(onTanimUygula).toHaveBeenLastCalledWith(MEVCUT, "onizle");
        expect(balonlar()).toHaveLength(6);
    });

    it("YEREL ONAY (G167): bekleyen tanım (geri alınmış kart) varken 'tamam' fetch'siz onTanimUygula(tanim, onizle), sahip kart rozet; 'csv indir' → indir_csv; onay dışı mesaj Gemini'ye; bekleyen yokken 'tamam' da Gemini'ye", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "neyi?", tanim: null, eylem: null }]));
        await render({ geriAlinabilir: true });

        // Bekleyen yokken "tamam" → Gemini (soru cevabı tanımsız)
        await gonder("tamam");
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).not.toHaveBeenCalled();

        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: null }]));
        await gonder("listele");
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenCalledTimes(1);           // otomatik uygulandı
        // Geri al → kart yeniden bekleyen
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).toBeNull();

        // "Tamam." → fetch YOK, bekleyen tanım uygulanır, kart (balon 2) rozet
        await gonder("Tamam.");
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM, "onizle");
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[2].textContent).toContain("Onaylandı");

        // Geri al → yeniden bekleyen; "csv indir" → fetch yok, indir_csv
        await tikla($("[data-testid='tanim-geri-al']"));
        await gonder("csv indir");
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM, "indir_csv");
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();

        // Uygulandıktan sonra onay dışı mesaj Gemini'ye gider; yerel satırlar geçmişte asistan olarak taşınır
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: null, eylem: null }]));
        await gonder("telefonu da ekle");
        expect(fetchMock).toHaveBeenCalledTimes(3);
        const mesajlar = sohbetGovdesi().mesajlar as { rol: string; icerik: string }[];
        expect(mesajlar.filter(m => m.rol === "assistant" && m.icerik.startsWith("Onaylandı"))).toHaveLength(2);
    });

    it("G168: uygulama sonrası önizleme sonucu gelince sonuç satırı (N kayıt / boş öneri), yalnız bir kez ve yalnız o tanım için", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: null }]));
        await render({ onizlemeSonucu: { tanim: MEVCUT, toplam: 9 } });
        await gonder("listele");
        // Otomatik uygulandı; eski sonuç (MEVCUT) uygulanan tanıma ait değil → satır yok
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        expect(balonlar()).toHaveLength(1);
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM, toplam: 3216 } });
        expect(balonlar()).toHaveLength(2);
        expect(balonlar()[1].textContent).toContain("3.216 kayıt bulundu.");
        // Aynı sonuç yeniden gelse de ikinci satır yok
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM, toplam: 3216 } });
        expect(balonlar()).toHaveLength(2);

        // Boş sonuç: filtreli tanımda gevşetme önerisi (tanım hemen uygulanır, onay adımı yok)
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "daralttım", tanim: TANIM2F, eylem: null }]));
        await gonder("sadece derdestler");
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2F, "onizle");
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM2F, toplam: 0 } });
        const son = balonlar().at(-1)!;
        expect(son.textContent).toContain("Sonuç boş");
        expect(son.textContent).toContain("status · eşittir · Derdest");
    });

    it("G168: 'bunu haftalık rapor olarak kaydet' → onSablonKaydet(bekleyen, ad) fetch'siz; 'kaydet' bekleyen yokken oluşturucu tanımıyla (ad null); hata satırı", async () => {
        const onSablonKaydet = vi.fn(async (_t: RaporTanimi, ad: string | null): Promise<string | null> => ad ?? "Davalar · Önerilen");
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: null }]));
        await render({ onSablonKaydet, geriAlinabilir: true });

        await gonder("kaydet");
        expect(fetchMock).not.toHaveBeenCalled();
        expect(onSablonKaydet).toHaveBeenCalledWith(MEVCUT, null);
        expect(balonlar()[0].textContent).toContain('"Davalar · Önerilen" adıyla şablonlara kaydedildi');

        await gonder("listele");
        expect(onTanimUygula).toHaveBeenCalledTimes(1);            // otomatik uygulandı
        await tikla($("[data-testid='tanim-geri-al']"));           // bekleyen = TANIM
        await gonder("bunu Haftalık Rapor olarak kaydet");
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(onSablonKaydet).toHaveBeenLastCalledWith(TANIM, "Haftalık Rapor");
        expect(balonlar().at(-1)!.textContent).toContain('"Haftalık Rapor" adıyla');
        expect(onTanimUygula).toHaveBeenCalledTimes(1);            // kaydetmek uygulamak değildir

        onSablonKaydet.mockResolvedValueOnce(null);
        await gonder("şablon olarak kaydet");
        expect(balonlar().at(-1)!.textContent).toContain("kaydedilemedi");
    });

    it("409 → onKapali çağrılır; 'Konuşmayı kapat' alanı kapatır geçmişi korur; Sohbeti temizle boş duruma döner", async () => {
        fetchMock
            .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: "kapalı" }) })
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]));
        await render();

        await gonder("merhaba");
        expect(onKapali).toHaveBeenCalledTimes(1);
        expect(container.querySelector("[data-testid='sohbet-hata']")?.textContent).toContain("kapalı");

        await tikla($("[aria-label='Konuşmayı kapat']"));
        expect(container.querySelector("[data-testid='asistan-konusmasi']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-satiri']")).not.toBeNull();

        await gonder("tekrar");
        expect(container.querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(2);
        // Hata kaydı geçmişe girmez
        expect(sohbetGovdesi().mesajlar).toEqual([{ rol: "user", icerik: "merhaba" }, { rol: "user", icerik: "tekrar" }]);

        await tikla($("[aria-label='Sohbeti temizle']"));
        expect(container.querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(0);
        expect(container.querySelector("[data-testid='asistan-bos']")).not.toBeNull();
    });

    // ---------------------------------------------------------------- G174: değer eşleme kartı

    it("G174 SORUNLU DEĞER: contains değeri kataloğa uymuyor → uygulama YOK, kart bekler; sorun satırı + ≤5 aday çipi + Yine de uygula; Onayla yok; düzeltme bekleyen tanımı taşır; tanim=null → kart yok", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: SORUNLU, eylem: "onizle" }]));
        await render({ katalog: KATALOG_G174 });
        await gonder("ankara ticaret dairesindeki davalar");

        expect(onTanimUygula).not.toHaveBeenCalled();
        const balon = balonlar()[0];
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-ozeti'] dl")).not.toBeNull();
        const sorunlar = Array.from(balon.querySelectorAll("[data-testid='tanim-sorun']"));
        expect(sorunlar).toHaveLength(1);
        expect(sorunlar[0].getAttribute("data-indeks")).toBe("1");
        expect(sorunlar[0].textContent).toContain("Mahkeme");
        expect(sorunlar[0].textContent).toContain('"Ankara Ticaret Dairesi" kataloğda bulunamadı');
        expect(sorunlar[0].textContent).toContain("şunlardan biri mi?");
        const adaylar = Array.from(sorunlar[0].querySelectorAll("[data-testid='deger-adayi']")).map(a => a.getAttribute("data-deger"));
        expect(adaylar).toHaveLength(5);
        expect(adaylar[0]).toBe("Ankara 3. Asliye Ticaret Mahkemesi");
        expect(sorunlar[0].querySelector("[data-testid='tanim-sorun-kesik']")).toBeNull();
        expect(balon.querySelector("[data-testid='yine-de-uygula']")).not.toBeNull();
        expect(dugmeler(balon)).not.toContain("Onayla ve uygula");
        expect(dugmeler(balon)).toEqual(expect.arrayContaining(["Excel indir", "CSV indir"]));
        expect(balon.querySelector("[data-testid='tanim-teyit-notu']")?.textContent).toContain("kataloğa uymadı");
        expect(girdi().placeholder).toContain("Düzeltme");

        // Düzeltme mesajı sunucuya BEKLEYEN (sorunlu) tanımı taşır; soru cevabı kartsız
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hangi mahkeme?", tanim: null, eylem: null }]));
        await gonder("aslında hukuk mahkemesi olacaktı");
        expect(sohbetGovdesi().mevcut_tanim).toEqual(SORUNLU);
        expect(balonlar()[1].querySelector("[data-testid='tanim-ozeti']")).toBeNull();
        expect(onTanimUygula).not.toHaveBeenCalled();
    });

    it("G174 ADAY TIK: değer katalog yazımıyla tanıma yazılır (kolonda eq izinli → eq) ve tanım o an uygulanır (eylem korunur); kart rozet; bekleyen düşer", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: SORUNLU, eylem: "onizle" }]));
        await render({ katalog: KATALOG_G174, geriAlinabilir: true });
        await gonder("ankara ticaret");
        const balon = balonlar()[0];
        const aday = Array.from(balon.querySelectorAll("[data-testid='deger-adayi']")).find(a => a.getAttribute("data-deger") === "Ankara 1. Asliye Hukuk Mahkemesi")!;
        await tikla(aday);

        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).toHaveBeenCalledWith({
            ...SORUNLU,
            filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }, { alan: "court", op: "eq", deger: "Ankara 1. Asliye Hukuk Mahkemesi" }],
        }, "onizle");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")?.textContent).toContain("2 kolon · 2 filtre");
        expect(balon.querySelector("[data-testid='tanim-sorunlar']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();
        expect(girdi().placeholder).not.toContain("Düzeltme");

        // Sonraki mesaj: bekleyen yok → mevcut_tanim oluşturucudaki
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: null, eylem: null }]));
        await gonder("peki ya");
        expect(sohbetGovdesi().mevcut_tanim).toEqual(MEVCUT);
    });

    it("G174 iki sorunlu filtre: ilk aday tık uygulamaz (diğer sorun bekler, kesik notu), ikinci aday tık uygular; contains-only kolonda op contains kalır", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: SORUNLU2, eylem: null }]));
        await render({ katalog: KATALOG_G174 });
        await gonder("x");
        const balon = balonlar()[0];
        const sorunlar = () => Array.from(balon.querySelectorAll("[data-testid='tanim-sorun']"));
        expect(sorunlar().map(s => s.getAttribute("data-indeks"))).toEqual(["1", "2"]);
        expect(sorunlar()[1].querySelector("[data-testid='tanim-sorun-kesik']")?.textContent).toContain("Liste kesik");
        expect(sorunlar()[1].textContent).toContain("Mahkeme İli");

        await tikla(sorunlar()[0].querySelector("[data-testid='deger-adayi']")!);      // Ankara 3. Asliye Ticaret
        expect(onTanimUygula).not.toHaveBeenCalled();
        expect(sorunlar().map(s => s.getAttribute("data-indeks"))).toEqual(["2"]);
        // Düzeltme mesajı artık kısmen düzeltilmiş bekleyen tanımı taşır
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: null, eylem: null }]));
        await gonder("hangisi olduğundan emin değilim");
        expect(sohbetGovdesi().mevcut_tanim.filtreler[1]).toEqual({ alan: "court", op: "eq", deger: "Ankara 3. Asliye Ticaret Mahkemesi" });

        await tikla(sorunlar()[0].querySelector("[data-testid='deger-adayi']")!);      // Ankara (contains-only kolon)
        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula.mock.calls[0][0].filtreler[2]).toEqual({ alan: "court_city", op: "contains", deger: "Ankara" });
        expect(onTanimUygula.mock.calls[0][1]).toBe("onizle");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
    });

    it("G174 YİNE DE UYGULA: ham tanım olduğu gibi uygulanır (asistanın eylemiyle); onTanimUygula false → kart sorunlarıyla beklemeye devam", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: SORUNLU, eylem: "indir_xlsx" }]));
        await render({ katalog: KATALOG_G174 });
        await gonder("x");
        const balon = balonlar()[0];

        onTanimUygula.mockResolvedValueOnce(false);
        await tikla(balon.querySelector("[data-testid='yine-de-uygula']")!);
        expect(onTanimUygula).toHaveBeenCalledWith(SORUNLU, "indir_xlsx");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-sorunlar']")).not.toBeNull();

        await tikla(balon.querySelector("[data-testid='yine-de-uygula']")!);
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenLastCalledWith(SORUNLU, "indir_xlsx");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(girdi().placeholder).not.toContain("Düzeltme");
    });

    // ---------------------------------------------------------------- G174: liste balonu

    it("G174 LİSTE BALONU: 'hangi durumlar var' fetch'siz DegerListesi (listbox + option, sayı rozeti); arama süzer; tık → onFiltreEkle yoksa girdiye yazılır + odak", async () => {
        await render({ katalog: KATALOG_G174 });
        await gonder("hangi durumlar var");
        expect(fetchMock).not.toHaveBeenCalled();
        expect(onTanimUygula).not.toHaveBeenCalled();

        const balon = balonlar()[0];
        expect(balon.textContent).toContain("Durum için kayıtlı 2 değer");
        const liste = balon.querySelector("[data-testid='deger-listesi']")!;
        expect(liste.getAttribute("data-alan")).toBe("status");
        const listbox = liste.querySelector("[role='listbox']")!;
        expect(listbox.getAttribute("aria-label")).toBe("Durum değerleri");
        const secenekler = () => Array.from(listbox.querySelectorAll<HTMLButtonElement>("[role='option']"));
        expect(secenekler().map(s => s.getAttribute("data-deger"))).toEqual(["Derdest", "Karar"]);
        expect(secenekler()[0].textContent).toContain("1.443");                    // secenek_sayilari rozeti
        expect(liste.querySelector("[data-testid='deger-listesi-kesik']")).toBeNull();

        // Arama normalize süzer (İ/i)
        const arama = liste.querySelector<HTMLInputElement>("[aria-label='Durum değerlerinde ara']")!;
        yaz(arama, "KARAR");
        await bekle(2);
        expect(secenekler().map(s => s.getAttribute("data-deger"))).toEqual(["Karar"]);
        yaz(arama, "zzz");
        await bekle(2);
        expect(secenekler()).toHaveLength(0);
        expect(liste.querySelector("[data-testid='deger-listesi-bos']")).not.toBeNull();
        yaz(arama, "");
        await bekle(2);

        // Klavye: ok tuşları seçenekler arasında gezer
        secenekler()[0].focus();
        await act(async () => {
            listbox.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }));
        });
        expect(document.activeElement).toBe(secenekler()[1]);

        // Tık: onFiltreEkle yok → girdiye doğal cümle, odak girdide, sohbete satır düşmez
        await tikla(secenekler()[1]);
        expect(girdi().value).toBe('Durum "Karar" olanlar');
        expect(document.activeElement).toBe(girdi());
        expect(balonlar()).toHaveLength(1);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("G174 LİSTE TIK onFiltreEkle ile: (alan, ham değer) çağrılır + yerel satır; kesik listede not; eşleşmeyen liste sorusu Gemini'ye gider", async () => {
        const onFiltreEkle = vi.fn<(alan: string, deger: string) => void>();
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "listeyi ekrandan alın", tanim: null, eylem: null }]));
        await render({ katalog: KATALOG_G174, onFiltreEkle });

        await gonder("hangi iller var");
        expect(fetchMock).not.toHaveBeenCalled();
        const liste = balonlar()[0].querySelector("[data-testid='deger-listesi']")!;
        expect(liste.getAttribute("data-alan")).toBe("court_city");
        expect(liste.querySelector("[data-testid='deger-listesi-kesik']")?.textContent).toContain("kesik");
        await tikla(liste.querySelector("[role='option'][data-deger='İzmir']")!);
        expect(onFiltreEkle).toHaveBeenCalledWith("court_city", "İzmir");
        expect(girdi().value).toBe("");
        expect(balonlar()[1].textContent).toContain("Mahkeme İli · İzmir filtre olarak eklendi.");

        // Öneri listesi olmayan kolon ("konu") → yerel eşleşme yok → Gemini
        await gonder("hangi konular var");
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(balonlar()[2].textContent).toContain("listeyi ekrandan alın");
        expect(balonlar()[2].querySelector("[data-testid='deger-listesi']")).toBeNull();
    });

    it("G174 BELİRSİZ: 'hangi mahkemeler var' iki kolona uyar → 'Hangisi?' çipleri; çip tık → o kolonun listesi; kaynak bekleyen tanımınki, yoksa seçili kaynak", async () => {
        await render({ katalog: KATALOG_G174 });
        await gonder("hangi mahkemeler var");
        expect(fetchMock).not.toHaveBeenCalled();
        const balon = balonlar()[0];
        expect(balon.textContent).toContain("Hangisini listeleyeyim?");
        const adaylar = Array.from(balon.querySelectorAll("[data-testid='kolon-adayi']"));
        expect(adaylar.map(a => a.textContent?.trim())).toEqual(["Mahkeme", "Mahkeme İli"]);
        expect(balon.querySelector("[data-testid='deger-listesi']")).toBeNull();

        await tikla(adaylar[0]);
        const liste = balonlar()[1].querySelector("[data-testid='deger-listesi']")!;
        expect(liste.getAttribute("data-alan")).toBe("court");
        expect(liste.querySelectorAll("[role='option']")).toHaveLength(MAHKEMELER.length);

        // Seçili kaynak müvekkiller → şehir listesi (davalar'ın mahkeme ili değil)
        await yenidenRender({ katalog: KATALOG_G174, veriKaynagi: "muvekkiller" });
        await gonder("hangi şehirler var");
        expect(balonlar()[2].querySelector("[data-testid='deger-listesi']")?.getAttribute("data-alan")).toBe("city");
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
