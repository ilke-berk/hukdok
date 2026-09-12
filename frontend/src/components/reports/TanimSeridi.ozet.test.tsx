// @vitest-environment jsdom
// TanimSeridi özet modu (12.09): "Σ Özet" özet modunu açar (Kayıt sayısı), üst satırda kolon çipleri yerine
// gruplama + ölçüm çipleri; "+ Grupla" (FieldPicker) tarih kolonunda ay kırılımıyla ekler, kırılım düğmesi
// gün→ay→yıl döner; "+ Ölçüm" popover'ı (portal) uygun işlemleri listeler; × ölçüm/gruplama kaldırır, son ölçüm
// liste görünümüne döndürür; "Liste görünümü" özeti kapatır; sıralama çipi ölçüm etiketini basar; salt modda düğme yok.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import {
    OP_BY_TIP, type FiltreKontrolu, type Katalog, type KatalogKolon, type KatalogVeriKaynagi, type KolonTipi,
} from "@/lib/reports";
import { TanimSeridi } from "./TanimSeridi";
import { kaynakIcinBaslangic, tanimOlustur, tanimdanDurum, type OlusturucuDurumu } from "./builderState";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
function kolon(k: Pick<KatalogKolon, "anahtar" | "etiket" | "tip"> & Partial<KatalogKolon>): KatalogKolon {
    return {
        filtrelenebilir: true, siralanabilir: true, turetilmis: false, secenekler: null, grup: "Kimlik", kontrol: KONTROL[k.tip],
        oplar: [...OP_BY_TIP[k.tip]], oneriler: null, oneri_kesik: false, secenek_kaynagi: null, secenek_etiketleri: null,
        secilebilir: true, ...k,
    };
}
const DAVALAR: KatalogVeriKaynagi = {
    anahtar: "davalar", etiket: "Davalar", aciklama: "Dava kartları", varsayilan_kolonlar: ["tracking_no", "subject"],
    kolonlar: [
        kolon({ anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" }),
        kolon({ anahtar: "subject", etiket: "Konu", tip: "metin" }),
        kolon({ anahtar: "status", etiket: "Durum", tip: "liste", secenekler: ["Derdest"], grup: "Karar" }),
        kolon({ anahtar: "opening_date", etiket: "Açılış Tarihi", tip: "tarih", grup: "Tarihler" }),
        kolon({ anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para", grup: "Tutarlar" }),
        kolon({ anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin", turetilmis: true, siralanabilir: false }),
        kolon({ anahtar: "arama", etiket: "Ara", tip: "metin", secilebilir: false, siralanabilir: false }),
    ],
    hizli_filtreler: [], kolon_setleri: [],
};
const KATALOG: Katalog = { veri_kaynaklari: [DAVALAR], limitler: { onizleme_sayfa_boyu_max: 200, export_max_satir: 50000 } };

type Kayit = { durum: OlusturucuDurumu };

function Harness({ kayit, baslangic, salt }: { kayit: Kayit[]; baslangic: OlusturucuDurumu; salt?: boolean }) {
    const [durum, setDurum] = useState<OlusturucuDurumu>(baslangic);
    return (
        <TanimSeridi
            katalog={KATALOG}
            durum={durum}
            onChange={d => { kayit.push({ durum: d }); setDurum(d); }}
            onHemen={() => undefined}
            onKaynakSec={() => undefined}
            bugun="2026-09-12"
            salt={salt}
        />
    );
}

describe("TanimSeridi — özet modu (12.09)", () => {
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

    function render(baslangic: OlusturucuDurumu = kaynakIcinBaslangic(DAVALAR), salt?: boolean) {
        root = createRoot(container);
        act(() => {
            root!.render(<Harness kayit={kayit} baslangic={baslangic} salt={salt} />);
        });
    }
    const $ = <T extends Element>(sel: string, kok: ParentNode = container): T | null => kok.querySelector<T>(sel);
    const $$ = <T extends Element>(sel: string): T | null => document.body.querySelector<T>(sel);
    const son = () => kayit[kayit.length - 1].durum;
    function tikla(el: Element | null) {
        if (!el) throw new Error("öğe yok");
        act(() => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    }
    const ozetDurum = () => tanimdanDurum({
        veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [{ alan: "sayi", yon: "desc" }],
        gruplama: [{ alan: "opening_date", kirilim: "ay" }], olcumler: [{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }],
    }, DAVALAR);

    it("liste görünümü: kolon çipleri + '+ Kolon' + 'Σ Özet'; Özet tıkı Kayıt sayısı ekler, kolon çipleri kalkar", () => {
        render();
        expect($("[data-testid='serit-kolon-tracking_no']")).not.toBeNull();
        expect($("[data-testid='serit-kolon-ekle']")).not.toBeNull();
        expect($("[data-testid='serit-ozet-kapat']")).toBeNull();
        tikla($("[data-testid='serit-ozet-ac']"));
        expect(son().olcumler).toEqual([{ islem: "sayi" }]);
        expect(tanimOlustur(son()).olcumler).toEqual([{ islem: "sayi" }]);
        expect($("[data-testid='serit-kolon-tracking_no']")).toBeNull();
        expect($("[data-testid='serit-kolon-ekle']")).toBeNull();
        expect($("[data-testid='serit-olcum-sayi']")?.textContent).toContain("Kayıt sayısı");
        expect($("[data-testid='serit-ozet-ac']")).toBeNull();
        expect($("[data-testid='serit-ozet-kapat']")).not.toBeNull();
        expect(($("[data-testid='serit-temizle']") as HTMLButtonElement).disabled).toBe(false);
    });

    it("özet çipleri: gruplama kırılımlı, ölçümler etiketli; kırılım düğmesi ay → yıl → gün; × kaldırır; sıralama çipi ölçüm etiketi", () => {
        render(ozetDurum());
        const grup = $("[data-testid='serit-grup-opening_date']");
        expect(grup?.textContent).toContain("Açılış Tarihi");
        expect(grup?.getAttribute("data-kirilim")).toBe("ay");
        expect($("[data-testid='serit-olcum-toplam:maddi_tazminat']")?.textContent).toContain("Toplam Maddi Tazminat");
        expect($("[data-testid='serit-siralama-sayi']")?.textContent).toContain("Kayıt sayısı");
        tikla($("[data-testid='serit-grup-kirilim']"));
        expect(son().gruplama).toEqual([{ alan: "opening_date", kirilim: "yil" }]);
        tikla($("[data-testid='serit-grup-kirilim']"));
        expect(son().gruplama).toEqual([{ alan: "opening_date", kirilim: "gun" }]);
        expect($("[data-testid='serit-grup-opening_date']")?.getAttribute("data-kirilim")).toBe("gun");
        tikla($("[aria-label='Açılış Tarihi gruplamasını kaldır']"));
        expect(son().gruplama).toEqual([]);
        expect(son().olcumler).toHaveLength(2);
        tikla($("[aria-label='Toplam Maddi Tazminat ölçümünü kaldır']"));
        expect(son().olcumler).toEqual([{ islem: "sayi" }]);
        // Son ölçüm kalkınca liste görünümü: kolon çipleri geri gelir, ölçüm anahtarlı sıralama düşer
        tikla($("[aria-label='Kayıt sayısı ölçümünü kaldır']"));
        expect(son().olcumler).toEqual([]);
        expect(son().siralama).toEqual([]);
        expect($("[data-testid='serit-kolon-tracking_no']")).not.toBeNull();
    });

    it("'+ Grupla' yalnız gruplanabilir kolonları listeler (türetilmiş/arama yok, gruplanmış olan düşer); tarih seçimi ay kırılımı; tavan 3", () => {
        render(ozetDurum());
        tikla($("[data-testid='serit-grup-ekle'] button"));
        const panel = $("[data-testid='alan-secici']");
        expect(panel).not.toBeNull();
        const alanlar = Array.from(panel!.querySelectorAll("[data-alan]")).map(e => e.getAttribute("data-alan"));
        expect(alanlar).toEqual(["tracking_no", "subject", "status", "maddi_tazminat"]);
        tikla(panel!.querySelector("[data-alan='status']"));
        expect(son().gruplama).toEqual([{ alan: "opening_date", kirilim: "ay" }, { alan: "status" }]);
        tikla($("[data-testid='serit-grup-ekle'] button"));
        tikla($("[data-testid='alan-secici'] [data-alan='tracking_no']"));
        expect(son().gruplama).toHaveLength(3);
        expect(($("[data-testid='serit-grup-ekle'] button") as HTMLButtonElement).disabled).toBe(true);
    });

    it("'+ Ölçüm' popover'ı: Genel grubunda Kayıt sayısı (eklenmişse yok), sayı/para/tarih kolonlarında uygun işlemler; seçim ekler", () => {
        render(ozetDurum());
        tikla($("[data-testid='serit-olcum-ekle']"));
        const panel = $$("[data-testid='olcum-secici']");
        expect(panel).not.toBeNull();
        const anahtarlar = Array.from(panel!.querySelectorAll("[data-olcum]")).map(e => e.getAttribute("data-olcum"));
        expect(anahtarlar).not.toContain("sayi");                                   // zaten eklenmiş
        expect(anahtarlar).not.toContain("toplam:maddi_tazminat");
        expect(anahtarlar).toEqual(expect.arrayContaining(["ortalama:maddi_tazminat", "min:maddi_tazminat", "max:maddi_tazminat", "min:opening_date", "max:opening_date"]));
        expect(anahtarlar.some(a => a?.startsWith("toplam:opening_date"))).toBe(false);
        expect(anahtarlar.some(a => a?.includes("status") || a?.includes("arama"))).toBe(false);
        tikla(panel!.querySelector("[data-olcum='ortalama:maddi_tazminat']"));
        expect(son().olcumler).toEqual([{ islem: "sayi" }, { islem: "toplam", alan: "maddi_tazminat" }, { islem: "ortalama", alan: "maddi_tazminat" }]);
        expect($("[data-testid='serit-olcum-ortalama:maddi_tazminat']")?.textContent).toContain("Ortalama Maddi Tazminat");
    });

    it("'Liste görünümü' özeti kapatır (gruplama + ölçüm boşalır, kolonlar aynı kalır); salt modda düğmeler yok", () => {
        render(ozetDurum());
        tikla($("[data-testid='serit-ozet-kapat']"));
        expect(son().gruplama).toEqual([]);
        expect(son().olcumler).toEqual([]);
        expect(son().kolonlar).toEqual(["tracking_no", "subject"]);
        expect(tanimOlustur(son())).toEqual({ veri_kaynagi: "davalar", kolonlar: ["tracking_no", "subject"], filtreler: [], siralama: [] });
        act(() => root!.unmount());
        root = null;
        render(ozetDurum(), true);
        expect($("[data-testid='serit-grup-opening_date']")?.textContent).toContain("ay");
        expect($("[data-testid='serit-grup-kirilim']")).toBeNull();
        expect($("[data-testid='serit-olcum-ekle']")).toBeNull();
        expect($("[data-testid='serit-grup-ekle']")).toBeNull();
        expect($("[data-testid='serit-ozet-kapat']")).toBeNull();
        expect($("[data-testid='serit-ozet-ac']")).toBeNull();
    });
});
