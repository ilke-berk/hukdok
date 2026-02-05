import { useState } from "react";
import { useMsal } from "@azure/msal-react";
import { getApiUrl } from "@/lib/api";

export interface ClientData {
    name: string;
    tc_no?: string;
    email?: string;
    phone?: string;
    address?: string;
    notes?: string;
    client_type?: string;
    category?: string;
}

export const useClients = () => {
    const { instance, accounts } = useMsal();
    const [isLoading, setIsLoading] = useState(false);

    const authenticatedRequest = async (url: string, method: string, body?: any) => {
        const baseUrl = await getApiUrl();
        const account = instance.getActiveAccount() || accounts[0];
        if (!account) return null;

        try {
            const response = await instance.acquireTokenSilent({
                scopes: ["User.Read"],
                account: account
            });

            const res = await fetch(`${baseUrl}${url}`, {
                method,
                headers: {
                    "Authorization": `Bearer ${response.idToken}`,
                    "Content-Type": "application/json"
                },
                body: body ? JSON.stringify(body) : undefined
            });

            return res;
        } catch (e) {
            console.error("API Request Failed", e);
            return null;
        }
    };

    const saveClient = async (data: ClientData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/clients", "POST", data);
        setIsLoading(false);
        return response ? response.ok : false;
    };

    const getClients = async () => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/clients", "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return [];
    };



    // START: Edit Client
    const updateClient = async (id: number, data: ClientData) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/clients/${id}`, "PUT", data);
        setIsLoading(false);
        return response ? response.ok : false;
    };
    // END: Edit Client

    return {
        saveClient,
        updateClient,
        getClients,
        isLoading
    };
};
