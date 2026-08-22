import { msalInstance, loginRequest } from "@/config/msalConfig";

// Base API URL helper
export const getApiUrl = async (): Promise<string> => {
    // Geliştirme modunda (Vite Proxy için) veya eğer API_URL tanımlanmamışsa bağıl yol kullan
    const apiUrl = import.meta.env.VITE_API_URL;

    if (!apiUrl) {
        return ""; // Tarayıcı mevcut origin (örn: http://localhost:8000) üzerinden /api/... çağırır
    }

    return apiUrl;
};

/**
 * Oturum kurtarılamayıp logout redirect'e gidilmeden HEMEN önce yayınlanır —
 * dinleyenler (ör. sihirbaz taslağı) durumlarını sessionStorage'a flush eder.
 */
export const SESSION_EXPIRED_EVENT = "hukdok:session-expired";

// Validates and returns the authentication token
const getAuthToken = async (forceRefresh = false): Promise<string | null> => {
    try {
        const activeAccount = msalInstance.getActiveAccount();
        const accounts = msalInstance.getAllAccounts();

        if (!activeAccount && accounts.length === 0) {
            console.warn("🔒 API Request: No active account found.");
            return null;
        }

        const request = {
            ...loginRequest,
            account: activeAccount || accounts[0],
            forceRefresh
        };

        // Try to get token silently
        const response = await msalInstance.acquireTokenSilent(request);
        // API scope'lu access token gönderilir (G8) — idToken değil. Backend aud
        // kontrolü "api://<client_id>" ve "<client_id>" formatlarının ikisini de kabul eder.
        return response.accessToken;
    } catch (error) {
        console.error("❌ Token acquisition failed:", error);
        return null;
    }
};

// --- Faz 4.1: zaman aşımı katmanları + idempotent GET retry ---------------
//
// Tarayıcı fetch'inin varsayılan timeout'u YOK — askıda kalan bağlantı sonsuz
// "yükleniyor" demek. İki katman:
//   - DEFAULT (30 sn): etkileşimli okuma/yazma uçları.
//   - LONG (300 sn): dosya yükleme, analiz/LLM, dönüşüm, indirme/export ve
//     e-posta gönderen uçlar — nginx proxy_read_timeout 300 sn ile hizalı;
//     sunucu kendi 504'ünü üretebilsin diye daha kısa tutulmaz.
export const DEFAULT_TIMEOUT_MS = 30_000;
export const LONG_TIMEOUT_MS = 300_000;

// Uzun katman eşlemesi (tasarım kararı): FormData gövdesi = dosya yükleme her
// zaman uzun; kalanlar yol tabanlı. Hızlı bir ucun uzun tavana girmesi zararsız
// (tavan bekleme değil), tersi 30 sn'de meşru işi keser — şüphede uzun seçildi.
const LONG_TIMEOUT_PREFIXES = [
    "/process",                   // upload + Gemini analiz stream'i
    "/confirm",                   // PDF/A dönüşümü + arşiv + e-posta
    "/api/case-intake/",          // otonom dava açma ailesi (analyze/merge/commit LLM'li)
    "/api/download/",             // işlenmiş PDF indirmesi (büyük gövde)
    "/preview-email-body",        // Gemini gövde üretimi
    "/preview-client-email-body",
    "/api/config/export/",        // dosya export indirmesi
    "/api/activity/admin/",       // rapor üretimi/toplu e-posta tetikleri
    "/refresh",                   // SharePoint config listelerinin yeniden yüklenmesi
];
// Yolun İÇİNDE geçen işaretler (ör. /api/documents/{id}/download).
const LONG_TIMEOUT_MARKERS = ["/download", "/resend-email", "/send-emails"];

export function resolveTimeoutMs(endpoint: string, options: RequestInit = {}): number {
    if (options.body instanceof FormData) return LONG_TIMEOUT_MS;
    const path = (endpoint.startsWith("/") ? endpoint : "/" + endpoint).split("?")[0];
    if (LONG_TIMEOUT_PREFIXES.some((p) => path.startsWith(p))) return LONG_TIMEOUT_MS;
    if (LONG_TIMEOUT_MARKERS.some((m) => path.includes(m))) return LONG_TIMEOUT_MS;
    return DEFAULT_TIMEOUT_MS;
}

