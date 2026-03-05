import { useState, useEffect } from "react";
import { getApiUrl } from "@/lib/api";
import { useMsal } from "@azure/msal-react";
import { InteractionRequiredAuthError } from "@azure/msal-browser";

export interface ConfigItem {
    id?: number;
    code?: string;
    name: string;
    email?: string;
    description?: string;
}

export const useConfig = () => {
    const { instance, accounts } = useMsal();
    const [lawyers, setLawyers] = useState<ConfigItem[]>([]);
    const [statuses, setStatuses] = useState<ConfigItem[]>([]);
    const [doctypes, setDoctypes] = useState<ConfigItem[]>([]);
    const [emailRecipients, setEmailRecipients] = useState<ConfigItem[]>([]);
    const [caseSubjects, setCaseSubjects] = useState<ConfigItem[]>([]); // Added
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const account = instance.getActiveAccount() || accounts[0];
                if (!account) {
                    console.warn("⚠️ No active account found for fetching config");
                    setIsLoading(false);
                    return;
                }

                // Acquire Token
                let token = "";
                try {
                    const response = await instance.acquireTokenSilent({
                        scopes: ["User.Read"],
                        account: account
                    });
                    token = response.idToken;
                } catch (error) {
                    if (error instanceof InteractionRequiredAuthError) {
                        // Fallback to interaction or just log (avoid popup spam on auto-fetch)
                        console.error("Interaction required for token", error);
                        // instance.acquireTokenPopup(...) 
                    } else {
                        console.error("Token acquisition failed", error);
                    }
                    setIsLoading(false);
                    return;
                }

                if (!token) return;

                const baseUrl = await getApiUrl();
                const headers = {
                    "Authorization": `Bearer ${token}`,
                    "Content-Type": "application/json"
                };

                const [resLawyers, resStatuses, resDoctypes, resRecipients, resCaseSubjects] = await Promise.all([
                    fetch(`${baseUrl}/api/config/lawyers`, { headers }),
                    fetch(`${baseUrl}/api/config/statuses`, { headers }),
                    fetch(`${baseUrl}/api/config/doctypes`, { headers }),
                    fetch(`${baseUrl}/api/config/email_recipients`, { headers }),
                    fetch(`${baseUrl}/api/config/case_subjects`, { headers }), // Added
                ]);

                if (resLawyers.ok) setLawyers((await resLawyers.json()) as ConfigItem[]);
                else console.error("Failed to fetch lawyers", resLawyers.status);

                if (resStatuses.ok) setStatuses((await resStatuses.json()) as ConfigItem[]);
                else console.error("Failed to fetch statuses", resStatuses.status);

                if (resDoctypes.ok) setDoctypes((await resDoctypes.json()) as ConfigItem[]);
                else console.error("Failed to fetch doctypes", resDoctypes.status);


                if (resRecipients.ok) setEmailRecipients((await resRecipients.json()) as ConfigItem[]);
                else console.error("Failed to fetch email recipients", resRecipients.status);

                if (resCaseSubjects.ok) setCaseSubjects((await resCaseSubjects.json()) as ConfigItem[]); // Added
                else console.error("Failed to fetch case subjects", resCaseSubjects.status);

            } catch (error) {
                console.error("Failed to load config:", error);
            } finally {
                setIsLoading(false);
            }
        };

        if (accounts.length > 0) {
            fetchConfig();
        }
    }, [instance, accounts]);

    // --- CRUD HELPER ---
    const authenticatedRequest = async (url: string, method: string, body?: unknown) => {
        const baseUrl = await getApiUrl();
        const account = instance.getActiveAccount() || accounts[0];
        if (!account) return false;

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

        return res.ok;
    };

    // --- ACTIONS ---
    const addLawyer = async (code: string, name: string) => {
        if (await authenticatedRequest("/api/config/lawyers", "POST", { code, name })) {
            return true;
        }
        return false;
    };
    const deleteLawyer = async (code: string) => authenticatedRequest(`/api/config/lawyers/${code}`, "DELETE");

    const addStatus = async (code: string, name: string) => authenticatedRequest("/api/config/statuses", "POST", { code, name });
    const deleteStatus = async (code: string) => authenticatedRequest(`/api/config/statuses/${code}`, "DELETE");

    const addDoctype = async (code: string, name: string) => authenticatedRequest("/api/config/doctypes", "POST", { code, name });
    const deleteDoctype = async (code: string) => authenticatedRequest(`/api/config/doctypes/${code}`, "DELETE");

    const addEmail = async (name: string, email: string, description: string) => authenticatedRequest("/api/config/email_recipients", "POST", { name, email, description });
    const deleteEmail = async (email: string) => authenticatedRequest("/api/config/email_recipients", "DELETE", { email });

    // Case Subject Actions
    const addCaseSubject = async (name: string) => {
        const generatedCode = name.replace(/\s+/g, '').substring(0, 4).toUpperCase() + Math.random().toString(36).substring(2, 6).toUpperCase();
        return authenticatedRequest("/api/config/case_subjects", "POST", { code: generatedCode, name });
    };
    const deleteCaseSubject = async (code: string) => authenticatedRequest(`/api/config/case_subjects/${code}`, "DELETE");

    const reorderList = async (type: string, orderedIds: string[]) => authenticatedRequest("/api/config/reorder", "POST", { type, ordered_ids: orderedIds });

    return {
        lawyers, statuses, doctypes, emailRecipients, caseSubjects, isLoading,
        addLawyer, deleteLawyer,
        addStatus, deleteStatus,
        addDoctype, deleteDoctype,
        addEmail, deleteEmail,
        addCaseSubject, deleteCaseSubject,
        reorderList
    };
};
