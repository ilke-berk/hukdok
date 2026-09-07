// @vitest-environment jsdom
// TemplateBar (G134 → G144) — izole: "☆ Favorilere ekle" bağlantısı yalnız taslak KAYITLI DEĞİLKEN
// (`kayitli=null`) ve `onFavoriEkle` verilmişken; tıklayınca `onFavoriEkle`; taslak geçersiz/işleniyorken
// pasif. `kayitli` verilince bağlantı yerine "★ Kayıtlı: <ad>" rozeti. Eski çağıran (prop yok) → ikisi de yok.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { RaporSablonu } from "@/lib/reports";
import { TemplateBar } from "./TemplateBar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SABLON: RaporSablonu = {
    id: 1, ad: "Müvekkiller · Doktor · Ankara", aciklama: null, paylasimli: false, olusturan: "admin@lexis.com.tr",
    tanim: { veri_kaynagi: "muvekkiller", kolonlar: ["name"], filtreler: [], siralama: [] },
    created_at: "2026-09-07T10:00:00Z", updated_at: "2026-09-07T10:00:00Z",
};

describe("TemplateBar — favori bağlantısı / kayıtlı rozeti (G144)", () => {
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

    type Ek = Partial<Parameters<typeof TemplateBar>[0]>;
    function render(ek: Ek = {}) {
        root = createRoot(container);
        act(() => {
            root!.render(
                <TemplateBar
                    sablonlar={[SABLON]}
                    yukleniyor={false}
                    hata={null}
                    onRetry={() => undefined}
                    kullanici="admin@lexis.com.tr"
                    seciliId={null}
                    onSecim={() => undefined}
                    onYukle={() => undefined}
                    onKaydet={() => undefined}
                    onGuncelle={() => undefined}
                    onSil={() => undefined}
                    taslakGecerli={true}
                    isleniyor={false}
                    {...ek}
                />,
            );
        });
    }
    const baglanti = () => container.querySelector<HTMLButtonElement>("[data-testid='favori-ekle-baglantisi']");
    const rozet = () => container.querySelector("[data-testid='favori-kayitli']");

    it("kayıtlı değilken bağlantı görünür ve tıklayınca onFavoriEkle çağrılır; rozet yok", () => {
        const onFavoriEkle = vi.fn();
        render({ kayitli: null, onFavoriEkle });
        expect(rozet()).toBeNull();
        const b = baglanti();
        expect(b).not.toBeNull();
        expect(b!.textContent?.trim()).toBe("Favorilere ekle");
        expect(b!.disabled).toBe(false);
        act(() => {
            b!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        expect(onFavoriEkle).toHaveBeenCalledTimes(1);
    });

    it("kayıtlıysa '★ Kayıtlı: <ad>' rozeti, bağlantı yok (seçim boş olsa da)", () => {
        const onFavoriEkle = vi.fn();
        render({ kayitli: SABLON, onFavoriEkle, seciliId: null });
        expect(baglanti()).toBeNull();
        expect(rozet()!.textContent).toContain("Kayıtlı: Müvekkiller · Doktor · Ankara");
        expect(rozet()!.getAttribute("title")).toContain("Müvekkiller · Doktor · Ankara");
    });

    it("taslak geçersizken ya da işlem sürerken bağlantı pasif", () => {
        render({ kayitli: null, onFavoriEkle: () => undefined, taslakGecerli: false });
        expect(baglanti()!.disabled).toBe(true);
        expect(baglanti()!.title).toContain("geçerli bir tanım");
        act(() => root!.unmount());
        root = null;
        render({ kayitli: null, onFavoriEkle: () => undefined, isleniyor: true });
        expect(baglanti()!.disabled).toBe(true);
    });

    it("onFavoriEkle verilmemişse (eski çağıran) ne bağlantı ne rozet", () => {
        render();
        expect(baglanti()).toBeNull();
        expect(rozet()).toBeNull();
        // Mevcut düğmeler aynen
        const metinler = Array.from(container.querySelectorAll("button")).map(b => b.textContent?.trim());
        expect(metinler).toEqual(expect.arrayContaining(["Yükle", "Kaydet"]));
    });
});
