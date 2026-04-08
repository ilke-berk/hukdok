import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface ConfigItem {
    id?: number;
    code?: string;
    name: string;
    email?: string;
    description?: string;
}

const CONFIG_KEYS = {
    lawyers: ["config", "lawyers"],
    statuses: ["config", "statuses"],
    doctypes: ["config", "doctypes"],
    emailRecipients: ["config", "email_recipients"],
    caseSubjects: ["config", "case_subjects"],
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

    const STALE_TIME = 5 * 60 * 1000; // 5 dakika — config verisi sık değişmez

    // --- QUERIES ---
    const lawyersQ = useQuery({ queryKey: CONFIG_KEYS.lawyers, queryFn: () => fetchJson("/api/config/lawyers"), enabled, staleTime: STALE_TIME });
    const statusesQ = useQuery({ queryKey: CONFIG_KEYS.statuses, queryFn: () => fetchJson("/api/config/statuses"), enabled, staleTime: STALE_TIME });
    const doctypesQ = useQuery({ queryKey: CONFIG_KEYS.doctypes, queryFn: () => fetchJson("/api/config/doctypes"), enabled, staleTime: STALE_TIME });
    const emailRecipientsQ = useQuery({ queryKey: CONFIG_KEYS.emailRecipients, queryFn: () => fetchJson("/api/config/email_recipients"), enabled, staleTime: STALE_TIME });
    const caseSubjectsQ = useQuery({ queryKey: CONFIG_KEYS.caseSubjects, queryFn: () => fetchJson("/api/config/case_subjects"), enabled, staleTime: STALE_TIME });

    const isLoading =
        lawyersQ.isLoading ||
        statusesQ.isLoading ||
        doctypesQ.isLoading ||
        emailRecipientsQ.isLoading ||
        caseSubjectsQ.isLoading;

    // --- MUTATIONS ---
    const addLawyerM = useMutation({
        mutationFn: ({ code, name }: { code: string; name: string }) =>
            mutate("/api/config/lawyers", "POST", { code, name }),
        onSuccess: () => invalidate(CONFIG_KEYS.lawyers),
    });
    const deleteLawyerM = useMutation({
        mutationFn: (code: string) => mutate(`/api/config/lawyers/${code}`, "DELETE"),
        onSuccess: () => invalidate(CONFIG_KEYS.lawyers),
    });

    const addStatusM = useMutation({
        mutationFn: ({ code, name }: { code: string; name: string }) =>
            mutate("/api/config/statuses", "POST", { code, name }),
        onSuccess: () => invalidate(CONFIG_KEYS.statuses),
    });
    const deleteStatusM = useMutation({
        mutationFn: (code: string) => mutate(`/api/config/statuses/${code}`, "DELETE"),
        onSuccess: () => invalidate(CONFIG_KEYS.statuses),
    });

    const addDoctypeM = useMutation({
        mutationFn: ({ code, name }: { code: string; name: string }) =>
            mutate("/api/config/doctypes", "POST", { code, name }),
        onSuccess: () => invalidate(CONFIG_KEYS.doctypes),
    });
    const deleteDoctypeM = useMutation({
        mutationFn: (code: string) => mutate(`/api/config/doctypes/${code}`, "DELETE"),
        onSuccess: () => invalidate(CONFIG_KEYS.doctypes),
    });

    const addEmailM = useMutation({
        mutationFn: ({ name, email, description }: { name: string; email: string; description: string }) =>
            mutate("/api/config/email_recipients", "POST", { name, email, description }),
        onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients),
    });
    const deleteEmailM = useMutation({
        mutationFn: (email: string) => mutate("/api/config/email_recipients", "DELETE", { email }),
        onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients),
    });

    const addCaseSubjectM = useMutation({
        mutationFn: (name: string) => {
            const generatedCode =
                name.replace(/\s+/g, "").substring(0, 4).toUpperCase() +
                Math.random().toString(36).substring(2, 6).toUpperCase();
            return mutate("/api/config/case_subjects", "POST", { code: generatedCode, name });
        },
        onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects),
    });
    const deleteCaseSubjectM = useMutation({
        mutationFn: (code: string) => mutate(`/api/config/case_subjects/${code}`, "DELETE"),
        onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects),
    });

    const typeToKey: Record<string, (typeof CONFIG_KEYS)[keyof typeof CONFIG_KEYS]> = {
        lawyers: CONFIG_KEYS.lawyers,
        statuses: CONFIG_KEYS.statuses,
        doctypes: CONFIG_KEYS.doctypes,
        email_recipients: CONFIG_KEYS.emailRecipients,
        case_subjects: CONFIG_KEYS.caseSubjects,
    };

    const reorderListM = useMutation({
        mutationFn: ({ type, orderedIds }: { type: string; orderedIds: string[] }) =>
            mutate("/api/config/reorder", "POST", { type, ordered_ids: orderedIds }),
        onSuccess: (_data, { type }) => {
            const key = typeToKey[type];
            if (key) return invalidate(key);
        },
    });

    // --- STABLE ACTION WRAPPERS (same interface as before) ---
    const addLawyer = (code: string, name: string) => addLawyerM.mutateAsync({ code, name });
    const deleteLawyer = (code: string) => deleteLawyerM.mutateAsync(code);

    const addStatus = (code: string, name: string) => addStatusM.mutateAsync({ code, name });
    const deleteStatus = (code: string) => deleteStatusM.mutateAsync(code);

    const addDoctype = (code: string, name: string) => addDoctypeM.mutateAsync({ code, name });
    const deleteDoctype = (code: string) => deleteDoctypeM.mutateAsync(code);

    const addEmail = (name: string, email: string, description: string) =>
        addEmailM.mutateAsync({ name, email, description });
    const deleteEmail = (email: string) => deleteEmailM.mutateAsync(email);

    const addCaseSubject = (name: string) => addCaseSubjectM.mutateAsync(name);
    const deleteCaseSubject = (code: string) => deleteCaseSubjectM.mutateAsync(code);

    const reorderList = (type: string, orderedIds: string[]) => reorderListM.mutateAsync({ type, orderedIds });

    return {
        lawyers: lawyersQ.data ?? [],
        statuses: statusesQ.data ?? [],
        doctypes: doctypesQ.data ?? [],
        emailRecipients: emailRecipientsQ.data ?? [],
        caseSubjects: caseSubjectsQ.data ?? [],
        isLoading,
        addLawyer, deleteLawyer,
        addStatus, deleteStatus,
        addDoctype, deleteDoctype,
        addEmail, deleteEmail,
        addCaseSubject, deleteCaseSubject,
        reorderList,
    };
};
