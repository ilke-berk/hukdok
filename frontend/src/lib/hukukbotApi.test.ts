// @vitest-environment jsdom
// hukukbotApi (G204) — HukuDok token'ıyla Hukukbot istemcisi. `apiClient` GERÇEK koşar; yalnız MSAL,
// sonner ve global `fetch` sahte: Bearer başlığı, `/hukukbot-api` öneki, `session-id` başlığı,
// bölünmüş/`\n`'siz NDJSON, akış sırasında iptal, 401 yenilemesi, 429 ayrı hata, yetkili indirme.
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

import {
  HUKUKBOT_API_ONEKI,
  HUKUKBOT_YETKI_MESAJI,
  HukukbotApiError,
  HukukbotHizSiniriError,
  HukukbotYetkiError,
  ask,
  hukudokBelgesiniAc,
  hukukbotApi,
  indir,
  oturumGetir,
  oturumGuncelle,
  oturumOlustur,
  oturumSil,
  oturumlariListele,
} from "./hukukbotApi";
import type { HukukbotAkisOlayi } from "@/types/hukukbot";

const account = { username: "avukat@example.com" };

beforeEach(() => {
  vi.clearAllMocks();
  (window as Window & { _isLoggingOut?: boolean })._isLoggingOut = false;
  msalMocks.getActiveAccount.mockReturnValue(account);
  msalMocks.getAllAccounts.mockReturnValue([account]);
  msalMocks.acquireTokenSilent.mockResolvedValue({ accessToken: "test-token" });
  msalMocks.logoutRedirect.mockResolvedValue(undefined);
  vi.spyOn(console, "log").mockImplementation(() => undefined);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function jsonResponse(status: number, govde: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => govde,
  } as unknown as Response;
}

/** Ham parçaları satır sınırına bakmadan veren sahte akış; `cancel` çağrısı izlenir. */
function streamResponse(parcalar: string[]) {
  const encoder = new TextEncoder();
  const kodlu = parcalar.map((p) => encoder.encode(p));
  let i = 0;
  const cancel = vi.fn(async () => undefined);
  const res = {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: async () => (i < kodlu.length ? { value: kodlu[i++], done: false } : { value: undefined, done: true }),
        cancel,
      }),
    },
  } as unknown as Response;
  return { res, cancel };
}

