// @vitest-environment jsdom
// CaseFoyPanel (G123) — föy düzeyi teslim alanlarının kartta görünmesi.
// Kart tek slotunda kardeş föyler çelişince hizmet türü/müvekkil tipi/durum
// karta yazılmaz; föyün kendi değeri bu panelde görünür. Bu dosya o bağı kilitler.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import CaseFoyPanel, { type CaseFoyEntry } from "./CaseFoyPanel";
import { foyDurumEtiketi, foyKapsamEtiketi } from "@/lib/foyLabels";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const foyler: CaseFoyEntry[] = [
    {
        id: 1, sistem_no: "H-1547", tku_no: "TKU-784", hasar_no: "HSR-1",
        mko_id: "1547", muvekkil_no: "1137",
        muvekkil_tipi: "Doktor", hizmet_turu: "Vekaletsiz Takip", durum: "DERDEST",
    },
    {
        id: 2, sistem_no: "H-1548", tku_no: "TKU-784", hasar_no: null,
        muvekkil_tipi: "Doktor", hizmet_turu: "Takip (doktor müvekkil)", durum: "MAHZEN",
        kapsam_durumu: "KAPSAM_DISI", kapsam_gerekcesi: "malpraktis dışı", kapsam_tarihi: "2026-09-04",
    },
];

describe("CaseFoyPanel", () => {
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
    });

    it("föy yoksa hiç basılmaz (boş kart gürültüdür)", () => {
        act(() => root.render(<CaseFoyPanel foyler={[]} />));
        expect(container.querySelector("[data-testid='case-foy-panel']")).toBeNull();
    });

    it("her föyün kimliği ve föy düzeyi alanları satır satır görünür", () => {
        act(() => root.render(<CaseFoyPanel foyler={foyler} />));
        const text = container.textContent ?? "";
        expect(text).toContain("Föyler");
        expect(text).toContain("(2)");
        expect(text).toContain("H-1547");
        expect(text).toContain("H-1548");
        expect(text).toContain("TKU-784");
        // Kart tek slotta tutamadığı iki farklı hizmet türü föy bazında görünür
        expect(text).toContain("Vekaletsiz Takip");
        expect(text).toContain("Takip (doktor müvekkil)");
        expect(text).toContain("Aktif");
        expect(text).toContain("Arşiv");
        expect(text).toContain("1547 / 1137");
        expect(container.querySelectorAll("tbody tr")).toHaveLength(2);
    });

    it("kapsam dışı föy silinmiş gibi değil, rozetle görünür", () => {
        act(() => root.render(<CaseFoyPanel foyler={foyler} />));
        const rozet = container.querySelector("span[title*='malpraktis dışı']");
        expect(rozet?.textContent).toBe("Kapsam dışı");
    });

    it("ham satır varsa açılır blokta tüm sütunlar görünür (G125)", () => {
        const hamli: CaseFoyEntry[] = [{
            ...foyler[0],
            ham_veri: { "Dava Değeri TL": 250000, "İş Kabul Tarihi": "2020-08-28", "Tanınmayan Sütun": "X" },
        }];
        act(() => root.render(<CaseFoyPanel foyler={hamli} />));
        const blok = container.querySelector("[data-testid='foy-ham-veri']");
        expect(blok?.textContent).toContain("Dava Değeri TL");
        expect(blok?.textContent).toContain("250000");
        expect(blok?.textContent).toContain("Tanınmayan Sütun");
    });

    it("ham satır yoksa blok hiç basılmaz", () => {
        act(() => root.render(<CaseFoyPanel foyler={foyler} />));
        expect(container.querySelector("[data-testid='foy-ham-veri']")).toBeNull();
    });

    it("etiket yardımcıları: havuz kodu Türkçe, ham yazım olduğu gibi", () => {
        expect(foyDurumEtiketi("DERDEST")).toBe("Aktif");
        expect(foyDurumEtiketi("MAHZEN")).toBe("Arşiv");
        expect(foyDurumEtiketi("Kapalı")).toBe("Kapalı");
        expect(foyDurumEtiketi(null)).toBe("—");
        expect(foyKapsamEtiketi(null)).toBeNull();
        expect(foyKapsamEtiketi("SILINDI")).toBe("Silinen föy");
    });
});
