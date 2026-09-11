// @vitest-environment jsdom
// TanimSeridi (G173) — sohbetin altındaki düzenlenebilir tanım şeridi: kaynak rozeti (menü) · kolon çipleri
// (× / "+ Kolon" gruplu combobox + hazır setler, bağlı kaynak kolonu ilişki öneği + renk çubuğu) · filtre
// çipleri (gövde → popover'da FilterControl; "+ Filtre" → FieldPicker; boş kontrol çip vermez) · sıralama
// çipleri · Temizle. Kontrollü: iç kopya yok, her değişiklik `onChange`. Radix menü/popover portal'da
// (document.body) açılır — testler oradan okur (ColumnSheet kalıbı).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, TANIM_LIMITLERI, type FiltreKontrolu, type HizliFiltre, type Katalog, type KatalogKolon, type KatalogVeriKaynagi,
    type KolonTipi, type RaporTanimi,
} from "@/lib/reports";
import { TanimSeridi } from "./TanimSeridi";
import { kaynakIcinBaslangic, tanimOlustur, tanimdanDurum, type OlusturucuDurumu } from "./builderState";
import { ANA_KAYNAK_RENGI, BAG_RENKLERI, kaynakRengi } from "./ui";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// cmdk/Radix: ResizeObserver ve scrollIntoView jsdom'da yok.
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
const hf = (alan: string, ek: Partial<HizliFiltre> = {}): HizliFiltre =>
    ({ alan, alternatifler: [], sunum: "varsayilan", etiket: null, ...ek });

/** 300 mahkeme önerisi (liste kesik). */
const MAHKEMELER = Array.from({ length: 300 }, (_, i) => `${i + 1}. Asliye Hukuk`);

const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar",
    etiket: "Davalar",
    aciklama: "Dava kartları",
    varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, siralanabilir: false, secilebilir: false, oplar: ["contains"] }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest", "Karar", "Kesin"], grup: "Karar ve aşama" }),
        kolon({ anahtar: "court", etiket: "Mahkeme", tip: "metin", grup: "Mahkeme ve konu", oneriler: MAHKEMELER, oneri_kesik: true }),
        kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "karar_tarihi", etiket: "Karar Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "foy_sayisi", etiket: "Föy Sayısı", tip: "sayi", filtrelenebilir: false, turetilmis: true, grup: "Sistem" }),
        // G166 bağlı kaynak kolonları: sunucu etiketi ve grubu "<İlişki> · …" ile verir
        kolon({ anahtar: "muvekkil.phone", etiket: "Müvekkil · Telefon", tip: "metin", grup: "Müvekkil · İletişim", bag: "muvekkil", siralanabilir: false }),
        kolon({ anahtar: "muvekkil.email", etiket: "Müvekkil · E-posta", tip: "metin", grup: "Müvekkil · İletişim", bag: "muvekkil", siralanabilir: false }),
        // Önek vermeyen (eski) katalog satırı: şerit öneği kendisi koyar, ikilemez
        kolon({ anahtar: "foy.dosya_no", etiket: "Dosya No", tip: "metin", grup: "Kimlik", bag: "foy", siralanabilir: false }),
    ],
    hizli_filtreler: [
        hf("opening_date", { alternatifler: ["karar_tarihi"] }),
        hf("status"),
        hf("court"),
        hf("maddi_tazminat"),
    ],
    kolon_setleri: [
        { ad: "Temel", kolonlar: ["tracking_no", "subject", "arama"] },
        { ad: "Karar takibi", kolonlar: ["tracking_no", "status", "karar_tarihi"] },
        { ad: "Boş set", kolonlar: ["olmayan"] },
    ],
    iliskiler: [
        { anahtar: "muvekkil", etiket: "Müvekkil", hedef: "muvekkiller", coklu: true },
        { anahtar: "foy", etiket: "Föy", hedef: "foyler", coklu: true },
    ],
};

const MUVEKKILLER: KatalogVeriKaynagi = {
    anahtar: "muvekkiller",
    etiket: "Müvekkiller",
    aciklama: "Müvekkil kartları",
    varsayilan_kolonlar: ["name"],
    kolonlar: [kolon({ anahtar: "name", etiket: "Ad", tip: "metin" })],
    hizli_filtreler: [],
    kolon_setleri: [],
};

const KATALOG: Katalog = {
    veri_kaynaklari: [DAVALAR, MUVEKKILLER],
    limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 },
};

