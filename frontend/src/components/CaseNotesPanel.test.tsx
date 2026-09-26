// @vitest-environment jsdom
// CaseNotesPanel (G215) — dava kartının tarihli not paneli. `apiClient` sahte (yol+yönteme göre
// yanıt); panel lib/caseNotes üzerinden gerçek eşlemeyle koşar. Kilitlenenler: listeleme sırası
// ve biçimi, "Henüz not yok", sınır doğrulaması + sayaç, ekleme sonrası YENİDEN ÇEKME (iyimser
// güncelleme yok), can_delete'e göre Sil, silme onayı, 403/404 Türkçe hata, HTML kaçışı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: fetchMock } }));
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

import CaseNotesPanel from "./CaseNotesPanel";
import type { CaseNote } from "@/lib/caseNotes";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const jsonYanit = (status: number, body: unknown) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const YENI: CaseNote = {
    id: 2,
    body: "İkinci satır\nüçüncü satır",
    author_name: null,
    author_email: "mehmet@example.com",
    created_at: "2026-09-26T07:05:00Z",
    can_delete: false,
};
const ESKI: CaseNote = {
    id: 1,
    body: "İlk not",
    author_name: "Av. Ayşe Kaya",
    author_email: "ayse@example.com",
    created_at: "2026-09-25T12:00:00Z",
    can_delete: true,
};

/** Sunucu durumu: GET bu listeyi döner; testler POST/DELETE yanıtını ayarlar. */
let sunucuNotlari: CaseNote[] = [];
let postYaniti: () => Response = () => jsonYanit(201, YENI);
let deleteYaniti: () => Response = () => new Response(null, { status: 204 });

const cagrilar = (method: string) =>
    fetchMock.mock.calls.filter(([, o]) => ((o as RequestInit | undefined)?.method ?? "GET") === method);

