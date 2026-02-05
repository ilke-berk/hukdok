import { useState, useEffect } from "react";
import { getApiUrl } from "@/lib/api";
import { useMsal } from "@azure/msal-react";
import { InteractionRequiredAuthError } from "@azure/msal-browser";

type Option = {
    code: string;
    name: string;
    email?: string;
    description?: string;
};

export const useConfig = () => {
    const { instance, accounts } = useMsal();
    const [lawyers, setLawyers] = useState<Option[]>([]);
    const [statuses, setStatuses] = useState<Option[]>([]);
    const [doctypes, setDoctypes] = useState<Option[]>([]);
    const [emailRecipients, setEmailRecipients] = useState<Option[]>([]);
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

                const [resLawyers, resStatuses, resDoctypes, resRecipients] = await Promise.all([
                    fetch(`${baseUrl}/api/config/lawyers`, { headers }),
                    fetch(`${baseUrl}/api/config/statuses`, { headers }),
                    fetch(`${baseUrl}/api/config/doctypes`, { headers }),
                    fetch(`${baseUrl}/api/config/email_recipients`, { headers }),
                ]);

                if (resLawyers.ok) setLawyers(await resLawyers.json());
                else console.error("Failed to fetch lawyers", resLawyers.status);

                if (resStatuses.ok) setStatuses(await resStatuses.json());
                else console.error("Failed to fetch statuses", resStatuses.status);

                if (resDoctypes.ok) setDoctypes(await resDoctypes.json());
                else console.error("Failed to fetch doctypes", resDoctypes.status);


                if (resRecipients.ok) setEmailRecipients(await resRecipients.json());
                else console.error("Failed to fetch email recipients", resRecipients.status);

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
    const authenticatedRequest = async (url: string, method: string, body?: any) => {
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
            // Optimistic update or refresh? For simplicity: refresh.
            // Actually, simply reloading the page or triggering re-fetch is easier, 
            // but useConfig context is local. We'd need to expose a refresh function.
            // For now, let's just return true and let AdminPage reload.
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

    const reorderList = async (type: string, orderedIds: string[]) => authenticatedRequest("/api/config/reorder", "POST", { type, ordered_ids: orderedIds });

    return {
        lawyers, statuses, doctypes, emailRecipients, isLoading,
        addLawyer, deleteLawyer,
        addStatus, deleteStatus,
        addDoctype, deleteDoctype,
        addEmail, deleteEmail,
        reorderList
    };
};
