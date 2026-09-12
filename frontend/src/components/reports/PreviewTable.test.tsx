// @vitest-environment jsdom
// PreviewTable (G138 → G139) — başlıktan sıralama: yalnız `siralanabilir` başlık tıklanabilir, aria-sort
// ve ok/sıra numarası etkin sıralamadan; "güncelleniyor…" durumu; bayat rozeti yok; geçersiz
// taslakta ipucu; hata DataErrorBanner; başlıkta kayıt rozeti yok (sayaç sayfada); boş sonuçta filtre kısayolu.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

vi.mock("@/lib/api", () => ({ apiClient: { fetch: vi.fn() } }));

import type { OnizlemeCevabi, Siralama } from "@/lib/reports";
import { PreviewTable } from "./PreviewTable";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CEVAP: OnizlemeCevabi = {
    kolonlar: [
        { anahtar: "tracking_no", etiket: "Ofis No", tip: "metin" },
        { anahtar: "muvekkil_adlari", etiket: "Müvekkiller", tip: "metin" },
        { anahtar: "maddi_tazminat", etiket: "Maddi Tazminat", tip: "para" },
    ],
    satirlar: [{ tracking_no: "2025/12", muvekkil_adlari: "A ; B", maddi_tazminat: 10 }],
    toplam: 1,
    sayfa: 1,
    sayfa_boyu: 50,
};

describe("PreviewTable (G138)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
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

    type Ayar = Partial<Parameters<typeof PreviewTable>[0]>;
    function render(ayar: Ayar = {}) {
        root = createRoot(container);
        act(() => {
            root!.render(
                <PreviewTable
                    cevap={CEVAP}
                    yukleniyor={false}
                    hata={null}
                    onRetry={() => undefined}
                    onSayfa={() => undefined}
                    gecersiz={false}
                    siralama={[]}
                    siralanabilirMi={a => a !== "muvekkil_adlari"}
                    onSirala={() => undefined}
                    {...ayar}
                />,
            );
        });
    }
    const basliklar = () => Array.from(container.querySelectorAll("thead th"));
    const tikla = (el: Element) => act(() => {
        el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    it("siralanabilir başlık düğmedir ve onSirala(alan) çağırır; siralanabilir=false başlık düz metin", () => {
        const onSirala = vi.fn();
        render({ onSirala });
        const [ofis, muvekkil, maddi] = basliklar();
        expect(ofis.querySelector("button")?.getAttribute("aria-label")).toBe("Ofis No sırala");
        expect(maddi.querySelector("button")?.getAttribute("aria-label")).toBe("Maddi Tazminat sırala");
        expect(muvekkil.querySelector("button")).toBeNull();
        expect(muvekkil.textContent).toBe("Müvekkiller");
        expect(basliklar().map(th => th.getAttribute("aria-sort"))).toEqual(["none", "none", "none"]);

        tikla(ofis.querySelector("button")!);
        expect(onSirala).toHaveBeenCalledWith("tracking_no");
        tikla(muvekkil);
        expect(onSirala).toHaveBeenCalledTimes(1);
    });

    it("aria-sort etkin sıralamadan; çok alanlı sıralamada sıra numarası; ipucu döngünün sonraki adımını söyler", () => {
        const siralama: Siralama[] = [{ alan: "maddi_tazminat", yon: "desc" }, { alan: "tracking_no", yon: "asc" }];
        render({ siralama });
        expect(basliklar().map(th => th.getAttribute("aria-sort"))).toEqual(["ascending", "none", "descending"]);
        const ofis = basliklar()[0].querySelector("button")!;
        const maddi = basliklar()[2].querySelector("button")!;
        expect(ofis.textContent).toContain("2");
        expect(maddi.textContent).toContain("1");
        expect(ofis.title).toBe("Azalan sırala");
        expect(maddi.title).toBe("Sıralamayı kaldır");
    });

    it("yükleniyorken başlıkta \"güncelleniyor…\" durumu; bayat rozeti DOM'da yok; tablo satırları kalır", () => {
        render({ yukleniyor: true });
        expect(container.querySelector("[data-testid='guncelleniyor']")?.textContent).toContain("güncelleniyor");
        expect(container.querySelector("[data-testid='bayat-rozeti']")).toBeNull();
        expect(container.textContent).not.toContain("yeniden önizleyin");
        expect(container.querySelectorAll("tbody tr")).toHaveLength(1);
    });

    it("başlıkta kayıt rozeti YOK (12.09: sayı yalnız sayfanın sayaç satırında); 'Toplam' ön eki yok", () => {
        render({ cevap: { ...CEVAP, toplam: 3064 } });
        expect(container.querySelector("[data-testid='toplam-rozeti']")).toBeNull();
        expect(container.textContent).not.toContain("kayıt ·");
        expect(container.textContent).not.toContain("Toplam");
    });

    it("boş sonuç: filtre varken 'filtreleri gevşetin' + Filtreleri temizle kısayolu onFiltreleriTemizle çağırır; filtresizken kısayol yok", () => {
        const onFiltreleriTemizle = vi.fn();
        render({ cevap: { ...CEVAP, satirlar: [], toplam: 0 }, filtreVar: true, onFiltreleriTemizle });
        const bos = container.querySelector("[data-testid='bos-sonuc']")!;
        expect(bos.textContent).toContain("Bu filtrelerle kayıt yok — filtreleri gevşetin.");
        expect(container.querySelector("table")).toBeNull();
        const kisayol = Array.from(bos.querySelectorAll("button")).find(b => b.textContent?.trim() === "Filtreleri temizle");
        expect(kisayol).toBeDefined();
        tikla(kisayol!);
        expect(onFiltreleriTemizle).toHaveBeenCalledTimes(1);

        act(() => root!.unmount());
        root = null;
        render({ cevap: { ...CEVAP, satirlar: [], toplam: 0 }, filtreVar: false, onFiltreleriTemizle });
        expect(container.querySelector("[data-testid='bos-sonuc']")?.textContent).toContain("Bu kaynakta kayıt yok.");
        expect(container.textContent).not.toContain("gevşetin");
        expect(container.querySelector("[data-testid='bos-sonuc'] button")).toBeNull();
    });

    it("cevap yokken: geçersiz taslakta kolon/filtre ipucu, geçerliyse \"hazırlanıyor\"; Önizle düğmesi yok", () => {
        render({ cevap: null, gecersiz: true });
        expect(container.textContent).toContain("en az bir kolon seçin ve filtreleri tamamlayın");
        expect(container.textContent).not.toContain("Önizle'ye basın");
        act(() => root!.unmount());
        root = null;
        render({ cevap: null, gecersiz: false });
        expect(container.textContent).toContain("Önizleme hazırlanıyor");
        expect(Array.from(container.querySelectorAll("button")).map(b => b.textContent?.trim())).not.toContain("Önizle");
    });

    it("hata: DataErrorBanner + Tekrar dene (boş liste değil)", () => {
        const onRetry = vi.fn();
        render({ hata: "Sunucuya ulaşılamadı.", onRetry });
        expect(container.querySelector("[role='alert']")?.textContent).toContain("Sunucuya ulaşılamadı.");
        expect(container.querySelector("table")).toBeNull();
        tikla(Array.from(container.querySelectorAll("button")).find(b => b.textContent?.trim() === "Tekrar dene")!);
        expect(onRetry).toHaveBeenCalledTimes(1);
    });
});
