// @vitest-environment jsdom
// FilterControl + yeni şerit bileşenleri (G142, §5.3): kontrol bileşeni `sunum` + `kontrol` ikilisinden
// seçilir — çoklu seçim (Sık/Tümü/(boş), etiketli, ham kod), görünür çip satırı (+N), var/yok üçlü anahtar,
// "X yok" kutucuğu, arama kutusu. "boş olanlar" yan kutucuğu hiçbir kontrolde YOK.
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
const HEPSI = [IL, TUR, KATEGORI, DAVA, EMAIL, ACILIS];
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

    it("çoklu seçim (veriden): Sık ilk 8 + Tümü + (boş); seçimler in, (boş) null; hiçbir yerde \"boş olanlar\"", () => {
        render(<Sahne baslangic={oge(IL)} kolon={IL} kayit={kayit} />);
        expect(container.textContent).not.toContain("boş olanlar");
        tikla(byLabel("İl seç"));
        const liste = byLabel("İl seçenekleri");
        expect(liste.querySelector("[data-bolum='Sık']")!.querySelectorAll("[role='option']")).toHaveLength(8);
        expect(liste.querySelector("[data-bolum='Tümü']")!.querySelectorAll("[role='option']")).toHaveLength(ILLER.length + 1);
        expect(liste.querySelector("[data-bolum='Tümü'] [role='option']:last-child")?.textContent).toBe("(boş)");
        tikla(byLabel("İl: Mersin"));
        expect(son()).toEqual({ filtre: { alan: "il", op: "eq", deger: "Mersin" }, gecikmeli: false });
        tikla(byLabel("İl: (boş)"));
        expect(son().filtre).toEqual({ alan: "il", op: "in", deger: ["Mersin", null] });
        expect(byLabel("İl seç").textContent).toBe("Mersin, (boş)");
    });

    it("etiketli çoklu seçim: gösterim etiket, değer ham kod", () => {
        render(<Sahne baslangic={oge(TUR)} kolon={TUR} kayit={kayit} />);
        tikla(byLabel("Müvekkil Türü seç"));
        expect(byLabel("Müvekkil Türü seçenekleri").textContent).not.toContain("Corporate");
        tikla(byLabel("Müvekkil Türü: Tüzel kişi"));
        expect(son().filtre).toEqual({ alan: "client_type", op: "eq", deger: "Corporate" });
    });

    it("sunum=cipler: görünür çip satırı, açılır düğme yok; sunum=varsayilan aynı kolonda açılır", () => {
        render(<Sahne baslangic={oge(KATEGORI, "cipler")} kolon={KATEGORI} kayit={kayit} />);
        expect(container.querySelector("[aria-label='Kategori seç']")).toBeNull();
        expect(byLabel("Kategori seçenekleri").getAttribute("role")).toBe("group");
        tikla(byLabel("Kategori: Doktor"));
        tikla(byLabel("Kategori: Sigorta"));
        expect(son().filtre).toEqual({ alan: "category", op: "in", deger: ["Doktor", "Sigorta"] });
        expect(container.querySelector("[data-testid='filtre-kontrolu']")?.getAttribute("data-sunum")).toBe("cipler");

        act(() => root!.unmount());
        root = null;
        render(<Sahne baslangic={oge(KATEGORI)} kolon={KATEGORI} kayit={kayit} />);
        expect(byLabel("Kategori seç").getAttribute("aria-haspopup")).toBe("listbox");
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

    it("boş anahtarı: tek kutucuk, açık is_null; etiket yoksa kolon etiketi + boş", () => {
        render(<Sahne baslangic={oge(EMAIL, "bos_anahtari", "E-postası yok")} kolon={EMAIL} kayit={kayit} />);
        expect(container.querySelector("[aria-label='E-posta içerir']")).toBeNull();
        tikla(byLabel("E-postası yok"));
        expect(son()).toEqual({ filtre: { alan: "email", op: "is_null" }, gecikmeli: false });
        tikla(byLabel("E-postası yok"));
        expect(son().filtre).toBeNull();

        act(() => root!.unmount());
        root = null;
        render(<Sahne baslangic={oge(EMAIL, "bos_anahtari")} kolon={EMAIL} kayit={kayit} />);
        expect(byLabel<HTMLInputElement>("E-posta boş").type).toBe("checkbox");
    });

    it("tarih aralığında yan kutucuk yok; girdiler kilitlenmez", () => {
        render(<Sahne baslangic={oge(ACILIS)} kolon={ACILIS} kayit={kayit} />);
        expect(container.querySelectorAll("input[type='checkbox']")).toHaveLength(0);
        expect(byLabel<HTMLInputElement>("Açılış başlangıç").disabled).toBe(false);
        yaz(byLabel("Açılış başlangıç"), "2025-01-01");
        expect(son()).toEqual({ filtre: { alan: "opening_date", op: "gte", deger: "2025-01-01" }, gecikmeli: true });
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
