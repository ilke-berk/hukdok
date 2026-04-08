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
}

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

    const mutate = async (url: string, method: string, body?: unknown): Promise<boolean> => {
        const res = await authRequest(url, method, body);
        return res ? res.ok : false;
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

    const isLoading =
        lawyersQ.isLoading || statusesQ.isLoading || doctypesQ.isLoading ||
        emailRecipientsQ.isLoading || caseSubjectsQ.isLoading ||
        fileTypesQ.isLoading || courtTypesQ.isLoading || partyRolesQ.isLoading ||
        bureauTypesQ.isLoading || citiesQ.isLoading || specialtiesQ.isLoading ||
        clientCategoriesQ.isLoading;

    // --- MUTATIONS ---
    const addLawyerM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/lawyers", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.lawyers) });
    const deleteLawyerM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/lawyers/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.lawyers) });

    const addStatusM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/statuses", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.statuses) });
    const deleteStatusM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/statuses/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.statuses) });

    const addDoctypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/doctypes", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.doctypes) });
    const deleteDoctypeM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/doctypes/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.doctypes) });

    const addEmailM = useMutation({ mutationFn: ({ name, email, description }: { name: string; email: string; description: string }) => mutate("/api/config/email_recipients", "POST", { name, email, description }), onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients) });
    const deleteEmailM = useMutation({ mutationFn: (email: string) => mutate("/api/config/email_recipients", "DELETE", { email }), onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients) });

    const addCaseSubjectM = useMutation({
        mutationFn: (name: string) => {
            const code = name.replace(/\s+/g, "").substring(0, 4).toUpperCase() + Math.random().toString(36).substring(2, 6).toUpperCase();
            return mutate("/api/config/case_subjects", "POST", { code, name });
        },
        onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects),
    });
    const deleteCaseSubjectM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/case_subjects/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects) });

    const addFileTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/file_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.fileTypes) });
    const deleteFileTypeM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/file_types/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.fileTypes) });

    const addCourtTypeM = useMutation({ mutationFn: ({ code, name, parent_code }: { code: string; name: string; parent_code: string }) => mutate("/api/config/court_types", "POST", { code, name, parent_code }), onSuccess: () => invalidate(CONFIG_KEYS.courtTypes) });
    const deleteCourtTypeM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/court_types/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.courtTypes) });

    const addPartyRoleM = useMutation({ mutationFn: ({ code, name, role_type }: { code: string; name: string; role_type: string }) => mutate("/api/config/party_roles", "POST", { code, name, role_type }), onSuccess: () => invalidate(CONFIG_KEYS.partyRoles) });
    const deletePartyRoleM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/party_roles/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.partyRoles) });

    const addBureauTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/bureau_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.bureauTypes) });
    const deleteBureauTypeM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/bureau_types/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.bureauTypes) });

    const addCityM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/cities", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.cities) });
    const deleteCityM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/cities/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.cities) });

    const addSpecialtyM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/specialties", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.specialties) });
    const deleteSpecialtyM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/specialties/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.specialties) });

    const addClientCategoryM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/client_categories", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.clientCategories) });
    const deleteClientCategoryM = useMutation({ mutationFn: (code: string) => mutate(`/api/config/client_categories/${code}`, "DELETE"), onSuccess: () => invalidate(CONFIG_KEYS.clientCategories) });

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
    };

    const reorderListM = useMutation({
        mutationFn: ({ type, orderedIds }: { type: string; orderedIds: string[] }) =>
            mutate("/api/config/reorder", "POST", { type, ordered_ids: orderedIds }),
        onSuccess: (_data, { type }) => {
            const key = typeToKey[type];
            if (key) return invalidate(key);
        },
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
        isLoading,

        addLawyer: (code: string, name: string) => addLawyerM.mutateAsync({ code, name }),
        deleteLawyer: (code: string) => deleteLawyerM.mutateAsync(code),

        addStatus: (code: string, name: string) => addStatusM.mutateAsync({ code, name }),
        deleteStatus: (code: string) => deleteStatusM.mutateAsync(code),

        addDoctype: (code: string, name: string) => addDoctypeM.mutateAsync({ code, name }),
        deleteDoctype: (code: string) => deleteDoctypeM.mutateAsync(code),

        addEmail: (name: string, email: string, description: string) => addEmailM.mutateAsync({ name, email, description }),
        deleteEmail: (email: string) => deleteEmailM.mutateAsync(email),

        addCaseSubject: (name: string) => addCaseSubjectM.mutateAsync(name),
        deleteCaseSubject: (code: string) => deleteCaseSubjectM.mutateAsync(code),

        addFileType: (code: string, name: string) => addFileTypeM.mutateAsync({ code, name }),
        deleteFileType: (code: string) => deleteFileTypeM.mutateAsync(code),

        addCourtType: (code: string, name: string, parent_code: string) => addCourtTypeM.mutateAsync({ code, name, parent_code }),
        deleteCourtType: (code: string) => deleteCourtTypeM.mutateAsync(code),

        addPartyRole: (code: string, name: string, role_type: string) => addPartyRoleM.mutateAsync({ code, name, role_type }),
        deletePartyRole: (code: string) => deletePartyRoleM.mutateAsync(code),

        addBureauType: (code: string, name: string) => addBureauTypeM.mutateAsync({ code, name }),
        deleteBureauType: (code: string) => deleteBureauTypeM.mutateAsync(code),

        addCity: (code: string, name: string) => addCityM.mutateAsync({ code, name }),
        deleteCity: (code: string) => deleteCityM.mutateAsync(code),

        addSpecialty: (code: string, name: string) => addSpecialtyM.mutateAsync({ code, name }),
        deleteSpecialty: (code: string) => deleteSpecialtyM.mutateAsync(code),

        addClientCategory: (code: string, name: string) => addClientCategoryM.mutateAsync({ code, name }),
        deleteClientCategory: (code: string) => deleteClientCategoryM.mutateAsync(code),

        reorderList: (type: string, orderedIds: string[]) => reorderListM.mutateAsync({ type, orderedIds }),
    };
};
