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

export interface CaseTrackingUpdate {
    case_stage?: string | null;
    dosya_son_durumu?: string | null;
    // Yerel Karar
    karar_tarihi?: string | null;
    karar_turu?: string | null;
    karar_lehine?: string | null;
    karar_no?: string | null;
    karar_teblig_tarihi?: string | null;
    karar_aciklama?: string | null;
    // İstinaf
    istinaf_basvuru_tarihi?: string | null;
    istinaf_karar_durumu?: string | null;
    istinaf_karar_tarihi?: string | null;
    istinaf_mahkemesi?: string | null;
    istinaf_esas_no?: string | null;
    istinaf_karar_no?: string | null;
    istinaf_karar_aciklama?: string | null;
    istinaf_teblig_tarihi?: string | null;
    // Temyiz
    temyiz_basvuru_tarihi?: string | null;
    temyiz_karar_durumu?: string | null;
    temyiz_karar_tarihi?: string | null;
    temyiz_mahkemesi?: string | null;
    temyiz_esas_no?: string | null;
    temyiz_karar_no?: string | null;
    temyiz_eden_durumu?: string | null;
    temyiz_karar_aciklama?: string | null;
    temyiz_teblig_tarihi?: string | null;
    // Karar Düzeltme
    karar_duzeltme_durumu?: string | null;
    karar_duzeltme_esas_no?: string | null;
    karar_duzeltme_karar_no?: string | null;
    karar_duzeltme_tarihi?: string | null;
    karar_duzeltme_teblig_tarihi?: string | null;
    karar_duzeltme_aciklama?: string | null;
    yeni_esas_no?: string | null;
    // Kesinleşme / İnfaz
    kesinlesme_tarihi?: string | null;
    infaz_tarihi?: string | null;
    note?: string | null;
}

export interface CaseStageLogEntry {
    id: number;
    case_id: number;
    stage: string;
    changed_at: string;
    changed_by?: string | null;
    source?: string | null;
    note?: string | null;
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

    const searchCases = useCallback(async (query: string, exact: boolean = false, activeOnly: boolean = false) => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/search?q=${encodeURIComponent(query)}&exact=${exact}&active_only=${activeOnly}`, "GET");
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

    // --- İlişkili Davalar (case_relations tabanlı) ---

    /** Bir davanın manuel + otomatik ilişkili davalarını getirir. */
    const getRelatedCases = useCallback(async (caseId: number) => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/relations`, "GET");
        if (response && response.ok) return await response.json();
        return { manual: [], automatic: [] };
    }, [authenticatedRequest]);

    /** Manuel bağlantı ekle */
    const addCaseRelation = useCallback(async (caseId: number, data: { target_case_id: number; relation_type: string; note?: string | null }) => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/relations`, "POST", data);
        if (response && response.ok) return await response.json();
        return null;
    }, [authenticatedRequest]);

    /** Manuel bağlantıyı sil */
    const removeCaseRelation = useCallback(async (caseId: number, relationId: number) => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/relations/${relationId}`, "DELETE");
        return !!(response && response.ok);
    }, [authenticatedRequest]);

    // --- Dava Takip ---

    const updateCaseTracking = useCallback(async (caseId: number, data: CaseTrackingUpdate) => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/tracking`, "PATCH", data);
        return !!(response && response.ok);
    }, [authenticatedRequest]);

    const getCaseStageLog = useCallback(async (caseId: number): Promise<CaseStageLogEntry[]> => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/stage-log`, "GET");
        if (response && response.ok) return await response.json();
        return [];
    }, [authenticatedRequest]);

    // --- Dava Grubu (CaseGroup sayfası için) ---

    /** Bir dava grubunu tüm ilişkili davalarıyla getirir */
    const getCaseGroup = useCallback(async (groupId: number) => {
        const response = await authenticatedRequest(`/api/case-groups/${groupId}`, "GET");
        if (response && response.ok) return await response.json();
        return null;
    }, [authenticatedRequest]);

    /** Bir dava ID'sine ait grubu getirir */
    const getCaseGroupByCase = useCallback(async (caseId: number) => {
        const response = await authenticatedRequest(`/api/cases/${caseId}/group`, "GET");
        if (response && response.ok) return await response.json();
        return null;
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
        // İlişkili davalar
        getRelatedCases,
        addCaseRelation,
        removeCaseRelation,
        // Dava takip
        updateCaseTracking,
        getCaseStageLog,
        // Dava grubu sayfası
        getCaseGroup,
        getCaseGroupByCase,
        isLoading
    };
};
