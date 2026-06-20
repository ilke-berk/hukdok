import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMsal } from "@azure/msal-react";
import { Scale, Lock, Loader2, Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { loginRequest } from "@/config/msalConfig";
import { useTheme } from "@/components/theme-provider";

const ALLOWED_DOMAINS = [
  "@hanyalogluacar.av.tr",
  "@lexisbio.onmicrosoft.com",
];

// Microsoft 4-square logo, brand-fg renkte
function MsLogo({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 21 21" aria-hidden="true">
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}

const Login = () => {
  const { instance, accounts, inProgress } = useMsal();
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();

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
      await instance.loginRedirect(loginRequest);
    } catch (error: unknown) {
      console.error("❌ Login hatası:", error);
      setIsLoggingIn(false);
      toast.error("Giriş Başarısız", {
        description: "Lütfen yetkili bir kurumsal e-posta adresi kullandığınızdan emin olun.",
        duration: 5000,
      });
    }
  };

  return (
    <div
      className="theme-classic relative min-h-screen w-full bg-[var(--bg)] text-[var(--fg)] font-sans grid p-[28px_44px] overflow-hidden"
      style={{ gridTemplateRows: "auto 1fr auto" }}
    >
      {/* İç çift çerçeve */}
      <div className="pointer-events-none absolute inset-5 border border-[var(--border)]" aria-hidden="true" />
      <div className="pointer-events-none absolute inset-[26px] border border-[var(--border)] opacity-50" aria-hidden="true" />

      {/* Köşe ornamentleri */}
      <span className="pointer-events-none absolute top-5 left-5 w-[18px] h-[18px] border-l border-t border-[var(--border-strong)]" aria-hidden="true" />
      <span className="pointer-events-none absolute top-5 right-5 w-[18px] h-[18px] border-r border-t border-[var(--border-strong)]" aria-hidden="true" />
      <span className="pointer-events-none absolute bottom-5 left-5 w-[18px] h-[18px] border-l border-b border-[var(--border-strong)]" aria-hidden="true" />
      <span className="pointer-events-none absolute bottom-5 right-5 w-[18px] h-[18px] border-r border-b border-[var(--border-strong)]" aria-hidden="true" />

      {/* Watermark "H" */}
      <div
        className="pointer-events-none absolute font-display font-normal text-[var(--brand)] leading-none select-none"
        style={{
          fontSize: "min(58vw, 380px)",
          opacity: 0.03,
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          letterSpacing: "-0.03em",
        }}
        aria-hidden="true"
      >
        H
      </div>

      {/* ÜST — EST. + Sistem rozeti + Tema */}
      <header className="relative z-10 flex items-center justify-between gap-4 px-[22px] pt-3">
        <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
          EST. MMVI · İstanbul
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 border border-[var(--border)] rounded-full bg-[var(--bg-elevated)]">
            <span
              className="inline-block w-1.5 h-1.5 rounded-full bg-[#2f8a5d]"
              style={{ boxShadow: "0 0 0 3px rgba(47,138,93,0.18)" }}
              aria-hidden="true"
            />
            <span className="font-sans text-[11px] font-medium text-[var(--fg-muted)] tracking-[0.01em]">
              Sistem Aktif
            </span>
            <span className="w-px h-2.5 bg-[var(--border-strong)] mx-0.5" />
            <span className="font-mono text-[10px] tracking-[0.1em] text-[var(--fg-subtle)]">
              v2.4.1
            </span>
          </div>
          <button
            type="button"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            aria-label={theme === "light" ? "Koyu tema" : "Açık tema"}
            title={theme === "light" ? "Koyu tema" : "Açık tema"}
            className="w-9 h-9 grid place-items-center border border-[var(--border)] rounded-full bg-[var(--bg-elevated)] text-[var(--fg-muted)] cursor-pointer transition-colors hover:text-[var(--brand)] hover:border-[var(--brand)]"
          >
            {theme === "light" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* SAHNE — Monogram + Başlık + CTA + Policy */}
      <section className="relative z-10 flex flex-col items-center justify-center py-2">
        {/* Monogram + yatay hairline'lar */}
        <div className="relative grid place-items-center mb-5">
          <span className="absolute h-px w-[100px] bg-[var(--border-strong)] top-1/2 right-[calc(50%+60px)]" aria-hidden="true" />
          <Scale className="w-14 h-14 text-[var(--brand)]" strokeWidth={1.25} />
          <span className="absolute h-px w-[100px] bg-[var(--border-strong)] top-1/2 left-[calc(50%+60px)]" aria-hidden="true" />
        </div>

        <div className="font-mono text-[10px] tracking-[0.22em] uppercase text-[var(--fg-subtle)] mb-2">
          Hanyaloğlu &amp; Acar
        </div>

        <h1
          className="font-display font-medium text-[var(--fg)] m-0"
          style={{ fontSize: "clamp(48px, 9vw, 76px)", letterSpacing: "0.06em", lineHeight: 1 }}
        >
          HUKDOK
        </h1>

        <p
          className="font-display italic font-normal text-[var(--fg-muted)] mt-3.5"
          style={{ fontSize: "17px", letterSpacing: "0.01em" }}
        >
          Hukuki Belge Otomasyon Sistemi
        </p>

        <div className="w-7 h-px bg-[var(--brand)] my-5" />

        <p
          className="text-[13px] leading-[1.7] text-[var(--fg-muted)] text-center max-w-[460px] mb-7"
          style={{ letterSpacing: "0.005em" }}
        >
          UYAP belgelerini saniyeler içinde <strong className="text-[var(--fg)] font-semibold">analiz eder</strong>,
          standart adlandırma şemasına <strong className="text-[var(--fg)] font-semibold">dönüştürür</strong> ve ilgili{" "}
          <strong className="text-[var(--fg)] font-semibold">dava dosyasına bağlar.</strong>
          {" "}Tüm işlemler büro içinde, güvenli ve denetlenebilir.
        </p>

        <button
          type="button"
          onClick={handleMicrosoftLogin}
          disabled={isLoggingIn}
          aria-busy={isLoggingIn}
          className="inline-flex items-center justify-center gap-3.5 px-8 py-4 border-none bg-[var(--brand)] text-[var(--brand-fg)] font-sans text-[14px] font-medium tracking-[0.04em] cursor-pointer transition-colors hover:bg-[var(--brand-hover)] active:translate-y-[1px] disabled:opacity-85 disabled:cursor-progress min-w-[340px]"
          style={{ boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 8px 24px -12px rgba(109,36,52,0.4)" }}
        >
          {isLoggingIn ? <Loader2 className="w-4 h-4 animate-spin" /> : <MsLogo size={18} />}
          <span>{isLoggingIn ? "Yönlendiriliyor…" : "Microsoft ile Giriş Yap"}</span>
        </button>

        <p className="mt-3.5 text-[12px] text-[var(--fg-subtle)] tracking-[0.01em]">
          Yalnızca yetkili kullanıcılar erişebilir.
        </p>

        {/* Yetkili Erişim policy tile */}
        <div
          className="relative mt-7 w-full max-w-[560px] border border-[var(--border)] bg-[var(--bg-elevated)] px-5 py-4 grid items-start gap-3.5"
          style={{ gridTemplateColumns: "auto 1fr" }}
        >
          <span
            className="absolute -top-2 left-[18px] px-2 bg-[var(--bg)] font-mono text-[9px] tracking-[0.22em] text-[var(--fg-subtle)] uppercase"
          >
            Yetkili Erişim
          </span>
          <div className="w-7 h-7 grid place-items-center text-[var(--brand)] border border-[var(--border-strong)] rounded-[3px] bg-[var(--bg)]">
            <Lock className="w-3.5 h-3.5" strokeWidth={1.8} />
          </div>
          <div className="text-[12px] leading-[1.65] text-[var(--fg-muted)]">
            <strong className="text-[var(--fg)] font-semibold">Sadece kurumsal e-postalar.</strong> Aşağıdaki
            uzantılara izin verilir; diğer hesaplar otomatik reddedilir. Cihaz uyumluluğu ve iki adımlı doğrulama
            zorunludur.
            <div className="flex flex-wrap gap-x-2.5 gap-y-1.5 mt-1.5 font-mono text-[11px] text-[var(--fg)] tracking-[0.01em]">
              {ALLOWED_DOMAINS.map(d => (
                <span key={d} className="px-2 py-0.5 border border-[var(--border)] bg-[var(--bg-sunken)] rounded-[2px]">
                  {d}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ALT — adres + telif */}
      <footer className="relative z-10 flex items-end justify-between gap-6 px-[22px] pb-3">
        <div className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] leading-[1.65]">
          Hanyaloğlu &amp; Acar Hukuk Bürosu<br />
          Nispetiye Cad. No: 24 · Levent / İstanbul
        </div>
        <div className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] leading-[1.65] text-right">
          Tüm haklar saklıdır © 2026<br />
          <span>Yasal · Gizlilik · Destek</span>
        </div>
      </footer>
    </div>
  );
};

export default Login;
