// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

// Login rozeti: görünür metin package.json "version" (v3.2.0 gibi okunur numara),
// git SHA'sı yalnız tooltip'te (deploy teyidi /healthz "version" ile aynı kaynak).

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("@azure/msal-react", () => ({
  useMsal: () => ({ instance: { loginRedirect: vi.fn() }, accounts: [], inProgress: "none" }),
}));
vi.mock("react-router", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@/hooks/useTheme", () => ({ useTheme: () => ({ theme: "dark", setTheme: vi.fn() }) }));
vi.mock("@/config/msalConfig", () => ({ loginRequest: { scopes: [] } }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

const SRC_DIR = path.dirname(fileURLToPath(import.meta.url));
const PKG_VERSION = (
  JSON.parse(readFileSync(path.join(SRC_DIR, "..", "..", "package.json"), "utf8")) as { version: string }
).version;

describe("Login sürüm rozeti", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;

  beforeEach(() => {
    vi.stubEnv("VITE_APP_VERSION", "d4d9d40");
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    vi.unstubAllEnvs();
  });

  it("görünür metin package.json sürümüdür, git SHA'sı yalnız tooltip'tedir", async () => {
    const { default: Login } = await import("./Login");
    root = createRoot(container);
    await act(async () => {
      root!.render(<Login />);
    });

    expect(PKG_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
    const rozet = container.querySelector(`span[title="Build: d4d9d40"]`);
    expect(rozet, "SHA tooltip'li rozet bulunmalı").not.toBeNull();
    expect(rozet!.textContent).toBe(`v${PKG_VERSION}`);
    // SHA görünür metinde yok — "abidik gubidik harfler" kullanıcıya gösterilmez.
    expect(container.textContent).not.toContain("d4d9d40");
    expect(container.textContent).toContain("Sistem Aktif");
  });
});
