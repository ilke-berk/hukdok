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

import {
    ApiTimeoutError,
    DEFAULT_TIMEOUT_MS,
    LONG_TIMEOUT_MS,
    apiClient,
    getApiUrl,
    resolveTimeoutMs,
    SESSION_EXPIRED_EVENT,
} from "./api";

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

    // G095: Bu test eskiden "token alınamazsa Authorization header'ı eklenmez
    // ama istek yine de gider" sözleşmesini kilitliyordu. O tur tamamen boşaydı
    // (backend 401 basar, forceRefresh edinimi de null döner → logout). Yeni
    // sözleşme: token yoksa ağa HİÇ çıkılmaz, sentetik 401 Response döner ve
    // oturum-bitti dalı aynen tetiklenir. Aşağıdaki testler bunu kilitler.
    it("token alınamazsa fetch HİÇ çağrılmaz ve 401 Response döner (istisna fırlamaz)", async () => {
        msalMocks.getActiveAccount.mockReturnValue(null);
        msalMocks.getAllAccounts.mockReturnValue([]);
        const fetchMock = stubFetch();

        const response = await apiClient.fetch("/api/cases");

        expect(fetchMock).not.toHaveBeenCalled();
        expect(response).toBeInstanceOf(Response);
        expect(response.status).toBe(401);
        expect(response.ok).toBe(false);
    });

    it("acquireTokenSilent fırlatınca da (refresh tavanı) ağa çıkılmaz, 401 döner", async () => {
        msalMocks.acquireTokenSilent.mockRejectedValue(new Error("interaction_required"));
        const fetchMock = stubFetch();

        const response = await apiClient.fetch("/process", { method: "POST", body: new FormData() });

        expect(fetchMock).not.toHaveBeenCalled();
        expect(response.status).toBe(401);
    });

    it("token alınamazsa flush olayı yayınlanır ve logout /login hedefiyle tetiklenir", async () => {
        msalMocks.getActiveAccount.mockReturnValue(null);
        msalMocks.getAllAccounts.mockReturnValue([]);
        stubFetch();
        const flushListener = vi.fn();
        window.addEventListener(SESSION_EXPIRED_EVENT, flushListener);

        await apiClient.fetch("/api/cases");

        expect(flushListener).toHaveBeenCalledTimes(1);
        await vi.waitFor(() => expect(toastError).toHaveBeenCalled(), { timeout: 2000 });
        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
        expect(msalMocks.logoutRedirect).toHaveBeenCalledWith({
            postLogoutRedirectUri: window.location.origin + "/login",
        });
        window.removeEventListener(SESSION_EXPIRED_EVENT, flushListener);
    });

    it("eşzamanlı iki token'sız istek tek logout tetikler (_isLoggingOut bekçisi)", async () => {
        msalMocks.getActiveAccount.mockReturnValue(null);
        msalMocks.getAllAccounts.mockReturnValue([]);
        const fetchMock = stubFetch();

        const responses = await Promise.all([apiClient.fetch("/api/a"), apiClient.fetch("/api/b")]);

        expect(fetchMock).not.toHaveBeenCalled();
        expect(responses.map((r) => r.status)).toEqual([401, 401]);
        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
        expect(msalMocks.logoutRedirect).toHaveBeenCalledTimes(1);
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

    it("401'de token sessizce yenilenip istek BİR kez tekrarlanır (Faz 6.2)", async () => {
        // İlk edinim "test-token", forceRefresh edinimi "fresh-token" döner
        msalMocks.acquireTokenSilent
            .mockResolvedValueOnce({ accessToken: "test-token" })
            .mockResolvedValueOnce({ accessToken: "fresh-token" });
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ status: 401, ok: false })
            .mockResolvedValueOnce({ status: 200, ok: true });
        vi.stubGlobal("fetch", fetchMock);

        const response = await apiClient.fetch("/api/cases");

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        const retryHeaders = fetchMock.mock.calls[1][1].headers as Headers;
        expect(retryHeaders.get("Authorization")).toBe("Bearer fresh-token");
        // forceRefresh ile ikinci edinim yapılmış olmalı
        expect(msalMocks.acquireTokenSilent.mock.calls[1][0].forceRefresh).toBe(true);
        expect(msalMocks.logoutRedirect).not.toHaveBeenCalled();
    });

    it("yenileme sonrası da 401 ise flush olayı yayınlanıp logout'a gidilir", async () => {
        msalMocks.acquireTokenSilent
            .mockResolvedValueOnce({ accessToken: "test-token" })
            .mockResolvedValueOnce({ accessToken: "fresh-token" });
        const fetchMock = vi.fn().mockResolvedValue({ status: 401, ok: false });
        vi.stubGlobal("fetch", fetchMock);
        const flushListener = vi.fn();
        window.addEventListener(SESSION_EXPIRED_EVENT, flushListener);

        await apiClient.fetch("/api/cases");

        expect(fetchMock).toHaveBeenCalledTimes(2); // orijinal + tek tekrar
        expect(flushListener).toHaveBeenCalledTimes(1);
        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
        window.removeEventListener(SESSION_EXPIRED_EVENT, flushListener);
    });

    it("401 yanıtta oturum kapatma akışı tetiklenir", async () => {
        stubFetch(401);
        await apiClient.fetch("/api/cases");

        // Dinamik import("sonner") + 500ms gecikme → toast ve logout'u bekle
        await vi.waitFor(() => expect(toastError).toHaveBeenCalled(), { timeout: 2000 });
        await vi.waitFor(() => expect(msalMocks.logoutRedirect).toHaveBeenCalled(), {
            timeout: 2000,
        });
        // G095: BrowserRouter rotası — HashRouter artığı hash fragment'i DEĞİL
        expect(msalMocks.logoutRedirect).toHaveBeenCalledWith({
            postLogoutRedirectUri: window.location.origin + "/login",
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

// --- Faz 4.1: zaman aşımı katmanları --------------------------------------

describe("resolveTimeoutMs (uç eşlemesi)", () => {
    it("etkileşimli okuma uçları varsayılan 30 sn'dedir", () => {
        expect(resolveTimeoutMs("/api/cases")).toBe(DEFAULT_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/hearing-dates")).toBe(DEFAULT_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/activity/history?days=30")).toBe(DEFAULT_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/documents/5/party")).toBe(DEFAULT_TIMEOUT_MS);
    });

    it("upload/analiz/dönüşüm uçları uzun katmandadır (300 sn)", () => {
        expect(resolveTimeoutMs("/process")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/confirm")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/case-intake/analyze")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/case-intake/commit")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/preview-email-body")).toBe(LONG_TIMEOUT_MS);
    });

    it("indirme/export/e-posta uçları uzun katmandadır", () => {
        expect(resolveTimeoutMs("/api/download/abc123")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/documents/5/download?inline=true")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/documents/5/resend-email")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/activity/daily-report/1/send-emails")).toBe(LONG_TIMEOUT_MS);
        expect(resolveTimeoutMs("/api/config/export/clients")).toBe(LONG_TIMEOUT_MS);
    });

    it("FormData gövdesi = dosya yükleme → yol ne olursa olsun uzun katman", () => {
        expect(resolveTimeoutMs("/api/herhangi-bir-uc", { body: new FormData() })).toBe(LONG_TIMEOUT_MS);
    });
});

// Abort signal'ine saygı duyan, hiç yanıt dönmeyen fetch stub'ı — timeout testleri.
// Gerçek fetch gibi: zaten abort edilmiş signal ANINDA reddeder.
function stubHangingFetch() {
    const fetchMock = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
        return new Promise((_resolve, reject) => {
            const fail = () =>
                reject(new DOMException("The operation was aborted.", "AbortError"));
            if (options.signal?.aborted) {
                fail();
                return;
            }
            options.signal?.addEventListener("abort", fail);
        });
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

describe("apiClient.fetch zaman aşımı (Faz 4.1)", () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    it("30 sn'de ApiTimeoutError fırlar; timeout'ta tekrar deneme YOKTUR", async () => {
        vi.useFakeTimers();
        const fetchMock = stubHangingFetch();

        const promise = apiClient.fetch("/api/cases");
        const assertion = expect(promise).rejects.toBeInstanceOf(ApiTimeoutError);
        await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS);
        await assertion;

        // GET olmasına rağmen timeout retry'lanmaz (30 sn × 3 = 90 sn askı olurdu)
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("kısa katman mesajı anlaşılırdır (çıplak AbortError sızmaz)", async () => {
        vi.useFakeTimers();
        stubHangingFetch();

        const promise = apiClient.fetch("/api/cases");
        const assertion = expect(promise).rejects.toThrow(/30 saniye içinde yanıt alınamadı/);
        await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS);
        await assertion;
    });

    it("uzun katman (/confirm) 5 dk bekler ve 'TEKRAR YÜKLEMEYİN' tavsiyesi taşır", async () => {
        vi.useFakeTimers();
        const fetchMock = stubHangingFetch();

        const promise = apiClient.fetch("/confirm", { method: "POST", body: new FormData() });
        const assertion = expect(promise).rejects.toThrow(/TEKRAR YÜKLEMEYİN/);

        // 30 sn'de HENÜZ düşmemeli (uzun katman)
        await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS);
        expect(fetchMock).toHaveBeenCalledTimes(1);

        await vi.advanceTimersByTimeAsync(LONG_TIMEOUT_MS - DEFAULT_TIMEOUT_MS);
        await assertion;
        expect(fetchMock).toHaveBeenCalledTimes(1); // POST asla tekrarlanmaz
    });

    it("çağıranın kendi iptali ApiTimeoutError'a ÇEVRİLMEZ, AbortError aynen fırlar", async () => {
        stubHangingFetch();
        const controller = new AbortController();

        const promise = apiClient.fetch("/api/cases", { signal: controller.signal });
        const assertion = expect(promise).rejects.toSatisfy(
            (e) => (e as Error).name === "AbortError",
        );
        controller.abort();
        await assertion;
    });
});

// --- Faz 4.1: yalnız idempotent GET retry ---------------------------------

describe("apiClient.fetch GET retry (Faz 4.1)", () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    it("GET 503'te 500ms→1000ms backoff'la iki kez tekrar dener, başarıyı döndürür", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn()
            .mockResolvedValueOnce({ status: 503, ok: false })
            .mockResolvedValueOnce({ status: 503, ok: false })
            .mockResolvedValueOnce({ status: 200, ok: true });
        vi.stubGlobal("fetch", fetchMock);

        const promise = apiClient.fetch("/api/cases");
        await vi.advanceTimersByTimeAsync(1500);
        const response = await promise;

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("denemeler tükenince son 503 yanıtı olduğu gibi döner (çağıran işler)", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn().mockResolvedValue({ status: 503, ok: false });
        vi.stubGlobal("fetch", fetchMock);

        const promise = apiClient.fetch("/api/cases");
        await vi.advanceTimersByTimeAsync(1500);
        const response = await promise;

        expect(response.status).toBe(503);
        expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it("GET ağ hatasında da tekrar dener", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn()
            .mockRejectedValueOnce(new TypeError("Failed to fetch"))
            .mockResolvedValueOnce({ status: 200, ok: true });
        vi.stubGlobal("fetch", fetchMock);

        const promise = apiClient.fetch("/api/cases");
        await vi.advanceTimersByTimeAsync(500);
        const response = await promise;

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("GET 500'de tekrar DENEMEZ (yalnız 502/503/504 geçicidir)", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ status: 500, ok: false });
        vi.stubGlobal("fetch", fetchMock);

        const response = await apiClient.fetch("/api/cases");

        expect(response.status).toBe(500);
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("POST 503'te ASLA tekrar denemez (/confirm, /commit disiplini)", async () => {
        const fetchMock = vi.fn().mockResolvedValue({ status: 503, ok: false });
        vi.stubGlobal("fetch", fetchMock);

        const response = await apiClient.fetch("/confirm", { method: "POST", body: "{}" });

        expect(response.status).toBe(503);
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("POST ağ hatasında anında fırlar, tekrar yok", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
        vi.stubGlobal("fetch", fetchMock);

        await expect(
            apiClient.fetch("/api/cases", { method: "POST", body: "{}" }),
        ).rejects.toBeInstanceOf(TypeError);
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });
});
