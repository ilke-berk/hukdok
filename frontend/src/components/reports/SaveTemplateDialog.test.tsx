// @vitest-environment jsdom
// SaveTemplateDialog (G212): yeni modal tasarımı — ActivityReportModal deseni (theme-classic, p-0 gap-0,
// başlık/gövde/alt ayrı kenarlıklı bloklar), girişler h-9 / 13px köşesiz, renkler yalnız var(--...).
// Davranış (G134) değişmez: sınırlar 120/500, boş adla Kaydet pasif, gövde {ad, aciklama, paylasimli}.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { SaveTemplateDialog, type SablonKunyesi } from "./SaveTemplateDialog";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Radix Switch useSize ile ResizeObserver ister — jsdom'da yok.
class ResizeObserverStub {
    observe() { /* jsdom */ }
    unobserve() { /* jsdom */ }
    disconnect() { /* jsdom */ }
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;

describe("SaveTemplateDialog (G212)", () => {
    let container: HTMLDivElement;
    let root: Root;

    beforeEach(() => {
        container = document.createElement("div");
        document.body.appendChild(container);
        root = createRoot(container);
    });
    afterEach(() => {
        act(() => root.unmount());
        container.remove();
        document.body.innerHTML = "";
    });

    function ciz(props: Partial<Parameters<typeof SaveTemplateDialog>[0]> = {}) {
        const onSubmit = vi.fn(async (_k: SablonKunyesi) => undefined);
        act(() => {
            root.render(
                <SaveTemplateDialog
                    open
                    onOpenChange={() => undefined}
                    mod="yeni"
                    onSubmit={onSubmit}
                    kaydediliyor={false}
                    {...props}
                />,
            );
        });
        return onSubmit;
    }
    const $ = <T extends Element = HTMLElement>(sel: string) => {
        const el = document.body.querySelector<T>(sel);
        if (!el) throw new Error(`bulunamadı: ${sel}`);
        return el;
    };
    const siniflar = (el: Element) => (el.getAttribute("class") ?? "").split(/\s+/);
    const yaz = (el: HTMLInputElement | HTMLTextAreaElement, deger: string) => {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, "value")!.set!;
        act(() => {
            setter.call(el, deger);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    };

    it("DialogContent ActivityReportModal deseninde: theme-classic, köşesiz, p-0 gap-0, var(--) renkleri", () => {
        ciz();
        const icerik = siniflar($("[data-testid='sablon-diyalogu']"));
        for (const s of [
            "theme-classic", "bg-[var(--bg-elevated)]", "border", "border-[var(--border)]", "rounded-none", "p-0", "gap-0",
        ]) {
            expect(icerik).toContain(s);
        }
    });

    it("başlık, gövde ve alt bölüm ayrı bloklar; alt bölüm kenarlıkla ayrılır ve sağa hizalıdır", () => {
        ciz();
        const baslik = $("[data-testid='sablon-diyalogu-baslik']");
        const govde = $("[data-testid='sablon-diyalogu-govde']");
        const alt = $("[data-testid='sablon-diyalogu-alt']");
        expect(siniflar(baslik)).toEqual(expect.arrayContaining(["border-b", "border-[var(--border)]", "px-6"]));
        expect(siniflar(govde)).toEqual(expect.arrayContaining(["px-6", "py-5"]));
        expect(siniflar(alt)).toEqual(expect.arrayContaining(["border-t", "border-[var(--border)]", "px-6", "sm:justify-end"]));
        // Paylaşımlı kutusu gövdede; düğmeler alt bölümde
        expect(govde.contains($("#sablon-paylasimli"))).toBe(true);
        expect(Array.from(alt.querySelectorAll("button")).map(b => b.textContent?.trim())).toEqual(["Vazgeç", "Kaydet"]);
    });

    it("Ad ve Açıklama girişleri h-9 / 13px, köşesiz, odakta --brand kenarı", () => {
        ciz();
        for (const sel of ["#sablon-ad", "#sablon-aciklama"]) {
            const s = siniflar($(sel));
            expect(s).toEqual(expect.arrayContaining(["text-[13px]", "rounded-none", "focus:border-[var(--brand)]"]));
            expect(s.some(x => x.startsWith("rounded-["))).toBe(false);
        }
        expect(siniflar($("#sablon-ad"))).toContain("h-9");
    });

    it("renkler yalnız var(--...) değişkenlerinden: diyalogda ham hex/rgb renk sınıfı yok", () => {
        ciz();
        const tum = Array.from($("[data-testid='sablon-diyalogu']").querySelectorAll("*"))
            .flatMap(el => siniflar(el));
        expect(tum.filter(s => /(bg|text|border)-\[(#|rgb)/.test(s))).toEqual([]);
    });

    it("davranış aynı: sınırlar 120/500, boş adla Kaydet pasif, gönderim künyesi kırpılır", async () => {
        const onSubmit = ciz();
        const ad = $<HTMLInputElement>("#sablon-ad");
        const aciklama = $<HTMLTextAreaElement>("#sablon-aciklama");
        expect(ad.maxLength).toBe(120);
        expect(aciklama.maxLength).toBe(500);
        const kaydet = Array.from($("form").querySelectorAll("button")).find(b => b.textContent?.trim() === "Kaydet")!;
        expect(kaydet.disabled).toBe(true);
        yaz(ad, "  Aylık rapor  ");
        yaz(aciklama, "   ");
        expect(kaydet.disabled).toBe(false);
        await act(async () => { kaydet.click(); });
        expect(onSubmit).toHaveBeenCalledWith({ ad: "Aylık rapor", aciklama: null, paylasimli: false });
    });

    it("düzenle modunda başlık ve düğme metni değişir, künye forma yazılır", () => {
        ciz({ mod: "duzenle", baslangic: { ad: "Eski", aciklama: "not", paylasimli: true } });
        expect($("[data-testid='sablon-diyalogu-baslik']").textContent).toContain("Şablonu düzenle");
        expect($<HTMLInputElement>("#sablon-ad").value).toBe("Eski");
        expect($<HTMLTextAreaElement>("#sablon-aciklama").value).toBe("not");
        expect($("#sablon-paylasimli").getAttribute("data-state")).toBe("checked");
        expect(Array.from($("[data-testid='sablon-diyalogu-alt']").querySelectorAll("button")).map(b => b.textContent?.trim()))
            .toEqual(["Vazgeç", "Güncelle"]);
    });
});
