// @vitest-environment jsdom
// FilterControl + yeni şerit bileşenleri (G142, §5.3; G146, §7.1): kontrol bileşeni `sunum` + `kontrol`
// ikilisinden seçilir — çoklu seçim (Sık/Tümü/Boş, sayı rozetli, etiketli, ham kod), görünür çip satırı
// (+N, rozetli, sıfırlılar soluk), var/yok üçlü anahtar, "X yok" kutucuğu (rozetli), arama kutusu;
// tarih/sayı/metin kontrolünde girdinin yanında "Boş" toggle çipi (is_null, girdiler kilitli).
// "boş olanlar" yan kutucuğu hiçbir kontrolde YOK; "(boş)" metni DOM'da YOK.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, bosKontrol, kontroldenFiltre,
    type Filtre, type FiltreKontrolu, type HizliFiltreSunumu, type KatalogKolon, type KolonTipi, type KontrolDurumu,
} from "@/lib/reports";
import { FilterControl } from "./FilterControl";
import { SearchBox } from "./SearchBox";
import type { SeritOgesi } from "./builderState";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
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

const ILLER = ["İstanbul", "Ankara", "İzmir", "Bursa", "Antalya", "Adana", "Konya", "Gaziantep", "Mersin", "Kayseri"];
const IL = kolon({ anahtar: "il", etiket: "İl", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ILLER });
const TUR = kolon({ anahtar: "client_type", etiket: "Müvekkil Türü", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri",
    secenekler: ["Individual", "Corporate"], secenek_etiketleri: { Individual: "Gerçek kişi", Corporate: "Tüzel kişi" } });
const KATEGORI = kolon({ anahtar: "category", etiket: "Kategori", tip: "liste", secenekler: ["Doktor", "Hasta", "Sigorta"] });
const DAVA = kolon({ anahtar: "dava_sayisi", etiket: "Dava Sayısı", tip: "sayi", turetilmis: true });
const EMAIL = kolon({ anahtar: "email", etiket: "E-posta", tip: "metin" });
const ACILIS = kolon({ anahtar: "opening_date", etiket: "Açılış", tip: "tarih" });
/** §7.2 sayılı katalog: sıra sunucudan (sayıya göre azalan, sıfırlılar sonda); 10 il, 2'si sıfır. */
const IL_SAYILI = kolon({
    anahtar: "il", etiket: "İl", tip: "metin", kontrol: "coklu_secim", secenek_kaynagi: "veri", secenekler: ILLER,
    secenek_sayilari: { İstanbul: 1443, Ankara: 423, İzmir: 120, Bursa: 44, Antalya: 20, Adana: 9, Konya: 3, Gaziantep: 1, Mersin: 0, Kayseri: 0 },
    bos_sayisi: 17,
});
const KATEGORI_SAYILI = kolon({
    anahtar: "category", etiket: "Kategori", tip: "liste", secenekler: ["Doktor", "Hasta", "Sigorta"],
    secenek_sayilari: { Doktor: 1443, Hasta: 5, Sigorta: 0 }, bos_sayisi: 0,
});
const MADDI = kolon({ anahtar: "maddi_tazminat", etiket: "Maddi", tip: "para", bos_sayisi: 312 });
const MAHKEME = kolon({ anahtar: "court", etiket: "Mahkeme", tip: "metin", oneriler: ["Ankara 1. Asliye", "İzmir 3. Asliye"], bos_sayisi: 4 });
const HEPSI = [IL, TUR, KATEGORI, DAVA, EMAIL, ACILIS, MADDI, MAHKEME];
const kolonOf = (anahtar: string) => HEPSI.find(k => k.anahtar === anahtar);

function oge(k: KatalogKolon, sunum: HizliFiltreSunumu = "varsayilan", etiket: string | null = null, durum?: KontrolDurumu): SeritOgesi {
    return { id: k.anahtar, durum: durum ?? bosKontrol(k, sunum), alanSecenekleri: [], hizli: true, sunum, etiket };
}

type Kayit = { filtre: Filtre | null; gecikmeli: boolean } | { hemen: true };

function Sahne({ baslangic, kolon: k, kayit }: { baslangic: SeritOgesi; kolon: KatalogKolon; kayit: Kayit[] }) {
    const [o, setO] = useState(baslangic);
    return (
        <FilterControl
            oge={o}
            kolon={k}
            kolonOf={kolonOf}
            onChange={(durum, gecikmeli) => { kayit.push({ filtre: kontroldenFiltre(durum), gecikmeli: !!gecikmeli }); setO({ ...o, durum }); }}
            onHemen={() => kayit.push({ hemen: true })}
        />
    );
}

