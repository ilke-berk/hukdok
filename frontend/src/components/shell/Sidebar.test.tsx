// @vitest-environment jsdom
// Sidebar "Araçlar" bölümü — Hukukbot HUKDOK'un iç sayfasıdır (karar 021): kendi sitesi/girişi yok,
// menü öğesi her kullanıcıda görünür, `/hukukbot`'a gider, dış adres/yeni sekme YOK.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

const adminMock = vi.hoisted(() => ({ value: false as boolean | null }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => adminMock.value }));
vi.mock("@azure/msal-react", () => ({
    useMsal: () => ({
        accounts: [{ username: "avukat@lexis.com.tr", name: "Avukat Kullanıcı" }],
        instance: { getActiveAccount: () => null, logoutRedirect: async () => undefined },
    }),
}));
vi.mock("@/hooks/useDashboardView", () => ({ useDashboardView: () => ({ view: "avukat", setView: () => undefined }) }));

import { Sidebar } from "./Sidebar";

function Konum() {
    return <span data-testid="konum">{useLocation().pathname}</span>;
}

describe("Sidebar Hukukbot öğesi", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        container = document.createElement("div");
        document.body.appendChild(container);
    });

    afterEach(() => {
        act(() => root?.unmount());
        root = null;
        container.remove();
    });

    async function render(admin: boolean, yol = "/") {
        adminMock.value = admin;
        root = createRoot(container);
        await act(async () => {
            root!.render(
                <MemoryRouter initialEntries={[yol]}>
                    <Sidebar open onClose={() => undefined} />
                    <Routes><Route path="*" element={<Konum />} /></Routes>
                </MemoryRouter>,
            );
        });
    }

    const hukukbotOgesi = () =>
        Array.from(container.querySelectorAll("button")).find(b => b.textContent?.trim() === "Hukukbot");

    it("yönetici olmayan kullanıcıda da görünür ve /hukukbot'a gider", async () => {
        await render(false);
        const oge = hukukbotOgesi();
        expect(oge).toBeDefined();
        await act(async () => oge!.click());
        expect(container.querySelector('[data-testid="konum"]')!.textContent).toBe("/hukukbot");
    });

    it("dış bağlantı yok: hukbot.tragic.tr'ye ya da yeni sekmeye giden <a> kalmadı", async () => {
        await render(true);
        const linkler = Array.from(container.querySelectorAll("a"));
        expect(linkler.some(a => a.textContent?.includes("Hukukbot"))).toBe(false);
        expect(container.innerHTML).not.toContain("hukbot.tragic.tr");
        expect(linkler.some(a => a.getAttribute("target") === "_blank")).toBe(false);
    });

    it("/hukukbot'tayken öğe aktif vurgulanır", async () => {
        await render(false, "/hukukbot");
        expect(hukukbotOgesi()!.className).toContain("bg-[var(--brand-soft)]");
    });

    // Lexis rapor aracı önizlemesi (04.10): örnek veriyle çalışır, entegrasyona dek yalnız yöneticide.
    const lexisOgesi = () =>
        Array.from(container.querySelectorAll("button")).find(b => b.textContent?.trim() === "Lexis");

    it("Lexis öğesi yönetici olmayan kullanıcıda görünmez", async () => {
        await render(false);
        expect(lexisOgesi()).toBeUndefined();
    });

    it("Lexis öğesi yöneticide görünür ve /lexis'e gider", async () => {
        await render(true);
        const oge = lexisOgesi();
        expect(oge).toBeDefined();
        await act(async () => oge!.click());
        expect(container.querySelector('[data-testid="konum"]')!.textContent).toBe("/lexis");
    });
});
