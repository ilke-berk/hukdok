// @vitest-environment jsdom
// FeatureSettingsCard — yönetici özellik anahtarları: listeleme, aç/kapa (PUT),
// hata durumunda geri alma. Backend sözleşmesi test_client_notice_switch.py'de
// kilitli; burada yalnız kartın uçlara nasıl bağlandığı sınanır.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMocks }));

import { FeatureSettingsCard, type FeatureSetting } from "./FeatureSettingsCard";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const ayar = (over: Partial<FeatureSetting> = {}): FeatureSetting => ({
    key: "client_notice_enabled",
    value: false,
    default: false,
    label: "Müvekkil bilgilendirme maili",
    description: "Sorumlu avukata müvekkile iletmesi için ayrı e-posta hazırlanır.",
    updated_by: null,
    updated_at: null,
    ...over,
});

const okJson = (payload: unknown) => ({ ok: true, json: async () => payload });
const failed = () => ({ ok: false, json: async () => ({}) });

describe("FeatureSettingsCard", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
        container = document.createElement("div");
        document.body.appendChild(container);
    });

    afterEach(() => {
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
    });

    async function render() {
        root = createRoot(container);
        await act(async () => {
            root!.render(<FeatureSettingsCard />);
        });
    }

    const anahtar = () => container.querySelector<HTMLButtonElement>("button[role='switch']")!;

    const tikla = async (el: Element) => {
        await act(async () => {
            el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
        });
    };

    it("ayarları listeler ve kapalı durumu gösterir", async () => {
        fetchMock.mockResolvedValue(okJson({ settings: [ayar()] }));

        await render();

        expect(fetchMock).toHaveBeenCalledWith("/api/admin/settings");
        expect(container.textContent).toContain("Müvekkil bilgilendirme maili");
        expect(container.textContent).toContain("Kapalı");
        expect(anahtar().getAttribute("aria-checked")).toBe("false");
    });

    it("anahtarı açınca PUT atar ve başarıyı bildirir", async () => {
        fetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
            if (options?.method === "PUT") return okJson({ status: "success", key: "client_notice_enabled", value: true });
            // İlk GET kapalı, PUT sonrası yeniden yükleme açık + iz döndürür.
            const acildi = fetchMock.mock.calls.some(([, o]) => (o as RequestInit | undefined)?.method === "PUT");
            return okJson({ settings: [ayar({ value: acildi, updated_by: acildi ? "yonetici@ofis.av.tr" : null })] });
        });

        await render();
        await tikla(anahtar());

        const putCall = fetchMock.mock.calls.find(([, o]) => (o as RequestInit | undefined)?.method === "PUT");
        expect(putCall?.[0]).toBe("/api/admin/settings/client_notice_enabled");
        expect(JSON.parse((putCall?.[1] as RequestInit).body as string)).toEqual({ value: true });
        expect(toastMocks.success).toHaveBeenCalled();
        expect(container.textContent).toContain("Açık");
        expect(container.textContent).toContain("yonetici@ofis.av.tr");
    });

    it("PUT başarısızsa eski değere geri döner ve hata bildirir", async () => {
        fetchMock.mockImplementation(async (_url: string, options?: RequestInit) =>
            options?.method === "PUT" ? failed() : okJson({ settings: [ayar()] }));

        await render();
        await tikla(anahtar());

        expect(toastMocks.error).toHaveBeenCalled();
        expect(anahtar().getAttribute("aria-checked")).toBe("false");
        expect(container.textContent).toContain("Kapalı");
    });

    it("liste alınamazsa hata metni gösterir", async () => {
        fetchMock.mockResolvedValue(failed());

        await render();

        expect(container.textContent).toContain("Ayarlar alınamadı");
    });
});
