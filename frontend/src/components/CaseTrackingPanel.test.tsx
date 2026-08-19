// @vitest-environment jsdom
// CaseTrackingPanel — karar durumu dropdown'larının resmî kapalı listelere
// bağlanması (G061). Liste içerikleri useConfig mock'undan gelir; backend
// uçlarının kendisi useConfig.test.tsx'te test edilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const updateCaseTrackingMock = vi.hoisted(() => vi.fn());
// G074: panel açılışta aşama tarihçesini de okur (salt okunur, ayrı route).
// Varsayılan boş yanıt — bu bloğun testleri tarihçeye bakmaz.
const stageDecisionsMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useCases", () => ({
    useCases: () => ({
        updateCaseTracking: updateCaseTrackingMock,
        getCaseStageDecisions: stageDecisionsMock,
    }),
    CASE_STAGE_DECISIONS_ERROR: "Aşama tarihçesi alınamadı — sunucuya ulaşılamadı.",
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

import { CASE_STAGE_DECISIONS_ERROR } from "@/hooks/useCases";
import CaseTrackingPanel from "./CaseTrackingPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("CaseTrackingPanel — karar durumu dropdown'ları (G061)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
        stageDecisionsMock.mockResolvedValue({ case_id: 1, decisions: [], onceki_esaslar: [] });
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

// ═══════════════════════════════════════════════════════════════════════════
// G074 — aşama zaman çizgisi (salt okunur) + aşamadan bağımsız alanlar
// ═══════════════════════════════════════════════════════════════════════════

const KARAR_SATIRI = {
    id: 11, case_id: 1, stage: "YEREL", sira_no: 1,
    mahkeme: "Ankara 3. Asliye Hukuk", esas_no: "2013/205", karar_no: "2014/88",
    karar_tarihi: "2014-03-09", karar_durumu: "Kabul", teblig_tarihi: "2014-04-01",
    basvuran_taraf: "Davalı", aciklama: "kısmen kabul", dogrulama_durumu: "TURETILDI",
    kaynak_id: null, source: "HUKDOK_TESLIM_tam_teslim.xlsx", created_at: null,
};

/** Efekt içindeki okuma sözü de akıtılır — tarihçe render edilmiş olur. */
function makeAsyncRenderer(getContainer: () => HTMLDivElement, setRoot: (r: Root) => void) {
    return async (caseData: Record<string, unknown>) => {
        const root = createRoot(getContainer());
        setRoot(root);
        await act(async () => {
            root.render(
                <CaseTrackingPanel caseId={1} caseData={caseData} onRefresh={() => {}} />,
            );
        });
    };
}