/**
 * apiClient'ın kendi zaman aşımı — çıplak AbortError yerine kullanıcıya
 * gösterilebilir Türkçe mesaj taşır (çağıranlar error.message'ı toast'lar).
 * Çağıranın kendi iptali (options.signal) bu sınıfa ÇEVRİLMEZ, aynen fırlar.
 */
export class ApiTimeoutError extends Error {
    readonly endpoint: string;
    readonly timeoutMs: number;

    constructor(endpoint: string, timeoutMs: number) {
        const message = timeoutMs >= LONG_TIMEOUT_MS
            ? "İşlem 5 dakika içinde tamamlanamadı. İşlem sunucuda sürüyor olabilir — " +
              "aynı belgeyi hemen TEKRAR YÜKLEMEYİN; birkaç dakika bekleyip aynı ekrandan tekrar deneyin."
            : "Sunucudan 30 saniye içinde yanıt alınamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.";
        super(message);
        this.name = "ApiTimeoutError";
        this.endpoint = endpoint;
        this.timeoutMs = timeoutMs;
    }
}

// YALNIZ idempotent GET'ler tekrar denenir: 2 deneme, 500ms→1000ms backoff.
// POST'lar (özellikle /confirm ve /commit) HİÇBİR koşulda otomatik tekrarlanmaz —
// 3-D idempotency kapısı sunucuda olsa da otomatik tekrar bilinçli yasak.
// Zaman aşımında da tekrar YOK (30 sn × 3 = 90 sn askı olurdu; timeout "geçici
// hıçkırık" değil "sunucu takıldı" sinyalidir).
const GET_RETRY_DELAYS_MS = [500, 1000];
const RETRYABLE_GET_STATUSES = new Set([502, 503, 504]);

/**
 * Oturum kurtarılamadı (token yok ya da yenileme sonrası da 401): flush olayı
 * yayınla, kullanıcıyı uyar, tek seferlik logout redirect'e git.
 * `_isLoggingOut` bekçisi eşzamanlı çağrılarda tek logout garantiler.
 */
function handleSessionExpired(): void {
    console.error("⛔ Unauthorized Access (401) - Logging out...");

    // Sessiz yenileme tutmadı → logout kaçınılmaz; redirect öncesi açık
    // taslaklar sessionStorage'a flush edilsin (sihirbaz dinler).
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));

    // Prevent multiple logout triggers for concurrent 401s
    const w = window as Window & { _isLoggingOut?: boolean };
    if (w._isLoggingOut) return;
    w._isLoggingOut = true;

    // Alert the user and logout
    import("sonner").then(({ toast }) => {
        toast.error("Oturum süresi doldu", {
            description: "Güvenlik nedeniyle tekrar giriş yapmanız gerekiyor.",
            duration: 3000
        });

        // Small delay to allow toast to be seen (optional)
        setTimeout(() => {
            // BrowserRouter'dayız (App.tsx) — hash fragment'li eski hedef HashRouter artığıydı (G095).
            msalInstance.logoutRedirect({
                postLogoutRedirectUri: window.location.origin + '/login',
            }).catch(err => {
                console.error("Logout failed:", err);
                w._isLoggingOut = false;
            });
        }, 500);
    });
}

/**
 * Global API Client wrapper
 * automatically handles Bearer Token injection
 */
