// @vitest-environment jsdom
// G079 — Avukat panosu "Yeni İşlenen — son 24 saat" paneli.
// Panel G078'in ucunu (`GET /api/documents/recent`) tüketir. Bu dosya dört şeyi
// kilitler: gerçek verinin çizilmesi, DÜRÜST boş durum (sahte satır yok),
// kesintide DataErrorBanner, ve mail rozetinin ÜÇ ayrı durumu (true/false/null).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ apiClient: { fetch: apiFetchMock } }));

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router", () => ({ useNavigate: () => navigateMock }));

import { RecentDocumentsPanel, type RecentDocument } from "./RecentDocumentsPanel";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function jsonOk(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

/** Mail gitmiş belge — tebligat, bağlı taraf adıyla. */
const mailliBelge: RecentDocument = {
  id: 101,
  case_id: 4210,
  tracking_no: "D1.H_YILMAZ..0002.HUKUK.00000",
  esas_no: "2024/118",
  original_filename: "tebligat.pdf",
  belge_turu_kodu: "TEBLIGAT______",
  belge_turu_adi: "Tebligat",
  case_party_name: "H. YILMAZ",
  muvekkil_adi: "H. YILMAZ",
  uploaded_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
  uploaded_by: "avukat@ornek.tr",
  email_sent: true,
  email_error: null,
};

/** Gönderim DENENDİ ve düştü — email_error dolu. */
const mailHataliBelge: RecentDocument = {
  id: 102,
  case_id: 4211,
  tracking_no: "D1.M_KAYA....0001.IDARE.00000",
  esas_no: null,
  original_filename: "karar.pdf",
  belge_turu_kodu: "ARA-KRR_______",
  belge_turu_adi: "Ara Karar",
  case_party_name: null,
  muvekkil_adi: "M. KAYA",
  uploaded_at: new Date(Date.now() - 20 * 60 * 1000).toISOString(),
  uploaded_by: "avukat@ornek.tr",
  email_sent: false,
  email_error: "SMTP 550: alıcı reddetti",
};

/** Hiç denenmedi — null. */
const mailsizBelge: RecentDocument = {
  id: 103,
  case_id: 4212,
  tracking_no: "D1.S_DEMIR...0003.ICRA_.00000",
  esas_no: "2025/9",
  original_filename: "dilekce.udf",
  belge_turu_kodu: "DILEKCE_______",
  belge_turu_adi: null,
  case_party_name: "S. DEMİR",
  muvekkil_adi: null,
  uploaded_at: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
  uploaded_by: "katip@ornek.tr",
  email_sent: null,
  email_error: null,
};

describe("RecentDocumentsPanel (G079)", () => {
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

  async function mount(ui: React.ReactNode) {
    await act(async () => { root!.render(ui); });
  }

  it("son 24 saat penceresiyle G078 ucunu çağırır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    await mount(<RecentDocumentsPanel />);

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const url = apiFetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/documents/recent");
    expect(url).toContain("since_hours=24");
    expect(url).toContain("limit=8");
  });

  it("gelen belgeleri satır olarak çizer: tür, taraf, dava no, göreli zaman", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([mailliBelge, mailHataliBelge]));
    await mount(<RecentDocumentsPanel />);

    const rows = container.querySelectorAll("[data-testid='recent-doc-row']");
    expect(rows.length).toBe(2);

    const first = rows[0].textContent!;
    expect(first).toContain("Tebligat");     // belge türü adı
    expect(first).toContain("H. YILMAZ");    // bağlı taraf
    expect(first).toContain("2024/118");     // dava kimliği (esas no önce)
    expect(first).toContain("3 sa");         // lib/relativeTime

    // esas_no yoksa tracking_no'ya düşer
    expect(rows[1].textContent).toContain("D1.M_KAYA....0001.IDARE.00000");
  });

  it("belge türü adı boşsa doctype kodunu `_` pad'inden arındırıp gösterir", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([mailsizBelge]));
    await mount(<RecentDocumentsPanel />);

    const row = container.querySelector("[data-testid='recent-doc-row']")!;
    expect(row.textContent).toContain("DILEKCE");
    expect(row.textContent).not.toContain("DILEKCE_");
  });

  it("boş listede dürüst mesaj gösterir, sahte satır üretmez", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    await mount(<RecentDocumentsPanel />);

    expect(container.querySelectorAll("[data-testid='recent-doc-row']").length).toBe(0);
    expect(container.textContent).toContain("Son 24 saatte işlenen belge yok");
    expect(container.textContent).not.toContain("Yakında aktif olacak");
    expect(container.querySelectorAll("[data-testid='mail-badge']").length).toBe(0);
  });

  it("kesintide DataErrorBanner çıkar ve tekrar dene yeniden çeker", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("Sunucuya ulaşılamadı"));
    await mount(<RecentDocumentsPanel />);

    const alert = container.querySelector("[role='alert']");
    expect(alert).not.toBeNull();
    expect(alert!.textContent).toContain("kayıtlarınız silinmedi");
    // Kesinti "kayıt yok" gibi gösterilmez.
    expect(container.textContent).not.toContain("Son 24 saatte işlenen belge yok");

    apiFetchMock.mockResolvedValueOnce(jsonOk([mailliBelge]));
    const retryButton = Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Tekrar dene"))!;
    await act(async () => { retryButton.click(); });

    expect(apiFetchMock).toHaveBeenCalledTimes(2);
    expect(container.querySelector("[role='alert']")).toBeNull();
    expect(container.querySelectorAll("[data-testid='recent-doc-row']").length).toBe(1);
  });

  it("HTTP hatası (500) da hata durumu sayılır", async () => {
    apiFetchMock.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });
    await mount(<RecentDocumentsPanel />);

    expect(container.querySelector("[role='alert']")).not.toBeNull();
  });

  it("mail rozeti üç durumu ayırır: gönderildi / hata / gönderilmedi", async () => {
    // Dördüncü satır: alan payload'da HİÇ yoksa da "gönderilmedi" tarafına düşmeli
    // (undefined, false ile birleşip sahte "hata" üretmemeli).
    const alansizBelge: RecentDocument = { ...mailsizBelge, id: 104, case_id: 4213 };
    delete alansizBelge.email_sent;
    apiFetchMock.mockResolvedValue(jsonOk([mailliBelge, mailHataliBelge, mailsizBelge, alansizBelge]));
    await mount(<RecentDocumentsPanel />);

    const badges = Array.from(container.querySelectorAll("[data-testid='mail-badge']"));
    expect(badges.length).toBe(4);
    expect(badges[3].getAttribute("data-mail-state")).toBe("none");

    expect(badges[0].getAttribute("data-mail-state")).toBe("sent");
    expect(badges[0].textContent).toContain("mail gönderildi");

    expect(badges[1].getAttribute("data-mail-state")).toBe("failed");
    expect(badges[1].textContent).toContain("mail hatası");
    expect(badges[1].getAttribute("title")).toBe("SMTP 550: alıcı reddetti");

    expect(badges[2].getAttribute("data-mail-state")).toBe("none");
    expect(badges[2].textContent).toContain("mail gönderilmedi");

    // Üçü görsel olarak da ayrık: sınıf dizeleri birbirinin aynısı olamaz.
    const classes = badges.slice(0, 3).map(b => b.getAttribute("class"));
    expect(new Set(classes).size).toBe(3);
  });

  it("satıra tıklayınca /cases/:id açılır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([mailliBelge, mailHataliBelge]));
    await mount(<RecentDocumentsPanel />);

    const rows = container.querySelectorAll("[data-testid='recent-doc-row']");
    act(() => { (rows[1] as HTMLButtonElement).click(); });

    expect(navigateMock).toHaveBeenCalledWith("/cases/4211");
  });

  it("boş durumdaki Belge Yükle kısayolu onUpload'u çağırır", async () => {
    apiFetchMock.mockResolvedValue(jsonOk([]));
    const onUpload = vi.fn();
    await mount(<RecentDocumentsPanel onUpload={onUpload} />);

    const button = Array.from(container.querySelectorAll("button"))
      .find(b => b.textContent?.includes("Belge Yükle"))!;
    act(() => { button.click(); });

    expect(onUpload).toHaveBeenCalledTimes(1);
  });
});
