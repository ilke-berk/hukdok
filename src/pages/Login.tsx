import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import HukdokLogo from "@/components/HukdokLogo";
import { ThemeToggle } from "@/components/theme-toggle";
import { LogIn, Shield, Loader2 } from "lucide-react";
import { useMsal } from "@azure/msal-react";
import { loginRequest } from "@/config/msalConfig";
import { toast } from "sonner";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const Login = () => {
    const { instance, accounts, inProgress } = useMsal();
    const [isLoggingIn, setIsLoggingIn] = useState(false);
    const navigate = useNavigate();

    // Auto-redirect if already logged in
    useEffect(() => {
        if (accounts.length > 0 && inProgress === "none") {
            console.log("✅ Kullanıcı zaten giriş yapmış, ana sayfaya yönlendiriliyor...");
            navigate("/", { replace: true });
        }
    }, [accounts, inProgress, navigate]);

    const handleMicrosoftLogin = async () => {
        try {
            setIsLoggingIn(true);
            console.log("🔐 Microsoft login başlatılıyor...");
            console.log("📋 Login request:", loginRequest);

            // Use redirect instead of popup for better compatibility with HashRouter
            await instance.loginRedirect(loginRequest);
            // Note: After redirect, user will return to this page
            // and handleRedirectPromise in App.tsx will process the login
        } catch (error: any) {
            console.error("❌ Login hatası:", error);
            console.error("📄 Hata detayları:", {
                message: error.message,
                errorCode: error.errorCode,
                errorMessage: error.errorMessage,
                subError: error.subError,
                correlationId: error.correlationId
            });

            setIsLoggingIn(false);

            // User-friendly error message
            const friendlyMessage = "Giriş yapılamadı. Lütfen yetkili bir kurumsal e-posta adresi kullandığınızdan emin olun.";

            toast.error("Giriş Başarısız", {
                description: friendlyMessage,
                duration: 5000
            });
        }
    };

    return (
        <div className="min-h-screen flex flex-col">
            {/* Header */}
            <header className="glass-header text-primary-foreground py-8 px-6 relative">
                <div className="absolute top-4 right-6">
                    <ThemeToggle />
                </div>
                <div className="container mx-auto">
                    <div className="flex items-center justify-center gap-4 mb-3">
                        <HukdokLogo className="drop-shadow-lg transition-transform hover:scale-105" />
                    </div>
                    <h1 className="text-4xl font-bold text-center mb-2 tracking-tight drop-shadow-lg">
                        HUKDOK
                    </h1>
                    <p className="text-center text-sm opacity-90 font-medium tracking-wide">
                        HANYALOĞLU&ACAR HUKUK BÜROSU DÖKÜMAN OTOMASYON SİSTEMİ BY TRAGIC
                    </p>
                </div>
            </header>

            {/* Login Content */}
            <div className="flex-1 flex items-center justify-center p-6">
                <Card className="glass-card p-8 max-w-md w-full animate-fade-in">
                    <div className="text-center space-y-6">
                        {/* Lock Icon */}
                        <div className="flex justify-center">
                            <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
                                <Shield className="w-10 h-10 text-primary" />
                            </div>
                        </div>

                        {/* Title */}
                        <div className="space-y-2">
                            <h2 className="text-2xl font-bold text-foreground">
                                Hoş Geldiniz
                            </h2>
                            <p className="text-muted-foreground">
                                Devam etmek için Microsoft hesabınızla giriş yapın
                            </p>
                        </div>

                        {/* Login Button */}
                        <Button
                            onClick={handleMicrosoftLogin}
                            disabled={isLoggingIn}
                            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground py-6 text-lg font-semibold gap-3 transition-all hover:shadow-lg hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed"
                        >
                            {isLoggingIn ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    Giriş Yapılıyor...
                                </>
                            ) : (
                                <>
                                    <LogIn className="w-5 h-5" />
                                    Microsoft ile Giriş Yap
                                </>
                            )}
                        </Button>

                        {/* Info Text */}
                        <div className="pt-4 border-t border-border">
                            <p className="text-xs text-muted-foreground">
                                Bu sistem sadece yetkili kullanıcılar için erişilebilir.
                                <br />
                                Giriş yaparak şirket politikalarını kabul etmiş olursunuz.
                            </p>
                        </div>
                    </div>
                </Card>
            </div>

            {/* Footer */}
            <footer className="py-4 text-center text-sm text-muted-foreground">
                <p>© 2026 Hanyaloğlu & Acar Hukuk Bürosu. Tüm hakları saklıdır.</p>
            </footer>
        </div>
    );
};

export default Login;
