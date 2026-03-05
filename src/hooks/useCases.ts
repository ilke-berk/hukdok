import { useState, useCallback } from "react";
import { useMsal } from "@azure/msal-react";
import { getApiUrl } from "@/lib/api";

export interface CasePartyData {
    client_id?: number | null;
    name: string;
    role: string;
    party_type: "CLIENT" | "COUNTER" | "THIRD";
    birth_year?: number;
    gender?: string;
}

export interface CaseData {
    tracking_no: string;
    esas_no?: string;
    status: string;
    file_type?: string;
    sub_type?: string;
    subject?: string;
    court?: string;
    opening_date?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    maddi_tazminat?: number;
    manevi_tazminat?: number;
    parties: CasePartyData[];
}

export const useCases = () => {
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

    const saveCase = useCallback(async (data: CaseData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "POST", data);
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);

    const getCases = useCallback(async () => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return [];
    }, [authenticatedRequest]);

    const getCase = useCallback(async (id: number) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/${id}`, "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return null;
    }, [authenticatedRequest]);

    const updateCase = useCallback(async (id: number, data: CaseData) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/${id}`, "PUT", data);
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);

    const searchCases = useCallback(async (query: string) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/search?q=${encodeURIComponent(query)}`, "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return [];
    }, [authenticatedRequest]);

    const getClientCaseSequence = useCallback(async (clientName: string) => {
        const response = await authenticatedRequest(`/api/cases/client-sequence?client_name=${encodeURIComponent(clientName)}`, "GET");
        if (response && response.ok) {
            const data = await response.json();
            return data.sequence || 1;
        }
        return 1;
    }, [authenticatedRequest]);

    const saveCaseAndReturn = useCallback(async (data: CaseData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "POST", data);
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json(); // { id, tracking_no, ... }
        }
        return null;
    }, [authenticatedRequest]);

    const deleteCase = useCallback(async (id: number) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/${id}`, "DELETE");
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);

    return {
        saveCase,
        saveCaseAndReturn,
        updateCase,
        deleteCase,
        getCases,
        getCase,
        searchCases,
        getClientCaseSequence,
        isLoading
    };
};
