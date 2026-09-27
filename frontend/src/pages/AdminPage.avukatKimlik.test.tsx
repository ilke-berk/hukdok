// @vitest-environment jsdom
// G229: arayüzden avukat kodu kalkar. Avukat tablosunda kod/kimlik sütunu YOK, ekleme
// formunda kod alanı YOK (sunucu üretir, G228); satırın tanımlayıcısı kurumsal kimlik
// (`AVK-…`): güncelle / pasife al / kullanım çağrıları kimlikle gider. Avukat SİLİNMEZ,
// pasife alınır (G225) → `DELETE /api/config/lawyers/{kimlik}`; boşalt/taşı sorulmaz.
// Diğer listeler (durumlar) eski davranışta kalır: kod sütunu + "Sil" + genel silme ucu.
// Gerçek `useConfig` + QueryClient; yalnız ağ (`authRequest`), MSAL ve yan kartlar taklit.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ConfigItem } from "@/hooks/useConfig";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
    useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
vi.mock("@azure/msal-react", () => ({ useMsal: () => ({ accounts: [{ username: "a@b.c" }] }) }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/components/admin/DeliveryInboxCard", () => ({ DeliveryInboxCard: () => null }));
vi.mock("@/components/admin/FeatureSettingsCard", () => ({ FeatureSettingsCard: () => null }));
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));

import AdminPage from "./AdminPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Reply = { ok: boolean; json: () => Promise<unknown> };
const reply = (body: unknown, ok = true): Reply => ({ ok, json: async () => JSON.parse(JSON.stringify(body)) });

const LAWYERS: ConfigItem[] = [
    { code: "AGB", kimlik: "AVK-00001", name: "Av. Ayşe Gül Bal", gorev: "AVUKAT", city: "İstanbul" },
    { code: "MKT", kimlik: "AVK-00002", name: "Av. Mehmet Kaya", gorev: "AVUKAT" },
];
const STATUSES: ConfigItem[] = [{ code: "DERDEST", name: "Derdest" }, { code: "MAHZEN", name: "Mahzen" }];
const USAGE = { name: "Av. Ayşe Gül Bal", total: 3, clearable: false, items: [{ label: "Dava", count: 3, clearable: false }] };

