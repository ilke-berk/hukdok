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
        cacheLocation: "localStorage", // Keep user logged in across sessions
    },
};

// Initialize MSAL instance
export const msalInstance = new PublicClientApplication(msalConfig);

/**
 * Scopes (Permissions) requested from Microsoft Graph API
 */
export const loginRequest = {
    scopes: ["User.Read"], // Read user profile (email, name, etc.)
};
