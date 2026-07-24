import { useState, useEffect } from "react";
import { useMsal } from "@azure/msal-react";
import { apiClient } from "@/lib/api";

// Sidebar ve ProtectedAdminRoute aynı anda sorduğu için tek istek paylaşılır;
// hata durumunda cache sıfırlanır ki sonraki mount yeniden denesin.
let cached: Promise<boolean> | null = null;

function fetchIsAdmin(): Promise<boolean> {
    if (!cached) {
        cached = apiClient
            .fetch("/api/config/is_admin")
            .then(res => res.json())
            .then(data => data.is_admin === true)
            .catch(() => {
                cached = null;
                return false;
            });
    }
    return cached;
}

/** Backend'in ADMIN_EMAILS kontrolüne göre admin mi? null = henüz bilinmiyor. */
export function useIsAdmin(): boolean | null {
    const { instance, accounts } = useMsal();
    const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

    const account = instance.getActiveAccount() || accounts[0];
    const username = account?.username;

    useEffect(() => {
        if (!username) return;
        let cancelled = false;
        fetchIsAdmin().then(result => {
            if (!cancelled) setIsAdmin(result);
        });
        return () => {
            cancelled = true;
        };
    }, [username]);

    return isAdmin;
}
