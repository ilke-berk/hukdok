// @vitest-environment jsdom
// QuickFilters (G138) — filtre şeridi: her kontrol §4.3'e göre doğru filtre JSON'u üretir
// (operatör seçici YOK), liste alanlarında serbest metin yok, öneri varsa combobox (seçim eq,
// yazım contains; taraf kolonunda eq yoksa contains), tarih kısayolları sabit bugünle,
// "+ Başka alan" gruplu/aranabilir ve şerittekileri gizler, çip × / "…" gelişmiş / Temizle.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import { OP_BY_TIP, type Filtre, type FiltreKontrolu, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi } from "@/lib/reports";
import { QuickFilters } from "./QuickFilters";
import { kaynakIcinBaslangic, seritFiltreleri, type SeritOgesi } from "./builderState";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// cmdk: liste yüksekliği için ResizeObserver, seçili öğe için scrollIntoView — jsdom'da yok.
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
        ...k,
    };
}

const KAYNAK: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "",
    varsayilan_kolonlar: ["tracking_no"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar", "Kesin"], grup: "Karar ve aşama" }),
        kolon({ anahtar: "court", etiket: "Mahkeme", tip: "metin", grup: "Mahkeme ve konu", oneriler: ["Ankara 1. Asliye", "Ankara 2. Asliye", "İzmir 3. Asliye"] }),
        kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "karar_tarihi", etiket: "Karar Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "active", etiket: "Aktif", tip: "mantik", grup: "Sistem" }),
        kolon({ anahtar: "foy_sayisi", etiket: "Föy Sayısı", tip: "sayi", filtrelenebilir: false, turetilmis: true, grup: "Sistem" }),
        kolon({ anahtar: "karsi_taraf_adlari", etiket: "Karşı Taraflar", tip: "metin", turetilmis: true, siralanabilir: false, grup: "Taraflar",
            oplar: ["contains", "is_null", "not_null"], oneriler: ["Sigorta A.Ş.", "Hastane B"] }),
    ],
    hizli_filtreler: [
        { alan: "opening_date", alternatifler: ["karar_tarihi"] },
        { alan: "status", alternatifler: [] },
        { alan: "court", alternatifler: [] },
        { alan: "maddi_tazminat", alternatifler: [] },
        { alan: "active", alternatifler: [] },
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no"] }],
};

type Kayit = { filtreler: Filtre[]; gecikmeli: boolean } | { hemen: true };
const BUGUN = () => new Date(2026, 8, 7);

function Harness({ kayit, baslangic }: { kayit: Kayit[]; baslangic: SeritOgesi[] }) {
    const [serit, setSerit] = useState<SeritOgesi[]>(baslangic);
    return (
        <QuickFilters
            kaynak={KAYNAK}
            serit={serit}
            onChange={(s, gecikmeli) => { kayit.push({ filtreler: seritFiltreleri(s), gecikmeli: !!gecikmeli }); setSerit(s); }}
            onHemen={() => kayit.push({ hemen: true })}
            bugun={BUGUN}
        />
    );
}

