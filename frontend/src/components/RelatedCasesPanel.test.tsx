// @vitest-environment jsdom
// RelatedCasesPanel — otomatik ilişki katmanının panele bağlanması.
// Backend `automatic` listesini services/case_relations_auto.py üretir (TKU grubu
// + esas/mahkeme ikizi); panel bugüne dek YALNIZ `manual`ı çiziyordu, otomatik
// liste dolu gelse bile ekranda hiç görünmüyordu. Bu dosya o bağı kilitler.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const getRelatedCasesMock = vi.hoisted(() => vi.fn());
const addCaseRelationMock = vi.hoisted(() => vi.fn());
const removeCaseRelationMock = vi.hoisted(() => vi.fn());
const rejectCaseRelationMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useCases", () => ({
    useCases: () => ({
        getRelatedCases: getRelatedCasesMock,
        addCaseRelation: addCaseRelationMock,
        removeCaseRelation: removeCaseRelationMock,
        rejectCaseRelation: rejectCaseRelationMock,
    }),
}));

vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("./AddRelationModal", () => ({ default: () => null }));

import RelatedCasesPanel, { type RelatedCase } from "./RelatedCasesPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** TKU-1230 kardeşi: aynı mahkeme + aynı esas, farklı müvekkil (canlı desen). */
const ayniDava: RelatedCase = {
    id: 804,
    tracking_no: "D1.E_CELIKOGL.0001.IDARE.00000",
    esas_no: "2020/2029",
    court: "İstanbul 8. İdare Mahkemesi",
    status: "DERDEST",
    file_type: "İdare",
    parties: [{ name: "E. ÇELİKOĞLU", role: "Müvekkil" }],
    relation_type: "AYNI_DAVA",
    match_reason: "Aynı TKU grubu (TKU-1230) · aynı mahkemede aynı esas (2020/2029)",
    is_manual: false,
};

/** TKU-4724: arabuluculuk → dava; bağı kuran tek şey TKU. */
const arabuluculuk: RelatedCase = {
    id: 13715,
    tracking_no: "D1.M_MERSIN...0003.ARABU.00000",
    esas_no: "2023/33233",
    court: null,
    status: "KAPALI",
    file_type: "Arabuluculuk",
    parties: [],
    relation_type: "ARABULUCULUK_ONCULU",
    match_reason: "Aynı TKU grubu (TKU-4724)",
    is_manual: false,
};

const elleBaglanan: RelatedCase = {
    id: 999,
    tracking_no: "D1.X.........0001.HUKUK.00000",
    esas_no: "2024/1",
    court: "Ankara 1. Asliye Hukuk Mahkemesi",
    status: "DERDEST",
    file_type: "Hukuk",
    parties: [],
    relation_id: 5,
    relation_type: "ILGILI",
    match_reason: "Kullanıcı tarafından bağlandı",
    is_manual: true,
    note: "Aynı olayın devamı",
};

