import { Navigate } from "react-router-dom";
import { useMsal } from "@azure/msal-react";
import { Loader2 } from "lucide-react";
import { useIsAdmin } from "@/hooks/useIsAdmin";

interface ProtectedAdminRouteProps {
    children: React.ReactNode;
}

export const ProtectedAdminRoute = ({ children }: ProtectedAdminRouteProps) => {
    const { instance, accounts, inProgress } = useMsal();
    const isAdmin = useIsAdmin();

    const account = instance.getActiveAccount() || accounts[0];

    if (inProgress !== "none" && accounts.length === 0) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    if (!account) {
        return <Navigate to="/login" replace />;
    }

    if (isAdmin === null) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    if (!isAdmin) {
        console.warn("⛔ Unauthorized Admin Access Attempt:", account.username);
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
};
