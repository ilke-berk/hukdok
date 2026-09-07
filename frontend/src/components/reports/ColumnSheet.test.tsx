// @vitest-environment jsdom
// ColumnSheet + ColumnPicker (G139) — "Kolonlar (N)" düğmesi sağdan yan panel (shadcn Sheet, Radix
// portal → document.body) açar: üstte hazır setler (`kolon_setleri`; "Temel" yoksa varsayılandan
// üretilir), arama, `grup` başlıklı checkbox listesi (grup başlığı "tümünü seç" — kısmi seçimde
// indeterminate, tavanda pasif), altta "Seçili · sıra" (↑↓ + kaldır + Temizle). Tip rozeti DOM'da YOK,
// tip yalnız satırın `title` ipucunda. Seçim sırası = rapordaki kolon sırası; set tıklaması seçimi
// setin sırasıyla DEĞİŞTİRİR.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { OP_BY_TIP, TANIM_LIMITLERI, type FiltreKontrolu, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi } from "@/lib/reports";
import { ColumnSheet } from "./ColumnSheet";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const KONTROL: Record<KolonTipi, FiltreKontrolu> = {
    metin: "metin_icerir", liste: "coklu_secim", tarih: "tarih_araligi", sayi: "sayi_araligi", para: "sayi_araligi", mantik: "mantik",
};
type KolonSahtesi = Pick<KatalogKolon, "anahtar" | "etiket" | "tip" | "grup"> & Partial<KatalogKolon>;
function kolon(k: KolonSahtesi): KatalogKolon {
    const filtrelenebilir = k.filtrelenebilir ?? true;
    return {
        filtrelenebilir, siralanabilir: true, turetilmis: false, secenekler: null,
        kontrol: filtrelenebilir ? KONTROL[k.tip] : null,
        oplar: filtrelenebilir ? [...OP_BY_TIP[k.tip]] : [],
        oneriler: null, oneri_kesik: false,
        ...k,
    };
}

const KAYNAK: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "Dava kartları",
    varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin", grup: "Kimlik" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin", grup: "Kimlik" }),
        kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", grup: "Taraflar", filtrelenebilir: false, siralanabilir: false, turetilmis: true }),
        kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "karar_tarihi", etiket: "Karar Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", grup: "Karar ve aşama", secenekler: ["Derdest", "Karar"] },),
    ],
    hizli_filtreler: [],
    kolon_setleri: [
        { ad: "Temel", kolonlar: ["tracking_no", "subject"] },
        { ad: "Karar takibi", kolonlar: ["tracking_no", "status", "karar_tarihi"] },
        { ad: "Tazminat", kolonlar: ["tracking_no", "maddi_tazminat", "olmayan_kolon"] },
    ],
};

/** Sayfa gibi: seçim dışarıda tutulur, her değişiklik kaydedilir. */
function Sahne({ kaynak, baslangic, onChange }: { kaynak: KatalogVeriKaynagi; baslangic: string[]; onChange: (k: string[]) => void }) {
    const [secili, setSecili] = useState(baslangic);
    return (
        <ColumnSheet
            kaynak={kaynak}
            secili={secili}
            onChange={next => {
                setSecili(next);
                onChange(next);
            }}
        />
    );
}

