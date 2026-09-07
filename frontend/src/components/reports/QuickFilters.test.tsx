// @vitest-environment jsdom
// QuickFilters (G138) — filtre şeridi: her kontrol §4.3'e göre doğru filtre JSON'u üretir
// (operatör seçici YOK), liste alanlarında serbest metin yok, öneri varsa combobox (seçim eq,
// yazım contains; taraf kolonunda eq yoksa contains), tarih kısayolları sabit bugünle,
// "+ Başka alan" gruplu/aranabilir ve şerittekileri gizler, çip × / "…" gelişmiş / Temizle.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, type Filtre, type FiltreKontrolu, type HizliFiltre, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi,
    type RaporTanimi,
} from "@/lib/reports";
import { QuickFilters } from "./QuickFilters";
import { CIP_DUZ_SINIRI } from "./ChipSelect";
import { SIK_SECENEK_SAYISI } from "./FilterControl";
import { kaynakIcinBaslangic, seritFiltreleri, tanimdanDurum, type SeritOgesi } from "./builderState";

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
        secenek_kaynagi: k.tip === "liste" ? "sabit" : null, secenek_etiketleri: null, secilebilir: true,
        ...k,
    };
}
const hf = (alan: string, ek: Partial<HizliFiltre> = {}): HizliFiltre =>
    ({ alan, alternatifler: [], sunum: "varsayilan", etiket: null, ...ek });

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
        hf("opening_date", { alternatifler: ["karar_tarihi"] }),
        hf("status"),
        hf("court"),
        hf("maddi_tazminat"),
        hf("active"),
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["tracking_no"] }],
};

/** 79 il gibi: 10 değer, sıklık sırasıyla (ilk 8 "Sık"). */
const ILLER = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep", "Mersin", "Kayseri"];
/** 13 kategori: çip satırı 12 düz + "+N". */
const KATEGORILER = ["Doktor", "Hasta", "Hastane", "Sigorta", "Avukat", "Şirket", "Dernek", "Vakıf", "Kamu", "Eczane", "Klinik", "Laboratuvar", "Diğer"];

/** §5.1 müvekkil şeridi (katalog sahtesi §5.2 sözleşmesiyle). */
const MUVEKKILLER: KatalogVeriKaynagi = {
    anahtar: "muvekkiller",
    etiket: "Müvekkiller",
    aciklama: "",
    varsayilan_kolonlar: ["name"],
    kolonlar: [
        kolon({ anahtar: "name", etiket: "Ad", tip: "metin" }),
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, siralanabilir: false, secilebilir: false, oplar: ["contains"],
            aciklama: "Ad, cari kod, e-posta veya telefon…" }),
        kolon({ anahtar: "category", etiket: "Kategori", tip: "liste", secenekler: KATEGORILER, grup: "Sınıflandırma" }),
        kolon({ anahtar: "il", etiket: "İl", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ILLER, grup: "İletişim" }),
        kolon({ anahtar: "specialty", etiket: "Uzmanlık", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ["Ortopedi", "Göz"], grup: "Sınıflandırma" }),
        kolon({ anahtar: "client_type", etiket: "Müvekkil Türü", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri",
            secenekler: ["Individual", "Corporate"], secenek_etiketleri: { Individual: "Gerçek kişi", Corporate: "Tüzel kişi" }, grup: "Sınıflandırma" }),
        kolon({ anahtar: "dava_sayisi", etiket: "Dava Sayısı", tip: "sayi", turetilmis: true, siralanabilir: false, grup: "Sistem" }),
        kolon({ anahtar: "email", etiket: "E-posta", tip: "metin", grup: "İletişim" }),
        kolon({ anahtar: "mobile_phone", etiket: "Cep Telefonu", tip: "metin", grup: "İletişim" }),
    ],
    hizli_filtreler: [
        hf("arama", { sunum: "arama" }),
        hf("category", { sunum: "cipler" }),
        hf("il"),
        hf("specialty"),
        hf("dava_sayisi", { sunum: "var_yok", etiket: "Davası var" }),
        hf("email", { sunum: "bos_anahtari", etiket: "E-postası yok" }),
        hf("mobile_phone", { sunum: "bos_anahtari", etiket: "Cep telefonu yok" }),
    ],
    kolon_setleri: [{ ad: "Temel", kolonlar: ["name"] }],
};