describe("FilterControl (G142 §5.3)", () => {
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

    function render(node: ReactNode) {
        root = createRoot(container);
        act(() => { root!.render(node); });
    }
    const son = () => {
        const s = [...kayit].reverse().find(k => "filtre" in k) as { filtre: Filtre | null; gecikmeli: boolean } | undefined;
        if (!s) throw new Error("onChange hiç çağrılmadı");
        return s;
    };
    const byLabel = <T extends HTMLElement>(label: string): T => {
        const el = container.querySelector<T>(`[aria-label="${label}"]`);
        if (!el) throw new Error("aria-label bulunamadı: " + label);
        return el;
    };
    const tikla = (el: Element) => act(() => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    const yaz = (el: HTMLInputElement, value: string) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    };

    it("çoklu seçim (veriden, eski katalog — sayı alanı yok): Sık ilk 8 + Tümü + Boş; rozet yok; seçimler in, Boş null; hiçbir yerde \"boş olanlar\"/\"(boş)\"", () => {
        render(<Sahne baslangic={oge(IL)} kolon={IL} kayit={kayit} />);
        expect(container.textContent).not.toContain("boş olanlar");
        tikla(byLabel("İl seç"));
        const liste = byLabel("İl seçenekleri");
        expect(liste.querySelector("[data-bolum='Sık']")!.querySelectorAll("[role='option']")).toHaveLength(8);
        expect(liste.querySelector("[data-bolum='Tümü']")!.querySelectorAll("[role='option']")).toHaveLength(ILLER.length + 1);
        expect(liste.querySelector("[data-bolum='Tümü'] [role='option']:last-child")?.textContent).toBe("Boş");
        expect(liste.querySelectorAll("[data-testid='sayi-rozeti']")).toHaveLength(0);
        expect(liste.querySelectorAll("[data-sifir]")).toHaveLength(0);
        expect(container.textContent).not.toContain("(boş)");
        tikla(byLabel("İl: Mersin"));
        expect(son()).toEqual({ filtre: { alan: "il", op: "eq", deger: "Mersin" }, gecikmeli: false });
        tikla(byLabel("İl: Boş"));
        expect(son().filtre).toEqual({ alan: "il", op: "in", deger: ["Mersin", null] });
        expect(byLabel("İl seç").textContent).toBe("Mersin, Boş");
        expect(container.textContent).not.toContain("(boş)");
    });

    it("§7.1 çoklu seçim (sayılı katalog): satırlarda tr-TR rozet, sıra katalogdan, Sık sıfırsız ilk 8, sıfırlılar Tümü'de sonda soluk ama seçilebilir, Boş satırı rozetli", () => {
        render(<Sahne baslangic={oge(IL_SAYILI)} kolon={IL_SAYILI} kayit={kayit} />);
        tikla(byLabel("İl seç"));
        const liste = byLabel("İl seçenekleri");
        const degerler = (kok: ParentNode) => Array.from(kok.querySelectorAll("[role='option']")).map(o => o.getAttribute("data-deger"));
        // Sık: sıfır olmayan ilk 8 (Mersin/Kayseri 0 → yok)
        expect(degerler(liste.querySelector("[data-bolum='Sık']")!)).toEqual(ILLER.slice(0, 8));
        // Tümü: katalog sırası aynen (istemci yeniden sıralamaz), sıfırlılar sonda, Boş en altta
        expect(degerler(liste.querySelector("[data-bolum='Tümü']")!)).toEqual([...ILLER, ""]);
        const tumu = liste.querySelector("[data-bolum='Tümü']")!;
        const satir = (deger: string) => tumu.querySelector<HTMLElement>(`[role='option'][data-deger='${deger}']`)!;
        expect(satir("İstanbul").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("1.443");
        expect(satir("Ankara").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("423");
        expect(satir("Mersin").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("0");
        expect(satir("Mersin").getAttribute("data-sifir")).toBe("true");
        expect(satir("Mersin").className).toContain("opacity-60");
        expect(satir("İstanbul").getAttribute("data-sifir")).toBeNull();
        expect(satir("İstanbul").className).not.toContain("opacity-60");
        // Boş satırı: italik, ayırıcı, rozet bos_sayisi
        expect(satir("").className).toContain("italic");
        expect(satir("").className).toContain("border-t");
        expect(satir("").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("17");
        // Sıfırlı yine seçilebilir
        tikla(byLabel("İl: Mersin"));
        expect(son().filtre).toEqual({ alan: "il", op: "eq", deger: "Mersin" });
        expect(byLabel<HTMLInputElement>("İl: Mersin").checked).toBe(true);
        // Seçili çipte "Boş" etiketi
        tikla(byLabel("İl: Boş"));
        expect(Array.from(container.querySelectorAll("[data-testid='secili-cipler'] [data-deger]")).map(c => c.textContent)).toEqual(["Mersin", "Boş"]);
        expect(container.textContent).not.toContain("(boş)");
    });

    it("etiketli çoklu seçim: gösterim etiket, değer ham kod", () => {
        render(<Sahne baslangic={oge(TUR)} kolon={TUR} kayit={kayit} />);
        tikla(byLabel("Müvekkil Türü seç"));
        expect(byLabel("Müvekkil Türü seçenekleri").textContent).not.toContain("Corporate");
        tikla(byLabel("Müvekkil Türü: Tüzel kişi"));
        expect(son().filtre).toEqual({ alan: "client_type", op: "eq", deger: "Corporate" });
    });

    it("sunum=cipler: görünür çip satırı, açılır düğme yok; eski katalogda rozetsiz; sunum=varsayilan aynı kolonda açılır", () => {
        render(<Sahne baslangic={oge(KATEGORI, "cipler")} kolon={KATEGORI} kayit={kayit} />);
        expect(container.querySelector("[aria-label='Kategori seç']")).toBeNull();
        expect(byLabel("Kategori seçenekleri").getAttribute("role")).toBe("group");
        expect(container.querySelectorAll("[data-testid='sayi-rozeti']")).toHaveLength(0);
        expect(byLabel("Kategori: Doktor").className).not.toContain("opacity-60");
        tikla(byLabel("Kategori: Doktor"));
        tikla(byLabel("Kategori: Sigorta"));
        expect(son().filtre).toEqual({ alan: "category", op: "in", deger: ["Doktor", "Sigorta"] });
        expect(container.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-sunum")).toBe("cipler");

        act(() => root!.unmount());
        root = null;
        render(<Sahne baslangic={oge(KATEGORI)} kolon={KATEGORI} kayit={kayit} />);
        expect(byLabel("Kategori seç").getAttribute("aria-haspopup")).toBe("listbox");
    });

    it("§7.1 çip satırı (sayılı katalog): her çipte rozet, 0 → soluk ama tıklanır, sonda ayırıcı + italik Boş çipi (bos_sayisi=0 iken de görünür, soluk)", () => {
        render(<Sahne baslangic={oge(KATEGORI_SAYILI, "cipler")} kolon={KATEGORI_SAYILI} kayit={kayit} />);
        const grup = byLabel("Kategori seçenekleri");
        expect(Array.from(grup.querySelectorAll("button[data-deger]")).map(b => b.getAttribute("data-deger"))).toEqual(["Doktor", "Hasta", "Sigorta", ""]);
        expect(byLabel("Kategori: Doktor").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("1.443");
        expect(byLabel("Kategori: Hasta").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("5");
        expect(byLabel("Kategori: Sigorta").querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("0");
        expect(byLabel("Kategori: Sigorta").getAttribute("data-sifir")).toBe("true");
        expect(byLabel("Kategori: Sigorta").className).toContain("opacity-60");
        expect(byLabel("Kategori: Doktor").className).not.toContain("opacity-60");
        // Boş: ayırıcıdan sonra, italik, rozet 0 → soluk ama var
        expect(container.querySelector("[data-testid='bos-ayirici']")).not.toBeNull();
        const bos = byLabel("Kategori: Boş");
        expect(bos.className).toContain("italic");
        expect(bos.className).toContain("opacity-60");
        expect(bos.querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("0");
        // Sıfırlı tıklanır
        tikla(byLabel("Kategori: Sigorta"));
        expect(son().filtre).toEqual({ alan: "category", op: "eq", deger: "Sigorta" });
        expect(byLabel("Kategori: Sigorta").getAttribute("aria-pressed")).toBe("true");
        tikla(bos);
        expect(son().filtre).toEqual({ alan: "category", op: "in", deger: ["Sigorta", null] });
        expect(container.textContent).not.toContain("(boş)");
    });

    it("var/yok: etiket HizliFiltre.etiket; var gte 1, yok eq 0, hepsi yok", () => {
        render(<Sahne baslangic={oge(DAVA, "var_yok", "Davası var")} kolon={DAVA} kayit={kayit} />);
        expect(container.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-kontrol")).toBe("var_yok");
        expect(container.querySelector("[aria-label='Dava Sayısı en az']")).toBeNull();
        tikla(byLabel("Davası var: var"));
        expect(son()).toEqual({ filtre: { alan: "dava_sayisi", op: "gte", deger: 1 }, gecikmeli: false });
        tikla(byLabel("Davası var: yok"));
        expect(son().filtre).toEqual({ alan: "dava_sayisi", op: "eq", deger: 0 });
        tikla(byLabel("Davası var: hepsi"));
        expect(son().filtre).toBeNull();
    });

    it("boş anahtarı: tek kutucuk, açık is_null; etiket yoksa kolon etiketi + boş; eski katalogda rozetsiz, sayılıda \"· N\"", () => {
        render(<Sahne baslangic={oge(EMAIL, "bos_anahtari", "E-postası yok")} kolon={EMAIL} kayit={kayit} />);
        expect(container.querySelector("[aria-label='E-posta içerir']")).toBeNull();
        expect(container.querySelector("[data-testid='sayi-rozeti']")).toBeNull();
        tikla(byLabel("E-postası yok"));
        expect(son()).toEqual({ filtre: { alan: "email", op: "is_null" }, gecikmeli: false });
        tikla(byLabel("E-postası yok"));
        expect(son().filtre).toBeNull();

        act(() => root!.unmount());
        root = null;
        render(<Sahne baslangic={oge(EMAIL, "bos_anahtari")} kolon={EMAIL} kayit={kayit} />);
        expect(byLabel<HTMLInputElement>("E-posta boş").type).toBe("checkbox");

        act(() => root!.unmount());
        root = null;
        const sayili = kolon({ ...EMAIL, bos_sayisi: 1200 });
        render(<Sahne baslangic={oge(sayili, "bos_anahtari", "E-postası yok")} kolon={sayili} kayit={kayit} />);
        expect(container.querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe(" · 1.200");
        expect(byLabel("E-postası yok").closest("label")?.textContent).toBe("E-postası yok · 1.200");
    });

    it("tarih aralığında yan kutucuk yok; girdiler başta açık; §7.1 \"Boş\" çipi: aria-pressed, is_null, girdiler+kısayol kilitli, kapatınca eski değer geri", () => {
        render(<Sahne baslangic={oge(ACILIS)} kolon={ACILIS} kayit={kayit} />);
        expect(container.querySelectorAll("input[type='checkbox']")).toHaveLength(0);
        expect(container.textContent).not.toContain("boş olanlar");
        expect(byLabel<HTMLInputElement>("Açılış başlangıç").disabled).toBe(false);
        yaz(byLabel("Açılış başlangıç"), "2025-01-01");
        expect(son()).toEqual({ filtre: { alan: "opening_date", op: "gte", deger: "2025-01-01" }, gecikmeli: true });

        const cip = byLabel<HTMLButtonElement>("Açılış boş");
        expect(cip.tagName).toBe("BUTTON");
        expect(cip.getAttribute("aria-pressed")).toBe("false");
        expect(cip.textContent).toBe("Boş"); // eski katalog: rozetsiz
        tikla(cip);
        expect(son()).toEqual({ filtre: { alan: "opening_date", op: "is_null" }, gecikmeli: false });
        expect(byLabel("Açılış boş").getAttribute("aria-pressed")).toBe("true");
        expect(byLabel<HTMLInputElement>("Açılış başlangıç").disabled).toBe(true);
        expect(byLabel<HTMLInputElement>("Açılış bitiş").disabled).toBe(true);
        expect(byLabel<HTMLSelectElement>("Açılış kısayol").disabled).toBe(true);
        // Girdi değeri durumda saklı, görünür
        expect(byLabel<HTMLInputElement>("Açılış başlangıç").value).toBe("2025-01-01");
        tikla(byLabel("Açılış boş"));
        expect(son()).toEqual({ filtre: { alan: "opening_date", op: "gte", deger: "2025-01-01" }, gecikmeli: false });
        expect(byLabel<HTMLInputElement>("Açılış başlangıç").disabled).toBe(false);
    });

    it("§7.1 sayı aralığı \"Boş\" çipi: rozet bos_sayisi, is_null, girdiler kilitli; şablondan bos: true ile açılınca çip basılı", () => {
        render(<Sahne baslangic={oge(MADDI)} kolon={MADDI} kayit={kayit} />);
        yaz(byLabel("Maddi en az"), "1000");
        expect(son().filtre).toEqual({ alan: "maddi_tazminat", op: "gte", deger: 1000 });
        const cip = byLabel<HTMLButtonElement>("Maddi boş");
        expect(cip.querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("312");
        tikla(cip);
        expect(son()).toEqual({ filtre: { alan: "maddi_tazminat", op: "is_null" }, gecikmeli: false });
        expect(byLabel<HTMLInputElement>("Maddi en az").disabled).toBe(true);
        expect(byLabel<HTMLInputElement>("Maddi en çok").disabled).toBe(true);
        tikla(byLabel("Maddi boş"));
        expect(son().filtre).toEqual({ alan: "maddi_tazminat", op: "gte", deger: 1000 });

        act(() => root!.unmount());
        root = null;
        const acik: KontrolDurumu = { kontrol: "sayi_araligi", alan: "maddi_tazminat", en_az: null, en_cok: null, bos: true };
        render(<Sahne baslangic={oge(MADDI, "varsayilan", null, acik)} kolon={MADDI} kayit={kayit} />);
        expect(byLabel("Maddi boş").getAttribute("aria-pressed")).toBe("true");
        expect(byLabel<HTMLInputElement>("Maddi en az").disabled).toBe(true);
    });

    it("§7.1 metin \"Boş\" çipi: düz girdi ve combobox kilitlenir, liste açılmaz; is_null izinsiz kolonda (sanal arama) çip yok", () => {
        render(<Sahne baslangic={oge(EMAIL)} kolon={EMAIL} kayit={kayit} />);
        yaz(byLabel("E-posta içerir"), "@");
        expect(son().filtre).toEqual({ alan: "email", op: "contains", deger: "@" });
        tikla(byLabel("E-posta boş"));
        expect(son()).toEqual({ filtre: { alan: "email", op: "is_null" }, gecikmeli: false });
        expect(byLabel<HTMLInputElement>("E-posta içerir").disabled).toBe(true);
        expect(byLabel<HTMLInputElement>("E-posta içerir").value).toBe("@");
        tikla(byLabel("E-posta boş"));
        expect(son().filtre).toEqual({ alan: "email", op: "contains", deger: "@" });
        expect(byLabel<HTMLInputElement>("E-posta içerir").disabled).toBe(false);

        act(() => root!.unmount());
        root = null;
        render(<Sahne baslangic={oge(MAHKEME)} kolon={MAHKEME} kayit={kayit} />);
        const cip = byLabel<HTMLButtonElement>("Mahkeme boş");
        expect(cip.querySelector("[data-testid='sayi-rozeti']")?.textContent).toBe("4");
        tikla(cip);
        expect(son().filtre).toEqual({ alan: "court", op: "is_null" });
        const girdi = byLabel<HTMLInputElement>("Mahkeme içerir");
        expect(girdi.disabled).toBe(true);
        act(() => { girdi.focus(); });
        expect(container.querySelector("[cmdk-list]")).toBeNull();

        act(() => root!.unmount());
        root = null;
        const ARAMA = kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", turetilmis: true, secilebilir: false, oplar: ["contains"] });
        render(<Sahne baslangic={oge(ARAMA)} kolon={ARAMA} kayit={kayit} />);
        expect(container.querySelector("[aria-label='Ara boş']")).toBeNull();
        expect(container.querySelector("[aria-pressed]")).toBeNull();
    });

    it("SearchBox: büyüteç + temizle ×, placeholder katalogdan (yoksa Ara…), yazım onYaz, × onTemizle, odak çıkışı onHemen", () => {
        const olaylar: string[] = [];
        function Kutu({ placeholder }: { placeholder?: string | null }) {
            const [m, setM] = useState("");
            return (
                <SearchBox etiket="Ara" placeholder={placeholder} metin={m}
                    onYaz={v => { olaylar.push("yaz:" + v); setM(v); }}
                    onTemizle={() => { olaylar.push("temizle"); setM(""); }}
                    onHemen={() => olaylar.push("hemen")} />
            );
        }
        render(<Kutu placeholder="Ad, cari kod…" />);
        const kutu = byLabel<HTMLInputElement>("Ara");
        expect(kutu.placeholder).toBe("Ad, cari kod…");
        expect(container.querySelector("[aria-label='Ara temizle']")).toBeNull();
        yaz(kutu, "Ay");
        expect(olaylar).toEqual(["yaz:Ay"]);
        act(() => { kutu.focus(); });
        act(() => { kutu.blur(); });
        expect(olaylar.at(-1)).toBe("hemen");
        tikla(byLabel("Ara temizle"));
        expect(olaylar.at(-1)).toBe("temizle");
        expect(kutu.value).toBe("");
        expect(container.querySelector("[aria-label='Ara temizle']")).toBeNull();

        act(() => root!.unmount());
        root = null;
        render(<Kutu placeholder={null} />);
        expect(byLabel<HTMLInputElement>("Ara").placeholder).toBe("Ara…");
    });
});
