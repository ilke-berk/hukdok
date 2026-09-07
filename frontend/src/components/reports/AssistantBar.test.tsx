// @vitest-environment jsdom
// AssistantBar + AssistantThread (G143) — izole: iskelet (`yukleniyor`) girdi/istek üretmez; çipler
// `ornekIstemler(veriKaynagi)`; ilk tık girdiye yazar + odak, ikinci tık gönderir; `complete`+`tanim` →
// `onTanimUygula(tanim, eylem)` düğme beklemeden; `onTanimUygula` false → düğme kalır, Geri al yok;
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

describe("AssistantBar (G143)", () => {
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
    const butonBul = (metin: string) => {
        const b = Array.from(container.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
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

    it("complete+tanim → onTanimUygula(tanim, eylem) düğme beklemeden; rozet + (geriAlinabilir ile) Geri al; onGeriAl balonu düğmeye döndürür", async () => {
        fetchMock.mockResolvedValue(akis([{ status: "complete", cevap: "hazır", tanim: TANIM, eylem: "onizle" }]));
        await render();
        yaz(girdi(), "listele");
        await enter(girdi());

        expect(onTanimUygula).toHaveBeenCalledTimes(1);
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, "onizle");
        const balon = $("[data-testid='sohbet-asistan']");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
        expect(Array.from(balon.querySelectorAll("button")).map(b => b.textContent?.trim())).not.toContain("Oluşturucuya uygula");
        // Sayfa henüz geri-al adımını vermedi → bağlantı yok
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).toBeNull();

        await yenidenRender({ geriAlinabilir: true });
        const geriAl = $("[data-testid='tanim-geri-al']");
        await tikla(geriAl);
        expect(onGeriAl).toHaveBeenCalledTimes(1);
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        // Balon yeniden uygulanabilir: düğme → onTanimUygula(tanim, null)
        await tikla(butonBul("Oluşturucuya uygula"));
        expect(onTanimUygula).toHaveBeenLastCalledWith(TANIM, null);
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).not.toBeNull();
    });

    it("onTanimUygula false (kaynak katalogda yok): düğme kalır, rozet ve Geri al yok; tanim=null + eylem → mevcut tanımla eylem", async () => {
        onTanimUygula.mockResolvedValueOnce(false);
        fetchMock
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "?", tanim: TANIM, eylem: null }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "önizliyorum", tanim: null, eylem: "onizle" }]))
            .mockResolvedValueOnce(akis([{ status: "complete", cevap: "soru?", tanim: null, eylem: null }]));
        await render({ geriAlinabilir: true });

        yaz(girdi(), "bir");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenCalledWith(TANIM, null);
        const balon = $("[data-testid='sohbet-asistan']");
        expect(balon.querySelector("[data-testid='tanim-uygulandi']")).toBeNull();
        expect(balon.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
        expect(Array.from(balon.querySelectorAll("button")).map(b => b.textContent?.trim())).toContain("Oluşturucuya uygula");

        yaz(girdi(), "iki");
        await enter(girdi());
        expect(onTanimUygula).toHaveBeenLastCalledWith(MEVCUT, "onizle");
        expect(onTanimUygula).toHaveBeenCalledTimes(2);

        yaz(girdi(), "üç");
        await enter(girdi());
        // Soru: uygulama çağrısı YOK
        expect(onTanimUygula).toHaveBeenCalledTimes(2);
        expect(container.querySelectorAll("[data-testid='sohbet-asistan']")).toHaveLength(3);
        expect(container.querySelector("[data-testid='tanim-geri-al']")).toBeNull();
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
