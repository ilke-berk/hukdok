// @vitest-environment jsdom
// G086 (idari yarı) — İdari pano "04 · İnceleme · Süreli İşler".
// Bu dosya beş şeyi kilitler: dolu listenin ALICI + OKUNMA durumuyla çizilmesi,
// G080 hedefsiz sayacının görünmesi, DÜRÜST boş durum (sahte satır yok),
// kesintide DataErrorBanner (iki uç BAĞIMSIZ) ve şerhin panelde BİR KEZ durması.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: apiFetchMock } }));

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

import { TimedWorkPanel } from "./TimedWorkPanel";
import { DEADLINE_DISCLAIMER } from "./deadlineBody";
import { OVERVIEW_ENDPOINT, UNRESOLVED_ENDPOINT } from "./timedWorkOverview";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function jsonOk(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

const bozuk = { ok: false, status: 500, json: async () => ({}) };

/** Bugünden N gün sonrası, uçtaki `due_date` biçiminde (yalın gün). */
function gunSonra(n: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + n);
  const ay = String(d.getMonth() + 1).padStart(2, "0");
  const gun = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${ay}-${gun}`;
}

function ucSatiri(over: Record<string, unknown> = {}) {
  return {
    id: 7,
    type: "sure_yaklasti",
    severity: "info",
    // Donmuş metin: panel geri sayımı BURADAN okumamalı.
    title: "Süre yaklaşıyor: İstinaf başvuru süresi — 99 gün kaldı",
    recipient_email: "a.yilmaz@hanyaloglu-acar.av.tr",
    case_id: 4210,
    due_date: gunSonra(14),
    read_at: null,
    is_read: false,
    created_at: "2026-08-20T06:00:00+00:00",
    ...over,
  };
}

function ozetZarfi(items: unknown[], over: Record<string, unknown> = {}) {
  return {
    days: 30,
    limit: 100,
    total: items.length,
    unread: items.filter((x) => !(x as { is_read?: boolean }).is_read).length,
    items,
    ...over,
  };
}

const HEDEFSIZ = {
  items: [
    { name: "Arşiv Dosya Yöneticisi", case_count: 93 },
    { name: "Asu Barış Karamık", case_count: 4 },
  ],
  total_names: 2,
  total_cases: 97,
};

const HEDEFSIZ_BOS = { items: [], total_names: 0, total_cases: 0 };

/** İki ucu URL'sine göre yanıtlar — panel ikisini paralel çağırıyor. */
function uclariKur(ozet: unknown, hedefsiz: unknown = jsonOk(HEDEFSIZ_BOS)) {
  apiFetchMock.mockImplementation(async (endpoint: string) => {
    if (endpoint.startsWith("/api/notifications/overview")) return ozet;
    if (endpoint === UNRESOLVED_ENDPOINT) return hedefsiz;
    throw new Error(`beklenmeyen uç: ${endpoint}`);
  });
}

describe("TimedWorkPanel (G086 idari)", () => {
  let container: HTMLDivElement;
  let root: Root | null = null;
  let warnSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
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
    warnSpy.mockRestore();
  });

  async function ciz() {
    await act(async () => {
      root!.render(<TimedWorkPanel />);
    });
  }

  const satirlar = () => [...container.querySelectorAll("[data-testid='timed-work-row']")];

  it("iki idari ucu birer kez çağırır", async () => {
    uclariKur(jsonOk(ozetZarfi([])));
    await ciz();

    expect(apiFetchMock).toHaveBeenCalledTimes(2);
    expect(apiFetchMock).toHaveBeenCalledWith(OVERVIEW_ENDPOINT);
    expect(apiFetchMock).toHaveBeenCalledWith(UNRESOLVED_ENDPOINT);
  });

  it("dolu listede ALICI ve OKUNMA durumunu gösterir", async () => {
    uclariKur(
      jsonOk(
        ozetZarfi([
          ucSatiri(),
          ucSatiri({
            id: 8,
            type: "durusma_yaklasti",
            title: "Duruşma yaklaşıyor: 22.08.2026 — 2 gün kaldı",
            recipient_email: "b.kaya@hanyaloglu-acar.av.tr",
            due_date: gunSonra(2),
            is_read: true,
            read_at: new Date().toISOString(),
          }),
        ]),
      ),
    );
    await ciz();

    expect(satirlar()).toHaveLength(2);
    const metin = container.textContent ?? "";
    expect(metin).toContain("a.yilmaz@hanyaloglu-acar.av.tr");
    expect(metin).toContain("b.kaya@hanyaloglu-acar.av.tr");

    const okunma = [...container.querySelectorAll("[data-testid='timed-work-read']")].map(
      (n) => n.textContent ?? "",
    );
    expect(okunma[0]).toContain("Okunmadı");
    expect(okunma[1]).toContain("Okundu");
    expect(satirlar().map((r) => r.getAttribute("data-read"))).toEqual(["0", "1"]);
  });

  it("uçtan gelen sayaçları yazar — satırlardan saymaz", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()], { total: 12, unread: 5 })));
    await ciz();

    const ozet = container.querySelector("[data-testid='timed-work-summary']");
    expect(ozet).not.toBeNull();
    expect(ozet!.textContent).toContain("12 uyarı · 5 okunmamış");
    // Tavana dayanıldığı dürüstçe yazılır: 12 uyarının 1'i listeleniyor.
    expect(ozet!.textContent).toContain("12 uyarının en yakın 1 tanesi listeleniyor.");
  });

  it("geri sayımı due_date'ten hesaplar — donmuş başlık metnini kullanmaz", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()])));
    await ciz();

    expect(satirlar()[0].getAttribute("data-days-left")).toBe("14");
    expect(container.textContent).toContain("14 gün kaldı");
    expect(container.textContent).not.toContain("99 gün kaldı");
  });

  it("günü geçmiş ve okunmamış uyarı listeden DÜŞMEZ", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri({ due_date: gunSonra(-3) })])));
    await ciz();

    expect(satirlar()).toHaveLength(1);
    expect(container.textContent).toContain("3 gün geçti");
  });

  it("G080 hedefsiz sayacını dava sayılarıyla gösterir", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()])), jsonOk(HEDEFSIZ));
    await ciz();

    const sayac = container.querySelector("[data-testid='unresolved-targets']");
    expect(sayac).not.toBeNull();
    expect(sayac!.textContent).toContain("97 dava · 2 sorumlu adı");
    expect(sayac!.textContent).toContain("Arşiv Dosya Yöneticisi");
    expect(sayac!.textContent).toContain("93");
    expect(sayac!.textContent).toContain("Asu Barış Karamık");
    expect(container.querySelectorAll("[data-testid='unresolved-row']")).toHaveLength(2);
  });

  it("hedefsiz dava yoksa dürüst mesaj yazar", async () => {
    uclariKur(jsonOk(ozetZarfi([])), jsonOk(HEDEFSIZ_BOS));
    await ciz();

    const sayac = container.querySelector("[data-testid='unresolved-targets']");
    expect(sayac!.textContent).toContain("Sorumlusu bildirime çözülemeyen dava yok.");
    expect(container.querySelectorAll("[data-testid='unresolved-row']")).toHaveLength(0);
  });

  it("boş listede ÖRNEK SATIR üretmez, dürüst mesaj yazar", async () => {
    uclariKur(jsonOk(ozetZarfi([])));
    await ciz();

    expect(satirlar()).toHaveLength(0);
    expect(container.textContent).toContain("Bildirilmiş süre uyarısı yok");
    expect(container.querySelector("[role='alert']")).toBeNull();
  });

  it("şerh panelde BİR KEZ görünür", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri(), ucSatiri({ id: 8 })])));
    await ciz();

    const serhler = [...container.querySelectorAll("[data-testid='timed-work-disclaimer']")];
    expect(serhler).toHaveLength(1);
    expect(serhler[0].textContent).toContain(DEADLINE_DISCLAIMER);
    expect((container.textContent ?? "").split(DEADLINE_DISCLAIMER)).toHaveLength(2);
  });

  it("boş durumda da şerh görünür kalır", async () => {
    uclariKur(jsonOk(ozetZarfi([])));
    await ciz();

    expect(container.querySelectorAll("[data-testid='timed-work-disclaimer']")).toHaveLength(1);
  });

  it("özet ucu kesilince hata şeridi gösterir — boş liste gibi görünmez", async () => {
    uclariKur(bozuk, jsonOk(HEDEFSIZ));
    await ciz();

    const alert = container.querySelector("[role='alert']");
    expect(alert).not.toBeNull();
    expect(alert!.textContent).toContain("Süre bildirimleri alınamadı.");
    expect(container.textContent).not.toContain("Bildirilmiş süre uyarısı yok");
    // İki uç BAĞIMSIZ: ayakta olan sayaç gizlenmez.
    expect(container.querySelector("[data-testid='unresolved-targets']")).not.toBeNull();
  });

  it("beklenmedik özet gövdesi de hatadır", async () => {
    uclariKur(jsonOk({ unread: 3 }));
    await ciz();

    expect(container.querySelector("[role='alert']")).not.toBeNull();
    expect(container.textContent).not.toContain("Bildirilmiş süre uyarısı yok");
  });

  it("sayaç ucu kesilse bile liste çizilmeye devam eder", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()])), bozuk);
    await ciz();

    expect(satirlar()).toHaveLength(1);
    const hata = container.querySelector("[data-testid='unresolved-error']");
    expect(hata).not.toBeNull();
    expect(hata!.textContent).toContain("Hedefsiz dava sayacı alınamadı.");
    expect(container.querySelector("[data-testid='unresolved-targets']")).toBeNull();
  });

  it("Tekrar dene iki ucu da yeniden çağırır", async () => {
    uclariKur(bozuk, jsonOk(HEDEFSIZ_BOS));
    await ciz();
    expect(container.querySelector("[role='alert']")).not.toBeNull();

    uclariKur(jsonOk(ozetZarfi([ucSatiri()])), jsonOk(HEDEFSIZ_BOS));
    const buton = [...container.querySelectorAll("button")].find((b) =>
      (b.textContent ?? "").includes("Tekrar dene"),
    );
    expect(buton).toBeDefined();
    await act(async () => {
      buton!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(4);
    expect(satirlar()).toHaveLength(1);
  });

  it("satıra tıklayınca dava kartına gider", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()])));
    await ciz();

    const satirButonu = satirlar()[0].querySelector("button");
    expect(satirButonu).not.toBeNull();
    await act(async () => {
      satirButonu!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(navigateMock).toHaveBeenCalledWith("/cases/4210");
  });

  it("case_id yoksa tıklanabilir satır çizilmez", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri({ case_id: null })])));
    await ciz();

    expect(satirlar()).toHaveLength(1);
    expect(satirlar()[0].querySelector("button")).toBeNull();
  });

  it("hiçbir satırı okundu işaretlemez — SALT OKUMA", async () => {
    uclariKur(jsonOk(ozetZarfi([ucSatiri()])));
    await ciz();

    const cagrilar = apiFetchMock.mock.calls.map((c) => String(c[0]));
    expect(cagrilar.some((u) => u.includes("/read"))).toBe(false);
  });
});
