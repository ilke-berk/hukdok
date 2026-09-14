// @vitest-environment jsdom
// G188 (F7) — tema sağlayıcısı depo erişimine dayanıklı:
// 1) localStorage erişimi fırlatınca (Safari private, kurumsal politika, kota) tema
//    varsayılana düşer, uygulama boyanır — açılışta beyaz ekran yok;
// 2) ThemeProvider App ağacında ErrorBoundary'nin ALTINDADIR: sağlayıcı yine de
//    çökerse kullanıcı boş ekran yerine hata ekranını görür.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const bayrak = vi.hoisted(() => ({ temaFirlat: false }));

// Gerçek sağlayıcı sarmalanır; yalnız ağaç sırası testi bayrakla fırlatır.
vi.mock("@/components/theme-provider", async (importOriginal) => {
  const gercek = await importOriginal<typeof import("./theme-provider")>();
  return {
    ThemeProvider: (props: Parameters<typeof gercek.ThemeProvider>[0]) => {
      if (bayrak.temaFirlat) throw new Error("tema sağlayıcı çöktü");
      return <gercek.ThemeProvider {...props} />;
    },
  };
});

// --- App bağımlılıkları: MSAL, oturum zamanlayıcısı, kabuk ve toaster'lar düzleştirilir ---
vi.mock("@/config/msalConfig", () => ({
  msalInstance: {
    initialize: async () => {},
    handleRedirectPromise: async () => null,
    getAllAccounts: () => [],
    setActiveAccount: () => {},
  },
  loginRequest: { scopes: [] },
}));
vi.mock("@azure/msal-react", () => ({
  MsalProvider: ({ children }: { children?: unknown }) => <>{children as never}</>,
  useMsal: () => ({ accounts: [], instance: {} }),
}));
vi.mock("@/hooks/useIdleTimeout", () => ({ useIdleTimeout: () => {} }));
vi.mock("@/components/ProtectedRoute", () => ({
  ProtectedRoute: () => <div data-testid="uygulama-icerigi">Uygulama içeriği</div>,
}));
vi.mock("@/components/ProtectedAdminRoute", () => ({ ProtectedAdminRoute: () => null }));
vi.mock("@/components/shell/Shell", () => ({ ShellLayout: () => null }));
vi.mock("@/components/ui/toaster", () => ({ Toaster: () => null }));
vi.mock("@/components/ui/sonner", () => ({ Toaster: () => null }));
vi.mock("@/lib/errorBeacon", () => ({ reportCaughtRenderError: vi.fn() }));

import { ThemeProvider } from "./theme-provider";
import { useTheme } from "@/hooks/useTheme";
import App from "@/App";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ANAHTAR = "hukudok-theme";

/** `localStorage` erişiminin kendisi fırlatır (getter) — Safari private / kurumsal politika. */
function localStorageErisiminiKapat(): () => void {
  const ozgun = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get() {
      throw new DOMException("Depo erişimi engellendi", "SecurityError");
    },
  });
  return () => {
    if (ozgun) Object.defineProperty(window, "localStorage", ozgun);
    else delete (window as { localStorage?: Storage }).localStorage;
  };
}

describe("ThemeProvider — depo erişimine dayanıklılık (G188 · F7)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let geriAl: (() => void) | null = null;
  let aktif: ReturnType<typeof useTheme> | null = null;

  function Gozcu() {
    aktif = useTheme();
    return <span data-testid="tema">{aktif.theme}</span>;
  }

  async function ciz(props: { defaultTheme?: "dark" | "light" | "system" } = {}) {
    root = createRoot(container);
    await act(async () => {
      root!.render(
        <ThemeProvider storageKey={ANAHTAR} {...props}>
          <Gozcu />
        </ThemeProvider>,
      );
    });
  }

  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("light", "dark");
    aktif = null;
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    geriAl?.();
    geriAl = null;
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("localStorage getter fırlatınca çocukları çizer, tema varsayılana düşer", async () => {
    geriAl = localStorageErisiminiKapat();

    await ciz({ defaultTheme: "dark" });

    expect(container.textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("kayıtlı geçerli tema okunur", async () => {
    localStorage.setItem(ANAHTAR, "light");

    await ciz({ defaultTheme: "dark" });

    expect(container.textContent).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("kayıtlı değer tanınmayan bir tema ise varsayılana düşer", async () => {
    localStorage.setItem(ANAHTAR, "mor");

    await ciz({ defaultTheme: "dark" });

    expect(container.textContent).toBe("dark");
  });

  it("setItem fırlatınca (kota/politika) setTheme fırlatmaz, tema bu oturumda yine değişir", async () => {
    await ciz({ defaultTheme: "dark" });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("Kota doldu", "QuotaExceededError");
    });

    await act(async () => { aktif!.setTheme("light"); });

    expect(container.textContent).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("depo açıkken setTheme seçimi kalıcı anahtara yazar", async () => {
    await ciz({ defaultTheme: "dark" });

    await act(async () => { aktif!.setTheme("light"); });

    expect(localStorage.getItem(ANAHTAR)).toBe("light");
  });
});

describe("App — tema sağlayıcısı ErrorBoundary içinde (G188 · F7)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let geriAl: (() => void) | null = null;

  async function appCiz() {
    root = createRoot(container);
    await act(async () => {
      root!.render(<App />);
    });
    // MSAL başlatma sözleri (initialize → handleRedirectPromise) → isReady.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }

  beforeEach(() => {
    bayrak.temaFirlat = false;
    vi.spyOn(console, "log").mockImplementation(() => {});
    document.documentElement.classList.remove("light", "dark");
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    geriAl?.();
    geriAl = null;
    bayrak.temaFirlat = false;
    vi.restoreAllMocks();
  });

  it("localStorage erişimi fırlatan ortamda App boyanır (beyaz ekran yok), tema varsayılana düşer", async () => {
    geriAl = localStorageErisiminiKapat();

    await appCiz();

    expect(container.querySelector('[data-testid="uygulama-icerigi"]')).not.toBeNull();
    expect(container.textContent).not.toContain("Beklenmedik bir hata oluştu");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("ThemeProvider çökerse ErrorBoundary yakalar: boş ekran yerine hata ekranı çizilir", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    bayrak.temaFirlat = true;

    await appCiz();

    expect(container.textContent).toContain("Beklenmedik bir hata oluştu");
    expect(container.querySelector('[data-testid="uygulama-icerigi"]')).toBeNull();
  });
});
