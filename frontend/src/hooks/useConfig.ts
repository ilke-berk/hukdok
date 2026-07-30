import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface ConfigItem {
    id?: number;
    code?: string;
    name: string;
    email?: string;
    description?: string;
    parent_code?: string;
    role_type?: string;
    tc_no?: string;
    sicil_no?: string;
    gorev?: string;
    phone?: string;
    address?: string;
    city?: string;
}

/** Bir liste öğesinin adını taşıyan bağlı kayıtların dökümü (silme onayı için). */
export interface ListUsage {
    name: string;
    total: number;
    items: { label: string; count: number; clearable: boolean }[];
    clearable: boolean;   // false → bağlı alan zorunlu, boşaltılamaz; yalnızca taşınabilir
}

/** Silmede bağlı kayıtlara ne olacağı. */
export type DeleteMode = "block" | "clear" | "reassign" | "keep";

const EMPTY: ConfigItem[] = [];

const CONFIG_KEYS = {
    lawyers: ["config", "lawyers"],
    statuses: ["config", "statuses"],
    doctypes: ["config", "doctypes"],
    emailRecipients: ["config", "email_recipients"],
    caseSubjects: ["config", "case_subjects"],
    fileTypes: ["config", "file_types"],
    courtTypes: ["config", "court_types"],
    partyRoles: ["config", "party_roles"],
    bureauTypes: ["config", "bureau_types"],
    cities: ["config", "cities"],
    specialties: ["config", "specialties"],
    clientCategories: ["config", "client_categories"],
    fileStatuses: ["config", "file_statuses"],
} as const;

