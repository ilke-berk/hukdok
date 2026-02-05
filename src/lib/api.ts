import { msalInstance, loginRequest } from "@/config/msalConfig";

// Base API URL helper
export const getApiUrl = async (): Promise<string> => {
    // Web Mode (Production / Dev)
    const apiUrl = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
    return apiUrl;
};

// Validates and returns the authentication token
const getAuthToken = async (): Promise<string | null> => {
    try {
        const activeAccount = msalInstance.getActiveAccount();
        const accounts = msalInstance.getAllAccounts();

        if (!activeAccount && accounts.length === 0) {
            console.warn("🔒 API Request: No active account found.");
            return null;
        }

        const request = {
            ...loginRequest,
            account: activeAccount || accounts[0]
        };

        // Try to get token silently
        const response = await msalInstance.acquireTokenSilent(request);
        return response.idToken;
    } catch (error) {
        console.error("❌ Token acquisition failed:", error);
        return null;
    }
};

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

        // Prepare Headers
        const headers = new Headers(options.headers);
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }

        // Ensure Content-Type is JSON unless specified otherwise (or FormData)
        if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
            headers.set("Content-Type", "application/json");
        }

        console.log(`📡 API Request: ${options.method || 'GET'} ${url}`);

        const response = await fetch(url, {
            ...options,
            headers
        });

        // Handle 401 Unauthorized globally if needed
        if (response.status === 401) {
            console.error("⛔ Unauthorized Access (401)");
            // Optional: Trigger logout or redirect
        }

        return response;
    }
};
