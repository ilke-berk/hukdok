// @vitest-environment jsdom
// AdminPage — config listeleri render sırasında türetilir (G187, performans denetimi F4).
// Gerçek `useConfig` + gerçek QueryClient kullanılır: "aynı içerikle yeniden çekme"
// güvencesi react-query'nin structural sharing'inden (dizi kimliği korunur) gelir;
// mock'lanmış hook bunu sınayamaz. Yalnız ağ (`authRequest`), MSAL ve ağır yan
// kartlar taklit edilir.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import type { ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { DndContextProps, DragCancelEvent, DragEndEvent, DragStartEvent } from "@dnd-kit/core";
import type { ConfigItem } from "@/hooks/useConfig";

const authRequestMock = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/useAuthRequest", () => ({
    useAuthRequest: () => ({ authRequest: authRequestMock }),
}));
// Oturum açık kabul edilir (useConfig sorguları enabled: accounts.length > 0).
vi.mock("@azure/msal-react", () => ({ useMsal: () => ({ accounts: [{ username: "a@b.c" }] }) }));
vi.mock("@/hooks/usePageTitle", () => ({ useSetPageTitle: () => undefined }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/components/admin/DeliveryInboxCard", () => ({ DeliveryInboxCard: () => null }));
vi.mock("@/components/admin/FeatureSettingsCard", () => ({ FeatureSettingsCard: () => null }));
// Silinenler paneli mount'ta kendi ucunu çağırır; ağa çıkmasın.
vi.mock("@/lib/api", () => ({ apiClient: { fetch: async () => ({ ok: false, json: async () => ({}) }) } }));

// Render sayacı: metin taşıyan her tablo hücresinin kaç kez render edildiği.
const cellRenders = vi.hoisted(() => new Map<string, number>());
vi.mock("@/components/ui/table", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/components/ui/table")>();
    const TableCell = (props: ComponentProps<typeof actual.TableCell>) => {
        if (typeof props.children === "string") {
            cellRenders.set(props.children, (cellRenders.get(props.children) ?? 0) + 1);
        }
        return <actual.TableCell {...props} />;
    };
    return { ...actual, TableCell };
});

// Sürükle-bırak olayları jsdom'da işaretçiyle üretilemez (yerleşim yok); sayfanın
// DndContext'e verdiği işleyiciler yakalanıp doğrudan çağrılır.
const dnd = vi.hoisted(() => ({ props: null as DndContextProps | null }));
vi.mock("@dnd-kit/core", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@dnd-kit/core")>();
    const DndContext = (props: DndContextProps) => {
        dnd.props = props;
        return <actual.DndContext {...props} />;
    };
    return { ...actual, DndContext };
});

import AdminPage from "./AdminPage";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Reply = { ok: boolean; json: () => Promise<unknown> };
const reply = (body: unknown, ok = true): Reply => ({ ok, json: async () => JSON.parse(JSON.stringify(body)) });

