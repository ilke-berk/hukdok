// @vitest-environment jsdom
// lexisWord — `/lexis` sayfasının gerçek servise giden tek çağrısı. `apiClient` GERÇEK koşar; yalnız MSAL, sonner
// ve global `fetch` sahte: `/lexis-api/word` yolu, Bearer başlığı, gövde (taslak + künye), dosya adı ve uyarı
// başlıkları, indirme; servis kapalı / proxy yok / servis hatası ayrımı.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const msalMocks = vi.hoisted(() => ({
  getActiveAccount: vi.fn(),
  getAllAccounts: vi.fn(),
  acquireTokenSilent: vi.fn(),
  logoutRedirect: vi.fn(),
}));

vi.mock("@/config/msalConfig", () => ({
  msalInstance: msalMocks,
  loginRequest: { scopes: ["api://test/.default"] },
}));

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

import { LexisApiError } from "./lexisApi";
import { LEXIS_API_ONEKI, LEXIS_SERVIS_YOK, LEXIS_YETKI_MESAJI, wordIndir } from "./lexisWord";
import type { LexisTaslak } from "@/types/lexis";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const account = { username: "yonetici@example.com" };

const taslak: LexisTaslak = {
  case_id: 9001,
  sirket: "ANADOLU",
  rapor_turu: "ANA",
  iskelet: "ANADOLU",
  etiketli: { hasar: [{ alan: "sigortali", etiket: "Sigortalı", deger: "Dr. Örnek Bir", zorunlu: true, kaynak: "KART" }] },
  ozet: {},
  degerlendirme: null,
  muallak: null,
  muallak_maddi: null,
  muallak_manevi: 120000,
  emsaller: [],
};
const kunye = { hasar_no: "99000111", rapor_no: "9.9001" };

const createUrl = vi.fn(() => "blob:sahte-url");
const revokeUrl = vi.fn();
let tiklamalar: { href: string; download: string }[];

