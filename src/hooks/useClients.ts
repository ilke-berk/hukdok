import { useState, useCallback } from "react";
import { useMsal } from "@azure/msal-react";
import { getApiUrl } from "@/lib/api";

export interface ClientData {
    name: string;
    tc_no?: string;
    email?: string;
    phone?: string;
    mobile_phone?: string;
    address?: string;
    notes?: string;
    client_type?: string;
    category?: string;
    birth_year?: number;
    gender?: string;
    specialty?: string;
    cari_kod?: string;
}

export const useClients = () => {
    const { instance, accounts } = useMsal();
    const [isLoading, setIsLoading] = useState(false);

    const authenticatedRequest = useCallback(async (url: string, method: string, body?: unknown) => {
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
    }, [instance, accounts]);

    const saveClient = useCallback(async (data: ClientData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/clients", "POST", data);
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);

    const getClients = useCallback(async () => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/clients", "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return [];
    }, [authenticatedRequest]);



    // START: Edit Client
    const updateClient = useCallback(async (id: number, data: ClientData) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/clients/${id}`, "PUT", data);
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);
    // END: Edit Client

    // START: Delete Client
    const deleteClient = useCallback(async (id: number) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/clients/${id}`, "DELETE");
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);
    // END: Delete Client

    return {
        saveClient,
        updateClient,
        deleteClient,
        getClients,
        isLoading
    };
};