describe("CaseTrackingPanel — aşama tarihçesi (G074)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    const renderPanelAsync = makeAsyncRenderer(() => container, r => { root = r; });

    beforeEach(() => {
        vi.clearAllMocks();
        stageDecisionsMock.mockResolvedValue({ case_id: 1, decisions: [], onceki_esaslar: [] });
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

    it("seçili aşamanın geçmiş kararları künyesiyle listelenir", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1, decisions: [KARAR_SATIRI], onceki_esaslar: [],
        });
        await renderPanelAsync({ case_stage: "KARAR" });

        expect(container.textContent).toContain("Bu aşamanın geçmiş kararları (1)");
        expect(container.textContent).toContain("Ankara 3. Asliye Hukuk");
        expect(container.textContent).toContain("Esas 2013/205");
        expect(container.textContent).toContain("Karar 2014/88");
        expect(container.textContent).toContain("09.03.2014");        // karar tarihi tr-TR
        expect(container.textContent).toContain("Kabul");
        expect(container.textContent).toContain("Tebliğ: 01.04.2014");
        expect(container.textContent).toContain("Başvuran: Davalı");
        expect(container.textContent).toContain("kısmen kabul");
    });

    it("her satırda doğrulama damgası rozeti var (tahmin yasağı)", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [KARAR_SATIRI, { ...KARAR_SATIRI, id: 12, sira_no: 2, dogrulama_durumu: "BELIRSIZ" }],
            onceki_esaslar: [],
        });
        await renderPanelAsync({ case_stage: "KARAR" });

        expect(container.textContent).toContain("Türetildi");
        expect(container.textContent).toContain("Belirsiz");
    });

    it("id-2271: aynı aşamanın İKİ kararı da basılır, sira_no sırası korunur", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [
                { ...KARAR_SATIRI, id: 21, stage: "TEMYIZ", sira_no: 1, karar_durumu: "Bozma", aciklama: null },
                { ...KARAR_SATIRI, id: 22, stage: "TEMYIZ", sira_no: 2, karar_durumu: "Onama", aciklama: null },
            ],
            onceki_esaslar: [],
        });
        await renderPanelAsync({ case_stage: "TEMYIZ" });

        const kutu = container.textContent ?? "";
        expect(kutu).toContain("Bu aşamanın geçmiş kararları (2)");
        expect(kutu.indexOf("Bozma")).toBeLessThan(kutu.indexOf("Onama"));
    });

    it("case_stage BOŞ olsa da tarihçe görünür (kartların neredeyse tamamı böyle)", async () => {
        // Tarihçe `case_stage`ten BAĞIMSIZ okunur; aşama boş diye gizlenseydi
        // 4.971 satırın hiçbiri ekrana gelmezdi. (G075'te alan formunun kilidi
        // de kalktı — bu test o kilidin varlığına DEĞİL, tarihçenin
        // görünürlüğüne bakar.)
        stageDecisionsMock.mockResolvedValue({
            case_id: 1, decisions: [KARAR_SATIRI], onceki_esaslar: [],
        });
        await renderPanelAsync({});

        expect(container.textContent).toContain("Aşama girilmemiş");
        expect(container.textContent).toContain("Bu aşamanın geçmiş kararları (1)");
        expect(container.textContent).toContain("Ankara 3. Asliye Hukuk");
    });

    it("seçili aşamanın satırı yoksa kutu hiç basılmaz (boş kutu gürültüsü yok)", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [{ ...KARAR_SATIRI, stage: "TEMYIZ" }],
            onceki_esaslar: [],
        });
        await renderPanelAsync({ case_stage: "KARAR" });   // YEREL seçili, satır TEMYIZ'de

        expect(container.textContent).not.toContain("Bu aşamanın geçmiş kararları");
    });

    it("hata ≠ boş tarihçe: okuma başarısızsa uyarı basılır (G002 disiplini)", async () => {
        stageDecisionsMock.mockRejectedValue(new Error(CASE_STAGE_DECISIONS_ERROR));
        await renderPanelAsync({ case_stage: "KARAR" });

        expect(container.textContent).toContain("Aşama tarihçesi alınamadı");
        expect(container.textContent).not.toContain("Bu aşamanın geçmiş kararları");
    });

    it("önceki esas numaraları ayrı blokta görünür", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [],
            onceki_esaslar: [{
                id: 5, case_id: 1, esas_no: "2013/1136", stage: "ONCEKI",
                court: "Ankara 3. Asliye Hukuk", is_current: false, source: null, created_at: null,
            }],
        });
        await renderPanelAsync({ case_stage: "KARAR" });

        expect(container.textContent).toContain("Önceki Esas Numaraları");
        expect(container.textContent).toContain("2013/1136");
    });

    it("önceki esas yoksa blok basılmaz", async () => {
        await renderPanelAsync({ case_stage: "KARAR" });
        expect(container.textContent).not.toContain("Önceki Esas Numaraları");
    });
});

describe("CaseTrackingPanel — aşamadan bağımsız alanlar (G073 → G074)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    const renderPanelAsync = makeAsyncRenderer(() => container, r => { root = r; });

    beforeEach(() => {
        vi.clearAllMocks();
        stageDecisionsMock.mockResolvedValue({ case_id: 1, decisions: [], onceki_esaslar: [] });
        configMock.fileStatuses = [];
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

    function inputByLabel(label: string): HTMLInputElement {
        const wrap = Array.from(container.querySelectorAll("label"))
            .find(l => l.textContent?.trim() === label)?.parentElement;
        const el = wrap?.querySelector("input");
        if (!el) throw new Error("'" + label + "' etiketli input bulunamadı");
        return el;
    }

    function typeInto(el: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(el, value);
            el.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }

    it("üç alan case_stage BOŞKEN de düzenlenebilir (aşama sekmesine gömülmediler)", async () => {
        await renderPanelAsync({});

        expect(inputByLabel("Arabuluculuk No")).toBeDefined();
        expect(inputByLabel("Arabuluculuk Karar Tarihi")).toBeDefined();
        expect(inputByLabel("Arşiv Tarihi")).toBeDefined();
    });

    it("aktarımdan gelen değerler alana basılır", async () => {
        await renderPanelAsync({ arsiv_tarihi: "2021-03-15", arabuluculuk_no: "ARB-2020/9" });

        expect(inputByLabel("Arşiv Tarihi").value).toBe("2021-03-15");
        expect(inputByLabel("Arabuluculuk No").value).toBe("ARB-2020/9");
    });

    it("değişiklik taslağa girer ve Kaydet PATCH'inde gider", async () => {
        updateCaseTrackingMock.mockResolvedValue(true);
        await renderPanelAsync({});

        typeInto(inputByLabel("Arşiv Tarihi"), "2026-01-02");
        expect(container.textContent).toContain("Kaydedilmemiş");

        const saveBtn = Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.includes("Kaydet"));
        await act(async () => { saveBtn!.click(); });

        expect(updateCaseTrackingMock).toHaveBeenCalledWith(1, { arsiv_tarihi: "2026-01-02" });
    });
});

