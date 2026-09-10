// @vitest-environment jsdom
// AssistantBar + AssistantThread (G143 → G167) — izole: iskelet (`yukleniyor`) girdi/istek üretmez; çipler
// `ornekIstemler(veriKaynagi)`; ilk tık girdiye yazar + odak, ikinci tık gönderir; `complete`+`tanim` →
// TEYİT KARTI (uygulama YOK), Onayla/Excel/CSV düğmeleri, düzeltme bekleyen tanımı taşır, sözle onay
// (aynı tanım + eylem) hemen yürür; `onTanimUygula` false → kart beklemede, Geri al yok;
// `geriAlinabilir` yalnız son uygulanan balonda "Geri al", tıklanınca `onGeriAl` + balon düğmeye döner;
// 409 → `onKapali`; "Konuşmayı kapat" geçmişi korur; Sohbeti temizle geri-al kimliğini de sıfırlar.
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

import type { AsistanEylemi, Katalog, RaporTanimi } from "@/lib/reports";
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

const TANIM: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no"], filtreler: [], siralama: [] };
const TANIM2: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] };
const TANIM2F: RaporTanimi = { ...TANIM2, filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }] };
const MEVCUT: RaporTanimi = { veri_kaynagi: "davalar", kolonlar: ["subject"], filtreler: [], siralama: [] };

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

