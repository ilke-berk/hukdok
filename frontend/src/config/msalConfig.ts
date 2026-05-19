import { Configuration, PublicClientApplication } from "@azure/msal-browser";

/**
 * MSAL Configuration for Microsoft Authentication
 * 
 * This configures the authentication flow for HukuDok web app.
 * Users will sign in with their Microsoft 365 accounts.
 */
export const msalConfig: Configuration = {
    auth: {
        clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
        authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID}`,
        redirectUri: window.location.origin, // Auto-detects localhost or production
    },
    cache: {
        cacheLocation: "sessionStorage",
    },
};

// Initialize MSAL instance
export const msalInstance = new PublicClientApplication(msalConfig);

/**
 * Backend API için scope. Azure AD app registration → "Expose an API" altında
 * tanımlı `access_as_user` scope'unu kullanır. Backend bu token'ın aud'unu
 * client_id'ye karşı doğrular (auth_verifier.py).
 */
const apiClientId = import.meta.env.VITE_AZURE_CLIENT_ID;
export const loginRequest = {
    scopes: [`api://${apiClientId}/access_as_user`],
};
