// @vitest-environment jsdom
// AdminPage — URL'deki `?tab=` parametresinin başlangıç sekmesine dönüşmesi (G117).
// Veri teslimi bildirimi `/admin?tab=deliveries`e gezinir; sayfa girişte o sekmeyi
// açmalı, tanınmayan değerde eski varsayılan (Avukatlar) korunmalı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Sekme içerikleri kendi testlerinde sınanır; burada yalnız hangi sekmenin
// AÇILDIĞI önemli. Radix inaktif TabsContent'i hiç basmaz → stub görünürlüğü
// sekme aktifliğinin kanıtıdır.
vi.mock("@/components/admin/DeliveryInboxCard", () => ({
    DeliveryInboxCard: () => <div data-testid="delivery-inbox-stub" />,
}));
vi.mock("@/components/admin/FeatureSettingsCard", () => ({
    FeatureSettingsCard: () => <div data-testid="feature-settings-stub" />,
}));

// Liste kimlikleri SABİT: AdminPage `useEffect(..., [lawyers])` ile yerel kopyaya
// yazar; her render'da yeni `[]` dönen mock sonsuz efekt döngüsüne sokar.
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

describe("AdminPage ?tab= başlangıç sekmesi (G117)", () => {
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

    const aktifSekme = () => container.querySelector("[role='tab'][data-state='active']")?.textContent;

    it("?tab=deliveries ile açılınca Veri Teslimleri sekmesi aktiftir", () => {
        render("/admin?tab=deliveries");

        expect(aktifSekme()).toBe("Veri Teslimleri");
        expect(container.querySelector("[data-testid='delivery-inbox-stub']")).not.toBeNull();
    });

    it("parametre yoksa Avukatlar sekmesi açılır (eski davranış)", () => {
        render("/admin");

        expect(aktifSekme()).toBe("Avukatlar");
        expect(container.querySelector("[data-testid='delivery-inbox-stub']")).toBeNull();
    });

    it("geçersiz ?tab=xyz Avukatlar'a düşer", () => {
        render("/admin?tab=xyz");

        expect(aktifSekme()).toBe("Avukatlar");
    });

    it("?tab=features Özellikler sekmesini açar (tanınan her sekme değeri geçer)", () => {
        render("/admin?tab=features");

        expect(aktifSekme()).toBe("Özellikler");
        expect(container.querySelector("[data-testid='feature-settings-stub']")).not.toBeNull();
    });
});
