// @vitest-environment jsdom
// G086 — Avukat panosu "02 · Süre / Vade · Süre Uyarıları".
// Bu dosya beş şeyi kilitler: dolu listenin TAZE geri sayımla ve dayanağıyla
// çizilmesi, DÜRÜST boş durum (sahte satır yok), kesintide DataErrorBanner,
// şerhin panelde BİR KEZ görünmesi ve "takvim doğrulanmadı" işaretinin satırda
// ayrıca belirtilmesi.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: apiFetchMock } }));

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

import type { NotificationItem } from "@/hooks/useNotifications";
import { DeadlineWarningsPanel, DEADLINE_FETCH_LIMIT } from "./DeadlineWarningsPanel";
import { DEADLINE_DISCLAIMER } from "./deadlineBody";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function jsonOk(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

/** Bugünden N gün sonrası, uçtaki `due_date` biçiminde (yalın gün). */
function gunSonra(n: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + n);
  const ay = String(d.getMonth() + 1).padStart(2, "0");
  const gun = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${ay}-${gun}`;
}

const TAKVIM_UYARISI =
  "DİKKAT: son günün yılı için resmî tatil takvimi doğrulanmadı — " +
  "hafta sonu/resmî tatil kaydırması UYGULANMADI, son gün elle teyit edilmeli.";

function sureBildirimi(over: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 1,
    type: "sure_yaklasti",
    severity: "info",
    // Donmuş metin: panel geri sayımı BURADAN okumamalı.
    title: "Süre yaklaşıyor: İstinaf başvuru süresi — 99 gün kaldı",
    body: [
      "Dava: D1.H_YILMAZ..0002.HUKUK.00000 · 2024/118 · Ankara 5. Asliye Hukuk Mahkemesi",
      "Aşama: Yerel mahkeme (YEREL, 1. karar)",
      "Tebliğ tarihi: 12.08.2026",
      "Kural: İstinaf başvuru süresi — HMK m. 345/1 (iki hafta, ilamın tebliğinden itibaren)",
      "Son gün: 03.09.2026 (99 gün kaldı)",
      DEADLINE_DISCLAIMER,
    ].join("\n"),
    case_id: 4210,
    document_id: null,
    due_date: gunSonra(14),
    read_at: null,
    is_read: false,
    created_at: "2026-08-20T06:00:00",
    ...over,
  };
}

function durusmaBildirimi(over: Partial<NotificationItem> = {}): NotificationItem {
  return sureBildirimi({
    id: 2,
    type: "durusma_yaklasti",
    severity: "warning",
    title: "Duruşma yaklaşıyor: 22.08.2026 — 2 gün kaldı",
    body: [
      "Dava: D1.M_KAYA....0001.IDARE.00000 · 2025/9 · İstanbul 2. İdare Mahkemesi",
      "Duruşma: 22.08.2026 10:30 (2 gün kaldı)",
      "Kaynak belge: durusma_zapti.pdf",
      DEADLINE_DISCLAIMER,
    ].join("\n"),
    case_id: 5150,
    due_date: gunSonra(2),
    ...over,
  });
}

describe("DeadlineWarningsPanel (G086)", () => {
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
      root!.render(<DeadlineWarningsPanel />);
    });
  }

  const satirlar = () => [...container.querySelectorAll("[data-testid='deadline-row']")];

  it("uca tavan limitiyle tek istek atar", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    await ciz();
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(apiFetchMock).toHaveBeenCalledWith(`/api/notifications?limit=${DEADLINE_FETCH_LIMIT}`);
  });

  it("dolu listede satırları çizer ve dayanağı gösterir", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi()]));
    await ciz();

    expect(satirlar()).toHaveLength(1);
    const metin = container.textContent ?? "";
    expect(metin).toContain("İstinaf başvuru süresi");
    // Kabul kriteri: aşama + tebliğ tarihi + uygulanan kural görünür.
    expect(metin).toContain("Aşama");
    expect(metin).toContain("Yerel mahkeme (YEREL, 1. karar)");
    expect(metin).toContain("Tebliğ tarihi");
    expect(metin).toContain("12.08.2026");
    expect(metin).toContain("HMK m. 345/1");
  });

  it("geri sayımı due_date'ten hesaplar — donmuş başlık metnini kullanmaz", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi()]));
    await ciz();

    expect(satirlar()[0].getAttribute("data-days-left")).toBe("14");
    expect(container.textContent).toContain("14 gün kaldı");
    expect(container.textContent).not.toContain("99 gün kaldı");
  });

  it("en yakın tarih en üstte sıralanır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi(), durusmaBildirimi()]));
    await ciz();

    expect(satirlar().map((r) => r.getAttribute("data-days-left"))).toEqual(["2", "14"]);
  });

  it("günü geçmiş bildirim listelenmez, boş durum gösterilir", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi({ due_date: gunSonra(-1) })]));
    await ciz();

    expect(satirlar()).toHaveLength(0);
    expect(container.textContent).toContain("Yaklaşan süre yok");
  });

  it("boş listede ÖRNEK SATIR üretmez, dürüst mesaj yazar", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    await ciz();

    expect(satirlar()).toHaveLength(0);
    expect(container.textContent).toContain("Yaklaşan süre yok");
    expect(container.querySelector("[role='alert']")).toBeNull();
  });

  it("süre/duruşma dışı bildirimler panele sızmaz", async () => {
    apiFetchMock.mockResolvedValue(
      jsonOk([sureBildirimi({ id: 9, type: "belge_islendi", title: "Belge işlendi" })]),
    );
    await ciz();

    expect(satirlar()).toHaveLength(0);
    expect(container.textContent).not.toContain("Belge işlendi");
  });

  it("şerh panelde BİR KEZ görünür — satır başına tekrar etmez", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi(), durusmaBildirimi()]));
    await ciz();

    const serhler = [...container.querySelectorAll("[data-testid='deadline-disclaimer']")];
    expect(serhler).toHaveLength(1);
    expect(serhler[0].textContent).toContain(DEADLINE_DISCLAIMER);
    expect((container.textContent ?? "").split(DEADLINE_DISCLAIMER)).toHaveLength(2);
  });

  it("boş durumda da şerh görünür kalır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    await ciz();

    expect(container.querySelectorAll("[data-testid='deadline-disclaimer']")).toHaveLength(1);
  });

  it("takvim doğrulanmadı işareti satırda ayrıca belirtilir", async () => {
    const bildirim = sureBildirimi();
    apiFetchMock.mockResolvedValue(
      jsonOk([{ ...bildirim, body: `${bildirim.body}\n${TAKVIM_UYARISI}` }]),
    );
    await ciz();

    const uyari = container.querySelector("[data-testid='calendar-warning']");
    expect(uyari).not.toBeNull();
    expect(uyari!.textContent).toContain("resmî tatil takvimi doğrulanmadı");
  });

  it("uyarı yoksa takvim şeridi çizilmez", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi()]));
    await ciz();

    expect(container.querySelector("[data-testid='calendar-warning']")).toBeNull();
  });

  it("kesintide hata şeridi gösterir — boş liste gibi görünmez", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    await ciz();

    const alert = container.querySelector("[role='alert']");
    expect(alert).not.toBeNull();
    expect(alert!.textContent).toContain("Süre uyarıları alınamadı.");
    expect(container.textContent).not.toContain("Yaklaşan süre yok");
  });

  it("beklenmedik gövde de hatadır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk({ unread: 3 }));
    await ciz();

    expect(container.querySelector("[role='alert']")).not.toBeNull();
    expect(container.textContent).not.toContain("Yaklaşan süre yok");
  });

  it("Tekrar dene ucu yeniden çağırır", async () => {
    apiFetchMock.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({}) });
    await ciz();
    expect(container.querySelector("[role='alert']")).not.toBeNull();

    apiFetchMock.mockResolvedValueOnce(jsonOk([sureBildirimi()]));
    const buton = [...container.querySelectorAll("button")].find((b) =>
      (b.textContent ?? "").includes("Tekrar dene"),
    );
    expect(buton).toBeDefined();
    await act(async () => {
      buton!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(apiFetchMock).toHaveBeenCalledTimes(2);
    expect(satirlar()).toHaveLength(1);
  });

  it("satıra tıklayınca dava kartına gider", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi()]));
    await ciz();

    const satirButonu = satirlar()[0].querySelector("button");
    expect(satirButonu).not.toBeNull();
    await act(async () => {
      satirButonu!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(navigateMock).toHaveBeenCalledWith("/cases/4210");
  });

  it("case_id yoksa tıklanabilir satır çizilmez", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([sureBildirimi({ case_id: null })]));
    await ciz();

    expect(satirlar()).toHaveLength(1);
    expect(satirlar()[0].querySelector("button")).toBeNull();
  });
});
