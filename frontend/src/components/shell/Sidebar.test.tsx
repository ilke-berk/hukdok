// @vitest-environment jsdom
// Sidebar "Araçlar" bölümü — Hukukbot ayrı uygulamadır (kendi alanı + girişi): bağlantı her kullanıcıda
// görünür, YENİ sekmede açılır ve açılan sekme HukuDok'a window.opener ile erişemez (noopener).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";

const adminMock = vi.hoisted(() => ({ value: false as boolean | null }));
vi.mock("@/hooks/useIsAdmin", () => ({ useIsAdmin: () => adminMock.value }));
vi.mock("@azure/msal-react", () => ({
    useMsal: () => ({
        accounts: [{ username: "avukat@lexis.com.tr", name: "Avukat Kullanıcı" }],
        instance: { getActiveAccount: () => null, logoutRedirect: async () => undefined },
    }),
}));
vi.mock("@/hooks/useDashboardView", () => ({ useDashboardView: () => ({ view: "avukat", setView: () => undefined }) }));

import { Sidebar, HUKUKBOT_URL } from "./Sidebar";

describe("Sidebar Hukukbot bağlantısı", () => {
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

    async function render(admin: boolean) {
        adminMock.value = admin;
        root = createRoot(container);
        await act(async () => {
            root!.render(<MemoryRouter><Sidebar open onClose={() => undefined} /></MemoryRouter>);
        });
    }

    const hukukbotLinki = () =>
        Array.from(container.querySelectorAll("a")).find(a => a.textContent?.includes("Hukukbot"));

    it("yönetici olmayan kullanıcıda da görünür ve hukukbot adresine gider", async () => {
        await render(false);
        const link = hukukbotLinki();
        expect(link).toBeDefined();
        expect(link!.getAttribute("href")).toBe(HUKUKBOT_URL);
        expect(HUKUKBOT_URL.startsWith("https://")).toBe(true);
    });

    it("yeni sekmede açılır, opener sızdırmaz", async () => {
        await render(true);
        const link = hukukbotLinki()!;
        expect(link.getAttribute("target")).toBe("_blank");
        expect(link.getAttribute("rel")).toContain("noopener");
        expect(link.getAttribute("rel")).toContain("noreferrer");
    });
});