function stubFetch(...yanitlar: Response[]) {
  const fetchMock = vi.fn();
  for (const y of yanitlar) fetchMock.mockResolvedValueOnce(y);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const cagri = (fetchMock: ReturnType<typeof vi.fn>, n = 0) => {
  const [url, init] = fetchMock.mock.calls[n] as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
};

async function hepsi(akis: AsyncIterable<HukukbotAkisOlayi>): Promise<HukukbotAkisOlayi[]> {
  const olaylar: HukukbotAkisOlayi[] = [];
  for await (const o of akis) olaylar.push(o);
  return olaylar;
}

const satir = (o: unknown) => JSON.stringify(o) + "\n";

describe("oturum CRUD", () => {
  it("GET /sessions: göreli /hukukbot-api önekli URL + access token Bearer başlıkta", async () => {
    const liste = [{ id: "s1", title: "Yeni Sohbet", created_at: "2026-09-26", is_pinned: true, preview: null }];
    const fetchMock = stubFetch(jsonResponse(200, liste));

    await expect(oturumlariListele()).resolves.toEqual(liste);

    const { url, init, headers } = cagri(fetchMock);
    expect(HUKUKBOT_API_ONEKI).toBe("/hukukbot-api");
    expect(url).toBe("/hukukbot-api/sessions");
    expect(init.method ?? "GET").toBe("GET");
    expect(headers.get("Authorization")).toBe("Bearer test-token");
    // G8: loginRequest scope'uyla access token istenir
    expect(msalMocks.acquireTokenSilent.mock.calls[0][0].scopes).toEqual(["api://test/.default"]);
  });

  it("GET /sessions/{id} mesajlarıyla; id yolda kodlanır", async () => {
    const oturum = { id: "a/b", title: "T", created_at: "x", is_pinned: false, messages: [] };
    const fetchMock = stubFetch(jsonResponse(200, oturum));

    await expect(oturumGetir("a/b")).resolves.toEqual(oturum);
    expect(cagri(fetchMock).url).toBe("/hukukbot-api/sessions/a%2Fb");
  });

  it("POST /sessions gövdesi {title}", async () => {
    const fetchMock = stubFetch(jsonResponse(200, { id: "s2", title: "Kira", created_at: "x", is_pinned: false, messages: [] }));

    const oturum = await oturumOlustur("Kira");

    expect(oturum.id).toBe("s2");
    const { url, init } = cagri(fetchMock);
    expect(url).toBe("/hukukbot-api/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ title: "Kira" });
  });

  it("PATCH /sessions/{id} yalnız verilen alanları gönderir (başlık / is_pinned)", async () => {
    const fetchMock = stubFetch(
      jsonResponse(200, { id: "s1", title: "Yeni ad", created_at: "x", is_pinned: false, messages: [] }),
      jsonResponse(200, { id: "s1", title: "Yeni ad", created_at: "x", is_pinned: true, messages: [] }),
    );

    await oturumGuncelle("s1", { title: "Yeni ad" });
    await oturumGuncelle("s1", { is_pinned: true });

    expect(cagri(fetchMock, 0).init.method).toBe("PATCH");
    expect(cagri(fetchMock, 0).url).toBe("/hukukbot-api/sessions/s1");
    expect(JSON.parse(cagri(fetchMock, 0).init.body as string)).toEqual({ title: "Yeni ad" });
    expect(JSON.parse(cagri(fetchMock, 1).init.body as string)).toEqual({ is_pinned: true });
  });

  it("DELETE /sessions/{id}; 404 sunucu detail'iyle HukukbotApiError olur", async () => {
    const fetchMock = stubFetch(jsonResponse(200, { status: "deleted" }), jsonResponse(404, { detail: "Session not found" }));

    await expect(oturumSil("s1")).resolves.toBeUndefined();
    expect(cagri(fetchMock).init.method).toBe("DELETE");
    expect(cagri(fetchMock).url).toBe("/hukukbot-api/sessions/s1");

    const hata = await oturumSil("yok").catch((e) => e);
    expect(hata).toBeInstanceOf(HukukbotApiError);
    expect(hata).toMatchObject({ status: 404, message: "Session not found" });
    expect(hata).not.toBeInstanceOf(HukukbotYetkiError);
  });
});

describe("ask — /ask NDJSON akışı", () => {
  it("POST /hukukbot-api/ask: gövde AskRequest, oturum session-id BAŞLIĞINDA, Bearer token", async () => {
    const { res } = streamResponse([satir({ type: "content", data: "Merhaba" })]);
    const fetchMock = stubFetch(res);

    const soru = { question: "Kira artışı?", history: [{ role: "user" as const, content: "önceki" }] };
    await hepsi(ask(soru, { sessionId: "oturum-42" }));

    const { url, init, headers } = cagri(fetchMock);
    expect(url).toBe("/hukukbot-api/ask");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(soru);
    expect(headers.get("session-id")).toBe("oturum-42");
    expect(headers.get("Authorization")).toBe("Bearer test-token");
  });

  it("oturum verilmezse session-id başlığı hiç gönderilmez (hukbot yeni oturum açar)", async () => {
    const fetchMock = stubFetch(streamResponse([]).res);

    await hepsi(ask({ question: "Soru" }));

    expect(cagri(fetchMock).headers.has("session-id")).toBe(false);
  });

  it("parça sınırında bölünmüş satırlar doğru birleşir; olay sırası korunur", async () => {
    const kaynak = { file_display_name: "Yargıtay - 2024/1", filename: "k1.pdf", text_preview: "…", download_url: "/download/k1.pdf" };
    const tam = satir({ type: "content", data: "Birinci " }) + satir({ type: "content", data: "ikinci" }) + satir({ type: "sources", data: [kaynak] });
    // Satırların ortasından, hatta çok baytlı karakterin (ı) içinden bölünen parçalar
    const bayt = new TextEncoder().encode(tam);
    const ortaBayt = bayt.indexOf(0xc4) + 1; // "ı" = C4 B1 → iki baytın arasından kes
    expect(ortaBayt).toBeGreaterThan(61);
    const kes = [7, 23, 40, 61, ortaBayt];
    const parcalar: Uint8Array[] = [];
    let onceki = 0;
    for (const k of [...kes, bayt.length]) {
      parcalar.push(bayt.slice(onceki, k));
      onceki = k;
    }
    let i = 0;
    const res = {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: async () => (i < parcalar.length ? { value: parcalar[i++], done: false } : { value: undefined, done: true }),
          cancel: vi.fn(async () => undefined),
        }),
      },
    } as unknown as Response;
    stubFetch(res);

    const olaylar = await hepsi(ask({ question: "q" }));

    expect(olaylar).toEqual([
      { type: "content", data: "Birinci " },
      { type: "content", data: "ikinci" },
      { type: "sources", data: [kaynak] },
    ]);
  });

  it("son satır \\n'siz gelse de işlenir", async () => {
    const { res } = streamResponse([satir({ type: "content", data: "Cevap" }), JSON.stringify({ type: "sources", data: [] })]);
    stubFetch(res);

    const olaylar = await hepsi(ask({ question: "q" }));

    expect(olaylar).toEqual([
      { type: "content", data: "Cevap" },
      { type: "sources", data: [] },
    ]);
  });

  it("akıştaki error olayı olduğu gibi verilir; bozuk satır ve tanınmayan tür atlanır", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { res } = streamResponse([
      "{bozuk json\n",
      satir({ type: "gelecekte_eklenecek", data: 1 }),
      satir({ type: "content", data: "Yarım" }),
      satir({ type: "error", data: "Gemini hatası" }),
    ]);
    stubFetch(res);

    const olaylar = await hepsi(ask({ question: "q" }));

    expect(olaylar).toEqual([
      { type: "content", data: "Yarım" },
      { type: "error", data: "Gemini hatası" },
    ]);
  });

  it("status olayı ara durum olarak verilir; boş/metin olmayan status atlanır", async () => {
    const { res } = streamResponse([
      satir({ type: "status", data: "Arşiv taranıyor: menenjit geç tanı" }),
      satir({ type: "status", data: "   " }),
      satir({ type: "status", data: 3 }),
      satir({ type: "content", data: "Cevap" }),
    ]);
    stubFetch(res);

    const olaylar = await hepsi(ask({ question: "q" }));

    expect(olaylar).toEqual([
      { type: "status", data: "Arşiv taranıyor: menenjit geç tanı" },
      { type: "content", data: "Cevap" },
    ]);
  });

  it("akış SIRASINDA AbortSignal: okuyucu kapatılır, AbortError fırlar", async () => {
    const encoder = new TextEncoder();
    let bekleyen: ((v: { value: undefined; done: true }) => void) | null = null;
    let okumaSayisi = 0;
    const cancel = vi.fn(async () => {
      bekleyen?.({ value: undefined, done: true });
    });
    const res = {
      ok: true,
      status: 200,
      body: {
        getReader: () => ({
          read: () => {
            okumaSayisi++;
            if (okumaSayisi === 1) return Promise.resolve({ value: encoder.encode(satir({ type: "content", data: "İlk" })), done: false });
            return new Promise((r) => {
              bekleyen = r;
            });
          },
          cancel,
        }),
      },
    } as unknown as Response;
    stubFetch(res);
    const controller = new AbortController();

    const akis = ask({ question: "q" }, { signal: controller.signal });
    const ilk = await akis.next();
    expect(ilk.value).toEqual({ type: "content", data: "İlk" });

    const ikinci = akis.next();
    controller.abort();

    await expect(ikinci).rejects.toMatchObject({ name: "AbortError" });
    expect(cancel).toHaveBeenCalled();
  });

  it("tüketici erken çıkarsa (break) bağlantı bırakılır", async () => {
    const { res, cancel } = streamResponse([satir({ type: "content", data: "a" }), satir({ type: "content", data: "b" })]);
    stubFetch(res);

    for await (const _olay of ask({ question: "q" })) break;

    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("istek öncesi iptal edilmiş sinyal fetch'e iletilir (ağ iptali)", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError"));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();
    controller.abort();

    await expect(hepsi(ask({ question: "q" }, { signal: controller.signal }))).rejects.toMatchObject({ name: "AbortError" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("429 → HukukbotHizSiniriError (sunucunun Türkçe detail metniyle), akış başlamaz", async () => {
    const detay = "Çok fazla istek gönderdiniz. Lütfen bir dakika sonra tekrar deneyin.";
    stubFetch(jsonResponse(429, { detail: detay }));

    const hata = await hepsi(ask({ question: "q" })).catch((e) => e);

    expect(hata).toBeInstanceOf(HukukbotHizSiniriError);
    expect(hata).toMatchObject({ status: 429, message: detay });
    expect(hata).not.toBeInstanceOf(HukukbotYetkiError);
  });

  it("401'de token forceRefresh ile yenilenip istek BİR kez tekrarlanır (api.ts deseni)", async () => {
    msalMocks.acquireTokenSilent
      .mockResolvedValueOnce({ accessToken: "test-token" })
      .mockResolvedValueOnce({ accessToken: "fresh-token" });
    const fetchMock = stubFetch(jsonResponse(401, {}), streamResponse([satir({ type: "content", data: "ok" })]).res);

    const olaylar = await hepsi(ask({ question: "q" }, { sessionId: "s1" }));

    expect(olaylar).toEqual([{ type: "content", data: "ok" }]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(msalMocks.acquireTokenSilent.mock.calls[1][0].forceRefresh).toBe(true);
    expect(cagri(fetchMock, 1).headers.get("Authorization")).toBe("Bearer fresh-token");
    expect(cagri(fetchMock, 1).headers.get("session-id")).toBe("s1");
    expect(msalMocks.logoutRedirect).not.toHaveBeenCalled();
  });

  it("yenileme sonrası da 401 → HukukbotYetkiError (ayrı tür); tekrar sayısı 2'yi aşmaz", async () => {
    msalMocks.acquireTokenSilent
      .mockResolvedValueOnce({ accessToken: "test-token" })
      .mockResolvedValueOnce({ accessToken: "fresh-token" });
    const fetchMock = stubFetch(jsonResponse(401, {}), jsonResponse(401, {}));

    const hata = await oturumlariListele().catch((e) => e);

    expect(hata).toBeInstanceOf(HukukbotYetkiError);
    expect(hata).toMatchObject({ status: 401, message: HUKUKBOT_YETKI_MESAJI });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("indir — yetkili PDF indirme", () => {
  const createUrl = vi.fn(() => "blob:sahte-url");
  const revokeUrl = vi.fn();
  let tiklamalar: { href: string; download: string }[];

  beforeEach(() => {
    tiklamalar = [];
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = createUrl;
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeUrl;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      tiklamalar.push({ href: this.getAttribute("href") ?? "", download: this.download });
    });
  });

  it("dosya adı encodeURIComponent'le kodlanır, Bearer'lı fetch → blob → <a download>, URL serbest bırakılır", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    const fetchMock = stubFetch({ ok: true, status: 200, blob: async () => blob } as unknown as Response);

    await indir("Yargıtay 3. HD #1/2024.pdf");

    const { url, headers } = cagri(fetchMock);
    expect(url).toBe(`/hukukbot-api/download/${encodeURIComponent("Yargıtay 3. HD #1/2024.pdf")}`);
    expect(url).toBe("/hukukbot-api/download/Yarg%C4%B1tay%203.%20HD%20%231%2F2024.pdf");
    expect(headers.get("Authorization")).toBe("Bearer test-token");
    expect(createUrl).toHaveBeenCalledWith(blob);
    expect(tiklamalar).toEqual([{ href: "blob:sahte-url", download: "Yargıtay 3. HD #1/2024.pdf" }]);
    expect(revokeUrl).toHaveBeenCalledWith("blob:sahte-url");
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("404'te blob URL hiç oluşturulmaz, hata detail'iyle fırlar", async () => {
    stubFetch(jsonResponse(404, { detail: "Belge bulunamadı." }));

    await expect(indir("yok.pdf")).rejects.toMatchObject({ status: 404, message: "Belge bulunamadı." });
    expect(createUrl).not.toHaveBeenCalled();
    expect(tiklamalar).toEqual([]);
  });
});

describe("hukudokBelgesiniAc — HukuDok'tan aktarılmış kaynak", () => {
  const createUrl = vi.fn(() => "blob:hukudok-belge");
  const revokeUrl = vi.fn();

  beforeEach(() => {
    createUrl.mockClear();
    revokeUrl.mockClear();
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = createUrl;
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = revokeUrl;
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("HukuDok'un KENDİ ucuna gider (Hukukbot öneki YOK), Bearer'lı; blob önceden açılan sekmeye yazılır", async () => {
    const blob = new Blob(["%PDF"], { type: "application/pdf" });
    const fetchMock = stubFetch({ ok: true, status: 200, blob: async () => blob } as unknown as Response);
    const sekme = { location: { href: "" } } as unknown as Window;

    await hukudokBelgesiniAc(14743, sekme);

    const { url, headers } = cagri(fetchMock);
    expect(url).toBe("/api/documents/14743/download?inline=true");
    expect(url.startsWith(HUKUKBOT_API_ONEKI)).toBe(false);
    expect(headers.get("Authorization")).toBe("Bearer test-token");
    expect(createUrl).toHaveBeenCalledWith(blob);
    expect(sekme.location.href).toBe("blob:hukudok-belge");
    expect(revokeUrl).not.toHaveBeenCalled(); // sekme okuyabilsin diye hemen bırakılmaz
    vi.advanceTimersByTime(60_000);
    expect(revokeUrl).toHaveBeenCalledWith("blob:hukudok-belge");
  });

  it("sekme engellendiyse (null) yeni pencere denenir", async () => {
    stubFetch({ ok: true, status: 200, blob: async () => new Blob(["x"]) } as unknown as Response);
    const ac = vi.spyOn(window, "open").mockReturnValue(null);
    await hukudokBelgesiniAc(5, null);
    expect(ac).toHaveBeenCalledWith("blob:hukudok-belge", "_blank");
    ac.mockRestore();
  });

  it("404'te blob oluşmaz, status'lu hata fırlar", async () => {
    stubFetch(jsonResponse(404, { detail: "Belge bulunamadı" }));
    await expect(hukudokBelgesiniAc(9, null)).rejects.toMatchObject({ status: 404 });
    expect(createUrl).not.toHaveBeenCalled();
  });
});

describe("hukukbotApi nesnesi", () => {
  it("sayfanın kullandığı tüm uçları tek nesnede toplar", () => {
    expect(Object.keys(hukukbotApi).sort()).toEqual(
      [
        "ask",
        "hukudokBelgesiniAc",
        "indir",
        "oturumGetir",
        "oturumGuncelle",
        "oturumOlustur",
        "oturumSil",
        "oturumlariListele",
      ].sort(),
    );
  });
});