export const apiClient = {
    fetch: async (endpoint: string, options: RequestInit = {}): Promise<Response> => {
        const baseUrl = await getApiUrl();
        const url = `${baseUrl}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`;

        // Get Token
        const token = await getAuthToken();

        // G095: token alınamıyorsa (hesap yok / refresh token tavana çarptı)
        // ağa hiç çıkılmaz — backend zaten 401 basacak, forceRefresh edinimi de
        // null dönecekti; tur tamamen boşaydı (upload'da koca FormData gövdesi).
        // Oturum-bitti dalı aynen çalışır, çağırana sentetik 401 Response döner
        // (sözleşme: apiClient.fetch daima Response döner, istisna FIRLATMAZ).
        if (!token) {
            console.warn(`🔒 API Request: token yok, istek atlandı → ${options.method || 'GET'} ${url}`);
            handleSessionExpired();
            return new Response(null, { status: 401, statusText: "Unauthorized" });
        }

        // Prepare Headers
        const headers = new Headers(options.headers);
        headers.set("Authorization", `Bearer ${token}`);

        // Ensure Content-Type is JSON unless specified otherwise (or FormData)
        if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }

        console.log(`📡 API Request: ${options.method || 'GET'} ${url}`);

        const timeoutMs = resolveTimeoutMs(endpoint, options);

        // Deneme başına kendi controller'ımız + setTimeout: AbortSignal.timeout
        // yerine bilinçli tercih — çağıranın signal'iyle elle köprülenir
        // (AbortSignal.any bağımlılığı yok) ve vitest fake-timer'larıyla test
        // edilebilir. Timeout gövde okumasını da kapsar (signal fetch'e bağlı).
        const doFetch = async (requestHeaders: Headers): Promise<Response> => {
            const controller = new AbortController();
            let timedOut = false;
            const timer = setTimeout(() => {
                timedOut = true;
                controller.abort();
            }, timeoutMs);
            const onCallerAbort = () => controller.abort(options.signal?.reason);
            if (options.signal) {
                if (options.signal.aborted) onCallerAbort();
                else options.signal.addEventListener("abort", onCallerAbort, { once: true });
            }
            try {
                return await fetch(url, { ...options, headers: requestHeaders, signal: controller.signal });
            } catch (err) {
                if (timedOut && !options.signal?.aborted) {
                    throw new ApiTimeoutError(endpoint, timeoutMs);
                }
                throw err;
            } finally {
                clearTimeout(timer);
                options.signal?.removeEventListener("abort", onCallerAbort);
            }
        };

        const method = (options.method || "GET").toUpperCase();
        const maxAttempts = method === "GET" ? 1 + GET_RETRY_DELAYS_MS.length : 1;

        let response: Response | null = null;
        let lastNetworkError: unknown = null;
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            if (attempt > 0) {
                await new Promise((r) => setTimeout(r, GET_RETRY_DELAYS_MS[attempt - 1]));
                if (options.signal?.aborted) break;
                console.warn(`🔁 GET tekrar denemesi ${attempt}/${GET_RETRY_DELAYS_MS.length}: ${url}`);
            }
            try {
                response = await doFetch(headers);
                lastNetworkError = null;
            } catch (err) {
                if (err instanceof ApiTimeoutError) throw err;               // timeout'ta tekrar yok
                if ((err as Error)?.name === "AbortError") throw err;        // çağıran iptali aynen
                if (method !== "GET") throw err;                             // yalnız GET retry'lanır
                lastNetworkError = err;
                response = null;
                continue;
            }
            if (method !== "GET" || !RETRYABLE_GET_STATUSES.has(response.status)) break;
            // 502/503/504 GET → bir sonraki turda tekrar denenir; denemeler
            // tükenirse son yanıt olduğu gibi döner (çağıran hata yolunu işler).
        }
        if (!response) {
            throw lastNetworkError instanceof Error
                ? lastNetworkError
                : new Error("Sunucuya ulaşılamadı.");
        }

        // Faz 6.2 katman 1: 401'de MSAL sessiz yenileme (forceRefresh) + isteği
        // BİR kez tekrar — 30+ dk review'da access token düşse de akış kesilmez.
        // (Gövdeler string/FormData; ikisi de güvenle yeniden gönderilebilir.)
        if (response.status === 401) {
            const freshToken = await getAuthToken(true);
            if (freshToken && freshToken !== token) {
                console.warn("🔄 401 sonrası token yenilendi — istek tekrarlanıyor");
                headers.set("Authorization", `Bearer ${freshToken}`);
                response = await doFetch(headers);
            }
        }

        // Handle 401 Unauthorized globally if needed
        if (response.status === 401) {
            handleSessionExpired();
        }

        return response;
    }
};