describe("AssistantBar (G143/G167)", () => {
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
    const sohbetGovdesi = () => JSON.parse((fetchMock.mock.calls.at(-1)![1] as RequestInit).body as string);

    it("iskelet: yukleniyor iken girdi, çip ve istek yok; aria-hidden", async () => {
        await render({ yukleniyor: true });
        expect(container.querySelector("[data-testid='asistan-iskelet']")?.getAttribute("aria-hidden")).toBe("true");
        expect(container.querySelector("[data-testid='asistan-satiri']")).toBeNull();
        expect(container.querySelector("[aria-label='Asistana mesaj']")).toBeNull();
        expect(cipler()).toHaveLength(0);
        expect(fetchMock).not.toHaveBeenCalled();
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

    it("complete+tanim → UYGULANMAZ (G167): teyit kartı + Onayla/Excel/CSV; düzeltme mesajı bekleyen tanımı mevcut_tanim olarak taşır; Onayla → onTanimUygula(tanim, null); Geri al kartı onay bekleyene döndürür; Excel indir → indir_xlsx", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: "onizle" }]));
        await render();
        yaz(girdi(), "listele");
        await enter(girdi());

        // Otomatik uygulama YOK
        expect(onTanimUygula).not.toHaveBeenCalled();
        const balon = $("[data-testid='sohbet-asistan']");
        expect(balon.querySelector("[data-testid='tanim-ozeti']")).not.toBeNull();
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-teyit-notu']")).not.toBeNull();
        const dugmeler = (kok: Element) => Array.from(kok.querySelectorAll("button")).map(x => x.textContent?.trim());
        expect(dugmeler(balon)).toEqual(expect.arrayContaining(["Onayla ve uygula", "Excel indir", "CSV indir"]));
        expect(girdi().placeholder).toContain("Düzeltme");

        // Düzeltme: sunucuya mevcut_tanim = BEKLEYEN tanım (oluşturucudaki MEVCUT değil)
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "güncelledim", tanim: TANIM2, eylem: null }]));
        yaz(girdi(), "konuyu da ekle");
        await enter(girdi());
        expect(sohbetGovdesi().mevcut_tanim).toEqual(TANIM);
        expect(onTanimUygula).not.toHaveBeenCalled();
        const balon2 = container.querySelectorAll("[data-testid='sohbet-asistan']")[1];

        // Onayla → onTanimUygula(TANIM2, null); rozet; bekleyen düşer (yer tutucu normale döner)
        await tikla(butonBulIcinde(balon2, "Onayla ve uygula"));
        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM2, null);
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(dugmeler(balon2)).not.toContain("Onayla ve uygula");
        expect(dugmeler(balon2)).toEqual(expect.arrayContaining(["Excel indir", "CSV indir"]));
        expect(girdi().placeholder).not.toContain("Düzeltme");
        // Sayfa henüz geri-al adımını vermedi → bağlantı yok
        expect(balon2.querySelector("[data-testid='tanim-geri-al']")).toBeNull();

        await yenidenRender({ geriAlinabilir: true });
        await tikla($("[data-testid='tanim-geri-al']"));
        expect(onGeriAl).toHaveBeenCalledTimes(1);
        expect(balon2.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(dugmeler(balon2)).toContain("Onayla ve uygula");
        expect(girdi().placeholder).toContain("Düzeltme");         // geri alınan tanım yeniden bekleyen

        // Karttan indirme: onTanimUygula(TANIM2, indir_xlsx) → uygulandı rozeti
        await tikla(butonBulIcinde(balon2, "Excel indir"));
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, "indir_xlsx");
        expect(balon2.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        await tikla(butonBulIcinde(balon2, "CSV indir"));
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM2, "indir_csv");
    });

    it("sözle onay: bekleyen tanım AYNEN + eylemle dönerse eylem hemen yürür; onTanimUygula false → kart beklemeye devam; tanim=null + eylem → bekleyen (yoksa mevcut) tanımla eylem; soru → yalnız balon", async () => {
        const TANIM3: RaporTanimi = { ...MEVCUT, kolonlar: ["subject", "court"] };
        fetchMock
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır?", tanim: TANIM, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "uyguluyorum", tanim: TANIM, eylem: "onizle" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "uyguluyorum", tanim: TANIM, eylem: "onizle" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "yeni", tanim: TANIM3, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "indiriyorum", tanim: null, eylem: "indir_csv" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "soru?", tanim: null, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "önizliyorum", tanim: null, eylem: "onizle" }]));
        await render({ geriAlinabilir: true });
        const balonlar = () => Array.from(container.querySelectorAll("[data-testid='sohbet-asistan']"));

        yaz(girdi(), "bir");
        await enter(girdi());
        expect(onTanimUygula).not.toHaveBeenCalled();

        // onay dışı cümle Gemini'ye gider; aynı tanım + eylem döner ama sayfa reddetti (false) → rozet yok, bekleyen kalır
        onTanimUygula.mockResolvedValueOnce(false);
        yaz(girdi(), "bu şekilde devam edelim mi");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balonlar()[1].querySelector("[data-testid='tanim-geri-al']")).toBeNull();

        // tekrar → uygulanır: rozet + Geri al; mevcut_tanim bekleyen tanımdı
        yaz(girdi(), "bu şekilde devam edelim mi");
        await enter(girdi());
        expect(sohbetGovdesi().mevcut_tanim).toEqual(TANIM);
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(balonlar()[2].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[2].querySelector("[data-testid='tanim-geri-al']")).not.toBeNull();

        // Yeni tanım → kart bekler; sonra tanımsız "indir" → bekleyen tanımla indirme, kart rozet alır
        yaz(girdi(), "başka");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        yaz(girdi(), "bunu csv olarak da atar mısın");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM3, "indir_csv");
        expect(balonlar()[3].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[4].querySelector("[data-testid='tanim-ozeti']")).toBeNull();

        // Soru: uygulama çağrısı YOK
        yaz(girdi(), "?");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenCalledTimes(3);

        // Bekleyen yok → tanımsız "önizle" oluşturucudaki tanımla
        yaz(girdi(), "önizleyebilir misin");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenLastCalledWith(MEVCUT, "onizle");
        expect(balonlar()).toHaveLength(7);
    });

    it("YEREL ONAY (G167): bekleyen tanım varken 'tamam' fetch'siz onTanimUygula(tanim, onizle), sahip kart rozet; 'csv indir' → indir_csv; onay dışı mesaj Gemini'ye; bekleyen yokken 'tamam' da Gemini'ye", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "neyi?", tanim: null, eylem: null }]));
        await render();
        const balonlar = () => Array.from(container.querySelectorAll("[data-testid='sohbet-asistan']"));

        // Bekleyen yokken "tamam" → Gemini (soru cevabı tanımsız)
        yaz(girdi(), "tamam");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).not.toHaveBeenCalled();

        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır?", tanim: TANIM, eylem: null }]));
        yaz(girdi(), "listele");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(balonlar()[1].querySelector("[data-testid='tanim-ozeti']")).not.toBeNull();

        // "Tamam." → fetch YOK, bekleyen tanım uygulanır, kart (balon 2) rozet
        yaz(girdi(), "Tamam.");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(balonlar()[2].textContent).toContain("Onaylandı");

        // Geri al → yeniden bekleyen; "csv indir" → fetch yok, indir_csv
        await yenidenRender({ geriAlinabilir: true });
        await tikla($("[data-testid='tanim-geri-al']"));
        yaz(girdi(), "csv indir");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM, "indir_csv");
        expect(balonlar()[1].querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();

        // Uygulandıktan sonra onay dışı mesaj Gemini'ye gider; yerel satırlar geçmişte asistan olarak taşınır
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: null, eylem: null }]));
        yaz(girdi(), "telefonu da ekle");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(3);
        const mesajlar = sohbetGovdesi().mesajlar as { rol: string; icerik: string }[];
        expect(mesajlar.filter(m => m.rol === "assistant" && m.icerik.startsWith("Onaylandı"))).toHaveLength(2);
    });

    it("G168: uygulama sonrası önizleme sonucu gelince sonuç satırı (N kayıt / boş öneri), yalnız bir kez ve yalnız o tanım için", async () => {
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır?", tanim: TANIM, eylem: null }]));
        await render({ onizlemeSonucu: { tanim: MEVCUT, toplam: 9 } });
        const balonlar = () => Array.from(container.querySelectorAll("[data-testid='sohbet-asistan']"));
        yaz(girdi(), "listele");
        await enter(girdi());
        // Eski sonuç (MEVCUT) uygulanan tanıma ait değil → satır yok
        await tikla(butonBulIcinde(balonlar()[0], "Onayla ve uygula"));
        expect(balonlar()).toHaveLength(1);
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM, toplam: 3216 } });
        expect(balonlar()).toHaveLength(2);
        expect(balonlar()[1].textContent).toContain("3.216 kayıt bulundu.");
        // Aynı sonuç yeniden gelse de ikinci satır yok
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM, toplam: 3216 } });
        expect(balonlar()).toHaveLength(2);

        // Boş sonuç: filtreli tanımda gevşetme önerisi
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "daralttım", tanim: TANIM2F, eylem: null }]));
        yaz(girdi(), "sadece derdestler");
        await enter(girdi());
        yaz(girdi(), "tamam");
        await enter(girdi());
        await yenidenRender({ onizlemeSonucu: { tanim: TANIM2F, toplam: 0 } });
        const son = balonlar().at(-1)!;
        expect(son.textContent).toContain("Sonuç boş");
        expect(son.textContent).toContain("status · eşittir · Derdest");
    });

    it("G168: 'bunu haftalık rapor olarak kaydet' → onSablonKaydet(bekleyen, ad) fetch'siz; 'kaydet' bekleyen yokken oluşturucu tanımıyla (ad null); hata satırı", async () => {
        const onSablonKaydet = vi.fn(async (_t: RaporTanimi, ad: string | null): Promise<string | null> => ad ?? "Davalar · Önerilen");
        fetchMock.mockResolvedValueOnce(akis([{ status: "complete", cevap: "hazır?", tanim: TANIM, eylem: null }]));
        await render({ onSablonKaydet });
        const balonlar = () => Array.from(container.querySelectorAll("[data-testid='sohbet-asistan']"));

        yaz(girdi(), "kaydet");
        await enter(girdi());
        expect(fetchMock).not.toHaveBeenCalled();
        expect(onSablonKaydet).toHaveBeenCalledWith(MEVCUT, null);
        expect(balonlar()[0].textContent).toContain('"Davalar · Önerilen" adıyla şablonlara kaydedildi');

        yaz(girdi(), "listele");
        await enter(girdi());
        yaz(girdi(), "bunu Haftalık Rapor olarak kaydet");
        await enter(girdi());
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(onSablonKaydet).toHaveBeenLastCalledWith(TANIM, "Haftalık Rapor");
        expect(balonlar().at(-1)!.textContent).toContain('"Haftalık Rapor" adıyla');
        expect(onTanimUygula).not.toHaveBeenCalled();          // kaydetmek uygulamak değildir

        onSablonKaydet.mockResolvedValueOnce(null);
        yaz(girdi(), "şablon olarak kaydet");
        await enter(girdi());
        expect(balonlar().at(-1)!.textContent).toContain("kaydedilemedi");
    });

    it("409 → onKapali çağrılır; 'Konuşmayı kapat' alanı kapatır geçmişi korur; Sohbeti temizle boş duruma döner", async () => {
        fetchMock
            .mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: "kapalı" }) })
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "ok", tanim: null, eylem: null }]));
        await render();

        yaz(girdi(), "merhaba");
        await enter(girdi());
        expect(onKapali).toHaveBeenCalledTimes(1);
        expect(container.querySelector("[data-testid='sohbet-hata']")?.textContent).toContain("kapalı");

        await tikla($("[aria-label='Konuşmayı kapat']"));
        expect(container.querySelector("[data-testid='asistan-konusmasi']")).toBeNull();
        expect(container.querySelector("[data-testid='asistan-satiri']")).not.toBeNull();

        yaz(girdi(), "tekrar");
        await enter(girdi());
        expect(container.querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(2);
        // Hata kaydı geçmişe girmez
        expect(sohbetGovdesi().mesajlar).toEqual([{ rol: "user", icerik: "merhaba" }, { rol: "user", icerik: "tekrar" }]);

        await tikla($("[aria-label='Sohbeti temizle']"));
        expect(container.querySelectorAll("[data-testid='sohbet-kullanici']")).toHaveLength(0);
        expect(container.querySelector("[data-testid='asistan-bos']")).not.toBeNull();
    });
});