describe("QuickFilters (G138)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let kayit: Kayit[];

    beforeEach(() => {
        kayit = [];
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

    function render(baslangic: SeritOgesi[] = kaynakIcinBaslangic(KAYNAK).serit) {
        root = createRoot(container);
        act(() => {
            root!.render(<Harness kayit={kayit} baslangic={baslangic} />);
        });
    }

    const sonFiltreler = () => {
        const son = [...kayit].reverse().find(k => "filtreler" in k) as { filtreler: Filtre[]; gecikmeli: boolean } | undefined;
        if (!son) throw new Error("onChange hiç çağrılmadı");
        return son;
    };
    const $ = <T extends Element>(sel: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const butonBul = (metin: string, kok: ParentNode = container): HTMLButtonElement => {
        const b = Array.from(kok.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };
    function sec(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }
    function yaz(el: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }
    function tikla(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    }
    /** Gerçek odak: jsdom focus()/blur() focusin/focusout üretir (React onFocus/onBlur bunları dinler). */
    function odakla(el: HTMLElement) {
        act(() => { el.focus(); });
    }
    function odakCik(el: HTMLElement) {
        act(() => { el.focus(); });
        act(() => { el.blur(); });
    }
    const kontroller = () => Array.from(container.querySelectorAll("[data-testid='filtre-kontrolu']")).map(k => k.getAttribute("data-alan"));
    const cipler = () => Array.from(container.querySelectorAll("[data-testid='filtre-cipi']")).map(c => c.textContent?.trim());

    it("hızlı filtreler kaynağın sırasıyla, kontrol türü kataloğun `kontrol`ünden; operatör açılır listesi HİÇBİR yerde yok", () => {
        render();
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active"]);
        expect(Array.from(container.querySelectorAll("[data-testid='filtre-kontrolu']")).map(k => k.getAttribute("data-kontrol")))
            .toEqual(["tarih_araligi", "coklu_secim", "metin_icerir", "sayi_araligi", "mantik"]);
        expect(container.querySelector("[aria-label='Operatör']")).toBeNull();
        expect(container.querySelector("option[value='between'], option[value='contains'], option[value='is_null']")).toBeNull();
        // Henüz etkin filtre yok: çip satırı ve sayaç yok
        expect(container.querySelector("[data-testid='etkin-filtreler']")).toBeNull();
        expect(container.querySelector("[data-testid='etkin-filtre-sayisi']")).toBeNull();
    });

    it("tarih aralığı: başlangıç gte (gecikmeli), bitiş → between iki ISO; kısayol sabit tarihle anında; alan değiştirici değeri korur; boş olanlar is_null", () => {
        render();
        yaz(byLabel("Açılış Tarihi başlangıç"), "2025-01-01");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "opening_date", op: "gte", deger: "2025-01-01" }], gecikmeli: true });
        yaz(byLabel("Açılış Tarihi bitiş"), "2025-12-31");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "opening_date", op: "between", deger: ["2025-01-01", "2025-12-31"] }]);
        odakCik(byLabel("Açılış Tarihi bitiş"));
        expect(kayit.at(-1)).toEqual({ hemen: true });
        expect(cipler()).toEqual(["Açılış Tarihi01.01.2025 – 31.12.2025"]);

        sec(byLabel<HTMLSelectElement>("Açılış Tarihi kısayol"), "bu_yil");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "opening_date", op: "between", deger: ["2026-01-01", "2026-09-07"] }], gecikmeli: false });
        sec(byLabel<HTMLSelectElement>("Açılış Tarihi kısayol"), "son_30_gun");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "opening_date", op: "between", deger: ["2026-08-09", "2026-09-07"] }]);

        // Alan değiştirici: aynı yuva, alan karar_tarihi, değerler korunur; etiketler yeni alana geçer
        sec(byLabel<HTMLSelectElement>("Açılış Tarihi alanı"), "karar_tarihi");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "karar_tarihi", op: "between", deger: ["2026-08-09", "2026-09-07"] }]);
        expect(kontroller()).toEqual(["karar_tarihi", "status", "court", "maddi_tazminat", "active"]);
        expect(container.querySelector("[aria-label='Karar Tarihi başlangıç']")).not.toBeNull();

        tikla(byLabel("Karar Tarihi boş olanlar"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "karar_tarihi", op: "is_null" }]);
        expect(byLabel<HTMLInputElement>("Karar Tarihi başlangıç").disabled).toBe(true);
        expect(cipler()).toEqual(["Karar Tarihiboş"]);

        // Çipin × düğmesi: yuva kendi alanına ve boşa döner (şeritten kalkmaz)
        tikla(byLabel("Karar Tarihi filtresini kaldır"));
        expect(sonFiltreler().filtreler).toEqual([]);
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active"]);
    });

    it("çoklu seçim: checkbox'lı açılır, 1 seçim eq, 2 seçim in; serbest metin girişi YOK; sayaç ve çip", () => {
        render();
        const durum = $("[data-testid='filtre-kontrolu'][data-alan='status']");
        expect(durum.querySelector("input[type='text']")).toBeNull();
        expect(container.querySelector("[aria-label='Durum: Derdest']")).toBeNull(); // kapalı
        tikla(byLabel("Durum seç"));
        const liste = byLabel("Durum seçenekleri");
        expect(Array.from(liste.querySelectorAll("input[type='checkbox']")).map(i => i.getAttribute("aria-label")))
            .toEqual(["Durum: Derdest", "Durum: Karar", "Durum: Kesin"]);
        tikla(byLabel("Durum: Derdest"));
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "status", op: "eq", deger: "Derdest" }], gecikmeli: false });
        tikla(byLabel("Durum: Karar"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "status", op: "in", deger: ["Derdest", "Karar"] }]);
        expect(byLabel<HTMLInputElement>("Durum: Karar").checked).toBe(true);
        expect($("[data-testid='etkin-filtre-sayisi']").textContent).toBe("1");
        expect(cipler()).toEqual(["DurumDerdest, Karar"]);
        // Tik kaldır → tekrar eq
        tikla(byLabel("Durum: Derdest"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "status", op: "eq", deger: "Karar" }]);
        expect(durum.querySelector("input[type='text']")).toBeNull();
    });

    it("sayı/para aralığı: en az gte (number), en çok → between [number, number]; mantık Evet/Hayır eq true/false", () => {
        render();
        yaz(byLabel("Maddi Tazminat en az"), "1000");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "maddi_tazminat", op: "gte", deger: 1000 }], gecikmeli: true });
        yaz(byLabel("Maddi Tazminat en çok"), "5000.5");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "maddi_tazminat", op: "between", deger: [1000, 5000.5] }]);
        yaz(byLabel("Maddi Tazminat en az"), "");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "maddi_tazminat", op: "lte", deger: 5000.5 }]);

        sec(byLabel<HTMLSelectElement>("Aktif değeri"), "true");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "maddi_tazminat", op: "lte", deger: 5000.5 }, { alan: "active", op: "eq", deger: true }]);
        sec(byLabel<HTMLSelectElement>("Aktif değeri"), "false");
        expect(sonFiltreler().filtreler.at(-1)).toEqual({ alan: "active", op: "eq", deger: false });
        sec(byLabel<HTMLSelectElement>("Aktif değeri"), "");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "maddi_tazminat", op: "lte", deger: 5000.5 }]);
    });

    /** Kontrolün öneri listesi (cmdk List, kendi aria-label'ını bastığı için `[cmdk-list]` ile). */
    const oneriListesi = (alan: string) => container.querySelector(`[data-testid='filtre-kontrolu'][data-alan='${alan}'] [cmdk-list]`);

    it("combobox (öneri listesi): yazdıkça daralır ve contains (gecikmeli); seçim eq (anında); taraf kolonunda eq yoksa contains", () => {
        render();
        const girdi = byLabel<HTMLInputElement>("Mahkeme içerir");
        expect(oneriListesi("court")).toBeNull();
        odakla(girdi);
        expect(oneriListesi("court")).not.toBeNull();
        yaz(girdi, "Ank");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "court", op: "contains", deger: "Ank" }], gecikmeli: true });
        const gorunen = () => Array.from(oneriListesi("court")!.querySelectorAll("[cmdk-item]")).map(i => i.textContent);
        expect(gorunen()).toEqual(["Ankara 1. Asliye", "Ankara 2. Asliye"]);
        tikla(oneriListesi("court")!.querySelectorAll("[cmdk-item]")[1]);
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "court", op: "eq", deger: "Ankara 2. Asliye" }], gecikmeli: false });
        expect(girdi.value).toBe("Ankara 2. Asliye");
        expect(oneriListesi("court")).toBeNull();
        expect(cipler()).toEqual(["Mahkeme= \"Ankara 2. Asliye\""]);
        // Seçimden sonra yazmak tam eşitliği bozar → contains
        yaz(girdi, "Ankara");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "court", op: "contains", deger: "Ankara" }]);

        // Taraf kolonu "+ Başka alan" ile: `oplar`da eq yok → seçim contains
        tikla(butonBul("Başka alan"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='karsi_taraf_adlari']"));
        const taraf = byLabel<HTMLInputElement>("Karşı Taraflar içerir");
        odakla(taraf);
        tikla(oneriListesi("karsi_taraf_adlari")!.querySelectorAll("[cmdk-item]")[0]);
        expect(sonFiltreler().filtreler).toEqual([
            { alan: "court", op: "contains", deger: "Ankara" },
            { alan: "karsi_taraf_adlari", op: "contains", deger: "Sigorta A.Ş." },
        ]);
        // Tam eşitlik menü öğesi taraf çipinde yok (eq izinli değil), mahkeme çipinde var
        tikla(byLabel("Karşı Taraflar filtre seçenekleri"));
        expect(Array.from(byLabel("Karşı Taraflar gelişmiş").querySelectorAll("button")).map(b => b.textContent)).toEqual(["dolu"]);
        tikla(byLabel("Mahkeme filtre seçenekleri"));
        expect(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button")).map(b => b.textContent))
            .toEqual(["Tam eşitlik", "eşit değil", "şunlardan biri", "dolu"]);
    });

    it("+ Başka alan: gruplu ve aranabilir; yalnız filtrelenebilir; şerittekiler (alternatif dahil) gizli; seçim aynı türde kontrol ekler, × şeritten kaldırır", () => {
        render();
        tikla(butonBul("Başka alan"));
        // Seçici kapanınca DOM'dan kalkar; her açılışta yeniden bulunur (bayat düğüm tuzağı).
        const secici = () => $("[data-testid='alan-secici']");
        // cmdk eşleşmeyen grubu DOM'dan kaldırmaz, `hidden` basar — görünen başlıklar sayılır.
        const basliklar = () => Array.from(secici().querySelectorAll("[cmdk-group]:not([hidden]) [cmdk-group-heading]")).map(h => h.textContent);
        const ogeler = () => Array.from(secici().querySelectorAll("[cmdk-item]")).map(i => i.getAttribute("data-alan"));
        expect(basliklar()).toEqual(["Kimlik", "Taraflar"]);
        // opening_date/karar_tarihi (yuva + alternatifi), status, court, maddi, active şeritte; foy_sayisi filtrelenemez
        expect(ogeler()).toEqual(["tracking_no", "subject", "karsi_taraf_adlari"]);

        yaz(byLabel("Alan ara"), "kon");
        expect(ogeler()).toEqual(["subject"]);
        expect(basliklar()).toEqual(["Kimlik"]);
        tikla(secici().querySelector("[cmdk-item][data-alan='subject']")!);
        expect(container.querySelector("[data-testid='alan-secici']")).toBeNull();
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active", "subject"]);

        // Öneri yok → düz metin: contains gecikmeli; odak çıkışı hemen
        const konu = byLabel<HTMLInputElement>("Konu içerir");
        yaz(konu, "Taz");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "subject", op: "contains", deger: "Taz" }], gecikmeli: true });
        odakCik(konu);
        expect(kayit.at(-1)).toEqual({ hemen: true });

        // Seçilen alan seçicide artık yok
        tikla(butonBul("Başka alan"));
        expect(ogeler()).toEqual(["tracking_no", "karsi_taraf_adlari"]);
        tikla(butonBul("Başka alan")); // kapat

        // Eklenen alanın × düğmesi şeritten kaldırır (yuva değil)
        tikla(byLabel("Konu alanını şeritten kaldır"));
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active"]);
        expect(sonFiltreler().filtreler).toEqual([]);
    });

    it("çipin \"…\" menüsü: yalnız kolonun `oplar`ındaki gelişmiş op'lar; dolu → gelişmiş çip (not_null); Basit kontrole dön yuvayı boşaltır", () => {
        render();
        tikla(byLabel("Durum seç"));
        tikla(byLabel("Durum: Kesin"));
        tikla(byLabel("Durum filtre seçenekleri"));
        const menu = byLabel("Durum gelişmiş");
        expect(Array.from(menu.querySelectorAll("button")).map(b => b.textContent)).toEqual(["eşit değil", "dolu"]);
        tikla(Array.from(menu.querySelectorAll("button")).find(b => b.textContent === "eşit değil")!);
        // Değer korunur, gelişmiş çip; kontrol yalnız değer girdisi (liste seçimi), operatör rozeti
        expect(sonFiltreler().filtreler).toEqual([{ alan: "status", op: "ne", deger: "Kesin" }]);
        const cip = $("[data-testid='filtre-cipi'][data-alan='status']");
        expect(cip.getAttribute("data-gelismis")).toBe("true");
        expect(cip.textContent).toContain("eşit değil Kesin");
        expect($("[data-testid='filtre-kontrolu'][data-alan='status']").getAttribute("data-kontrol")).toBe("gelismis");
        sec(byLabel<HTMLSelectElement>("Durum değeri"), "Karar");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "status", op: "ne", deger: "Karar" }]);

        // Gelişmiş çipin menüsü: diğer izinli op'lar + basit kontrole dön
        tikla(byLabel("Durum filtre seçenekleri"));
        const gelismisMenu = byLabel("Durum gelişmiş");
        expect(Array.from(gelismisMenu.querySelectorAll("button")).map(b => b.textContent))
            .toEqual(["eşittir", "şunlardan biri", "boş", "dolu", "Basit kontrole dön"]);
        tikla(Array.from(gelismisMenu.querySelectorAll("button")).find(b => b.textContent === "dolu")!);
        expect(sonFiltreler().filtreler).toEqual([{ alan: "status", op: "not_null" }]);
        expect(container.querySelector("[aria-label='Durum değeri']")).toBeNull();

        tikla(byLabel("Durum filtre seçenekleri"));
        tikla(Array.from(byLabel("Durum gelişmiş").querySelectorAll("button")).find(b => b.textContent === "Basit kontrole dön")!);
        expect(sonFiltreler().filtreler).toEqual([]);
        expect($("[data-testid='filtre-kontrolu'][data-alan='status']").getAttribute("data-kontrol")).toBe("coklu_secim");
        expect(kontroller()).toHaveLength(5);
    });

    it("metin çipinde \"Tam eşitlik\" anahtarı contains ↔ eq çevirir", () => {
        render();
        yaz(byLabel("Mahkeme içerir"), "Ankara");
        tikla(byLabel("Mahkeme filtre seçenekleri"));
        tikla(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button")).find(b => b.textContent === "Tam eşitlik")!);
        expect(sonFiltreler().filtreler).toEqual([{ alan: "court", op: "eq", deger: "Ankara" }]);
        tikla(byLabel("Mahkeme filtre seçenekleri"));
        expect(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button")).map(b => b.textContent)[0]).toBe("✓ Tam eşitlik");
        tikla(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button"))[0]);
        expect(sonFiltreler().filtreler).toEqual([{ alan: "court", op: "contains", deger: "Ankara" }]);
    });

    it("Filtreleri temizle: tüm değerler düşer, eklenen alanlar kalkar, yuvalar boş kalır", () => {
        render();
        yaz(byLabel("Açılış Tarihi başlangıç"), "2025-01-01");
        tikla(byLabel("Durum seç"));
        tikla(byLabel("Durum: Derdest"));
        tikla(butonBul("Başka alan"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='subject']"));
        yaz(byLabel("Konu içerir"), "x");
        expect(sonFiltreler().filtreler).toHaveLength(3);
        expect($("[data-testid='etkin-filtre-sayisi']").textContent).toBe("3");

        tikla(butonBul("Filtreleri temizle"));
        expect(sonFiltreler().filtreler).toEqual([]);
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active"]);
        expect(byLabel<HTMLInputElement>("Açılış Tarihi başlangıç").value).toBe("");
        expect(container.querySelector("[data-testid='etkin-filtreler']")).toBeNull();
        expect(butonBul("Filtreleri temizle").disabled).toBe(true);
    });
});