describe("AdminPage avukat listesi kurumsal kimlikle, kodsuz (G229)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let queryClient: QueryClient;

    beforeEach(() => {
        vi.clearAllMocks();
        authRequestMock.mockImplementation(async (url: string) => {
            if (url === "/api/config/lawyers") return reply(LAWYERS);
            if (url === "/api/config/statuses") return reply(STATUSES);
            if (url === "/api/config/required_case_fields") return reply({ fields: [], party_rule: null });
            if (url.startsWith("/api/config/usage")) return reply(USAGE);
            if (url === "/api/config/update") return reply({ status: "success", updated: 0 });
            if (url === "/api/config/delete") return reply({ status: "success", affected: 0 });
            if (url.startsWith("/api/config/lawyers/")) return reply({ status: "success" });
            return reply([]);
        });
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

    function render(url = "/admin") {
        root = createRoot(container);
        act(() => {
            root!.render(
                <QueryClientProvider client={queryClient}>
                    <MemoryRouter initialEntries={[url]}>
                        <AdminPage />
                    </MemoryRouter>
                </QueryClientProvider>,
            );
        });
    }

    async function waitFor(condition: () => boolean, label: string): Promise<void> {
        for (let i = 0; i < 200; i++) {
            if (condition()) return;
            await act(async () => { await new Promise(r => setTimeout(r, 5)); });
        }
        throw new Error(`Koşul sağlanmadı: ${label}`);
    }

    const rows = () => Array.from(container.querySelectorAll("tbody tr"));
    const headers = () => Array.from(container.querySelectorAll("thead th")).map(th => th.textContent?.trim() ?? "");
    const dialog = () => document.body.querySelector("[role='dialog']");
    const dialogButton = (label: string) =>
        Array.from(dialog()?.querySelectorAll("button") ?? []).find(b => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
    const callsTo = (pred: (url: string, method: string) => boolean) =>
        authRequestMock.mock.calls.filter(([u, m]) => pred(u as string, m as string));

    function type(input: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(input, value);
            input.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }

    it("avukat tablosunda kod/kimlik sütunu yok; tablo metninde kod ve AVK- geçmez", async () => {
        render();
        await waitFor(() => rows().length === 2, "avukat satırları");

        expect(headers()).not.toContain("Kod");
        expect(headers()).not.toContain("Kimlik");
        expect(headers()).toContain("Ad Soyad");
        const text = container.querySelector("table")?.textContent ?? "";
        expect(text).toContain("Av. Ayşe Gül Bal");
        expect(text).not.toContain("AVK-");
        expect(text).not.toContain("AGB");
        expect(text).not.toContain("MKT");
    });

    it("yeni avukat formunda kod alanı yok; istek gövdesi kod taşımaz", async () => {
        render();
        await waitFor(() => rows().length === 2, "avukat satırları");

        const addButton = Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes("Yeni Avukat"))!;
        act(() => { addButton.click(); });
        await waitFor(() => dialog() !== null, "ekleme diyaloğu");

        const labels = Array.from(dialog()!.querySelectorAll("label")).map(l => l.textContent?.trim());
        expect(labels).not.toContain("Kod");
        expect(labels).toContain("İsim");

        const nameInput = dialog()!.querySelector("input") as HTMLInputElement;
        expect(nameInput.getAttribute("placeholder")).toBe("Av. Ahmet Güzel");
        type(nameInput, "Av. Yeni Avukat");
        await act(async () => { dialogButton("Kaydet")!.click(); });
        await waitFor(() => callsTo((u, m) => u === "/api/config/lawyers" && m === "POST").length === 1, "ekleme isteği");

        const body = callsTo((u, m) => u === "/api/config/lawyers" && m === "POST")[0][2] as Record<string, unknown>;
        expect(body.name).toBe("Av. Yeni Avukat");
        expect(body).not.toHaveProperty("code");
        expect(toastMock.warning).not.toHaveBeenCalled();
    });

    it("Pasife al: kullanım kimlikle sorulur, metin geçmişi korur der, DELETE kimlikle gider; boşalt/taşı yok", async () => {
        render();
        await waitFor(() => rows().length === 2, "avukat satırları");

        const pasifeAl = rows()[0].querySelector("button[aria-label='Pasife al']") as HTMLButtonElement;
        expect(pasifeAl).not.toBeNull();
        await act(async () => { pasifeAl.click(); });
        await waitFor(() => dialogButton("Pasife al") !== undefined && !dialogButton("Pasife al")!.disabled, "pasife alma diyaloğu");

        expect(callsTo(u => u.startsWith("/api/config/usage")).map(([u]) => u))
            .toEqual(["/api/config/usage?type=lawyers&code=AVK-00001"]);
        const text = dialog()!.textContent ?? "";
        expect(text).toContain("pasife alınacak, geçmiş davaları korunur");
        expect(text).not.toContain("AVK-");
        expect(text).not.toContain("Alanı boşalt");
        expect(dialog()!.querySelectorAll("input[type='radio']").length).toBe(0);
        expect(dialogButton("Sil")).toBeUndefined();

        await act(async () => { dialogButton("Pasife al")!.click(); });
        await waitFor(() => callsTo((u, m) => m === "DELETE").length === 1, "pasife alma isteği");
        expect(callsTo((u, m) => m === "DELETE")[0][0]).toBe("/api/config/lawyers/AVK-00001");
        expect(callsTo(u => u === "/api/config/delete")).toHaveLength(0);
        expect(toastMock.success).toHaveBeenCalledWith("Pasife alındı — geçmiş davaları korunur");
    });

    it("düzenleme güncelleme ucuna kimlikle gider", async () => {
        render();
        await waitFor(() => rows().length === 2, "avukat satırları");

        const editButton = rows()[1].querySelector("td:last-child button") as HTMLButtonElement;
        act(() => { editButton.click(); });
        await waitFor(() => dialog() !== null, "düzenleme diyaloğu");
        expect(dialog()!.textContent ?? "").not.toContain("AVK-");

        await act(async () => { dialogButton("Kaydet")!.click(); });
        await waitFor(() => callsTo(u => u === "/api/config/update").length === 1, "güncelleme isteği");
        const body = callsTo(u => u === "/api/config/update")[0][2] as { type: string; code: string };
        expect(body.type).toBe("lawyers");
        expect(body.code).toBe("AVK-00002");
    });

    it("diğer listeler değişmez: durumlarda kod sütunu, 'Sil' ve genel silme ucu kalır", async () => {
        render("/admin?tab=statuses");
        await waitFor(() => rows().length === 2, "durum satırları");

        expect(headers()).toContain("Kod");
        expect(rows()[0].textContent).toContain("DERDEST");

        const del = rows()[0].querySelectorAll("td:last-child button")[1] as HTMLButtonElement;
        await act(async () => { del.click(); });
        await waitFor(() => dialogButton("Sil") !== undefined && !dialogButton("Sil")!.disabled, "silme diyaloğu");
        expect(callsTo(u => u.startsWith("/api/config/usage")).map(([u]) => u))
            .toEqual(["/api/config/usage?type=statuses&code=DERDEST"]);
        expect(dialog()!.textContent ?? "").toContain("Başka bir değere taşı");
        expect(dialogButton("Pasife al")).toBeUndefined();
    });
});
