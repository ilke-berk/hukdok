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

    // G229: sunucu avukata kurumsal kimlik de verir (G228); kodun ilk harfinden türetilir
    // (AAA → AVK-00001, BBB → AVK-00002, …). Satır tanımlayıcısı kimliktir, kod ekranda yok.
    const kimlikOf = (code: string) => `AVK-${String(code.charCodeAt(0) - 64).padStart(5, "0")}`;
    const lawyer = (code: string, name: string, extra: Partial<ConfigItem> = {}): ConfigItem =>
        ({ code, kimlik: kimlikOf(code), name, gorev: "AVUKAT", ...extra });
    const [K_A, K_B, K_C] = ["AAA", "BBB", "CCC"].map(kimlikOf);
    const [N_A, N_B, N_C] = ["Av. Ayşe Ak", "Av. Burak Bal", "Av. Cem Can"];

    const applyReorder = (body: { type: string; ordered_ids: string[] }) => {
        const list = body.type === "emails" ? server.emails : server.lawyers;
        const idOf = (i: ConfigItem) => (body.type === "emails" ? i.email : i.kimlik) ?? "";
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
        // G229: kod sütunu kalktı → ad artık 1. sütun (0 = sürükleme tutamacı).
        expect(column(1)).toEqual(["Av. Ayşe Akın", "Av. Burak Bal", "Av. Cem Can"]);
    });

    it("görev sırası render'da uygulanır (AVUKAT → DIŞ AVUKAT → görevsiz)", async () => {
        server.lawyers = [
            lawyer("ZZZ", "Av. Görevsiz", { gorev: undefined }),
            lawyer("DDD", "Av. Dış", { gorev: "DIŞ AVUKAT" }),
            lawyer("AAA", "Av. İç"),
        ];
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        expect(column(1)).toEqual(["Av. İç", "Av. Dış", "Av. Görevsiz"]);
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

        expect(column(1)).toContain("Av. Yeni Gelen");
        expect(nameInput()?.value).toBe("Av. Taslak Ad");
    });

    it("sürükle-bırak: iyimser sıra kayıt sürerken görünür, kayıt bitince sunucu sırası okunur", async () => {
        let release!: () => void;
        reorderReply = () => new Promise<Reply>(resolve => {
            release = () => resolve(reply({ status: "success" }));
        });
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        // G229: sürükleme/sıralama tanımlayıcısı kurumsal kimlik; ekranda ad okunur.
        await drag(p => p.onDragStart?.(start(K_A)));
        expect(column(1)).toEqual([N_A, N_B, N_C]);

        // Bırakma: sonuç beklenmeden yeni sıra ekranda, istek yeni sırayla gider.
        let ended!: Promise<unknown>;
        await act(async () => { ended = Promise.resolve(dnd.props!.onDragEnd?.(end(K_A, K_C))); });
        expect(column(1)).toEqual([N_B, N_C, N_A]);
        const reorderCall = authRequestMock.mock.calls.find(([u]) => u === "/api/config/reorder");
        expect(reorderCall?.[2]).toEqual({ type: "lawyers", ordered_ids: [K_B, K_C, K_A] });

        // Sunucu uygular, mutasyon listeyi yeniden çeker; ekran sunucu sırasını gösterir.
        server.lawyers = [server.lawyers[1], server.lawyers[2], server.lawyers[0]];
        await act(async () => { release(); await ended; });
        await flush();
        expect(callsTo("/api/config/lawyers")).toBe(2);
        expect(column(1)).toEqual([N_B, N_C, N_A]);

        // Geçici sıra temizlendi: sonraki sunucu değişikliği doğrudan görünür.
        server.lawyers = [server.lawyers[2], server.lawyers[0], server.lawyers[1]];
        await refetch("lawyers");
        expect(column(1)).toEqual([N_A, N_B, N_C]);
    });

    it("sıralama kaydedilemezse hata bildirilir ve sunucu sırasına dönülür", async () => {
        reorderReply = async () => reply({ detail: "bozuk" }, false);
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        await drag(p => p.onDragStart?.(start(K_A)));
        await drag(p => p.onDragEnd?.(end(K_A, K_C)));
        await flush();

        expect(toastMock.error).toHaveBeenCalledWith("Sıralama kaydedilemedi.");
        expect(column(1)).toEqual([N_A, N_B, N_C]);
    });

    it("yerinden oynamayan bırakma ve vazgeçme istek atmaz, sıra ve sunucu güncellemesi korunur", async () => {
        render();
        await waitFor(() => column(1).length === 3, "avukat satırları");

        await drag(p => p.onDragStart?.(start(K_B)));
        await drag(p => p.onDragEnd?.(end(K_B, null)));
        await drag(p => p.onDragStart?.(start(K_B)));
        await drag(p => p.onDragEnd?.(end(K_B, K_B)));
        await drag(p => p.onDragStart?.(start(K_C)));
        await drag(p => p.onDragCancel?.({ active: { id: K_C }, over: null } as unknown as DragCancelEvent));
        await flush();

        expect(callsTo("/api/config/reorder", "POST")).toBe(0);
        expect(column(1)).toEqual([N_A, N_B, N_C]);

        server.lawyers = [...server.lawyers].reverse();
        await refetch("lawyers");
        expect(column(1)).toEqual([N_C, N_B, N_A]);
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

// G256 — "Hizmet Türleri" sekmesi: karttaki hizmet açılır listesinin seçenekleri panelden
// yönetilir (ekle, yeniden adlandır, kullanımdaysa taşıyarak sil, sürükle-sırala). Gerçek
// `useConfig` kullanılır: mutasyon sonrası `["config","service_types"]` sorgusunun yeniden
// çekildiği (önbellek tazeleme) ancak böyle sınanır.
describe("AdminPage Hizmet Türleri sekmesi (G256)", () => {
    interface Usage {
        name: string;
        total: number;
        items: { label: string; count: number; clearable: boolean }[];
        clearable: boolean;
    }

    const SERVICE_URL = "/api/config/service_types";
    const RENAME_WARNING =
        "Veri ekibinin paketindeki ad değişmedikçe aktarım bu hizmeti tanımaz; ad değişikliğini veri ekibine bildirin.";

    let container: HTMLDivElement;
    let root: Root | null = null;
    let queryClient: QueryClient;
    // Sahte sunucu: liste her GET'te yeni JSON kopyası olarak döner.
    let services: ConfigItem[];
    let fileStatuses: ConfigItem[];
    let usage: Usage;

    beforeEach(() => {
        vi.clearAllMocks();
        dnd.props = null;
        services = [
            { code: "TAKIP-DOKTOR-MUVEKKIL", name: "Takip (doktor müvekkil)" },
            { code: "LEXIS-RAPOR", name: "Lexis Rapor" },
            { code: "DANISMANLIK", name: "Danışmanlık" },
        ];
        fileStatuses = [{ code: "BILIRKISIDE", name: "Bilirkişide" }];
        usage = { name: "Lexis Rapor", total: 0, items: [], clearable: true };
        authRequestMock.mockImplementation(async (url: string, method: string, body?: unknown) => {
            if (url === SERVICE_URL && method === "GET") return reply(services);
            if (url === SERVICE_URL && method === "POST") {
                services = [...services, body as ConfigItem];
                return reply({ status: "success" });
            }
            if (url === "/api/config/file_statuses") return reply(fileStatuses);
            if (url === "/api/config/required_case_fields") return reply({ fields: [], party_rule: null });
            if (url === "/api/config/update") {
                const { code, fields } = body as { code: string; fields: { name: string } };
                services = services.map(s => (s.code === code ? { ...s, name: fields.name } : s));
                return reply({ status: "success", updated: 4 });
            }
            if (url === "/api/config/reorder") {
                const { ordered_ids } = body as { ordered_ids: string[] };
                services = ordered_ids.map(id => services.find(s => s.code === id)!).filter(Boolean);
                return reply({ status: "success" });
            }
            if (url.startsWith("/api/config/usage")) return reply(usage);
            if (url === "/api/config/delete") {
                const { code } = body as { code: string };
                services = services.filter(s => s.code !== code);
                return reply({ status: "success", affected: usage.total });
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
        vi.restoreAllMocks();
    });

    function render(url = "/admin?tab=service_types") {
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

    const callsTo = (url: string, method: string) =>
        authRequestMock.mock.calls.filter(([u, m]) => u === url && m === method);
    const bodyOf = (url: string) => callsTo(url, "POST").map(c => c[2]);

    /** Açık sekmedeki tablonun ad sütunu (0 = sürükleme tutamacı). */
    const names = () =>
        Array.from(container.querySelectorAll("tbody tr")).map(tr => tr.querySelectorAll("td")[1]?.textContent ?? "");
    const rowOf = (name: string) =>
        Array.from(container.querySelectorAll("tbody tr")).find(tr => tr.querySelectorAll("td")[1]?.textContent === name)!;
    /** Satırın işlem düğmeleri: [düzenle, sil]. */
    const rowButtons = (name: string) =>
        Array.from(rowOf(name).querySelectorAll("td:last-child button")) as HTMLButtonElement[];

    const dialog = () => document.body.querySelector("[role='dialog']") as HTMLElement | null;
    const dialogButton = (text: string) =>
        Array.from(dialog()!.querySelectorAll("button")).find(b => b.textContent?.trim() === text) as HTMLButtonElement;
    const click = (el: HTMLElement) => act(async () => { el.click(); });

    function typeInto(input: HTMLInputElement, value: string) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
        act(() => {
            setter.call(input, value);
            input.dispatchEvent(new Event("input", { bubbles: true }));
        });
    }

    async function openTab(): Promise<void> {
        render();
        await waitFor(() => names().length === 3, "hizmet türü satırları");
    }

    it("?tab=service_types sekmeyi açar; liste sunucu sırasıyla basılır, arama süzer, Excel aktarımı görünür", async () => {
        await openTab();

        expect(container.querySelector("[role='tab'][data-state='active']")?.textContent).toBe("Hizmet Türleri");
        expect(names()).toEqual(["Takip (doktor müvekkil)", "Lexis Rapor", "Danışmanlık"]);
        // Excel dışa aktarımı TAB_TO_LIST'ten çözülür — sekmede düğme görünür.
        expect(Array.from(container.querySelectorAll("button")).some(b => b.textContent?.includes("Excel'e Aktar"))).toBe(true);

        typeInto(container.querySelector("input[placeholder='Ara...']") as HTMLInputElement, "lexis");
        expect(names()).toEqual(["Lexis Rapor"]);
    });

    it("ekleme: yalnız ad girilir, kod addan üretilir; POST gövdesi {code, name} ve liste yeniden çekilir", async () => {
        await openTab();

        await click(Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes("Yeni Hizmet Türü"))!);
        const inputs = dialog()!.querySelectorAll("input");
        expect(inputs.length).toBe(1);   // yalnız ad — kod alanı yok
        typeInto(inputs[0], "sulh görüşmesi (şirket)");
        await click(dialogButton("Kaydet"));
        await waitFor(() => names().length === 4, "eklenen satır");

        // Ad yazarken başlık biçimine çevrilir; kod seed biçiminde (ASCII, "-" ayraçlı).
        expect(callsTo(SERVICE_URL, "POST").map(c => c[2]))
            .toEqual([{ code: "SULH-GORUSMESI-SIRKET", name: "Sulh Görüşmesi (şirket)" }]);
        expect(callsTo(SERVICE_URL, "GET").length).toBe(2);
        expect(toastMock.success).toHaveBeenCalledWith("Eklendi");
        expect(names()).toContain("Sulh Görüşmesi (şirket)");
    });

    it("ekleme: boş ad istek atmaz; benzer ad onaylanmazsa istek atmaz", async () => {
        const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
        await openTab();

        await click(Array.from(container.querySelectorAll("button")).find(b => b.textContent?.includes("Yeni Hizmet Türü"))!);
        await click(dialogButton("Kaydet"));
        expect(toastMock.warning).toHaveBeenCalledWith("İsim zorunlu");

        typeInto(dialog()!.querySelector("input") as HTMLInputElement, "Lexis Raporu");
        await click(dialogButton("Kaydet"));

        expect(confirmSpy).toHaveBeenCalledTimes(1);
        expect(String(confirmSpy.mock.calls[0][0])).toContain("Lexis Rapor");
        expect(callsTo(SERVICE_URL, "POST").length).toBe(0);
    });

    it("yeniden adlandırma: diyalogda veri ekibi uyarısı; kayıt sonrası yansıyan kayıt sayısı ve tazelenen liste", async () => {
        await openTab();

        await click(rowButtons("Lexis Rapor")[0]);
        expect(dialog()!.textContent).toContain(RENAME_WARNING);
        const input = dialog()!.querySelector("input") as HTMLInputElement;
        expect(input.value).toBe("Lexis Rapor");
        typeInto(input, "Lexis Raporu");
        await click(dialogButton("Kaydet"));
        await waitFor(() => names().includes("Lexis Raporu"), "yeni ad ekranda");

        expect(bodyOf("/api/config/update"))
            .toEqual([{ type: "service_types", code: "LEXIS-RAPOR", fields: { name: "Lexis Raporu" } }]);
        expect(toastMock.success).toHaveBeenCalledWith("Güncellendi — eski adı taşıyan 4 kayıt da yansıtıldı");
        // Önbellek tazelendi: service_types sorgusu yeniden çekildi.
        expect(callsTo(SERVICE_URL, "GET").length).toBe(2);
        expect(names()).toEqual(["Takip (doktor müvekkil)", "Lexis Raporu", "Danışmanlık"]);
    });

    it("veri ekibi uyarısı yalnız hizmet türlerinde çıkar (dosya durumu düzenlemesinde yok)", async () => {
        render("/admin?tab=file_statuses");
        await waitFor(() => names().length === 1, "dosya durumu satırı");

        await click(rowButtons("Bilirkişide")[0]);

        expect((dialog()!.querySelector("input") as HTMLInputElement).value).toBe("Bilirkişide");
        expect(dialog()!.textContent).not.toContain(RENAME_WARNING);
    });

    it("sürükle-bırak: yeni sıra /api/config/reorder'a kodlarla gider ve liste yeniden çekilir", async () => {
        await openTab();

        await act(async () => { await dnd.props!.onDragStart?.({ active: { id: "TAKIP-DOKTOR-MUVEKKIL" } } as unknown as DragStartEvent); });
        await act(async () => {
            await dnd.props!.onDragEnd?.({ active: { id: "TAKIP-DOKTOR-MUVEKKIL" }, over: { id: "DANISMANLIK" } } as unknown as DragEndEvent);
        });
        await waitFor(() => callsTo(SERVICE_URL, "GET").length === 2, "sıralama sonrası yeniden çekme");

        expect(bodyOf("/api/config/reorder"))
            .toEqual([{ type: "service_types", ordered_ids: ["LEXIS-RAPOR", "DANISMANLIK", "TAKIP-DOKTOR-MUVEKKIL"] }]);
        expect(toastMock.error).not.toHaveBeenCalled();
        expect(names()).toEqual(["Lexis Rapor", "Danışmanlık", "Takip (doktor müvekkil)"]);
    });

    it("silme: kullanımdaki değerde sayı gösterilir, 'boşalt' devre dışı, yalnız başka değere taşınır", async () => {
        usage = {
            name: "Lexis Rapor", total: 7, clearable: false,
            items: [{ label: "dava hizmeti", count: 7, clearable: false }],
        };
        await openTab();

        await click(rowButtons("Lexis Rapor")[1]);
        await waitFor(() => dialog()?.querySelectorAll("input[type='radio']").length === 2, "silme seçenekleri");

        expect(callsTo("/api/config/usage?type=service_types&code=LEXIS-RAPOR", "GET").length).toBe(1);
        expect(dialog()!.textContent).toContain("dava hizmeti");
        expect(dialog()!.querySelector("li")?.textContent).toContain("7");
        const [clearRadio, reassignRadio] = Array.from(dialog()!.querySelectorAll("input[type='radio']")) as HTMLInputElement[];
        expect(clearRadio.disabled).toBe(true);
        expect(clearRadio.checked).toBe(false);
        expect(reassignRadio.disabled).toBe(false);
        expect(reassignRadio.checked).toBe(true);

        // Hedef seçilmeden silinmez.
        await click(dialogButton("Sil"));
        expect(toastMock.warning).toHaveBeenCalledWith("Taşınacak kaydı seçin");
        expect(callsTo("/api/config/delete", "POST").length).toBe(0);

        // Hedef adayları: silinen değerin kendisi dışındaki hizmet türleri.
        const select = dialog()!.querySelector("select") as HTMLSelectElement;
        expect(Array.from(select.options).map(o => o.value)).toEqual(["", "TAKIP-DOKTOR-MUVEKKIL", "DANISMANLIK"]);
        act(() => {
            select.value = "DANISMANLIK";
            select.dispatchEvent(new Event("change", { bubbles: true }));
        });
        await click(dialogButton("Sil"));
        await waitFor(() => names().length === 2, "silinen satır listeden çıktı");

        expect(bodyOf("/api/config/delete"))
            .toEqual([{ type: "service_types", code: "LEXIS-RAPOR", mode: "reassign", target_code: "DANISMANLIK" }]);
        expect(toastMock.success).toHaveBeenCalledWith("Silindi — 7 kayıt taşındı");
        expect(callsTo(SERVICE_URL, "GET").length).toBe(2);
        expect(names()).toEqual(["Takip (doktor müvekkil)", "Danışmanlık"]);
    });

    it("silme: kullanılmayan değer seçenek sorulmadan doğrudan silinir", async () => {
        await openTab();

        await click(rowButtons("Lexis Rapor")[1]);
        await waitFor(() => dialog()?.textContent?.includes("güvenle silinebilir") ?? false, "kullanım yok bilgisi");
        expect(dialog()!.querySelectorAll("input[type='radio']").length).toBe(0);
        await click(dialogButton("Sil"));
        await waitFor(() => names().length === 2, "silinen satır listeden çıktı");

        expect(bodyOf("/api/config/delete"))
            .toEqual([{ type: "service_types", code: "LEXIS-RAPOR", mode: "keep", target_code: undefined }]);
        expect(toastMock.success).toHaveBeenCalledWith("Silindi");
        expect(callsTo(SERVICE_URL, "GET").length).toBe(2);
    });
});