beforeEach(() => {
  vi.clearAllMocks();
  (window as Window & { _isLoggingOut?: boolean })._isLoggingOut = false;
  msalMocks.getActiveAccount.mockReturnValue(account);
  msalMocks.getAllAccounts.mockReturnValue([account]);
  msalMocks.acquireTokenSilent.mockResolvedValue({ accessToken: "test-token" });
  msalMocks.logoutRedirect.mockResolvedValue(undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  tiklamalar = [];
  (URL as unknown as { createObjectURL: unknown }).createObjectURL = createUrl;
  (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeUrl;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    tiklamalar.push({ href: this.getAttribute("href") ?? "", download: this.download });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function yanit(status: number, basliklar: Record<string, string>, govde: { json?: unknown; blob?: Blob } = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers(basliklar),
    json: async () => {
      if (govde.json === undefined) throw new SyntaxError("JSON değil");
      return govde.json;
    },
    blob: async () => govde.blob ?? new Blob(),
  } as unknown as Response;
}

function stubFetch(...yanitlar: Response[]) {
  const fetchMock = vi.fn();
  for (const y of yanitlar) fetchMock.mockResolvedValueOnce(y);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("wordIndir", () => {
  it("taslak + künyeyi /lexis-api/word'e Bearer'la gönderir; dosyayı sunucunun verdiği adla indirir, uyarıları çözer", async () => {
    const blob = new Blob(["PK"], { type: DOCX });
    const uyarilar = ["alan boş: talep_tarihi", "bölüm boş: beyan"];
    const fetchMock = stubFetch(
      yanit(
        200,
        {
          "Content-Type": DOCX,
          "Content-Disposition": 'attachment; filename="Lexis_9.9001_ANA_taslak.docx"',
          "X-Lexis-Uyari-Sayisi": "5",
          "X-Lexis-Uyarilar": encodeURIComponent(JSON.stringify(uyarilar)),
        },
        { blob },
      ),
    );

    const sonuc = await wordIndir(taslak, kunye);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(LEXIS_API_ONEKI).toBe("/lexis-api");
    expect(url).toBe("/lexis-api/word");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer test-token");
    expect(JSON.parse(init.body as string)).toEqual({ taslak, kunye });
    // Sayı sunucunun saydığıdır; liste başlığa sığan kısımdır.
    expect(sonuc).toEqual({ dosya_adi: "Lexis_9.9001_ANA_taslak.docx", uyari_sayisi: 5, uyarilar });
    expect(createUrl).toHaveBeenCalledWith(blob);
    expect(tiklamalar).toEqual([{ href: "blob:sahte-url", download: "Lexis_9.9001_ANA_taslak.docx" }]);
    expect(revokeUrl).toHaveBeenCalledWith("blob:sahte-url");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("PDF: gövdede bicim=pdf gider, application/pdf kabul edilir; Word içerik türü PDF sanılmaz", async () => {
    const blob = new Blob(["%PDF-"], { type: "application/pdf" });
    const fetchMock = stubFetch(yanit(200, { "Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="Lexis_9.9001_ANA_taslak.pdf"' }, { blob }));
    await expect(wordIndir(taslak, kunye, undefined, "pdf")).resolves.toEqual({ dosya_adi: "Lexis_9.9001_ANA_taslak.pdf", uyari_sayisi: 0, uyarilar: [] });
    expect(JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string)).toEqual({ taslak, kunye, bicim: "pdf" });
    expect(tiklamalar).toEqual([{ href: "blob:sahte-url", download: "Lexis_9.9001_ANA_taslak.pdf" }]);
    stubFetch(yanit(200, { "Content-Type": DOCX }));
    await expect(wordIndir(taslak, kunye, undefined, "pdf")).rejects.toMatchObject({ status: 502, message: LEXIS_SERVIS_YOK });
    stubFetch(yanit(200, { "Content-Type": "application/pdf" }));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ status: 502 });          // Word beklenirken PDF
  });

  it("başlıklar eksik ya da bozuksa varsayılan ad ve boş uyarı listesiyle yine indirir", async () => {
    stubFetch(yanit(200, { "Content-Type": DOCX, "X-Lexis-Uyarilar": "%E0%A4%A" }));
    await expect(wordIndir(taslak, kunye)).resolves.toEqual({ dosya_adi: "Lexis_taslak.docx", uyari_sayisi: 0, uyarilar: [] });
    expect(tiklamalar).toHaveLength(1);
  });

  it("servisin hatası kendi metniyle gelir (yazıcısı olmayan biçim 422, şablon yok 503)", async () => {
    stubFetch(yanit(422, {}, { json: { detail: "Word çıktısı şimdilik yalnız Anadolu biçiminde üretiliyor." } }));
    const hata = await wordIndir(taslak, kunye).catch((e: unknown) => e);
    expect(hata).toBeInstanceOf(LexisApiError);
    expect((hata as LexisApiError).status).toBe(422);
    expect((hata as LexisApiError).message).toContain("Anadolu");
    expect(tiklamalar).toHaveLength(0);
  });

  it.each([404, 502, 504])("servis kapalı ya da uç proxy'de yok (%i, nginx HTML'i): 'servise ulaşılamadı'", async (status) => {
    stubFetch(yanit(status, { "Content-Type": "text/html" }));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ status, message: LEXIS_SERVIS_YOK });
  });

  it("200 ama Word değil (istek SPA'ya düşmüş): dosya indirilmez", async () => {
    stubFetch(yanit(200, { "Content-Type": "text/html" }));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ message: LEXIS_SERVIS_YOK });
    expect(tiklamalar).toHaveLength(0);
  });

  it("ağ hatası 'servise ulaşılamadı' olur; çağıranın iptali aynen fırlar", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch")));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ status: 0, message: LEXIS_SERVIS_YOK });

    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new DOMException("iptal", "AbortError")));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ name: "AbortError" });
  });

  it("403 servisin metniyle (yalnız yönetici), kurtarılamayan 401 yetki mesajıyla gelir", async () => {
    stubFetch(yanit(403, {}, { json: { detail: "Lexis aracı şimdilik yalnız yöneticiye açık." } }));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ status: 403, message: "Lexis aracı şimdilik yalnız yöneticiye açık." });

    // 401: apiClient token'ı yeniler; yeni token aynıysa istek tekrarlanmaz ve 401 çağırana döner.
    stubFetch(yanit(401, {}));
    await expect(wordIndir(taslak, kunye)).rejects.toMatchObject({ status: 401, message: LEXIS_YETKI_MESAJI });
  });
});