export const useConfig = () => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();
    const queryClient = useQueryClient();
    const enabled = accounts.length > 0;

    const fetchJson = async (url: string): Promise<ConfigItem[]> => {
        const res = await authRequest(url, "GET");
        if (!res?.ok) return [];
        return res.json();
    };

    // Backend'in mesajını (örn. 409 "… zaten listede mevcut") çağırana taşıyarak yanıtı döner
    const request = async <T,>(url: string, method: string, body?: unknown, fallback = "İşlem başarısız"): Promise<T> => {
        const res = await authRequest(url, method, body);
        if (!res?.ok) {
            let detail = fallback;
            try {
                const data = await res?.json();
                if (typeof data?.detail === "string") detail = data.detail;
            } catch { /* gövde JSON değilse generic mesaj kalır */ }
            throw new Error(detail);
        }
        return res.json().catch(() => ({} as T));
    };

    const mutate = async (url: string, method: string, body?: unknown): Promise<boolean> => {
        await request(url, method, body);
        return true;
    };

    const invalidate = (...keys: (typeof CONFIG_KEYS)[keyof typeof CONFIG_KEYS][]) =>
        Promise.all(keys.map((k) => queryClient.invalidateQueries({ queryKey: k })));

    const STALE_TIME = 5 * 60 * 1000;

    // --- QUERIES ---
    const lawyersQ = useQuery({ queryKey: CONFIG_KEYS.lawyers, queryFn: () => fetchJson("/api/config/lawyers"), enabled, staleTime: STALE_TIME });
    const statusesQ = useQuery({ queryKey: CONFIG_KEYS.statuses, queryFn: () => fetchJson("/api/config/statuses"), enabled, staleTime: STALE_TIME });
    const doctypesQ = useQuery({ queryKey: CONFIG_KEYS.doctypes, queryFn: () => fetchJson("/api/config/doctypes"), enabled, staleTime: STALE_TIME });
    const emailRecipientsQ = useQuery({ queryKey: CONFIG_KEYS.emailRecipients, queryFn: () => fetchJson("/api/config/email_recipients"), enabled, staleTime: STALE_TIME });
    const caseSubjectsQ = useQuery({ queryKey: CONFIG_KEYS.caseSubjects, queryFn: () => fetchJson("/api/config/case_subjects"), enabled, staleTime: STALE_TIME });
    const fileTypesQ = useQuery({ queryKey: CONFIG_KEYS.fileTypes, queryFn: () => fetchJson("/api/config/file_types"), enabled, staleTime: STALE_TIME });
    const courtTypesQ = useQuery({ queryKey: CONFIG_KEYS.courtTypes, queryFn: () => fetchJson("/api/config/court_types"), enabled, staleTime: STALE_TIME });
    const partyRolesQ = useQuery({ queryKey: CONFIG_KEYS.partyRoles, queryFn: () => fetchJson("/api/config/party_roles"), enabled, staleTime: STALE_TIME });
    const bureauTypesQ = useQuery({ queryKey: CONFIG_KEYS.bureauTypes, queryFn: () => fetchJson("/api/config/bureau_types"), enabled, staleTime: STALE_TIME });
    const citiesQ = useQuery({ queryKey: CONFIG_KEYS.cities, queryFn: () => fetchJson("/api/config/cities"), enabled, staleTime: STALE_TIME });
    const specialtiesQ = useQuery({ queryKey: CONFIG_KEYS.specialties, queryFn: () => fetchJson("/api/config/specialties"), enabled, staleTime: STALE_TIME });
    const clientCategoriesQ = useQuery({ queryKey: CONFIG_KEYS.clientCategories, queryFn: () => fetchJson("/api/config/client_categories"), enabled, staleTime: STALE_TIME });
    const fileStatusesQ = useQuery({ queryKey: CONFIG_KEYS.fileStatuses, queryFn: () => fetchJson("/api/config/file_statuses"), enabled, staleTime: STALE_TIME });

    const isLoading =
        lawyersQ.isLoading || statusesQ.isLoading || doctypesQ.isLoading ||
        emailRecipientsQ.isLoading || caseSubjectsQ.isLoading ||
        fileTypesQ.isLoading || courtTypesQ.isLoading || partyRolesQ.isLoading ||
        bureauTypesQ.isLoading || citiesQ.isLoading || specialtiesQ.isLoading ||
        clientCategoriesQ.isLoading || fileStatusesQ.isLoading;

    const typeToKey: Record<string, (typeof CONFIG_KEYS)[keyof typeof CONFIG_KEYS]> = {
        lawyers: CONFIG_KEYS.lawyers,
        statuses: CONFIG_KEYS.statuses,
        doctypes: CONFIG_KEYS.doctypes,
        email_recipients: CONFIG_KEYS.emailRecipients,
        case_subjects: CONFIG_KEYS.caseSubjects,
        file_types: CONFIG_KEYS.fileTypes,
        court_types: CONFIG_KEYS.courtTypes,
        party_roles: CONFIG_KEYS.partyRoles,
        bureau_types: CONFIG_KEYS.bureauTypes,
        cities: CONFIG_KEYS.cities,
        specialties: CONFIG_KEYS.specialties,
        client_categories: CONFIG_KEYS.clientCategories,
        file_statuses: CONFIG_KEYS.fileStatuses,
    };

    const invalidateType = (type: string) => {
        const key = typeToKey[type];
        // Dava türü adı mahkeme türlerinin parent_code'unda da geçer
        const extra = type === "file_types" ? [CONFIG_KEYS.courtTypes] : [];
        return key ? invalidate(key, ...extra) : undefined;
    };

    // --- MUTATIONS ---
    const addLawyerM = useMutation({ mutationFn: ({ code, name, tc_no, sicil_no, gorev, email, phone, address, city }: { code: string; name: string; tc_no?: string; sicil_no?: string; gorev?: string; email?: string; phone?: string; address?: string; city?: string }) => mutate("/api/config/lawyers", "POST", { code, name, tc_no, sicil_no, gorev, email, phone, address, city }), onSuccess: () => invalidate(CONFIG_KEYS.lawyers) });
    const addStatusM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/statuses", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.statuses) });
    const addDoctypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/doctypes", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.doctypes) });
    const addEmailM = useMutation({ mutationFn: ({ name, email, description }: { name: string; email: string; description: string }) => mutate("/api/config/email_recipients", "POST", { name, email, description }), onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients) });

    const addCaseSubjectM = useMutation({
        mutationFn: (name: string) => {
            const code = name.replace(/\s+/g, "").substring(0, 4).toUpperCase() + Math.random().toString(36).substring(2, 6).toUpperCase();
            return mutate("/api/config/case_subjects", "POST", { code, name });
        },
        onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects),
    });

    const addFileTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/file_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.fileTypes) });
    const addCourtTypeM = useMutation({ mutationFn: ({ code, name, parent_code }: { code: string; name: string; parent_code: string }) => mutate("/api/config/court_types", "POST", { code, name, parent_code }), onSuccess: () => invalidate(CONFIG_KEYS.courtTypes) });
    const addPartyRoleM = useMutation({ mutationFn: ({ code, name, role_type }: { code: string; name: string; role_type: string }) => mutate("/api/config/party_roles", "POST", { code, name, role_type }), onSuccess: () => invalidate(CONFIG_KEYS.partyRoles) });
    const addBureauTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/bureau_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.bureauTypes) });
    const addCityM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/cities", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.cities) });
    const addSpecialtyM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/specialties", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.specialties) });
    const addClientCategoryM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/client_categories", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.clientCategories) });
    const addFileStatusM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/file_statuses", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.fileStatuses) });

    // Ortak düzenleme — ad değiştiyse backend eski adı taşıyan dava/müvekkil/belge
    // kayıtlarına yayar; dönen sayı kaç kaydın yansıdığıdır.
    const updateItemM = useMutation({
        mutationFn: ({ type, code, fields }: { type: string; code: string; fields: Record<string, string | undefined> }) =>
            request<{ updated?: number }>("/api/config/update", "POST", { type, code, fields }, "Güncelleme başarısız")
                .then(d => d.updated ?? 0),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    // Ortak silme — mode bağlı kayıtlara ne olacağını belirler (boşalt / taşı / dokunma)
    const deleteItemM = useMutation({
        mutationFn: ({ type, code, mode, targetCode }: { type: string; code: string; mode: DeleteMode; targetCode?: string }) =>
            request<{ affected?: number }>("/api/config/delete", "POST", { type, code, mode, target_code: targetCode }, "Silme başarısız")
                .then(d => d.affected ?? 0),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    const reorderListM = useMutation({
        mutationFn: ({ type, orderedIds }: { type: string; orderedIds: string[] }) =>
            mutate("/api/config/reorder", "POST", { type, ordered_ids: orderedIds }),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    // Derived: court types grouped by parent
    const courtTypesByParent = (courtTypesQ.data ?? EMPTY).reduce<Record<string, ConfigItem[]>>((acc, item) => {
        const parent = item.parent_code ?? "";
        if (!acc[parent]) acc[parent] = [];
        acc[parent].push(item);
        return acc;
    }, {});

    // Derived: party roles split by type
    const mainPartyRoles = (partyRolesQ.data ?? EMPTY).filter(r => r.role_type === "MAIN");
    const thirdPartyRoles = (partyRolesQ.data ?? EMPTY).filter(r => r.role_type === "THIRD");

    return {
        lawyers: lawyersQ.data ?? EMPTY,
        statuses: statusesQ.data ?? EMPTY,
        doctypes: doctypesQ.data ?? EMPTY,
        emailRecipients: emailRecipientsQ.data ?? EMPTY,
        caseSubjects: caseSubjectsQ.data ?? EMPTY,
        fileTypes: fileTypesQ.data ?? EMPTY,
        courtTypes: courtTypesQ.data ?? EMPTY,
        courtTypesByParent,
        partyRoles: partyRolesQ.data ?? EMPTY,
        mainPartyRoles,
        thirdPartyRoles,
        bureauTypes: bureauTypesQ.data ?? EMPTY,
        cities: citiesQ.data ?? EMPTY,
        specialties: specialtiesQ.data ?? EMPTY,
        clientCategories: clientCategoriesQ.data ?? EMPTY,
        fileStatuses: fileStatusesQ.data ?? EMPTY,
        isLoading,

        addLawyer: (code: string, name: string, tc_no?: string, sicil_no?: string, gorev?: string, email?: string, phone?: string, address?: string, city?: string) => addLawyerM.mutateAsync({ code, name, tc_no, sicil_no, gorev, email, phone, address, city }),
        addStatus: (code: string, name: string) => addStatusM.mutateAsync({ code, name }),
        addDoctype: (code: string, name: string) => addDoctypeM.mutateAsync({ code, name }),
        addEmail: (name: string, email: string, description: string) => addEmailM.mutateAsync({ name, email, description }),
        addCaseSubject: (name: string) => addCaseSubjectM.mutateAsync(name),
        addFileType: (code: string, name: string) => addFileTypeM.mutateAsync({ code, name }),
        addCourtType: (code: string, name: string, parent_code: string) => addCourtTypeM.mutateAsync({ code, name, parent_code }),
        addPartyRole: (code: string, name: string, role_type: string) => addPartyRoleM.mutateAsync({ code, name, role_type }),
        addBureauType: (code: string, name: string) => addBureauTypeM.mutateAsync({ code, name }),
        addCity: (code: string, name: string) => addCityM.mutateAsync({ code, name }),
        addSpecialty: (code: string, name: string) => addSpecialtyM.mutateAsync({ code, name }),
        addClientCategory: (code: string, name: string) => addClientCategoryM.mutateAsync({ code, name }),
        addFileStatus: (code: string, name: string) => addFileStatusM.mutateAsync({ code, name }),

        reorderList: (type: string, orderedIds: string[]) => reorderListM.mutateAsync({ type, orderedIds }),

        /** Liste öğesini düzenler; yansıyan bağlı kayıt sayısını döner. */
        updateItem: (type: string, code: string, fields: Record<string, string | undefined>) => updateItemM.mutateAsync({ type, code, fields }),
        /** Öğenin adını taşıyan bağlı kayıtların dökümü — silme onayı öncesi. */
        fetchUsage: (type: string, code: string) =>
            request<ListUsage>(`/api/config/usage?type=${encodeURIComponent(type)}&code=${encodeURIComponent(code)}`, "GET", undefined, "Kullanım bilgisi alınamadı"),
        /** Liste öğesini siler; etkilenen bağlı kayıt sayısını döner. */
        deleteItem: (type: string, code: string, mode: DeleteMode, targetCode?: string) => deleteItemM.mutateAsync({ type, code, mode, targetCode }),
    };
};