type Kayit = { filtreler: Filtre[]; gecikmeli: boolean } | { hemen: true };
const BUGUN = () => new Date(2026, 8, 7);

function Harness({ kayit, baslangic, kaynak = KAYNAK }: { kayit: Kayit[]; baslangic: SeritOgesi[]; kaynak?: KatalogVeriKaynagi }) {
    const [serit, setSerit] = useState<SeritOgesi[]>(baslangic);
    return (
        <QuickFilters
            kaynak={kaynak}
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

    function render(baslangic: SeritOgesi[] = kaynakIcinBaslangic(KAYNAK).serit, kaynak: KatalogVeriKaynagi = KAYNAK) {
        root = createRoot(container);
        act(() => {
            root!.render(<Harness kayit={kayit} baslangic={baslangic} kaynak={kaynak} />);
        });
    }
    const renderMuvekkil = (baslangic: SeritOgesi[] = kaynakIcinBaslangic(MUVEKKILLER).serit) => render(baslangic, MUVEKKILLER);

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

    it("tarih aralığı: başlangıç gte (gecikmeli), bitiş → between iki ISO; kısayol sabit tarihle anında; alan değiştirici değeri korur; boş yalnız çipin \"…\" menüsünden (is_null)", () => {
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

        // "boş olanlar" kutucuğu YOK (§5.1 madde 8); boşluk çipin "…" menüsünden — gelişmiş is_null çipi
        expect(container.querySelector("[aria-label$='boş olanlar']")).toBeNull();
        tikla(byLabel("Karar Tarihi filtre seçenekleri"));
        expect(Array.from(byLabel("Karar Tarihi gelişmiş").querySelectorAll("button")).map(b => b.textContent)).toEqual(["eşittir", "boş", "dolu"]);
        tikla(Array.from(byLabel("Karar Tarihi gelişmiş").querySelectorAll("button")).find(b => b.textContent === "boş")!);
        expect(sonFiltreler().filtreler).toEqual([{ alan: "karar_tarihi", op: "is_null" }]);
        expect(container.querySelector("[aria-label='Karar Tarihi başlangıç']")).toBeNull();
        expect(cipler()).toEqual(["Karar Tarihigelişmişboş"]);

        // Çipin × düğmesi: yuva kendi alanına ve boşa döner (şeritten kalkmaz)
        tikla(byLabel("Karar Tarihi filtresini kaldır"));
        expect(sonFiltreler().filtreler).toEqual([]);
        expect(kontroller()).toEqual(["opening_date", "status", "court", "maddi_tazminat", "active"]);
    });

    it("çoklu seçim: checkbox'lı açılır, 1 seçim eq, 2 seçim in; serbest metin girişi YOK; sayaç ve çip; listenin sonunda (boş)", () => {
        render();
        const durum = $("[data-testid='filtre-kontrolu'][data-alan='status']");
        expect(durum.querySelector("input[type='text']")).toBeNull();
        expect(container.querySelector("[aria-label='Durum: Derdest']")).toBeNull(); // kapalı
        tikla(byLabel("Durum seç"));
        const liste = byLabel("Durum seçenekleri");
        expect(Array.from(liste.querySelectorAll("input[type='checkbox']")).map(i => i.getAttribute("aria-label")))
            .toEqual(["Durum: Derdest", "Durum: Karar", "Durum: Kesin", "Durum: (boş)"]);
        // 3 seçenek ≤ 8: "Sık" bölümü yok
        expect(liste.querySelector("[data-bolum]")).toBeNull();
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
        expect(Array.from(byLabel("Karşı Taraflar gelişmiş").querySelectorAll("button")).map(b => b.textContent)).toEqual(["boş", "dolu"]);
        tikla(byLabel("Mahkeme filtre seçenekleri"));
        expect(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button")).map(b => b.textContent))
            .toEqual(["Tam eşitlik", "eşit değil", "şunlardan biri", "boş", "dolu"]);
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

    // -----------------------------------------------------------------------
    // G142 — §5.1 müvekkil şeridi: arama · kategori çipleri · il · uzmanlık · davası var/yok · e-postası yok · cep yok
    // -----------------------------------------------------------------------

    const sunumlar = () => Array.from(container.querySelectorAll("[data-testid='filtre-kontrolu']")).map(k => k.getAttribute("data-sunum"));
    const tus = (el: HTMLElement, key: string) => act(() => {
        el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
    });

    it("§5.1 sıra: arama kutusu en üstte ayrı satır, kategori görünür çipler, il/uzmanlık çoklu seçim, var/yok anahtarı, iki boş anahtarı; \"boş olanlar\" DOM'da YOK", () => {
        renderMuvekkil();
        expect(kontroller()).toEqual(["arama", "category", "il", "specialty", "dava_sayisi", "email", "mobile_phone"]);
        expect(sunumlar()).toEqual(["arama", "cipler", "varsayilan", "varsayilan", "var_yok", "bos_anahtari", "bos_anahtari"]);
        // Arama kutusu şeridin en üstünde, ızgaranın DIŞINDA; placeholder katalog açıklamasından
        const serit = $("[data-testid='filtre-seridi']");
        const arama = $("[data-testid='arama-kutusu']");
        expect(arama.closest(".grid")).toBeNull();
        expect(byLabel<HTMLInputElement>("Ara").placeholder).toBe("Ad, cari kod, e-posta veya telefon…");
        expect(serit.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-alan")).toBe("arama");
        // Kategori: açılır değil, görünür çip düğmeleri
        expect(container.querySelector("[aria-label='Kategori seç']")).toBeNull();
        expect(byLabel("Kategori seçenekleri").getAttribute("role")).toBe("group");
        expect(byLabel<HTMLButtonElement>("Kategori: Doktor").tagName).toBe("BUTTON");
        // İl / Uzmanlık: aranabilir açılır
        expect(byLabel("İl seç").getAttribute("aria-haspopup")).toBe("listbox");
        expect(byLabel("Uzmanlık seç").getAttribute("aria-haspopup")).toBe("listbox");
        // Var/yok üçlü, boş anahtarları kutucuk; etiketler HizliFiltre.etiket'ten
        expect(Array.from(byLabel("Davası var").querySelectorAll("button")).map(b => b.textContent)).toEqual(["Hepsi", "Var", "Yok"]);
        expect(byLabel<HTMLInputElement>("E-postası yok").type).toBe("checkbox");
        expect(byLabel<HTMLInputElement>("Cep telefonu yok").type).toBe("checkbox");
        // "boş olanlar" hiçbir kontrolde yok
        expect(container.querySelector("[aria-label$='boş olanlar']")).toBeNull();
        expect(container.textContent).not.toContain("boş olanlar");
        expect(container.querySelector("[data-testid='etkin-filtreler']")).toBeNull();
    });

    it("İl: birden fazla değer in; \"(boş)\" null öğesi ekler (yalnız boş → is_null); Sık ilk 8 + Tümü; arama daraltır; seçili çipler ×; klavye ↑↓ Enter Esc", () => {
        renderMuvekkil();
        expect(container.querySelector("[aria-label='İl seçenekleri']")).toBeNull();
        tikla(byLabel("İl seç"));
        const liste = () => byLabel("İl seçenekleri");
        const bolum = (ad: string) => liste().querySelector(`[data-bolum='${ad}']`)!;
        const secenekler = (kok: ParentNode) => Array.from(kok.querySelectorAll("[role='option']")).map(o => o.getAttribute("data-deger"));
        expect(secenekler(bolum("Sık"))).toEqual(ILLER.slice(0, SIK_SECENEK_SAYISI));
        expect(secenekler(bolum("Tümü"))).toEqual([...ILLER, ""]); // katalog sırası (sıklık), sonda (boş)
        expect(liste().textContent).toContain("(boş)");

        tikla(byLabel("İl: Ankara"));
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "il", op: "eq", deger: "Ankara" }], gecikmeli: false });
        tikla(byLabel("İl: İzmir"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "in", deger: ["Ankara", "İzmir"] }]);
        tikla(byLabel("İl: (boş)"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "in", deger: ["Ankara", "İzmir", null] }]);
        expect(cipler()).toEqual(["İlAnkara, İzmir, boş"]);
        // Sık ve Tümü'de aynı öğe iki kez listelenir; ikisi de işaretli
        expect(Array.from(liste().querySelectorAll("[aria-label='İl: Ankara']")).every(i => (i as HTMLInputElement).checked)).toBe(true);
        // Seçilenler düğmenin altında çip; × düşürür
        const seciliCipler = () => Array.from($("[data-testid='secili-cipler']").querySelectorAll("[data-deger]")).map(c => c.getAttribute("data-deger"));
        expect(seciliCipler()).toEqual(["Ankara", "İzmir", ""]);
        tikla(byLabel("İl: Ankara kaldır"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "in", deger: ["İzmir", null] }]);

        // Arama: Sık kaybolur, Tümü daralır (tr-TR); (boş) sorguya uymaz
        const ara = byLabel<HTMLInputElement>("İl ara");
        yaz(ara, "kay");
        expect(liste().querySelector("[data-bolum]")).toBeNull();
        expect(secenekler(liste())).toEqual(["Kayseri"]);
        // Enter aktif öğeyi işaretler
        tus(ara, "Enter");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "in", deger: ["İzmir", null, "Kayseri"] }]);
        yaz(ara, "yok böyle il");
        expect(liste().textContent).toContain("Aramaya uyan seçenek yok");
        yaz(ara, "");
        // ↓ ↓ → üçüncü öğe (İzmir) aktif; Enter işaretini KALDIRIR
        tus(ara, "ArrowDown");
        tus(ara, "ArrowDown");
        expect(liste().querySelector("[data-aktif='true']")?.getAttribute("data-deger")).toBe("İzmir");
        tus(ara, "Enter");
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "in", deger: [null, "Kayseri"] }]);
        // Yalnız (boş) kalınca is_null
        tikla(byLabel("İl: Kayseri kaldır"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "il", op: "is_null" }]);
        expect(cipler()).toEqual(["İlboş"]);
        // Esc kapatır
        tus(ara, "Escape");
        expect(container.querySelector("[aria-label='İl seçenekleri']")).toBeNull();
        // Serbest metin girişi yok
        expect($("[data-testid='filtre-kontrolu'][data-alan='il']").querySelector("input[type='text']")).toBeNull();
    });

    it("client_type: seçenekler etiketle görünür (Gerçek kişi / Tüzel kişi), filtre HAM kodla gider; çip özeti etiketli", () => {
        renderMuvekkil();
        tikla(butonBul("Başka alan"));
        tikla($("[data-testid='alan-secici'] [cmdk-item][data-alan='client_type']"));
        tikla(byLabel("Müvekkil Türü seç"));
        const liste = byLabel("Müvekkil Türü seçenekleri");
        expect(Array.from(liste.querySelectorAll("input[type='checkbox']")).map(i => i.getAttribute("aria-label")))
            .toEqual(["Müvekkil Türü: Gerçek kişi", "Müvekkil Türü: Tüzel kişi", "Müvekkil Türü: (boş)"]);
        expect(liste.textContent).not.toContain("Individual");
        tikla(byLabel("Müvekkil Türü: Gerçek kişi"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "client_type", op: "eq", deger: "Individual" }]);
        tikla(byLabel("Müvekkil Türü: Tüzel kişi"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "client_type", op: "in", deger: ["Individual", "Corporate"] }]);
        expect(cipler()).toEqual(["Müvekkil TürüGerçek kişi, Tüzel kişi"]);
        expect(byLabel("Müvekkil Türü seç").textContent).toBe("Gerçek kişi, Tüzel kişi");
    });

    it("Kategori çip satırı: ≤ 12 düz, fazlası \"+N\"; çoklu seçim in (1 → eq); (boş) sonda; seçili çipler daraltılınca da görünür", () => {
        renderMuvekkil();
        const grup = () => byLabel("Kategori seçenekleri");
        const gorunen = () => Array.from(grup().querySelectorAll("button[data-deger]")).map(b => b.getAttribute("data-deger"));
        expect(gorunen()).toEqual(KATEGORILER.slice(0, CIP_DUZ_SINIRI));
        expect(byLabel("Kategori tümünü göster").textContent).toBe("+2"); // Laboratuvar, Diğer ve (boş) → 14 seçenek, 12 görünür
        tikla(byLabel("Kategori: Doktor"));
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "category", op: "eq", deger: "Doktor" }], gecikmeli: false });
        expect(byLabel("Kategori: Doktor").getAttribute("aria-pressed")).toBe("true");
        tikla(byLabel("Kategori: Hasta"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "category", op: "in", deger: ["Doktor", "Hasta"] }]);
        tikla(byLabel("Kategori tümünü göster"));
        expect(gorunen()).toEqual([...KATEGORILER, ""]);
        tikla(byLabel("Kategori: (boş)"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "category", op: "in", deger: ["Doktor", "Hasta", null] }]);
        tikla(byLabel("Kategori daha az göster"));
        expect(gorunen()).toEqual([...KATEGORILER.slice(0, CIP_DUZ_SINIRI), ""]);
        expect(byLabel("Kategori tümünü göster").textContent).toBe("+1");
        expect(cipler()).toEqual(["KategoriDoktor, Hasta, boş"]);
        tikla(byLabel("Kategori: Doktor"));
        tikla(byLabel("Kategori: Hasta"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "category", op: "is_null" }]);
    });

    it("arama kutusu: contains gecikmeli, odak çıkışı hemen, × temizler; Filtreleri temizle aramayı da siler", () => {
        renderMuvekkil();
        const kutu = byLabel<HTMLInputElement>("Ara");
        expect(container.querySelector("[aria-label='Ara temizle']")).toBeNull();
        yaz(kutu, "Ayşe");
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "arama", op: "contains", deger: "Ayşe" }], gecikmeli: true });
        odakCik(kutu);
        expect(kayit.at(-1)).toEqual({ hemen: true });
        expect(cipler()).toEqual(["Araiçerir \"Ayşe\""]);
        expect($("[data-testid='etkin-filtre-sayisi']").textContent).toBe("1");
        tikla(byLabel("Ara temizle"));
        expect(sonFiltreler()).toEqual({ filtreler: [], gecikmeli: false });
        expect(kutu.value).toBe("");
        expect(container.querySelector("[aria-label='Ara temizle']")).toBeNull();

        yaz(kutu, "Mehmet");
        tikla(byLabel("Kategori: Hasta"));
        expect(sonFiltreler().filtreler).toHaveLength(2);
        tikla(butonBul("Filtreleri temizle"));
        expect(sonFiltreler().filtreler).toEqual([]);
        expect(kutu.value).toBe("");
        expect(kontroller()).toEqual(["arama", "category", "il", "specialty", "dava_sayisi", "email", "mobile_phone"]);
        // Arama kolonu "+ Başka alan"da yok (şeritte); Kategori de yok
        tikla(butonBul("Başka alan"));
        const ogeler = Array.from($("[data-testid='alan-secici']").querySelectorAll("[cmdk-item]")).map(i => i.getAttribute("data-alan"));
        expect(ogeler).toEqual(["name", "client_type"]);
    });

    it("var/yok üç durum: var gte 1, yok eq 0, hepsi yok; boş anahtarları is_null; çip × yuvayı kendi kontrolüyle boşa döndürür", () => {
        renderMuvekkil();
        tikla(byLabel("Davası var: var"));
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "dava_sayisi", op: "gte", deger: 1 }], gecikmeli: false });
        expect(byLabel("Davası var: var").getAttribute("aria-pressed")).toBe("true");
        expect(cipler()).toEqual(["Dava Sayısıvar"]);
        tikla(byLabel("Davası var: yok"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "dava_sayisi", op: "eq", deger: 0 }]);
        expect(cipler()).toEqual(["Dava Sayısıyok"]);
        // "…" menüsü: sayı kolonunun diğer op'ları (gte/eq doğal) — başka aralık gelişmiş çipten
        tikla(byLabel("Dava Sayısı filtre seçenekleri"));
        expect(Array.from(byLabel("Dava Sayısı gelişmiş").querySelectorAll("button")).map(b => b.textContent)).toEqual(["≤ (en çok)", "aralıkta", "boş", "dolu"]);
        tikla(byLabel("Dava Sayısı filtre seçenekleri")); // kapat
        tikla(byLabel("Davası var: hepsi"));
        expect(sonFiltreler().filtreler).toEqual([]);

        tikla(byLabel("E-postası yok"));
        expect(sonFiltreler()).toEqual({ filtreler: [{ alan: "email", op: "is_null" }], gecikmeli: false });
        expect(byLabel<HTMLInputElement>("E-postası yok").checked).toBe(true);
        expect(cipler()).toEqual(["E-postaboş"]);
        tikla(byLabel("Cep telefonu yok"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "email", op: "is_null" }, { alan: "mobile_phone", op: "is_null" }]);
        expect($("[data-testid='etkin-filtre-sayisi']").textContent).toBe("2");
        // Çip ×: yuva boş anahtarı olarak kalır (kontrol türü değişmez), kutucuk açılmamış
        tikla(byLabel("E-posta filtresini kaldır"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "mobile_phone", op: "is_null" }]);
        expect($("[data-testid='filtre-kontrolu'][data-alan='email']").getAttribute("data-kontrol")).toBe("bos_anahtari");
        expect(byLabel<HTMLInputElement>("E-postası yok").checked).toBe(false);
        tikla(byLabel("Cep telefonu yok"));
        expect(sonFiltreler().filtreler).toEqual([]);
    });

    it("şablon/asistan tanımı şeride çözülür: arama kutusu dolu, (boş) seçili, var/yok basılı, boş anahtarı işaretli; JSON kayıpsız", () => {
        const tanim: RaporTanimi = {
            veri_kaynagi: "muvekkiller", kolonlar: ["name"], siralama: [],
            filtreler: [
                { alan: "arama", op: "contains", deger: "Ayşe" },
                { alan: "il", op: "in", deger: ["Ankara", null] },
                { alan: "dava_sayisi", op: "gte", deger: 1 },
                { alan: "email", op: "is_null" },
            ],
        };
        renderMuvekkil(tanimdanDurum(tanim, MUVEKKILLER).serit);
        expect(byLabel<HTMLInputElement>("Ara").value).toBe("Ayşe");
        expect(byLabel("İl seç").textContent).toBe("Ankara, (boş)");
        expect(byLabel("Davası var: var").getAttribute("aria-pressed")).toBe("true");
        expect(byLabel<HTMLInputElement>("E-postası yok").checked).toBe(true);
        expect(cipler()).toEqual(["Araiçerir \"Ayşe\"", "İlAnkara, boş", "Dava Sayısıvar", "E-postaboş"]);
        expect(container.querySelectorAll("[data-gelismis='true']")).toHaveLength(0);
        tikla(byLabel("İl seç"));
        expect(byLabel<HTMLInputElement>("İl: (boş)").checked).toBe(true);
        // Değişiklik yapıp geri alınca aynı JSON
        tikla(byLabel("İl: Bursa"));
        tikla(byLabel("İl: Bursa"));
        expect(sonFiltreler().filtreler).toEqual(tanim.filtreler);
    });

    it("kalıp kaynak bağımsız: Davalar'da `court` veriden çoklu seçim gelince aynı bileşen (checkbox listesi, in), combobox değil", () => {
        const davalar: KatalogVeriKaynagi = {
            ...KAYNAK,
            kolonlar: KAYNAK.kolonlar.map(k => k.anahtar === "court"
                ? kolon({ anahtar: "court", etiket: "Mahkeme", tip: "metin", grup: "Mahkeme ve konu", kontrol: "coklu_secim", secenek_kaynagi: "veri",
                    secenekler: ["Ankara 1. Asliye", "İzmir 3. Asliye"] })
                : k),
        };
        render(kaynakIcinBaslangic(davalar).serit, davalar);
        expect($("[data-testid='filtre-kontrolu'][data-alan='court']").getAttribute("data-kontrol")).toBe("coklu_secim");
        expect(container.querySelector("[aria-label='Mahkeme içerir']")).toBeNull();
        tikla(byLabel("Mahkeme seç"));
        tikla(byLabel("Mahkeme: Ankara 1. Asliye"));
        tikla(byLabel("Mahkeme: İzmir 3. Asliye"));
        expect(sonFiltreler().filtreler).toEqual([{ alan: "court", op: "in", deger: ["Ankara 1. Asliye", "İzmir 3. Asliye"] }]);
        // Metin kolonu olduğu için "…" menüsünde "içerir" gelişmiş op olarak kalır
        tikla(byLabel("Mahkeme filtre seçenekleri"));
        expect(Array.from(byLabel("Mahkeme gelişmiş").querySelectorAll("button")).map(b => b.textContent)).toEqual(["eşit değil", "içerir", "dolu"]);
    });
});
