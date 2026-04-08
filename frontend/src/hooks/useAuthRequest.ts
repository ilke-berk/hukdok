import { useCallback } from "react";
import { useMsal } from "@azure/msal-react";
import { apiClient } from "@/lib/api";

export const useAuthRequest = () => {
    const { accounts } = useMsal();

    const authRequest = useCallback(async (url: string, method: string, body?: unknown): Promise<Response | null> => {
        if (accounts.length === 0) return null;

        try {
            return await apiClient.fetch(url, {
                method,
                body: body ? JSON.stringify(body) : undefined
            });
        } catch (e) {
            console.error("API Request Failed", e);
            return null;
        }
    }, [accounts]);

    return { authRequest };
};
