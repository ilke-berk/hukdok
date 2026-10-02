import { Navigate } from "react-router";
import { useMsal } from "@azure/msal-react";
import { PageSkeleton } from "@/components/skeletons/Skeletons";
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
            <PageSkeleton />
        );
    }

    if (!account) {
        return <Navigate to="/login" replace />;
    }

    if (isAdmin === null) {
        return (
            <PageSkeleton />
        );
    }

    if (!isAdmin) {
        console.warn("⛔ Unauthorized Admin Access Attempt:", account.username);
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
};