describe("AdminPage config listeleri render'da türetilir (G187)", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;
    let queryClient: QueryClient;
    // Sahte sunucu: her GET yeni bir JSON kopyası döner (gerçek ağ gibi yeni nesneler).
    let server: { lawyers: ConfigItem[]; emails: ConfigItem[] };
    // Sıralama isteğinin yanıtı; verilmezse sunucu sırayı uygular ve başarı döner.
    let reorderReply: (() => Promise<Reply>) | null;

    const lawyer = (code: string, name: string, extra: Partial<ConfigItem> = {}): ConfigItem =>
        ({ code, name, gorev: "AVUKAT", ...extra });

    const applyReorder = (body: { type: string; ordered_ids: string[] }) => {
        const list = body.type === "emails" ? server.emails : server.lawyers;
        const idOf = (i: ConfigItem) => (body.type === "emails" ? i.email : i.code) ?? "";
        const sorted = body.ordered_ids.map(id => list.find(i => idOf(i) === id)!).filter(Boolean);
        if (body.type === "emails") server.emails = sorted; else server.lawyers = sorted;
    };

    beforeEach(() => {
        vi.clearAllMocks();
        cellRenders.clear();
        dnd.props = null;
        reorderReply = null;
        server = {
            lawyers: [lawyer("AAA", "Av. Ayşe Ak"), lawyer("BBB", "Av. Burak Bal"), lawyer("CCC", "Av. Cem Can")],
            emails: [
                { email: "a@x.com", name: "Ali Alan" },
                { email: "b@x.com", name: "Banu Bora" },
            ],
        };
        authRequestMock.mockImplementation(async (url: string, _method: string, body?: unknown) => {
            if (url === "/api/config/lawyers") return reply(server.lawyers);
            if (url === "/api/config/email_recipients") return reply(server.emails);
            if (url === "/api/config/required_case_fields") return reply({ fields: [], party_rule: null });
            if (url === "/api/config/reorder") {
                if (reorderReply) return reorderReply();
                applyReorder(body as { type: string; ordered_ids: string[] });
                return reply({ status: "success" });
            }
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

    async function flush(): Promise<void> {
        for (let i = 0; i < 5; i++) {
            await act(async () => { await new Promise(r => setTimeout(r, 5)); });
        }
    }

    const callsTo = (url: string, method = "GET") =>
        authRequestMock.mock.calls.filter(([u, m]) => u === url && m === method).length;

    /** Açık sekmedeki tablonun satırlarında `col`. hücrenin metni (0 = sürükleme tutamacı). */
    const column = (col: number) =>
        Array.from(container.querySelectorAll("tbody tr")).map(tr => tr.querySelectorAll("td")[col]?.textContent ?? "");

    async function refetch(key: string): Promise<void> {
        await act(async () => { await queryClient.refetchQueries({ queryKey: ["config", key] }); });
        await flush();
    }

    const drag = (fn: (p: DndContextProps) => unknown) => act(async () => { await fn(dnd.props!); });
    const start = (id: string) => ({ active: { id } }) as unknown as DragStartEvent;
    const end = (id: string, overId: string | null) =>
        ({ active: { id }, over: overId === null ? null : { id: overId } }) as unknown as DragEndEvent;

    it("aynı içerikle yeniden çekilen liste satırları yeniden render ETMEZ; farklı içerikte güncellenir", async () => {
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");
        await flush();
        const before = cellRenders.get("Av. Ayşe Ak");
        expect(before).toBeGreaterThan(0);

        // Aynı içerik: istek gerçekten gider, ama dizi kimliği korunur → satırlar çizilmez.
        await refetch("lawyers");
        expect(callsTo("/api/config/lawyers")).toBe(2);
        expect(cellRenders.get("Av. Ayşe Ak")).toBe(before);

        // Farklı içerik: yeni ad ekrana gelir.
        server.lawyers = [lawyer("AAA", "Av. Ayşe Akın"), ...server.lawyers.slice(1)];
        await refetch("lawyers");
        expect(callsTo("/api/config/lawyers")).toBe(3);
        expect(column(2)).toEqual(["Av. Ayşe Akın", "Av. Burak Bal", "Av. Cem Can"]);
    });

    it("görev sırası render'da uygulanır (AVUKAT → DIŞ AVUKAT → görevsiz)", async () => {
        server.lawyers = [
            lawyer("ZZZ", "Av. Görevsiz", { gorev: undefined }),
            lawyer("DDD", "Av. Dış", { gorev: "DIŞ AVUKAT" }),
            lawyer("AAA", "Av. İç"),
        ];
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        expect(column(1)).toEqual(["AAA", "DDD", "ZZZ"]);
    });

    it("kaydedilmemiş düzenleme, aynı liste arka planda yeniden çekilince KAYBOLMAZ", async () => {
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        const editButton = container.querySelector("tbody tr td:last-child button") as HTMLButtonElement;
        act(() => { editButton.click(); });
        const nameInput = () => document.body.querySelector("[role='dialog'] input") as HTMLInputElement | null;
        expect(nameInput()?.value).toBe("Av. Ayşe Ak");

        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(nameInput()!, "Av. Taslak Ad");
            nameInput()!.dispatchEvent(new Event("input", { bubbles: true }));
        });
        expect(nameInput()?.value).toBe("Av. Taslak Ad");

        await refetch("lawyers");
        server.lawyers = [...server.lawyers, lawyer("EEE", "Av. Yeni Gelen")];
        await refetch("lawyers");

        expect(column(1)).toContain("EEE");
        expect(nameInput()?.value).toBe("Av. Taslak Ad");
    });

    it("sürükle-bırak: iyimser sıra kayıt sürerken görünür, kayıt bitince sunucu sırası okunur", async () => {
        let release!: () => void;
        reorderReply = () => new Promise<Reply>(resolve => {
            release = () => resolve(reply({ status: "success" }));
        });
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        await drag(p => p.onDragStart?.(start("AAA")));
        expect(column(1)).toEqual(["AAA", "BBB", "CCC"]);

        // Bırakma: sonuç beklenmeden yeni sıra ekranda, istek yeni sırayla gider.
        let ended!: Promise<unknown>;
        await act(async () => { ended = Promise.resolve(dnd.props!.onDragEnd?.(end("AAA", "CCC"))); });
        expect(column(1)).toEqual(["BBB", "CCC", "AAA"]);
        const reorderCall = authRequestMock.mock.calls.find(([u]) => u === "/api/config/reorder");
        expect(reorderCall?.[2]).toEqual({ type: "lawyers", ordered_ids: ["BBB", "CCC", "AAA"] });

        // Sunucu uygular, mutasyon listeyi yeniden çeker; ekran sunucu sırasını gösterir.
        server.lawyers = [server.lawyers[1], server.lawyers[2], server.lawyers[0]];
        await act(async () => { release(); await ended; });
        await flush();
        expect(callsTo("/api/config/lawyers")).toBe(2);
        expect(column(1)).toEqual(["BBB", "CCC", "AAA"]);

        // Geçici sıra temizlendi: sonraki sunucu değişikliği doğrudan görünür.
        server.lawyers = [server.lawyers[2], server.lawyers[0], server.lawyers[1]];
        await refetch("lawyers");
        expect(column(1)).toEqual(["AAA", "BBB", "CCC"]);
    });

    it("sıralama kaydedilemezse hata bildirilir ve sunucu sırasına dönülür", async () => {
        reorderReply = async () => reply({ detail: "bozuk" }, false);
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        await drag(p => p.onDragStart?.(start("AAA")));
        await drag(p => p.onDragEnd?.(end("AAA", "CCC")));
        await flush();

        expect(toastMock.error).toHaveBeenCalledWith("Sıralama kaydedilemedi.");
        expect(column(1)).toEqual(["AAA", "BBB", "CCC"]);
    });

    it("yerinden oynamayan bırakma ve vazgeçme istek atmaz, sıra ve sunucu güncellemesi korunur", async () => {
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        await drag(p => p.onDragStart?.(start("BBB")));
        await drag(p => p.onDragEnd?.(end("BBB", null)));
        await drag(p => p.onDragStart?.(start("BBB")));
        await drag(p => p.onDragEnd?.(end("BBB", "BBB")));
        await drag(p => p.onDragStart?.(start("CCC")));
        await drag(p => p.onDragCancel?.({ active: { id: "CCC" }, over: null } as unknown as DragCancelEvent));
        await flush();

        expect(callsTo("/api/config/reorder", "POST")).toBe(0);
        expect(column(1)).toEqual(["AAA", "BBB", "CCC"]);

        server.lawyers = [...server.lawyers].reverse();
        await refetch("lawyers");
        expect(column(1)).toEqual(["CCC", "BBB", "AAA"]);
    });

    it("e-posta alıcıları: kayıt önbelleği yenilemese de kaydedilen sıra ekranda kalır", async () => {
        render("/admin?tab=emails");
        await waitFor(() => column(1).length === 2, "alıcı satırları");

        await drag(p => p.onDragStart?.(start("a@x.com")));
        await drag(p => p.onDragEnd?.(end("a@x.com", "b@x.com")));
        await flush();

        expect(authRequestMock.mock.calls.find(([u]) => u === "/api/config/reorder")?.[2])
            .toEqual({ type: "emails", ordered_ids: ["b@x.com", "a@x.com"] });
        expect(toastMock.error).not.toHaveBeenCalled();
        expect(column(1)).toEqual(["Banu Bora", "Ali Alan"]);
    });
});
