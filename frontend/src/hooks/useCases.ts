import { useState, useCallback } from "react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface CasePartyData {
    client_id?: number | null;
    name: string;
    role: string;
    party_type: "CLIENT" | "COUNTER" | "THIRD";
    birth_year?: number;
    gender?: string;
}

export interface CaseLawyerData {
    lawyer_id?: number | null;
    name: string;
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
    acceptance_date?: string;
    bureau_type?: string;
    sub_type_extra?: string;
    judicial_unit?: string;
    parties: CasePartyData[];
    lawyers?: CaseLawyerData[];
}

export const useCases = () => {
    const { authRequest } = useAuthRequest();
    const [isLoading, setIsLoading] = useState(false);

    const authenticatedRequest = authRequest;

    const saveCase = useCallback(async (data: CaseData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "POST", data);
        setIsLoading(false);
        return response ? response.ok : false;
    }, [authenticatedRequest]);

    const getCases = useCallback(async (options: {
        limit?: number;
        offset?: number;
        status?: string;
        lawyer?: string;
        q?: string;
        exact?: boolean;
    } = {}) => {
        setIsLoading(true);
        const params = new URLSearchParams();
        if (options.limit !== undefined) params.append("limit", options.limit.toString());
        if (options.offset !== undefined) params.append("offset", options.offset.toString());
        if (options.status && options.status !== "ALL") params.append("status", options.status);
        if (options.lawyer && options.lawyer !== "ALL") params.append("lawyer", options.lawyer);
        if (options.q) params.append("q", options.q);
        if (options.exact) params.append("exact", "true");

        const queryString = params.toString() ? `?${params.toString()}` : "";
        const response = await authenticatedRequest(`/api/cases${queryString}`, "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return [];
    }, [authenticatedRequest]);

    const getCaseStats = useCallback(async () => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases/stats", "GET");
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json();
        }
        return { total: 0, active: 0, closed: 0, appeal: 0, statuses: {} };
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

    const searchCases = useCallback(async (query: string, exact: boolean = false) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/search?q=${encodeURIComponent(query)}&exact=${exact}`, "GET");
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
        getCaseStats,
        getCase,
        searchCases,
        getClientCaseSequence,
        isLoading
    };
};
