// @vitest-environment jsdom
// Toplu yüklemede ek bağlama: tezgâhta bir satıra bağlanan ek dosyalar EmailModal'a
// `defaultExtraAttachments` ile gelir — açılışta listelenir, kullanıcı çıkarabilir,
// her yeniden açılışta prop'tan tazelenir (önceki dosyanın elle ekleri kalmaz).
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

const RECIPIENT = { name: "Ali Ak", email: "a@x.com" };
const noop = () => undefined;

describe("EmailModal — defaultExtraAttachments (toplu ek bağlama)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    authRequestMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => (url === "/api/config/email_recipients" ? [RECIPIENT] : []),
    }));
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    if (root) {
      act(() => root!.unmount());
      root = null;
    }
    container.remove();
    queryClient.clear();
  });

  function render(isOpen: boolean, extras?: File[]) {
    act(() => root!.render(
      <QueryClientProvider client={queryClient}>
        <EmailModal isOpen={isOpen} onClose={noop} onConfirm={noop} defaultTo={[RECIPIENT]} defaultExtraAttachments={extras} />
      </QueryClientProvider>,
    ));
  }

  const badges = () => Array.from(container.querySelectorAll("[data-testid='extra-attachment']"));
  const badgeNames = () => badges().map(b => b.querySelector("span")?.textContent);

  it("açılışta bağlı ekler listelenir ve 'toplu' etiketi taşır; X ile çıkarılabilir", () => {
    const mazbata = new File(["m"], "mazbata.pdf", { type: "application/pdf" });
    render(true, [mazbata]);

    expect(badgeNames()).toEqual(["mazbata.pdf"]);
    expect(badges()[0].textContent).toContain("toplu");

    // Çıkar simgesi bir SVG: jsdom'da SVGElement.click yok, olay elle yayılır.
    const remove = container.querySelector("[aria-label='Eki çıkar: mazbata.pdf']") as Element;
    act(() => { remove.dispatchEvent(new MouseEvent("click", { bubbles: true })); });
    expect(badges()).toHaveLength(0);
  });

  it("yeniden açılışta liste prop'tan tazelenir: ilk dosyanın eki ikinci dosyaya sızmaz", () => {
    const mazbata = new File(["m"], "mazbata.pdf", { type: "application/pdf" });
    render(true, [mazbata]);
    expect(badgeNames()).toEqual(["mazbata.pdf"]);

    render(false, [mazbata]);
    render(true, undefined);
    expect(badges()).toHaveLength(0);

    const baska = new File(["b"], "baska.pdf", { type: "application/pdf" });
    render(false, [baska]);
    render(true, [baska]);
    expect(badgeNames()).toEqual(["baska.pdf"]);
  });
});
