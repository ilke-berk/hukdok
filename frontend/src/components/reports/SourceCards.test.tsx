// @vitest-environment jsdom
// SourceCards (G139) — kaynak kartları: `role=radiogroup` / `role=radio` + `aria-checked`, kimlik
// `[data-kaynak]`; etiket + tek satır açıklama (boş açıklama satır üretmez); tıklama `onSec(anahtar)`;
// dar ekranda yatay kaydırma sınıfı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import type { KatalogVeriKaynagi } from "@/lib/reports";
import { SourceCards } from "./SourceCards";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const kaynak = (anahtar: string, etiket: string, aciklama: string): KatalogVeriKaynagi => ({
    anahtar, etiket, aciklama, varsayilan_kolonlar: [], kolonlar: [], hizli_filtreler: [], kolon_setleri: [],
});
const KAYNAKLAR = [
    kaynak("davalar", "Davalar", "Dava kartları"),
    kaynak("muvekkiller", "Müvekkiller", ""),
    kaynak("belgeler", "Belgeler", "İşlenmiş belgeler"),
    kaynak("foyler", "Föyler", "Aktarım föyleri"),
];

describe("SourceCards (G139)", () => {
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

    function render(secili: string, onSec = vi.fn()) {
        root = createRoot(container);
        act(() => {
            root!.render(<SourceCards kaynaklar={KAYNAKLAR} secili={secili} onSec={onSec} />);
        });
        return onSec;
    }
    const kartlar = () => Array.from(container.querySelectorAll<HTMLButtonElement>("[data-kaynak]"));

    it("dört kart radio grubunda, seçili kart aria-checked; etiket + açıklama; boş açıklama satır üretmez", () => {
        render("belgeler");
        const grup = container.querySelector("[role='radiogroup']")!;
        expect(grup.getAttribute("aria-label")).toBe("Veri kaynağı");
        expect(grup.className).toContain("overflow-x-auto");
        expect(kartlar().map(k => k.getAttribute("data-kaynak"))).toEqual(["davalar", "muvekkiller", "belgeler", "foyler"]);
        expect(kartlar().every(k => k.getAttribute("role") === "radio")).toBe(true);
        expect(kartlar().map(k => k.getAttribute("aria-checked"))).toEqual(["false", "false", "true", "false"]);
        expect(kartlar()[0].textContent).toContain("Davalar");
        expect(kartlar()[0].textContent).toContain("Dava kartları");
        expect(kartlar()[1].textContent?.trim()).toBe("Müvekkiller");
        expect(kartlar()[1].title).toBe("Müvekkiller");
        expect(kartlar()[0].title).toBe("Dava kartları");
    });

    it("tıklama onSec(anahtar) çağırır (seçili kart dahil — karar sayfada)", () => {
        const onSec = render("davalar");
        act(() => {
            kartlar()[3].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        expect(onSec).toHaveBeenCalledWith("foyler");
        act(() => {
            kartlar()[0].dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
        expect(onSec).toHaveBeenLastCalledWith("davalar");
        expect(onSec).toHaveBeenCalledTimes(2);
    });
});