type Kayit = { durum: OlusturucuDurumu; gecikmeli: boolean | undefined } | { hemen: true } | { kaynak: string };

let dısSet: ((d: OlusturucuDurumu) => void) | null = null;

function Harness({ kayit, baslangic, salt }: { kayit: Kayit[]; baslangic: OlusturucuDurumu; salt?: boolean }) {
    const [durum, setDurum] = useState<OlusturucuDurumu>(baslangic);
    dısSet = setDurum;
    return (
        <TanimSeridi
            katalog={KATALOG}
            durum={durum}
            onChange={(d, gecikmeli) => { kayit.push({ durum: d, gecikmeli }); setDurum(d); }}
            onHemen={() => kayit.push({ hemen: true })}
            onKaynakSec={anahtar => kayit.push({ kaynak: anahtar })}
            bugun="2026-09-11"
            salt={salt}
        />
    );
}

describe("TanimSeridi (G173)", () => {
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
        dısSet = null;
    });

    function render(baslangic: OlusturucuDurumu = kaynakIcinBaslangic(DAVALAR), salt?: boolean) {
        root = createRoot(container);
        act(() => {
            root!.render(<Harness kayit={kayit} baslangic={baslangic} salt={salt} />);
        });
    }
    const renderTanim = (tanim: RaporTanimi) => render(tanimdanDurum(tanim, DAVALAR));

    const $ = <T extends Element>(sel: string, kok: ParentNode = container): T => {
        const el = kok.querySelector<T>(sel);
        if (!el) throw new Error("bulunamadı: " + sel);
        return el;
    };
    /** Portal'da (document.body) açılan panel. */
    const $$ = <T extends Element>(sel: string): T => $(sel, document.body);
    const byLabel = <T extends HTMLElement>(label: string, kok: ParentNode = document.body): T => {
        const el = kok.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const butonBul = (metin: string, kok: ParentNode = container): HTMLButtonElement => {
        const b = Array.from(kok.querySelectorAll("button")).find(x => x.textContent?.trim() === metin);
        if (!b) throw new Error("düğme bulunamadı: " + metin);
        return b;
    };
    function tikla(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    }
    /** Radix DropdownMenu tetikleyicisi pointerdown ile açılır (click ile değil). */
    function bas(el: Element) {
        act(() => {
            el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, button: 0 }));
        });
    }
    function tus(el: Element, key: string) {
        act(() => {
            el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
        });
    }
    function yaz(el: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }
    function sec(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }
    function odakla(el: HTMLElement) {
        act(() => { el.focus(); });
    }
    function odakCik(el: HTMLElement) {
        act(() => { el.focus(); });
        act(() => { el.blur(); });
    }

    const sonDurum = () => {
        const son = [...kayit].reverse().find(k => "durum" in k) as { durum: OlusturucuDurumu; gecikmeli: boolean | undefined } | undefined;
        if (!son) throw new Error("onChange hiç çağrılmadı");
        return son;
    };
    const kolonCipleri = () => Array.from(container.querySelectorAll("[data-testid^='serit-kolon-']"))
        .filter(e => e.getAttribute("data-testid") !== "serit-kolon-ekle")
        .map(e => e.getAttribute("data-testid")!.replace("serit-kolon-", ""));
    const filtreCipleri = () => Array.from(container.querySelectorAll("[data-testid='filtre-cipi']")).map(c => c.textContent?.trim());
    const siralamaCipleri = () => Array.from(container.querySelectorAll("[data-testid^='serit-siralama-']")).map(c => c.textContent?.trim());
    const duzenleyici = (alan?: string) =>
        document.body.querySelector(`[data-testid='filtre-duzenleyici']${alan ? `[data-alan='${alan}']` : ""}`);

    const DOLU_TANIM: RaporTanimi = {
        veri_kaynagi: "davalar",
        kolonlar: ["tracking_no", "muvekkil.phone", "foy.dosya_no"],
        filtreler: [
            { alan: "status", op: "in", deger: ["Derdest", "Karar"] },
            { alan: "subject", op: "contains", deger: "Tazminat" },
        ],
        siralama: [{ alan: "opening_date", yon: "asc" }, { alan: "maddi_tazminat", yon: "desc" }],
    };

    it("yedi öğe: grup + kaynak rozeti + kolon çipleri (bağlı: ilişki öneği + ayrık renk çubuğu, ikileme yok) + filtre çipleri (yalnız dolu) + '+ Kolon' / '+ Filtre' + sıralama çipleri + Temizle; şerit sarar", () => {
        renderTanim(DOLU_TANIM);
        const serit = $("[data-testid='tanim-seridi']");
        expect(serit.getAttribute("role")).toBe("group");
        expect(serit.getAttribute("aria-label")).toBe("Rapor tanımı");
        // İki satır: üst satır kaynak + kolonlar + "+ Kolon", alt satır filtreler + "+ Filtre" + sıralama + Temizle; her biri sarar
        expect(serit.className).toContain("flex-col");
        const satirlar = Array.from(serit.children) as HTMLElement[];
        expect(satirlar.map(r => r.getAttribute("data-testid"))).toEqual(["serit-kolonlar", "serit-filtreler"]);
        for (const r of satirlar) expect(r.className).toContain("flex-wrap");
        expect(satirlar[0].contains($("[data-testid='serit-kaynak']"))).toBe(true);
        expect(satirlar[0].contains($("[data-testid='serit-kolon-ekle']"))).toBe(true);
        expect(satirlar[1].contains($("[data-testid='serit-filtre-ekle']"))).toBe(true);
        expect(satirlar[1].contains($("[data-testid='serit-temizle']"))).toBe(true);
        expect(satirlar[1].querySelector("[data-testid^='serit-kolon-']:not([data-testid='serit-kolon-ekle'])")).toBeNull();
        expect(serit.className).not.toMatch(/max-w-/);
        expect($("[data-testid='serit-kaynak']").textContent).toContain("Davalar");

        expect(kolonCipleri()).toEqual(["tracking_no", "muvekkil.phone", "foy.dosya_no"]);
        // Ana kaynak kolonu: önek yok, ana renk
        const ofis = $("[data-testid='serit-kolon-tracking_no']");
        expect(ofis.textContent).toContain("Ofis No");
        expect(ofis.getAttribute("data-bag")).toBeNull();
        expect($<HTMLElement>("[data-testid='kaynak-cubugu']", ofis).style.background).toBe(ANA_KAYNAK_RENGI);
        // Bağlı kolon: "Müvekkil ·" öneği bir kez, ad "Telefon", ilişki rengi (ana kaynaktan farklı)
        const tel = $("[data-testid='serit-kolon-muvekkil.phone']");
        expect(tel.getAttribute("data-bag")).toBe("muvekkil");
        expect(tel.textContent?.replace(/\s+/g, " ").trim()).toBe("Müvekkil · Telefon");
        expect(tel.textContent).not.toContain("Müvekkil · Müvekkil");
        const telRenk = $<HTMLElement>("[data-testid='kaynak-cubugu']", tel).style.background;
        expect(telRenk).toBe(BAG_RENKLERI[0]);
        expect(telRenk).not.toBe(ANA_KAYNAK_RENGI);
        // Önek vermeyen katalog etiketi: şerit ilişki etiketiyle önek koyar; ikinci ilişki ikinci renk
        const dosya = $("[data-testid='serit-kolon-foy.dosya_no']");
        expect(dosya.textContent?.replace(/\s+/g, " ").trim()).toBe("Föy · Dosya No");
        expect($<HTMLElement>("[data-testid='kaynak-cubugu']", dosya).style.background).toBe(BAG_RENKLERI[1]);
        expect(kaynakRengi("muvekkil", ["muvekkil", "foy"])).not.toBe(kaynakRengi("foy", ["muvekkil", "foy"]));

        // Filtre çipleri yalnız dolu kontroller (boş hızlı yuvalar court/opening_date/maddi görünmez)
        expect(filtreCipleri()).toEqual(["DurumDerdest, Karar", "Konuiçerir \"Tazminat\""]);
        expect(container.querySelectorAll("[data-testid='filtre-kontrolu']")).toHaveLength(0);

        expect(butonBul("Kolon").getAttribute("data-testid")).toBe("serit-kolon-ekle");
        expect($("[data-testid='serit-filtre-ekle'] button").textContent?.trim()).toBe("Filtre");
        expect(siralamaCipleri()).toEqual(["↑ Açılış Tarihi", "↓ Maddi Tazminat"]);
        expect($("[data-testid='serit-siralama-opening_date']").getAttribute("data-yon")).toBe("asc");
        expect($<HTMLButtonElement>("[data-testid='serit-temizle']").disabled).toBe(false);
        // "+ Sıralama" YOK (ekleme tablo başlığından)
        expect(container.textContent).not.toContain("Sıralama ekle");
    });

    it("kontrollü: dışarıdan `durum` değişince şerit değişir (iç kopya yok)", () => {
        render();
        expect(kolonCipleri()).toEqual(["tracking_no", "subject"]);
        expect(filtreCipleri()).toEqual([]);
        act(() => { dısSet!(tanimdanDurum(DOLU_TANIM, DAVALAR)); });
        expect(kolonCipleri()).toEqual(["tracking_no", "muvekkil.phone", "foy.dosya_no"]);
        expect(filtreCipleri()).toHaveLength(2);
        expect(siralamaCipleri()).toHaveLength(2);
        expect(kayit).toEqual([]);
    });

    it("kaynak rozeti menüsü: katalog kaynakları etiket + açıklamayla; farklı kaynak → onKaynakSec(anahtar); aynı kaynak → çağrı yok, onChange yok", () => {
        render();
        const rozet = $("[data-testid='serit-kaynak']");
        expect(document.body.querySelector("[role='menu']")).toBeNull();
        bas(rozet);
        const menu = $$("[role='menu']");
        // Portal içeriği Shell'in tema sarmalayıcısı DIŞINDA → sınıfı kendisi taşımalı (12.09: şeffaf panel bulgusu)
        expect(menu.className).toContain("theme-classic");
        const ogeler = Array.from(menu.querySelectorAll("[data-kaynak]"));
        expect(ogeler.map(o => o.getAttribute("data-kaynak"))).toEqual(["davalar", "muvekkiller"]);
        expect(ogeler[0].getAttribute("data-secili")).toBe("true");
        expect(ogeler[1].textContent).toContain("Müvekkiller");
        expect(ogeler[1].textContent).toContain("Müvekkil kartları");
        // Aynı kaynak: no-op
        tikla(ogeler[0]);
        expect(kayit).toEqual([]);
        bas(rozet);
        tikla($$("[role='menu'] [data-kaynak='muvekkiller']"));
        expect(kayit).toEqual([{ kaynak: "muvekkiller" }]);
        // Şerit kaynağı KENDİSİ değiştirmez (sayfa `kaynakIcinBaslangic` ile sıfırlar)
        expect($("[data-testid='serit-kaynak']").textContent).toContain("Davalar");
    });

    it("kolon ×: onChange kolon çıkarılmış durumla, gecikmeli yok; tek kolon kalınca × disabled + title", () => {
        render();
        tikla(byLabel("Konu kolonunu kaldır", container));
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(sonDurum().durum.kolonlar).toEqual(["tracking_no"]);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([]);
        const son = byLabel<HTMLButtonElement>("Ofis No kolonunu kaldır", container);
        expect(son.disabled).toBe(true);
        expect(son.title).toBe("En az bir kolon gerekli");
        tikla(son);
        expect(kayit.filter(k => "durum" in k)).toHaveLength(1);
    });

    it("+ Kolon combobox: 'Hazır setler' en üstte; grup başlıkları katalog `grup` / bağlı 'İlişki · grup'; seçilmiş ve `secilebilir=false` yok; arama etikete göre süzer; seçim ekler ve kapatır", () => {
        render();
        expect(document.body.querySelector("[data-testid='kolon-secici']")).toBeNull();
        tikla(butonBul("Kolon"));
        const secici = () => $$("[data-testid='kolon-secici']");
        expect(secici().className).toContain("max-w-[min(90vw,28rem)]");
        expect(secici().className).toContain("theme-classic");
        const basliklar = () => Array.from(secici().querySelectorAll("[cmdk-group]:not([hidden]) [cmdk-group-heading]")).map(h => h.textContent);
        const ogeler = () => Array.from(secici().querySelectorAll("[cmdk-item][data-kolon]")).map(i => i.getAttribute("data-kolon"));
        // tracking_no/subject seçili ve arama seçilemez → ana "Kimlik" grubu boş, listede yok; bağlı gruplar katalog sırasında
        // ("Müvekkil · İletişim" sunucudan önekli; "Föy · Kimlik" öneği şerit koyar — ana "Kimlik"e karışmaz)
        expect(basliklar()).toEqual(["Hazır setler", "Karar ve aşama", "Mahkeme ve konu", "Tarihler", "Tutarlar", "Sistem", "Müvekkil · İletişim", "Föy · Kimlik"]);
        expect(ogeler()).toEqual(["status", "court", "opening_date", "karar_tarihi", "maddi_tazminat", "foy_sayisi", "muvekkil.phone", "muvekkil.email", "foy.dosya_no"]);
        const foyGrubu = secici().querySelector("[cmdk-item][data-kolon='foy.dosya_no']")!.closest("[cmdk-group]")!;
        expect(foyGrubu.querySelector("[cmdk-group-heading]")?.textContent).toBe("Föy · Kimlik");
        // Bağlı kolon satırında ad öneksiz (grup başlığı önek taşır)
        expect(secici().querySelector("[cmdk-item][data-kolon='muvekkil.phone']")?.textContent).toBe("Telefon");
        // Hazır setler: boş set elenir, seçilemeyen anahtar düşer
        expect(Array.from(secici().querySelectorAll("[cmdk-item][data-set]")).map(i => i.getAttribute("data-set"))).toEqual(["Temel", "Karar takibi"]);

        yaz(byLabel("Kolon ara"), "tel");
        expect(ogeler()).toEqual(["muvekkil.phone"]);
        expect(basliklar()).toEqual(["Müvekkil · İletişim"]);
        tikla(secici().querySelector("[cmdk-item][data-kolon='muvekkil.phone']")!);
        expect(sonDurum().durum.kolonlar).toEqual(["tracking_no", "subject", "muvekkil.phone"]);
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(document.body.querySelector("[data-testid='kolon-secici']")).toBeNull();
        expect(kolonCipleri()).toEqual(["tracking_no", "subject", "muvekkil.phone"]);
        // Seçilen artık listede yok
        tikla(butonBul("Kolon"));
        expect(ogeler()).not.toContain("muvekkil.phone");
    });

    it("hazır set seçimi set kolonlarını tekrar olmadan ekler (sıra korunur); 60 tavanında düğme disabled + 'En çok 60 kolon'", () => {
        render();
        tikla(butonBul("Kolon"));
        tikla($$("[data-testid='kolon-secici'] [cmdk-item][data-set='Karar takibi']"));
        expect(sonDurum().durum.kolonlar).toEqual(["tracking_no", "subject", "status", "karar_tarihi"]);
        expect(document.body.querySelector("[data-testid='kolon-secici']")).toBeNull();
        // Tümü seçiliyken set tıklaması onChange üretmez (kolonEkle aynı nesne)
        const onceki = kayit.length;
        tikla(butonBul("Kolon"));
        tikla($$("[data-testid='kolon-secici'] [cmdk-item][data-set='Temel']"));
        expect(kayit.length).toBe(onceki);

        act(() => { dısSet!({ ...kaynakIcinBaslangic(DAVALAR), kolonlar: Array.from({ length: TANIM_LIMITLERI.kolon_max }, (_, i) => `k${i}`) }); });
        const dugme = butonBul("Kolon");
        expect(dugme.disabled).toBe(true);
        expect(dugme.title).toBe("En çok 60 kolon");
        // Katalogda olmayan kolon çipi ham anahtarla çizilir, kaldırılabilir
        expect($("[data-testid='serit-kolon-k0']").textContent).toContain("k0");
    });

    it("filtre çipine tık → popover'da FilterControl: metin girişi onChange(…, true), odak çıkışı onHemen; liste seçimi hemen; × filtreyi durumdan düşürür", () => {
        renderTanim(DOLU_TANIM);
        expect(duzenleyici()).toBeNull();
        const govde = byLabel("Konu filtresini düzenle", container);
        expect(govde.getAttribute("aria-haspopup")).toBe("dialog");
        expect(govde.getAttribute("aria-expanded")).toBe("false");
        tikla(govde);
        expect(govde.getAttribute("aria-expanded")).toBe("true");
        const panel = duzenleyici("subject")!;
        expect(panel).not.toBeNull();
        expect(panel.className).toContain("max-w-[min(90vw,28rem)]");
        expect(panel.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-kontrol")).toBe("metin_icerir");
        const girdi = byLabel<HTMLInputElement>("Konu içerir", panel);
        expect(girdi.value).toBe("Tazminat");
        yaz(girdi, "Tazmin");
        expect(sonDurum().gecikmeli).toBe(true);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([
            { alan: "status", op: "in", deger: ["Derdest", "Karar"] },
            { alan: "subject", op: "contains", deger: "Tazmin" },
        ]);
        expect(filtreCipleri()[1]).toBe("Konuiçerir \"Tazmin\"");
        odakCik(girdi);
        expect(kayit.at(-1)).toEqual({ hemen: true });
        // Gövdeye yeniden tık: kapanır
        tikla(byLabel("Konu filtresini düzenle", container));
        expect(duzenleyici("subject")).toBeNull();

        // Liste seçimi hemen (gecikmeli yok)
        tikla(byLabel("Durum filtresini düzenle", container));
        tikla(byLabel("Durum seç", duzenleyici("status")!));
        tikla(byLabel("Durum: Kesin"));
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(tanimOlustur(sonDurum().durum).filtreler[0]).toEqual({ alan: "status", op: "in", deger: ["Derdest", "Karar", "Kesin"] });
        // Aynı anda tek popover: Konu açılınca Durum kapanır
        tikla(byLabel("Konu filtresini düzenle", container));
        expect(duzenleyici("status")).toBeNull();
        expect(duzenleyici("subject")).not.toBeNull();

        // ×: hızlı yuva (status) boşa döner — çip düşer, öğe durumda kalır; eklenen alan (subject) şeritten kalkar
        tikla(byLabel("Durum filtresini kaldır", container));
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([{ alan: "subject", op: "contains", deger: "Tazmin" }]);
        expect(sonDurum().durum.serit.some(o => o.durum.alan === "status" && o.hizli)).toBe(true);
        tikla(byLabel("Konu filtresini kaldır", container));
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([]);
        expect(sonDurum().durum.serit.some(o => o.durum.alan === "subject")).toBe(false);
        expect(filtreCipleri()).toEqual([]);
        expect(duzenleyici()).toBeNull();
    });

    it("öneri listeli kolon (mahkeme): popover'daki combobox 300 öneriyle gelir, kesik başlığı korunur; tarih kısayolu sabit bugünle hemen", () => {
        renderTanim({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], siralama: [],
            filtreler: [{ alan: "court", op: "contains", deger: "Asliye" }, { alan: "opening_date", op: "gte", deger: "2025-01-01" }] });
        tikla(byLabel("Mahkeme filtresini düzenle", container));
        const panel = duzenleyici("court")!;
        const girdi = byLabel<HTMLInputElement>("Mahkeme içerir", panel);
        odakla(girdi);
        const liste = panel.querySelector("[cmdk-list]")!;
        expect(liste).not.toBeNull();
        expect(liste.querySelectorAll("[cmdk-item]")).toHaveLength(300);
        expect(liste.querySelector("[cmdk-group-heading]")?.textContent).toBe("İlk 300 değer (liste kesildi)");
        tikla(liste.querySelectorAll("[cmdk-item]")[4]);
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(tanimOlustur(sonDurum().durum).filtreler[0]).toEqual({ alan: "court", op: "eq", deger: "5. Asliye Hukuk" });
        expect(filtreCipleri()[0]).toBe("Mahkeme= \"5. Asliye Hukuk\"");

        tikla(byLabel("Açılış Tarihi filtresini düzenle", container));
        const tarih = duzenleyici("opening_date")!;
        expect(tarih.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-kontrol")).toBe("tarih_araligi");
        sec(byLabel<HTMLSelectElement>("Açılış Tarihi kısayol", tarih), "bu_yil");
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(tanimOlustur(sonDurum().durum).filtreler[1]).toEqual({ alan: "opening_date", op: "between", deger: ["2026-01-01", "2026-09-11"] });
        // Alan değiştirici yuvanın alternatifini sunar
        expect(Array.from(byLabel("Açılış Tarihi alanı", tarih).querySelectorAll("option")).map(o => o.value)).toEqual(["opening_date", "karar_tarihi"]);
    });

    it("+ Filtre: FieldPicker (filtrelenebilir, dolu alanlar hariç, bağlı kolonlar dahil) → boş kontrol + popover açık, çip yok; doldurunca çip; boş yuvası olan alan yuvayı yeniden kullanır", () => {
        renderTanim({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], siralama: [], filtreler: [{ alan: "status", op: "eq", deger: "Karar" }] });
        tikla($("[data-testid='serit-filtre-ekle'] button"));
        const secici = $("[data-testid='alan-secici']");
        expect(secici.className).toContain("left-0");   // düğme solda: panel sola hizalı, sol kenardan taşmaz (12.09)
        expect(secici.className).not.toContain("right-0");
        const alanlar = Array.from(secici.querySelectorAll("[cmdk-item]")).map(i => i.getAttribute("data-alan"));
        // status dolu → yok; foy_sayisi filtrelenemez → yok; boş hızlı yuvalar (court, opening_date, maddi) ve bağlı kolonlar VAR
        expect(alanlar).toEqual(["tracking_no", "subject", "arama", "court", "opening_date", "karar_tarihi", "maddi_tazminat", "muvekkil.phone", "muvekkil.email", "foy.dosya_no"]);
        tikla(secici.querySelector("[cmdk-item][data-alan='subject']")!);
        // Boş öğe eklendi (tanıma girmez), düzenleyici açık, çip yok — taslak çapa var
        const serit = sonDurum().durum.serit;
        expect(serit.at(-1)?.durum).toEqual({ kontrol: "metin_icerir", alan: "subject", metin: "", tam: false, bos: false });
        expect(serit.at(-1)?.hizli).toBe(false);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([{ alan: "status", op: "eq", deger: "Karar" }]);
        expect(filtreCipleri()).toEqual(["DurumKarar"]);
        expect($("[data-testid='serit-filtre-taslak']").getAttribute("data-alan")).toBe("subject");
        const panel = duzenleyici("subject")!;
        expect(panel).not.toBeNull();
        yaz(byLabel<HTMLInputElement>("Konu içerir", panel), "Taz");
        expect(sonDurum().gecikmeli).toBe(true);
        expect(filtreCipleri()).toEqual(["DurumKarar", "Konuiçerir \"Taz\""]);
        expect(container.querySelector("[data-testid='serit-filtre-taslak']")).toBeNull();

        // Boş hızlı yuvası olan alan (court): yeni öğe eklenmez, yuvanın düzenleyicisi açılır
        const onceki = sonDurum().durum.serit.length;
        tikla($("[data-testid='serit-filtre-ekle'] button"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='court']"));
        expect(duzenleyici("court")).not.toBeNull();
        expect(duzenleyici("subject")).toBeNull();
        const guncel = [...kayit].reverse().find(k => "durum" in k) as { durum: OlusturucuDurumu };
        expect(guncel.durum.serit).toHaveLength(onceki);
        expect(guncel.durum.serit.find(o => o.durum.alan === "court")?.hizli).toBe(true);
    });

    it("+ Filtre: doldurulmadan kapatılan alan çip vermez ama durumda kalır; 20 dolu filtrede düğme disabled + 'En çok 20 filtre'", () => {
        render();
        tikla($("[data-testid='serit-filtre-ekle'] button"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='subject']"));
        expect(duzenleyici("subject")).not.toBeNull();
        // Escape kapatır (Radix); öğe boş → çip yok, taslak yok, durumda var
        tus(duzenleyici("subject")!, "Escape");
        expect(duzenleyici("subject")).toBeNull();
        expect(filtreCipleri()).toEqual([]);
        expect(container.querySelector("[data-testid='serit-filtre-taslak']")).toBeNull();
        expect(sonDurum().durum.serit.some(o => o.durum.alan === "subject" && !o.hizli)).toBe(true);
        // Aynı alanı yeniden seçmek ikinci öğe eklemez, boş öğeyi açar
        const onceki = kayit.length;
        tikla($("[data-testid='serit-filtre-ekle'] button"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='subject']"));
        expect(kayit.length).toBe(onceki);
        expect(duzenleyici("subject")).not.toBeNull();

        const filtreler = Array.from({ length: TANIM_LIMITLERI.filtre_max }, (_, i) => ({ alan: "subject", op: "contains" as const, deger: `t${i}` }));
        act(() => { dısSet!(tanimdanDurum({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], siralama: [], filtreler }, DAVALAR)); });
        const dugme = $<HTMLButtonElement>("[data-testid='serit-filtre-ekle'] button");
        expect(dugme.disabled).toBe(true);
        expect(dugme.title).toBe("En çok 20 filtre");
        expect(filtreCipleri()).toHaveLength(TANIM_LIMITLERI.filtre_max);
    });

    it("sıralama çipi yön oku + etiket; × sıralamayı düşürür (diğeri kalır)", () => {
        renderTanim(DOLU_TANIM);
        expect($("[data-testid='serit-siralama-maddi_tazminat']").textContent?.trim()).toBe("↓ Maddi Tazminat");
        tikla(byLabel("Açılış Tarihi sıralamasını kaldır", container));
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(sonDurum().durum.siralama).toEqual([{ alan: "maddi_tazminat", yon: "desc" }]);
        expect(siralamaCipleri()).toEqual(["↓ Maddi Tazminat"]);
        // Diğer alanlar dokunulmaz
        expect(sonDurum().durum.kolonlar).toEqual(DOLU_TANIM.kolonlar);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual(DOLU_TANIM.filtreler);
    });

    it("Temizle: filtreler boş, kolonlar kaynağın varsayılanı, sıralama boş; kaynak değişmez; zaten temizken disabled", () => {
        renderTanim(DOLU_TANIM);
        tikla($("[data-testid='serit-temizle']"));
        expect(sonDurum().gecikmeli).toBeFalsy();
        expect(tanimOlustur(sonDurum().durum)).toEqual({ veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] });
        expect(sonDurum().durum.serit.every(o => o.hizli)).toBe(true);
        expect(filtreCipleri()).toEqual([]);
        expect(kolonCipleri()).toEqual(["tracking_no", "subject"]);
        expect($<HTMLButtonElement>("[data-testid='serit-temizle']").disabled).toBe(true);
        expect(kayit.some(k => "kaynak" in k)).toBe(false);
        // Kolon eklemek Temizle'yi yeniden açar
        tikla(butonBul("Kolon"));
        tikla($$("[data-testid='kolon-secici'] [cmdk-item][data-kolon='status']"));
        expect($<HTMLButtonElement>("[data-testid='serit-temizle']").disabled).toBe(false);
    });

    it("QuickFilters'tan taşınan çip davranışı: özet etiketli; '…' menüsü gelişmiş op → gelişmiş çip (data-gelismis), 'Basit kontrole dön' yuvayı boşaltır; boş kontrol çip vermez", () => {
        renderTanim({ veri_kaynagi: "davalar", kolonlar: ["tracking_no"], siralama: [], filtreler: [{ alan: "status", op: "eq", deger: "Kesin" }] });
        expect(filtreCipleri()).toEqual(["DurumKesin"]);
        tikla(byLabel("Durum filtre seçenekleri", container));
        const menu = byLabel("Durum gelişmiş", container);
        expect(Array.from(menu.querySelectorAll("button")).map(b => b.textContent)).toEqual(["eşit değil", "dolu"]);
        tikla(Array.from(menu.querySelectorAll("button")).find(b => b.textContent === "eşit değil")!);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([{ alan: "status", op: "ne", deger: "Kesin" }]);
        const cip = $("[data-testid='filtre-cipi'][data-alan='status']");
        expect(cip.getAttribute("data-gelismis")).toBe("true");
        expect(cip.textContent).toContain("eşit değil Kesin");
        // Gelişmiş çipin popover'ı değer girdisini (liste seçimi) açar
        tikla(byLabel("Durum filtresini düzenle", container));
        const panel = duzenleyici("status")!;
        expect(panel.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-kontrol")).toBe("gelismis");
        sec(byLabel<HTMLSelectElement>("Durum değeri", panel), "Karar");
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([{ alan: "status", op: "ne", deger: "Karar" }]);
        // Basit kontrole dön → yuva boş, çip düşer, popover kapanmaz ama boş kontrol çip vermez
        tikla(byLabel("Durum filtre seçenekleri", container));
        tikla(Array.from(byLabel("Durum gelişmiş", container).querySelectorAll("button")).find(b => b.textContent === "Basit kontrole dön")!);
        expect(tanimOlustur(sonDurum().durum).filtreler).toEqual([]);
        expect(filtreCipleri()).toEqual([]);
        expect(sonDurum().durum.serit.find(o => o.durum.alan === "status")?.durum.kontrol).toBe("coklu_secim");
    });

    it("salt: düzenleme kontrolleri gizli — rozet menüsüz, × yok, + Kolon / + Filtre / Temizle yok, çip gövdesi düğme değil; içerik görünür", () => {
        render(tanimdanDurum(DOLU_TANIM, DAVALAR), true);
        expect($("[data-testid='serit-kaynak']").tagName).toBe("SPAN");
        expect(kolonCipleri()).toEqual(["tracking_no", "muvekkil.phone", "foy.dosya_no"]);
        expect(filtreCipleri()).toHaveLength(2);
        expect(siralamaCipleri()).toHaveLength(2);
        expect(container.querySelector("[data-testid='serit-kolon-ekle']")).toBeNull();
        expect(container.querySelector("[data-testid='serit-filtre-ekle']")).toBeNull();
        expect(container.querySelector("[data-testid='serit-temizle']")).toBeNull();
        expect(container.querySelector("[aria-label$='kolonunu kaldır']")).toBeNull();
        expect(container.querySelector("[aria-label$='sıralamasını kaldır']")).toBeNull();
        expect(container.querySelector("[aria-label$='filtresini düzenle']")).toBeNull();
        expect(kayit).toEqual([]);
    });
});
