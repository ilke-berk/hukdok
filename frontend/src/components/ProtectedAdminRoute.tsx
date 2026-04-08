
import { Navigate } from "react-router-dom";
import { useMsal } from "@azure/msal-react";
import { Loader2 } from "lucide-react";

interface ProtectedAdminRouteProps {
    children: React.ReactNode;
}

// Hardcoded admin list for frontend-only protection
const ADMIN_EMAILS = [
    "IlkeKutluk@lexisbio.onmicrosoft.com",
    // Add other admins here if needed
];

export const ProtectedAdminRoute = ({ children }: ProtectedAdminRouteProps) => {
    const { instance, accounts, inProgress } = useMsal();

    if (inProgress !== "none" && accounts.length === 0) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-background">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        );
    }

    const account = instance.getActiveAccount() || accounts[0];

    // 1. Check if logged in
    if (!account) {
        return <Navigate to="/login" replace />;
    }

    // 2. Check if admin
    // Turkish-aware case-insensitive email comparison
    const userEmail = (account.username || "").toLocaleLowerCase('tr-TR');
    const isAdmin = ADMIN_EMAILS.some(email => email.toLocaleLowerCase('tr-TR') === userEmail);

    if (!isAdmin) {
        console.warn("⛔ Unauthorized Admin Access Attempt:", userEmail);
        return <Navigate to="/" replace />;
    }

    return <>{children}</>;
};
