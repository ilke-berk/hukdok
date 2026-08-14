import { Navigate } from "react-router";
import { useMsal } from "@azure/msal-react";

interface ProtectedRouteProps {
    children: React.ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
    const { accounts } = useMsal();
    const isAuthenticated = accounts.length > 0;

    console.log("🔒 ProtectedRoute kontrol:", {
        accountCount: accounts.length,
        isAuthenticated,
        accounts: accounts.map(acc => ({ username: acc.username, name: acc.name }))
    });

    if (!isAuthenticated) {
        console.log("❌ Kimlik doğrulanamadı, login'e yönlendiriliyor...");
        // Redirect to login if not authenticated
        return <Navigate to="/login" replace />;
    }

    console.log("✅ Kimlik doğrulandı, içeriğe erişim veriliyor");
    return <>{children}</>;
};
