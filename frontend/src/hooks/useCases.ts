import { useState, useCallback } from "react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface CasePartyData {
    client_id?: number | null;
    name: string;
    role: string;
    party_type: "CLIENT" | "COUNTER" | "THIRD";
    birth_year?: number;
    gender?: string;
    tc_no?: string;
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

/** check-duplicate yanıt satırı */
export interface DuplicateCaseMatch {
    id: number;
    tracking_no: string;
    esas_no: string;
    court?: string | null;
    status: string;
    court_match: boolean;
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
    // Hükmedilen tutarlar — normalizeMoney sonrası düz sayı string'i gider,
    // backend Pydantic float'a coerce eder
    hukmedilen_maddi?: string | null;
    hukmedilen_manevi?: string | null;
    hukmedilen_toplam?: string | null;
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

/**
 * G002: Liste ve sıra numarası uçlarında "hata ≠ boş veri". Bu mesajlar
 * kullanıcıya banner/toast olarak aynen gösterilir.
 */
export const CASE_LIST_ERROR = "Dava listesi alınamadı — sunucuya ulaşılamadı.";
export const CASE_SEQUENCE_ERROR =
    "Ofis numarası alınamadı — sunucuya ulaşılamadı. Kaydetmeden önce tekrar deneyin.";

export const useCases = () => {
    const { authRequest } = useAuthRequest();
    const [isLoading, setIsLoading] = useState(false);

    const authenticatedRequest = authRequest;

    // Hata gövdesindeki `detail` mesajını okur (ör. 409 ofis no çakışması)
    const readErrorDetail = async (response: Response | null): Promise<string | undefined> => {
        if (!response) return undefined;
        try {
            const data = await response.json();
            return typeof data?.detail === "string" ? data.detail : undefined;
        } catch {
            return undefined;
        }
    };

    const saveCase = useCallback(async (data: CaseData): Promise<{ ok: boolean; error?: string }> => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "POST", data);
        setIsLoading(false);
        if (response && response.ok) return { ok: true };
        return { ok: false, error: await readErrorDetail(response) };
    }, [authenticatedRequest]);

    const getCases = useCallback(async <T = Record<string, unknown>>(options: {
        limit?: number;
        offset?: number;
        status?: string;
        lawyer?: string;
        q?: string;
        exact?: boolean;
        fileType?: string;
        urgentDays?: number;
        missingRequired?: boolean;
    } = {}): Promise<{ cases: T[]; total: number }> => {
        setIsLoading(true);
        const params = new URLSearchParams();
        if (options.limit !== undefined) params.append("limit", options.limit.toString());
        if (options.offset !== undefined) params.append("offset", options.offset.toString());
        if (options.status && options.status !== "ALL") params.append("status", options.status);
        if (options.lawyer && options.lawyer !== "ALL") params.append("lawyer", options.lawyer);
        if (options.q) params.append("q", options.q);
        if (options.exact) params.append("exact", "true");
        if (options.fileType && options.fileType !== "ALL") params.append("file_type", options.fileType);
        if (options.urgentDays !== undefined) params.append("urgent_days", String(options.urgentDays));
        if (options.missingRequired) params.append("missing_required", "true");

        const queryString = params.toString() ? `?${params.toString()}` : "";
        const response = await authenticatedRequest(`/api/cases${queryString}`, "GET");
        setIsLoading(false);
        // G002: eskiden hata da `{cases: [], total: 0}` dönüyordu — kullanıcı
        // kesintide "dosya bulunamadı" görüp veri kaybı sanıyordu. Artık fırlatılır;
        // çağıran sayfa hata şeridini "kayıt yok" görünümünün yerine gösterir.
        if (!response || !response.ok) throw new Error(CASE_LIST_ERROR);
        const data = await response.json();
        const cases: T[] = Array.isArray(data) ? data : [];
        // Toplam sayı header'da; eski backend'e karşı fallback: offset + sayfa boyu
        const parsed = parseInt(response.headers.get("X-Total-Count") ?? "", 10);
        const total = Number.isFinite(parsed) ? parsed : (options.offset ?? 0) + cases.length;
        return { cases, total };
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

    /** Mükerrer dava kontrolü — aynı esas no'lu aktif kayıtlar (normalize eşleşme). */
    const checkDuplicateCase = useCallback(async (esasNo: string, court?: string): Promise<DuplicateCaseMatch[]> => {
        if (!esasNo.trim()) return [];
        const params = new URLSearchParams({ esas_no: esasNo.trim() });
        if (court?.trim()) params.append("court", court.trim());
        const response = await authenticatedRequest(`/api/cases/check-duplicate?${params.toString()}`, "GET");
        if (response && response.ok) {
            const data = await response.json();
            return data.matches ?? [];
        }
        return [];
    }, [authenticatedRequest]);

    const updateCase = useCallback(async (id: number, data: CaseData): Promise<{ ok: boolean; error?: string }> => {
        setIsLoading(true);
        const response = await authenticatedRequest(`/api/cases/${id}`, "PUT", data);
        setIsLoading(false);
        if (response && response.ok) return { ok: true };
        return { ok: false, error: await readErrorDetail(response) };
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

    /**
     * G002: Hata YUTMAZ. Eski sessiz `1` fallback'i kesintide sıfırdan sıra
     * numarası üretiyor, dolu bir ofis numarası öneriyor ve kaydı 409'a
     * düşürüyordu. Artık fırlatır — çağıran kaydetmeyi bloke eder.
     */
    const getClientCaseSequence = useCallback(async (clientName: string, nameBlock?: string): Promise<number> => {
        const params = new URLSearchParams({ client_name: clientName });
        if (nameBlock) params.append("name_block", nameBlock);
        const response = await authenticatedRequest(`/api/cases/client-sequence?${params.toString()}`, "GET");
        if (!response || !response.ok) throw new Error(CASE_SEQUENCE_ERROR);
        let sequence: unknown;
        try {
            sequence = (await response.json())?.sequence;
        } catch {
            throw new Error(CASE_SEQUENCE_ERROR);
        }
        const parsed = Number(sequence);
        if (!Number.isFinite(parsed) || parsed < 1) throw new Error(CASE_SEQUENCE_ERROR);
        return parsed;
    }, [authenticatedRequest]);

    const saveCaseAndReturn = useCallback(async (data: CaseData) => {
        setIsLoading(true);
        const response = await authenticatedRequest("/api/cases", "POST", data);
        setIsLoading(false);
        if (response && response.ok) {
            return await response.json(); // { id, tracking_no, ... }
        }
        return { error: (await readErrorDetail(response)) || "Sunucu hatası" };
    }, [authenticatedRequest]);

    /** Soft-delete: gerekçe zorunlu; kayıt arşive taşınır, admin geri alabilir. */
    const deleteCase = useCallback(async (id: number, reason: string) => {
        setIsLoading(true);
        const response = await authenticatedRequest(
            `/api/cases/${id}?reason=${encodeURIComponent(reason)}`, "DELETE"
        );
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

    // --- Belge Bağlama ---

    /** link_mode'a göre belgeleri getirir (ör. bağlantısız belgeler için "UNLINKED"). */
    const getDocuments = useCallback(async (linkMode?: string, limit = 100) => {
        const params = new URLSearchParams({ limit: String(limit) });
        if (linkMode) params.set("link_mode", linkMode);
        const response = await authenticatedRequest(`/api/documents?${params.toString()}`, "GET");
        if (response && response.ok) return await response.json();
        return [];
    }, [authenticatedRequest]);

    /** Bağlantısız bir belgeyi bir davaya bağlar. */
    const linkDocument = useCallback(async (docId: number, caseId: number) => {
        const response = await authenticatedRequest(`/api/documents/${docId}/link`, "PATCH", { case_id: caseId });
        return !!(response && response.ok);
    }, [authenticatedRequest]);

    return {
        saveCase,
        saveCaseAndReturn,
        checkDuplicateCase,
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
        // Belge bağlama
        getDocuments,
        linkDocument,
        isLoading
    };
};