describe("CaseNotesPanel", () => {
    let container: HTMLDivElement;
    let root: Root | null = null;

    beforeEach(() => {
        vi.clearAllMocks();
        sunucuNotlari = [YENI, ESKI];
        postYaniti = () => jsonYanit(201, YENI);
        deleteYaniti = () => new Response(null, { status: 204 });
        fetchMock.mockImplementation(async (_yol: string, o?: RequestInit) => {
            const m = o?.method ?? "GET";
            if (m === "POST") return postYaniti();
            if (m === "DELETE") return deleteYaniti();
            return jsonYanit(200, sunucuNotlari);
        });
        container = document.createElement("div");
        document.body.appendChild(container);
    });

    afterEach(() => {
        if (root) {
            act(() => root!.unmount());
            root = null;
        }
        container.remove();
        vi.restoreAllMocks();
    });

    const bas = async () => {
        await act(async () => {
            root = createRoot(container);
            root.render(<CaseNotesPanel caseId={42} />);
        });
    };

    const q = <T extends Element = HTMLElement>(testId: string) =>
        container.querySelector<T>(`[data-testid="${testId}"]`);
    const qa = (testId: string) => Array.from(container.querySelectorAll(`[data-testid="${testId}"]`));

    const yaz = async (deger: string) => {
        const ta = q<HTMLTextAreaElement>("case-note-input")!;
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
        await act(async () => {
            setter.call(ta, deger);
            ta.dispatchEvent(new Event("input", { bubbles: true }));
        });
    };
    const ekleDugmesi = () => q<HTMLButtonElement>("case-note-add")!;

    it("listeyi sunucu sırasıyla basar: yazan adı (yoksa e-posta), TR tarih-saat, satır sonları", async () => {
        await bas();
        expect(fetchMock.mock.calls[0][0]).toBe("/api/cases/42/notes");
        const ogeler = qa("case-note-item");
        expect(ogeler).toHaveLength(2);
        expect(ogeler[0].textContent).toContain("mehmet@example.com");
        expect(ogeler[0].textContent).toContain("26.09.2026 10:05");
        expect(ogeler[1].textContent).toContain("Av. Ayşe Kaya");
        expect(ogeler[1].textContent).toContain("25.09.2026 15:00");
        const govde = ogeler[0].querySelector('[data-testid="case-note-body"]')!;
        expect(govde.textContent).toBe("İkinci satır\nüçüncü satır");
        expect(govde.className).toContain("whitespace-pre-wrap");
        expect(q("case-notes-empty")).toBeNull();
    });

    it("liste boşken 'Henüz not yok'", async () => {
        sunucuNotlari = [];
        await bas();
        expect(q("case-notes-empty")?.textContent).toBe("Henüz not yok");
        expect(qa("case-note-item")).toHaveLength(0);
    });

    it("not metni HTML olarak yorumlanmaz", async () => {
        sunucuNotlari = [{ ...ESKI, body: '<img src=x onerror="alert(1)"><b>kalın</b>' }];
        await bas();
        const govde = q("case-note-body")!;
        expect(govde.querySelector("img")).toBeNull();
        expect(govde.querySelector("b")).toBeNull();
        expect(govde.textContent).toBe('<img src=x onerror="alert(1)"><b>kalın</b>');
    });

    it("Sil düğmesi yalnız can_delete=true notlarda", async () => {
        await bas();
        const ogeler = qa("case-note-item");
        expect(ogeler[0].querySelector('[data-testid="case-note-delete"]')).toBeNull();
        expect(ogeler[1].querySelector('[data-testid="case-note-delete"]')).not.toBeNull();
        expect(qa("case-note-delete")).toHaveLength(1);
    });

    it("sınır doğrulaması: boş/boşluk ve 5000 üstü pasif; sayaç 4500'den sonra", async () => {
        await bas();
        expect(ekleDugmesi().disabled).toBe(true);
        await yaz("   \n  ");
        expect(ekleDugmesi().disabled).toBe(true);
        await yaz("a");
        expect(ekleDugmesi().disabled).toBe(false);
        expect(q("case-note-counter")).toBeNull();
        await yaz("a".repeat(4500));
        expect(q("case-note-counter")).toBeNull();
        await yaz("a".repeat(4501));
        expect(q("case-note-counter")?.textContent).toBe("499 karakter kaldı");
        await yaz("a".repeat(5000));
        expect(ekleDugmesi().disabled).toBe(false);
        expect(q("case-note-counter")?.textContent).toBe("0 karakter kaldı");
        await yaz("a".repeat(5001));
        expect(ekleDugmesi().disabled).toBe(true);
        expect(q("case-note-counter")?.textContent).toBe("1 karakter fazla");
    });

    it("ekleme: gönderimde düğme pasif, başarıda kutu temizlenir ve liste YENİDEN çekilir", async () => {
        sunucuNotlari = [ESKI];
        await bas();
        expect(cagrilar("GET")).toHaveLength(1);

        let postCoz: (r: Response) => void = () => undefined;
        fetchMock.mockImplementationOnce(
            (_yol: string, o?: RequestInit) =>
                new Promise<Response>(res => {
                    expect(o?.method).toBe("POST");
                    postCoz = res;
                }),
        );

        await yaz("  Yeni not  ");
        await act(async () => {
            ekleDugmesi().click();
        });
        // gönderim sürerken düğme pasif
        expect(ekleDugmesi().disabled).toBe(true);
        const [yol, secenek] = cagrilar("POST")[0];
        expect(yol).toBe("/api/cases/42/notes");
        expect(JSON.parse((secenek as RequestInit).body as string)).toEqual({ body: "Yeni not" });
        // iyimser güncelleme yok: sunucu cevap vermeden liste değişmez
        expect(qa("case-note-item")).toHaveLength(1);

        sunucuNotlari = [YENI, ESKI];
        await act(async () => {
            postCoz(jsonYanit(201, YENI));
        });
        expect(cagrilar("GET")).toHaveLength(2);
        expect(qa("case-note-item")).toHaveLength(2);
        expect(q<HTMLTextAreaElement>("case-note-input")!.value).toBe("");
    });

    it("ekleme hatasında toast, kutu korunur", async () => {
        postYaniti = () => new Response(null, { status: 422 });
        await bas();
        await yaz("Not");
        await act(async () => {
            ekleDugmesi().click();
        });
        expect(toastMock.error).toHaveBeenCalledWith("Not boş olamaz ve en fazla 5000 karakter olabilir.");
        expect(q<HTMLTextAreaElement>("case-note-input")!.value).toBe("Not");
        expect(cagrilar("GET")).toHaveLength(1);
    });

    it("silme onay sorar; vazgeçilirse istek gitmez", async () => {
        const onay = vi.spyOn(window, "confirm").mockReturnValue(false);
        await bas();
        await act(async () => {
            q<HTMLButtonElement>("case-note-delete")!.click();
        });
        expect(onay).toHaveBeenCalledTimes(1);
        expect(cagrilar("DELETE")).toHaveLength(0);
    });

    it("onaylanan silme DELETE atar ve listeyi yeniden çeker", async () => {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        await bas();
        sunucuNotlari = [YENI];
        await act(async () => {
            q<HTMLButtonElement>("case-note-delete")!.click();
        });
        const [yol] = cagrilar("DELETE")[0];
        expect(yol).toBe("/api/cases/42/notes/1");
        expect(cagrilar("GET")).toHaveLength(2);
        expect(qa("case-note-item")).toHaveLength(1);
        expect(toastMock.error).not.toHaveBeenCalled();
    });

    it("silmede 403 ve 404 Türkçe hata verir", async () => {
        vi.spyOn(window, "confirm").mockReturnValue(true);
        deleteYaniti = () => new Response(null, { status: 403 });
        await bas();
        await act(async () => {
            q<HTMLButtonElement>("case-note-delete")!.click();
        });
        expect(toastMock.error).toHaveBeenLastCalledWith(
            "Bu notu silme yetkiniz yok (yalnız yazan ya da yönetici silebilir).",
        );

        deleteYaniti = () => new Response(null, { status: 404 });
        await act(async () => {
            q<HTMLButtonElement>("case-note-delete")!.click();
        });
        expect(toastMock.error).toHaveBeenLastCalledWith("Not bulunamadı; daha önce silinmiş olabilir.");
        expect(cagrilar("GET")).toHaveLength(1);
    });
});
