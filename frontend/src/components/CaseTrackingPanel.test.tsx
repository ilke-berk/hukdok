// @vitest-environment jsdom
// CaseTrackingPanel — karar durumu dropdown'larının resmî kapalı listelere
// bağlanması (G061). Liste içerikleri useConfig mock'undan gelir; backend
// uçlarının kendisi useConfig.test.tsx'te test edilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const updateCaseTrackingMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useCases", () => ({
    useCases: () => ({ updateCaseTracking: updateCaseTrackingMock }),
}));

// Her test kendi listelerini doldurur; boş dizi = "liste boş ya da yüklenemedi".
const configMock = vi.hoisted(() => ({
    fileStatuses: [] as { code?: string; name: string }[],
    localDecisions: [] as { code?: string; name: string }[],
    appealDecisions: [] as { code?: string; name: string }[],
    cassationDecisions: [] as { code?: string; name: string }[],
    revisionDecisions: [] as { code?: string; name: string }[],
}));
vi.mock("@/hooks/useConfig", () => ({
    useConfig: () => configMock,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import CaseTrackingPanel from "./CaseTrackingPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("CaseTrackingPanel — karar durumu dropdown'ları (G061)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
        configMock.fileStatuses = [];
        configMock.localDecisions = [];
        configMock.appealDecisions = [];
        configMock.cassationDecisions = [];
        configMock.revisionDecisions = [];
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

    function renderPanel(caseData: Record<string, unknown>) {
        root = createRoot(container);
        act(() => root!.render(
            <CaseTrackingPanel caseId={1} caseData={caseData} onRefresh={() => {}} />,
        ));
    }

    /** Aşama kartındaki alan etiketinden select'i bulur (etiket + kontrol aynı sarmalayıcıda). */
    function selectByLabel(label: string): HTMLSelectElement {
        const wrap = Array.from(container.querySelectorAll("label"))
            .find(l => l.textContent?.trim() === label)?.parentElement;
        const sel = wrap?.querySelector("select");
        if (!sel) throw new Error(`'${label}' etiketli select bulunamadı`);
        return sel;
    }

    const optionTexts = (sel: HTMLSelectElement) =>
        Array.from(sel.options).map(o => o.textContent);

    /** React controlled select'e kullanıcı seçimi: prototip setter + change (value tracker aşımı). */
    function chooseOption(sel: HTMLSelectElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
        act(() => {
            setter.call(sel, value);
            sel.dispatchEvent(new Event("change", { bubbles: true }));
        });
    }

    it("yerel karar durumu select'i resmî listeyle dolar, resmi havuz SIRASI korunur", () => {
        configMock.localDecisions = [
            { code: "DERDEST", name: "Derdest" },
            { code: "BERAAT", name: "Beraat" },   // bilinçli alfabetik değil
            { code: "KABUL", name: "Kabul" },
        ];
        renderPanel({ case_stage: "KARAR" });

        expect(optionTexts(selectByLabel("Karar Durumu")))
            .toEqual(["Seçiniz", "Derdest", "Beraat", "Kabul"]);
    });

    it("temyiz aşamasına Karar Durumu select'i eklendi (Temyiz Onama Durumları)", () => {
        configMock.cassationDecisions = [
            { code: "BOZMA", name: "Bozma" },
            { code: "ONAMA", name: "Onama" },
            { code: "DUZELTEREK_ONAMA", name: "Düzelterek Onama" },
        ];
        renderPanel({ case_stage: "TEMYIZ" });

        expect(optionTexts(selectByLabel("Karar Durumu")))
            .toEqual(["Seçiniz", "Bozma", "Onama", "Düzelterek Onama"]);
    });

    it("karar_turu/karar_lehine gömülü seçenekleri BİREBİR aynı kalır", () => {
        configMock.localDecisions = [{ code: "KABUL", name: "Kabul" }];
        renderPanel({ case_stage: "KARAR" });

        expect(optionTexts(selectByLabel("Karar Türü")))
            .toEqual(["Seçiniz", "KABUL", "RED", "KISMI_KABUL", "FERAGAT", "UZLASMA", "DUSME"]);
        expect(optionTexts(selectByLabel("Karar Lehine")))
            .toEqual(["Seçiniz", "LEHINE", "ALEYHINE", "KISMI"]);
    });

    it("listeden çıkarılmış kayıtlı değer KAYBOLMAZ — '(liste dışı)' geçici seçenek olur", () => {
        configMock.appealDecisions = [
            { code: "KALDIRMA", name: "Kaldırma" },
            { code: "BASVURU_RET", name: "Başvuru Ret" },
        ];
        // Eski gömülü dizinin değeri ("ONANMADI") resmi havuzda yok
        renderPanel({ case_stage: "ISTINAF", istinaf_karar_durumu: "ONANMADI" });

        const sel = selectByLabel("Karar Durumu");
        expect(sel.value).toBe("ONANMADI");                       // görüntü korunur
        expect(optionTexts(sel))
            .toEqual(["Seçiniz", "ONANMADI (liste dışı)", "Kaldırma", "Başvuru Ret"]);
        expect(Array.from(sel.options).map(o => o.value))
            .toContain("ONANMADI");                               // değer HAM kalır, etiket damgalı
    });

    it("liste boş/yüklenemediyse form kırılmaz: Seçiniz + kayıtlı değer (damgasız)", () => {
        // configMock.appealDecisions boş — yüklenememiş ya da boş doğmuş liste
        renderPanel({ case_stage: "ISTINAF", istinaf_karar_durumu: "ONANMADI" });

        const sel = selectByLabel("Karar Durumu");
        expect(sel.value).toBe("ONANMADI");
        // Liste boşken "liste dışı" damgası vurulmaz (closedListState "unknown" kuralı)
        expect(optionTexts(sel)).toEqual(["Seçiniz", "ONANMADI"]);
    });

    it("boş liste + boş değer: yalnız Seçiniz kalır, panel render olur", () => {
        renderPanel({ case_stage: "ISTINAF" });
        expect(optionTexts(selectByLabel("Karar Durumu"))).toEqual(["Seçiniz"]);
    });

    it("yerel karar durumu seçimi taslağa girer ve Kaydet PATCH'inde gider", async () => {
        configMock.localDecisions = [{ code: "DERDEST", name: "Derdest" }];
        updateCaseTrackingMock.mockResolvedValue(true);
        renderPanel({ case_stage: "KARAR" });

        chooseOption(selectByLabel("Karar Durumu"), "Derdest");

        // Kaydedilmemiş değişiklik çubuğu doğar
        expect(container.textContent).toContain("Kaydedilmemiş");
        const saveBtn = Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.includes("Kaydet"));
        expect(saveBtn).toBeDefined();

        await act(async () => { saveBtn!.click(); });

        expect(updateCaseTrackingMock).toHaveBeenCalledWith(1, { yerel_karar_durumu: "Derdest" });
    });
});
