// @vitest-environment jsdom
// G185: EmailModal yalnız alıcı listesine (email_recipients) abone olur —
// useConfig() 32 `/api/config/*` ucu çağırıyordu. Modal Index'te ve CaseDetails'te
// KAPALIYKEN de monte edildiği için sayfa yüküne doğrudan yansıyordu.
// Gerçek useConfig modülü + gerçek QueryClient; ağ (authRequest) ve MSAL taklit
// edilir. Dialog/Popover/Command düz DOM'a indirilir: alıcı SIRASI okunur.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
  useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
const msal = vi.hoisted(() => ({ accounts: [{ username: "a@b.c" }] }));
vi.mock("@azure/msal-react", () => ({ useMsal: () => msal }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));

type Kids = { children?: ReactNode };
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: Kids & { open: boolean }) => (open ? <div>{children}</div> : null),
  DialogContent: ({ children }: Kids) => <div>{children}</div>,
  DialogHeader: ({ children }: Kids) => <div>{children}</div>,
  DialogTitle: ({ children }: Kids) => <div>{children}</div>,
  DialogDescription: ({ children }: Kids) => <div>{children}</div>,
  DialogFooter: ({ children }: Kids) => <div>{children}</div>,
}));
// Popover: içerik daima basılır (açık/kapalı durumu testin konusu değil).
vi.mock("@/components/ui/popover", () => ({
  Popover: ({ children }: Kids) => <>{children}</>,
  PopoverTrigger: ({ children }: Kids) => <>{children}</>,
  PopoverContent: ({ children }: Kids) => <div>{children}</div>,
}));
vi.mock("@/components/ui/command", () => ({
  Command: ({ children }: Kids) => <div>{children}</div>,
  CommandInput: () => null,
  CommandList: ({ children }: Kids) => <div>{children}</div>,
  CommandEmpty: () => null,
  CommandGroup: ({ children }: Kids) => <div>{children}</div>,
  CommandItem: ({ children }: Kids) => <div data-item="">{children}</div>,
}));

import { EmailModal } from "./EmailModal";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// Bilinçli alfabetik DEĞİL: liste backend sırasıyla basılmalı.
const RECIPIENTS = [
  { name: "Zeynep Zor", email: "z@x.com" },
  { name: "Ali Ak", email: "a@x.com" },
];

const configUrls = (): string[] =>
  authRequestMock.mock.calls
    .map(([url]) => url as string)
    .filter(u => u.startsWith("/api/config/"))
    .sort();

const noop = () => undefined;

describe("EmailModal — config aboneliği (G185)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => (url === "/api/config/email_recipients" ? RECIPIENTS : []),
    }));
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    queryClient.clear();
  });

  function render(isOpen: boolean) {
    root = createRoot(container);
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <EmailModal isOpen={isOpen} onClose={noop} onConfirm={noop} />
      </QueryClientProvider>,
    ));
  }

  async function waitFor(condition: () => boolean, label: string): Promise<void> {
    for (let i = 0; i < 100; i++) {
      if (condition()) return;
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
    throw new Error(`Koşul sağlanmadı: ${label}`);
  }

  async function flush(): Promise<void> {
    for (let i = 0; i < 5; i++) {
      await act(async () => { await new Promise(r => setTimeout(r, 10)); });
    }
  }

  it("kapalıyken monte edilince yalnız /api/config/email_recipients çağrılır (useConfig 32 uç çağırıyordu)", async () => {
    render(false);
    await waitFor(
      () => queryClient.getQueryState(["config", "email_recipients"])?.status === "success",
      "alıcı listesi yüklendi",
    );
    await flush();

    expect(configUrls()).toEqual(["/api/config/email_recipients"]);
  });

  it("açıkken alıcı seçicisi listeyi backend sırasıyla basar", async () => {
    render(true);
    await waitFor(() => container.querySelectorAll("[data-item]").length === 2, "alıcı seçenekleri doldu");
    await flush();

    expect(Array.from(container.querySelectorAll("[data-item]")).map(el => el.textContent))
      .toEqual(["Zeynep Zorz@x.com", "Ali Aka@x.com"]);
    expect(configUrls()).toEqual(["/api/config/email_recipients"]);
  });
});