describe("CaseTrackingPanel — aşama bilinmiyorken panel kilitlenmez (G075)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    const renderPanelAsync = makeAsyncRenderer(() => container, r => { root = r; });

    beforeEach(() => {
        vi.clearAllMocks();
        stageDecisionsMock.mockResolvedValue({ case_id: 1, decisions: [], onceki_esaslar: [] });
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

    const labels = () =>
        Array.from(container.querySelectorAll("label")).map(l => l.textContent?.trim());

    it("case_stage BOŞKEN aşama alanları basılır — 'gelinmedi' kilidi yok", async () => {
        // Kusur buydu: currentIdx = -1 → isReached her aşamada false → 14.344
        // kartın hiçbirinde karar künyesi ne görünüyor ne düzeltilebiliyordu.
        await renderPanelAsync({ karar_no: "2014/88" });

        expect(container.textContent).not.toContain("Bu aşamaya henüz gelinmedi");
        expect(labels()).toContain("Karar No");
    });

    it("aşama bilinmiyorken aktarımdan gelen künye alana basılır", async () => {
        await renderPanelAsync({ karar_no: "2014/88" });

        const wrap = Array.from(container.querySelectorAll("label"))
            .find(l => l.textContent?.trim() === "Karar No")?.parentElement;
        expect(wrap?.querySelector("input")?.value).toBe("2014/88");
    });

    it("aşama bilinmiyorken KAPALI sekmesi 'Dava kapatılmış' DEMEZ (iddia üretmez)", async () => {
        await renderPanelAsync({});
        const kapaliBtn = Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.includes("Kapalı"));
        act(() => { kapaliBtn!.click(); });

        expect(container.textContent).not.toContain("Dava kapatılmış");
    });

    it("aşama BİLİNİYORSA gelecek aşama hâlâ kilitli (mevcut davranış korunur)", async () => {
        await renderPanelAsync({ case_stage: "KARAR" });
        const temyizBtn = Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.includes("Temyiz") || b.textContent?.includes("Tem."));
        act(() => { temyizBtn!.click(); });

        expect(container.textContent).toContain("Bu aşamaya henüz gelinmedi");
    });

    it("karar kaydı varsa en ileri aşama ÖNERİLİR (yazılmaz)", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [
                { ...KARAR_SATIRI, id: 31, stage: "YEREL", sira_no: 1 },
                { ...KARAR_SATIRI, id: 32, stage: "ISTINAF", sira_no: 1 },
            ],
            onceki_esaslar: [],
        });
        await renderPanelAsync({});

        expect(container.textContent).toContain("Karar kayıtlarına göre bu dosya en az");
        expect(container.textContent).toContain("İstinaf");
        // ÖNERİ yalnız öneridir: hiçbir şey kaydedilmedi
        expect(updateCaseTrackingMock).not.toHaveBeenCalled();
    });

    it("öneri kullanıcı onayıyla MEVCUT aşama geçişi yolundan yazılır", async () => {
        updateCaseTrackingMock.mockResolvedValue(true);
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [{ ...KARAR_SATIRI, id: 33, stage: "ISTINAF", sira_no: 1 }],
            onceki_esaslar: [],
        });
        await renderPanelAsync({});

        const ayarlaBtn = Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.trim() === "Aşamayı ayarla");
        act(() => { ayarlaBtn!.click(); });

        // Onay dialogu açılır — tek tıkla sessiz yazma YOK
        const gecBtn = Array.from(document.querySelectorAll("button"))
            .find(b => b.textContent?.trim() === "Geç");
        expect(gecBtn).toBeDefined();
        expect(updateCaseTrackingMock).not.toHaveBeenCalled();

        await act(async () => { gecBtn!.click(); });

        expect(updateCaseTrackingMock).toHaveBeenCalledWith(1, { case_stage: "ISTINAF", note: null });
    });

    it("aşama boş ve karar da yoksa öneri basılmaz — uydurmuyoruz", async () => {
        await renderPanelAsync({});
        expect(container.textContent).not.toContain("Karar kayıtlarına göre");
    });

    it("aşama biliniyorsa öneri basılmaz", async () => {
        stageDecisionsMock.mockResolvedValue({
            case_id: 1,
            decisions: [{ ...KARAR_SATIRI, id: 34, stage: "TEMYIZ", sira_no: 1 }],
            onceki_esaslar: [],
        });
        await renderPanelAsync({ case_stage: "KARAR" });

        expect(container.textContent).not.toContain("Karar kayıtlarına göre");
    });
});
