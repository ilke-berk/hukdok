// @vitest-environment jsdom
// AdminPage — "Ofis No Kodları" sekmesinin bağlantısı (G241). Panelin kendisi
// OfisNoKodlariPanel.test.tsx'te sınanır; burada yalnız sekmenin var olduğu ve
// `?tab=ofis_no_kodlari` ile açıldığı kilitlenir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Radix inaktif TabsContent'i hiç basmaz → stub görünürlüğü sekme aktifliğinin kanıtıdır.
vi.mock("@/components/admin/OfisNoKodlariPanel", () => ({
    OfisNoKodlariPanel: () => <div data-testid="ofis-no-kodlari-stub" />,
}));
vi.mock("@/components/admin/DeliveryInboxCard", () => ({
    DeliveryInboxCard: () => <div data-testid="delivery-inbox-stub" />,
}));
vi.mock("@/components/admin/FeatureSettingsCard", () => ({
    FeatureSettingsCard: () => <div data-testid="feature-settings-stub" />,
}));

// Liste kimlikleri SABİT (AdminPage.test.tsx'teki gerekçe: her render'da yeni `[]`
// dönen mock `useEffect(..., [lawyers])`'ı sonsuz döngüye sokar).
const configMock = vi.hoisted(() => {
    const EMPTY: never[] = [];
    const noop = () => undefined;
    return {
        lawyers: EMPTY, statuses: EMPTY, doctypes: EMPTY, emailRecipients: EMPTY, caseSubjects: EMPTY,
        fileTypes: EMPTY, courtTypes: EMPTY, partyRoles: EMPTY, bureauTypes: EMPTY, cities: EMPTY,
        specialties: EMPTY, clientCategories: EMPTY, fileStatuses: EMPTY,
        isLoading: false,
        addLawyer: noop, addStatus: noop, addDoctype: noop, addEmail: noop, addCaseSubject: noop,
        addFileType: noop, addCourtType: noop, addPartyRole: noop, addBureauType: noop,
        addCity: noop, addSpecialty: noop, addClientCategory: noop, addFileStatus: noop,
        reorderList: noop, updateItem: noop, deleteItem: noop, fetchUsage: noop,
    };
});
vi.mock("@/hooks/useConfig", () => ({ useConfig: () => configMock }));

import AdminPage from "./AdminPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("AdminPage Ofis No Kodları sekmesi (G241)", () => {
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

    function render(url: string) {
        root = createRoot(container);
        act(() => {
            root!.render(
                <MemoryRouter initialEntries={[url]}>
                    <AdminPage />
                </MemoryRouter>,
            );
        });
    }

    const sekmeler = () => Array.from(container.querySelectorAll("[role='tab']")).map(t => t.textContent);
    const aktifSekme = () => container.querySelector("[role='tab'][data-state='active']")?.textContent;
    const panel = () => container.querySelector("[data-testid='ofis-no-kodlari-stub']");

    it("sekme listesinde Ofis No Kodları vardır; varsayılan açılışta panel basılmaz", () => {
        render("/admin");

        expect(sekmeler()).toContain("Ofis No Kodları");
        expect(panel()).toBeNull();
    });

    it("?tab=ofis_no_kodlari paneli açar", () => {
        render("/admin?tab=ofis_no_kodlari");

        expect(aktifSekme()).toBe("Ofis No Kodları");
        expect(panel()).not.toBeNull();
    });
});