describe("ColumnSheet (G139)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let onChange: ReturnType<typeof vi.fn<(k: string[]) => void>>;

    beforeEach(() => {
        container = document.createElement("div");
        document.body.appendChild(container);
        onChange = vi.fn<(k: string[]) => void>();
    });
    afterEach(() => {
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
    });

    function render(baslangic: string[] = ["tracking_no", "subject"], kaynak: KatalogVeriKaynagi = KAYNAK) {
        root = createRoot(container);
        act(() => {
            root!.render(<Sahne kaynak={kaynak} baslangic={baslangic} onChange={onChange} />);
        });
    }
    const dugme = () => container.querySelector<HTMLButtonElement>("[data-testid='kolon-dugmesi']")!;
    const panel = () => document.body.querySelector("[data-testid='kolon-paneli']");
    const tikla = (el: Element) => act(() => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    function ac(): ParentNode {
        tikla(dugme());
        const p = panel();
        if (!p) throw new Error("panel açılmadı");
        return p;
    }
    const seciliSira = (p: ParentNode) => Array.from(p.querySelectorAll("[data-kolon]")).map(li => li.getAttribute("data-kolon"));
    const setler = (p: ParentNode) => Array.from(p.querySelectorAll("[data-kolon-seti]"));
    const gruplar = (p: ParentNode) => Array.from(p.querySelectorAll("[data-kolon-grubu]")).map(g => g.getAttribute("data-kolon-grubu"));

    it("düğme sayıyı taşır; panel kapalıyken kolon listesi DOM'da yok; açılınca portal'da setler + gruplar + sıra; tip rozeti yok, tip title'da", () => {
        render();
        expect(dugme().textContent?.trim()).toBe("Kolonlar (2)");
        expect(dugme().getAttribute("aria-expanded")).toBe("false");
        expect(panel()).toBeNull();
        expect(document.body.querySelector("[data-kolon]")).toBeNull();

        const p = ac();
        expect(dugme().getAttribute("aria-expanded")).toBe("true");
        // Panel sayfa kabında değil, portal'da
        expect(container.contains(p as Node)).toBe(false);

        // Hazır setler: katalog sırası, geçersiz anahtar düşer (Tazminat 2 kolon); Temel seçili
        expect(setler(p).map(s => s.getAttribute("data-kolon-seti"))).toEqual(["Temel", "Karar takibi", "Tazminat"]);
        expect(setler(p).map(s => s.getAttribute("aria-pressed"))).toEqual(["true", "false", "false"]);
        expect(setler(p)[2].textContent).toContain("2");

        // Gruplar katalogdaki ilk görülme sırasıyla
        expect(gruplar(p)).toEqual(["Kimlik", "Taraflar", "Tarihler", "Tutarlar", "Karar ve aşama"]);
        expect(byLabel<HTMLInputElement>("Kimlik tümünü seç", p).checked).toBe(true);
        expect(byLabel<HTMLInputElement>("Tarihler tümünü seç", p).checked).toBe(false);

        // Seçili sıra
        expect(seciliSira(p)).toEqual(["tracking_no", "subject"]);

        // Tip rozeti yok — yalnız title
        const metin = (p as Element).textContent ?? "";
        expect(metin).not.toContain("abc");
        expect(metin).not.toContain("123");
        expect(metin).not.toContain("₺");
        expect(metin).not.toContain("türetilmiş");
        const satir = byLabel<HTMLInputElement>("Maddi Tazminat", p).closest("label")!;
        expect(satir.title).toBe("Maddi Tazminat · para");
        const turetilmis = byLabel<HTMLInputElement>("Müvekkiller", p).closest("label")!;
        expect(turetilmis.title).toContain("türetilmiş");

        // Kaynak açıklaması panelde tekrar etmez (sadeleştirme)
        expect(metin).not.toContain("Dava kartları");
    });

    it("set tıklaması seçimi setin sırasıyla DEĞİŞTİRİR; Temel varsayılana döndürür; aynı küme farklı sırada da set 'seçili'", () => {
        render();
        const p = ac();
        tikla(setler(p)[1]);
        expect(onChange).toHaveBeenLastCalledWith(["tracking_no", "status", "karar_tarihi"]);
        expect(seciliSira(p)).toEqual(["tracking_no", "status", "karar_tarihi"]);
        expect(dugme().textContent?.trim()).toBe("Kolonlar (3)");
        expect(setler(p).map(s => s.getAttribute("aria-pressed"))).toEqual(["false", "true", "false"]);

        // Sırayı değiştir → küme aynı, set hâlâ seçili
        tikla(byLabel("Ofis No aşağı", p));
        expect(seciliSira(p)).toEqual(["status", "tracking_no", "karar_tarihi"]);
        expect(setler(p)[1].getAttribute("aria-pressed")).toBe("true");

        tikla(setler(p)[0]);
        expect(onChange).toHaveBeenLastCalledWith(["tracking_no", "subject"]);
        expect(setler(p)[0].getAttribute("aria-pressed")).toBe("true");
    });

    it("grup 'tümünü seç': eksikleri sona ekler (kısmi → indeterminate), tam seçiliyken grubu kaldırır; tekil checkbox ve kaldır düğmesi", () => {
        render();
        const p = ac();
        const tarihler = byLabel<HTMLInputElement>("Tarihler tümünü seç", p);
        expect(tarihler.indeterminate).toBe(false);

        tikla(byLabel("Açılış Tarihi", p));
        expect(onChange).toHaveBeenLastCalledWith(["tracking_no", "subject", "opening_date"]);
        expect(byLabel<HTMLInputElement>("Tarihler tümünü seç", p).indeterminate).toBe(true);
        expect(byLabel<HTMLInputElement>("Tarihler tümünü seç", p).checked).toBe(false);

        tikla(byLabel("Tarihler tümünü seç", p));
        expect(onChange).toHaveBeenLastCalledWith(["tracking_no", "subject", "opening_date", "karar_tarihi"]);
        expect(byLabel<HTMLInputElement>("Tarihler tümünü seç", p).checked).toBe(true);
        expect(byLabel<HTMLInputElement>("Tarihler tümünü seç", p).indeterminate).toBe(false);

        tikla(byLabel("Tarihler tümünü seç", p));
        expect(onChange).toHaveBeenLastCalledWith(["tracking_no", "subject"]);

        // Kimlik grubu tam seçili → tık kaldırır; sıradaki × de kaldırır
        tikla(byLabel("Kimlik tümünü seç", p));
        expect(onChange).toHaveBeenLastCalledWith([]);
        expect((p as Element).textContent).toContain("Kolon seçilmedi");
        tikla(byLabel("Durum", p));
        tikla(byLabel("Konu", p));
        expect(seciliSira(p)).toEqual(["status", "subject"]);
        tikla(byLabel("Durum kaldır", p));
        expect(onChange).toHaveBeenLastCalledWith(["subject"]);
    });

    it("arama grupları süzer (boş grup çıkmaz); Temizle hepsini kaldırır; kolon tavanında grup başlığı ve boş satırlar pasif", () => {
        render();
        const p = ac();
        const arama = byLabel<HTMLInputElement>("Kolon ara", p);
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(arama, "tarih");
            arama.dispatchEvent(new Event("input", { bubbles: true }));
        });
        expect(gruplar(p)).toEqual(["Tarihler"]);
        act(() => {
            setter.call(arama, "yok böyle");
            arama.dispatchEvent(new Event("input", { bubbles: true }));
        });
        expect((p as Element).textContent).toContain("Aramaya uyan kolon yok");
        act(() => {
            setter.call(arama, "");
            arama.dispatchEvent(new Event("input", { bubbles: true }));
        });

        const temizle = Array.from(p.querySelectorAll("button")).find(b => b.textContent?.trim() === "Temizle")!;
        tikla(temizle);
        expect(onChange).toHaveBeenLastCalledWith([]);
        expect(dugme().textContent?.trim()).toBe("Kolonlar (0)");
        expect(seciliSira(p)).toEqual([]);

        // Tavan: kolon_max kadar kolonlu kaynakta hepsi seçiliyken yeni grup başlığı pasif
        act(() => root!.unmount());
        root = null;
        const cok = Array.from({ length: TANIM_LIMITLERI.kolon_max }, (_, i) =>
            kolon({ anahtar: `k${i}`, etiket: `Kolon ${i}`, tip: "metin", grup: "Çok" }));
        const kaynak: KatalogVeriKaynagi = {
            ...KAYNAK,
            kolonlar: [...cok, kolon({ anahtar: "ek", etiket: "Ek Kolon", tip: "metin", grup: "Ek" })],
            varsayilan_kolonlar: cok.map(k => k.anahtar),
            kolon_setleri: [],
        };
        render(cok.map(k => k.anahtar), kaynak);
        const p2 = ac();
        expect(dugme().textContent?.trim()).toBe(`Kolonlar (${TANIM_LIMITLERI.kolon_max})`);
        expect(byLabel<HTMLInputElement>("Ek tümünü seç", p2).disabled).toBe(true);
        expect(byLabel<HTMLInputElement>("Ek Kolon", p2).disabled).toBe(true);
        // Katalogda "Temel" seti yok → varsayılandan üretilir
        expect(setler(p2).map(s => s.getAttribute("data-kolon-seti"))).toEqual(["Temel"]);
    });

    it("Paneli kapat düğmesi paneli kapatır; seçim korunur", () => {
        render();
        const p = ac();
        tikla(byLabel("Durum", p));
        tikla(byLabel("Paneli kapat", p));
        expect(panel()).toBeNull();
        expect(dugme().getAttribute("aria-expanded")).toBe("false");
        expect(dugme().textContent?.trim()).toBe("Kolonlar (3)");
    });
});