describe("RelatedCasesPanel — otomatik ilişki katmanı", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
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

    async function renderPanel(
        yanit: { manual: RelatedCase[]; automatic: RelatedCase[] },
        onCountChange?: (n: number) => void,
    ) {
        getRelatedCasesMock.mockResolvedValue(yanit);
        root = createRoot(container);
        await act(async () => {
            root!.render(<RelatedCasesPanel caseId={803} onCountChange={onCountChange} />);
        });
    }

    const buton = (metin: string) =>
        Array.from(container.querySelectorAll("button"))
            .find(b => b.textContent?.includes(metin));

    // G128 — öneri katmanı: aynı hasta + aynı doktor, onay bekler.
    const oneri: RelatedCase = {
        id: 5594,
        tracking_no: "D1.O_ERDENER..0007.ICRAA.00000",
        esas_no: "2014/5156",
        court: "İstanbul 37. İcra Müdürlüğü",
        status: "DERDEST",
        file_type: "İcra",
        parties: [{ name: "Semra Kurt", role: "Borçlu" }],
        relation_type: "ICRA_PARALEL",
        match_reason: "Aynı hasta (Semra Kurt) + aynı doktor (Oktay Erdener) — aynı tıbbi vaka olabilir, onay bekler",
        is_manual: false,
    };

    it("öneri bölümü ayrı başlıkla çiziliyor, rozete sayılmıyor, Bağla + Reddet var", async () => {
        const sayac = vi.fn();
        await renderPanel({ manual: [], automatic: [ayniDava], suggested: [oneri] } as never, sayac);
        const blok = container.querySelector("[data-testid='related-suggested']");
        expect(blok?.textContent).toContain("Öneri: aynı hasta ve doktor");
        expect(blok?.textContent).toContain("2014/5156");
        expect(blok?.textContent).toContain("aynı tıbbi vaka olabilir");
        expect(sayac).toHaveBeenLastCalledWith(1);            // yalnız otomatik + elle sayılır
        expect(Array.from(blok!.querySelectorAll("button")).map(b => b.textContent?.trim())).toEqual(
            expect.arrayContaining(["Git", "Bağla", "Reddet"]),
        );
    });

    it("Reddet öneriyi backend'e yazıyor ve listeyi yeniliyor", async () => {
        rejectCaseRelationMock.mockResolvedValue(true);
        await renderPanel({ manual: [], automatic: [], suggested: [oneri] } as never);
        getRelatedCasesMock.mockResolvedValue({ manual: [], automatic: [], suggested: [] });
        await act(async () => { buton("Reddet")!.click(); });
        expect(rejectCaseRelationMock).toHaveBeenCalledWith(803, 5594);
        expect(container.querySelector("[data-testid='related-suggested']")).toBeNull();
    });

    it("yalnız öneri varken boş durum GÖSTERİLMEZ", async () => {
        await renderPanel({ manual: [], automatic: [], suggested: [oneri] } as never);
        expect(container.textContent).not.toContain("bağlantı yok");
        expect(container.querySelector("[data-testid='related-suggested']")).not.toBeNull();
    });

    it("otomatik ilişkiler çiziliyor (eski panel yalnız manual'ı gösteriyordu)", async () => {
        await renderPanel({ manual: [], automatic: [ayniDava, arabuluculuk] });

        // Kart başlığı esas_no'yu gösterir (yoksa tracking_no'ya düşer).
        expect(container.textContent).toContain("Sistemin bulduğu");
        expect(container.textContent).toContain("2020/2029");
        expect(container.textContent).toContain("İstanbul 8. İdare Mahkemesi");
        expect(container.textContent).toContain("2023/33233");
    });

    it("ilişki türleri Türkçe etiketleriyle görünüyor", async () => {
        await renderPanel({ manual: [], automatic: [ayniDava, arabuluculuk] });

        expect(container.textContent).toContain("Aynı Dava");
        expect(container.textContent).toContain("Arabuluculuk → Dava");
    });

    it("otomatik satırda gerekçe gösteriliyor, manuel satırda gösterilmiyor", async () => {
        await renderPanel({ manual: [elleBaglanan], automatic: [ayniDava] });

        expect(container.textContent).toContain("Aynı TKU grubu (TKU-1230)");
        expect(container.textContent).toContain("Aynı olayın devamı");        // kullanıcı notu
        expect(container.textContent).not.toContain("Kullanıcı tarafından bağlandı");
    });

    it("rozet iki katmanı birden sayıyor", async () => {
        const sayac = vi.fn();
        await renderPanel({ manual: [elleBaglanan], automatic: [ayniDava, arabuluculuk] }, sayac);

        expect(sayac).toHaveBeenCalledWith(3);
    });

    it("yalnız otomatik ilişki varken boş durum GÖSTERİLMEZ", async () => {
        await renderPanel({ manual: [], automatic: [ayniDava] });

        expect(container.textContent).not.toContain("İlişkili dava yok");
    });

    it("iki liste de boşken boş durum gösteriliyor", async () => {
        await renderPanel({ manual: [], automatic: [] });

        expect(container.textContent).toContain("İlişkili dava yok");
    });

    it("otomatik satırda Sil yok, Kalıcı Bağla var", async () => {
        await renderPanel({ manual: [], automatic: [ayniDava] });

        expect(buton("Sil")).toBeUndefined();
        expect(buton("Kalıcı Bağla")).toBeDefined();
    });

    it("manuel satırda Kalıcı Bağla yok, Sil var", async () => {
        await renderPanel({ manual: [elleBaglanan], automatic: [] });

        expect(buton("Kalıcı Bağla")).toBeUndefined();
        expect(buton("Sil")).toBeDefined();
    });

    it("Kalıcı Bağla öneriyi tür + gerekçesiyle manuel katmana yazıyor", async () => {
        addCaseRelationMock.mockResolvedValue({ id: 7, status: "created" });
        await renderPanel({ manual: [], automatic: [ayniDava] });

        await act(async () => { buton("Kalıcı Bağla")!.click(); });

        expect(addCaseRelationMock).toHaveBeenCalledWith(803, {
            target_case_id: 804,
            relation_type: "AYNI_DAVA",
            note: ayniDava.match_reason,
        });
        // Kayıttan sonra liste tazelenir: backend elle bağlananı otomatik listede
        // tekrar etmez, satır kendiliğinden "Sistemin bulduğu"ndan çıkar.
        expect(getRelatedCasesMock).toHaveBeenCalledTimes(2);
    });
});
