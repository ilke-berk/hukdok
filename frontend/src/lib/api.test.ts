// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// MSAL ve sonner modülleri mock'lanır — gerçek login/toast yok
const msalMocks = vi.hoisted(() => ({
    getActiveAccount: vi.fn(),
    getAllAccounts: vi.fn(),
    acquireTokenSilent: vi.fn(),
    logoutRedirect: vi.fn(),
}));

vi.mock("@/config/msalConfig", () => ({
    msalInstance: msalMocks,
    loginRequest: { scopes: ["api://test/.default"] },
}));

const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", () => ({ toast: { error: toastError } }));

import { apiClient, getApiUrl } from "./api";

const account = { username: "test@example.com" };

beforeEach(() => {
    vi.clearAllMocks();
    (window as Window & { _isLoggingOut?: boolean })._isLoggingOut = false;
    msalMocks.getActiveAccount.mockReturnValue(account);
    msalMocks.getAllAccounts.mockReturnValue([account]);
    msalMocks.acquireTokenSilent.mockResolvedValue({ accessToken: "test-token" });
    msalMocks.logoutRedirect.mockResolvedValue(undefined);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

function stubFetch(status = 200) {
    const fetchMock = vi.fn().mockResolvedValue({ status, ok: status < 400 });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

describe("getApiUrl", () => {
    it("VITE_API_URL tanımsızken bağıl yol (boş taban) döner", async () => {
        expect(await getApiUrl()).toBe("");
    });
});

describe("apiClient.fetch", () => {
    it("access token'ı Authorization header'ına ekler (G8: idToken değil)", async () => {
        const fetchMock = stubFetch();
        await apiClient.fetch("/api/cases");

        const [url, options] = fetchMock.mock.calls[0];
        expect(url).toBe("/api/cases");
        expect((options.headers as Headers).get("Authorization")).toBe("Bearer test-token");
    });

    it("token alınamazsa Authorization header'ı eklenmez", async () => {
        msalMocks.getActiveAccount.mockReturnValue(null);
        msalMocks.getAllAccounts.mockReturnValue([]);
        const fetchMock = stubFetch();

        await apiClient.fetch("/api/cases");

        const [, options] = fetchMock.mock.calls[0];
        expect((options.headers as Headers).get("Authorization")).toBe(null);
    });

    it("başında / olmayan endpoint'e / eklenir", async () => {
        const fetchMock = stubFetch();
        await apiClient.fetch("api/cases");
        expect(fetchMock.mock.calls[0][0]).toBe("/api/cases");
    });

    it("varsayılan Content-Type JSON'dur", async () => {
        const fetchMock = stubFetch();
        await apiClient.fetch("/api/cases", { method: "POST", body: "{}" });

        const [, options] = fetchMock.mock.calls[0];
        expect((options.headers as Headers).get("Content-Type")).toBe("application/json");
    });

    it("FormData gövdesinde Content-Type set edilmez (boundary tarayıcıya kalır)", async () => {
        const fetchMock = stubFetch();
        await apiClient.fetch("/process", { method: "POST", body: new FormData() });

        const [, options] = fetchMock.mock.calls[0];
        expect((options.headers as Headers).get("Content-Type")).toBe(null);
    });

    it("401 yanıtta oturum kapatma akışı tetiklenir", async () => {
        stubFetch(401);
        await apiClient.fetch("/api/cases");

        // Dinamik import("sonner") + 500ms gecikme → toast ve logout'u bekle
        await vi.waitFor(() => expect(toastError).toHaveBeenCalled(), { timeout: 2000 });
        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
    });

    it("eşzamanlı 401'ler tek logout tetikler", async () => {
        stubFetch(401);
        await Promise.all([apiClient.fetch("/api/a"), apiClient.fetch("/api/b")]);

        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
        expect(msalMocks.logoutRedirect).toHaveBeenCalledTimes(1);
    });
});
