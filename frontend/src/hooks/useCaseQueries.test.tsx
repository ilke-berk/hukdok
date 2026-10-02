// @vitest-environment jsdom
// Faz 3: dava sorgu katmanı. Kilitlenenler: detayda `getCase` null → hata (ilk yüklemede "bulunamadı"),
// yenileme başarısızsa eski kart KORUNUR; liste ve panel anahtarları ortak önbelleği paylaşır.
// Faz 4: niyet gecikmeli önden yükleme, tekrar gelişte istek yok, sağlayıcısız no-op, boşta liste ısıtma.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const casesApi = vi.hoisted(() => ({
  getCases: vi.fn(),
  getCaseStats: vi.fn(),
  getCase: vi.fn(),
}));
vi.mock("@/hooks/useCases", () => ({ useCases: () => casesApi }));
const parcaMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/sayfaOnYukleme", () => ({ sayfaParcasiniOnYukle: parcaMock }));

import {
  caseKeys, davaListesiFiltresi, NIYET_GECIKMESI_MS, SON_DOSYALAR_FILTRESI, useCaseDetailQuery, useCaseListQuery,
  useCasePrefetch, useDavaListesiIsitma, type PrefetchHandlers,
} from "./useCaseQueries";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
let queryClient: QueryClient;
let son: { data?: unknown; isError: boolean; isPending: boolean; refetch: () => Promise<unknown> };

function DetayKoprusu({ id }: { id?: number }) {
  const q = useCaseDetailQuery(id);
  son = q;
  return null;
}
function ListeKoprusu() {
  const q = useCaseListQuery(SON_DOSYALAR_FILTRESI);
  son = q;
  return null;
}

const ciz = (el: React.ReactElement) =>
  act(() => root.render(<QueryClientProvider client={queryClient}>{el}</QueryClientProvider>));

async function bekle(kosul: () => boolean) {
  for (let i = 0; i < 100 && !kosul(); i++) {
    await act(async () => { await new Promise(r => setTimeout(r, 5)); });
  }
  expect(kosul()).toBe(true);
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient = new QueryClient();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  queryClient.clear();
});

describe("useCaseDetailQuery", () => {
  it("getCase null dönerse hata (yeniden denemesiz) — sayfa 'bulunamadı' gösterir", async () => {
    casesApi.getCase.mockResolvedValue(null);
    ciz(<DetayKoprusu id={7} />);
    await bekle(() => son.isError);
    expect(son.data).toBeUndefined();
    expect(casesApi.getCase).toHaveBeenCalledTimes(1);
  });

  it("yenileme başarısızsa eski kart ekranda kalır", async () => {
    casesApi.getCase.mockResolvedValue({ id: 7, esas_no: "2024/1" });
    ciz(<DetayKoprusu id={7} />);
    await bekle(() => son.data !== undefined);

    casesApi.getCase.mockResolvedValue(null);
    // refetch sonucu gözlemcinin güncel hâlidir (köprü takip edilen alan okumadığı için yeniden çizilmez)
    const sonuc = (await act(async () => son.refetch())) as { isError: boolean; data: unknown };
    expect(sonuc.isError).toBe(true);
    expect(sonuc.data).toEqual({ id: 7, esas_no: "2024/1" });
  });

  it("id yoksa istek atılmaz", async () => {
    ciz(<DetayKoprusu id={undefined} />);
    await act(async () => { await new Promise(r => setTimeout(r, 20)); });
    expect(casesApi.getCase).not.toHaveBeenCalled();
  });
});

describe("useCaseListQuery", () => {
  it("panel anahtarı ortak: önbellekte varsa ilk çizimde veri hazırdır", async () => {
    queryClient.setQueryData(caseKeys.list({ limit: 8, offset: 0 }), { cases: [{ id: 1 }], total: 1 });
    casesApi.getCases.mockImplementation(() => new Promise(() => {}));
    ciz(<ListeKoprusu />);
    expect(son.isPending).toBe(false);
    expect(son.data).toEqual({ cases: [{ id: 1 }], total: 1 });
    // staleTime 0: yine de arkada tazelenir
    expect(casesApi.getCases).toHaveBeenCalledTimes(1);
  });
});

describe("useCasePrefetch (Faz 4)", () => {
  let onYukle: (id: number) => PrefetchHandlers;
  function PrefetchKoprusu() {
    onYukle = useCasePrefetch();
    return null;
  }
  const bekleMs = (ms: number) => act(async () => { await new Promise(r => setTimeout(r, ms)); });

  it("fare satırda niyet süresi kalırsa kart + sayfa parçası arkada yüklenir; detay sorgusu onu kullanır", async () => {
    casesApi.getCase.mockResolvedValue({ id: 9, esas_no: "2024/9" });
    ciz(<PrefetchKoprusu />);
    act(() => onYukle(9).onMouseEnter!());
    expect(casesApi.getCase).not.toHaveBeenCalled();
    await bekleMs(NIYET_GECIKMESI_MS + 30);
    expect(casesApi.getCase).toHaveBeenCalledWith(9);
    expect(parcaMock).toHaveBeenCalledWith("/cases/:id");
    expect(queryClient.getQueryData(caseKeys.detail(9))).toEqual({ id: 9, esas_no: "2024/9" });
  });

  it("niyet süresinden önce ayrılırsa istek atılmaz (listeyi tarayan fare)", async () => {
    ciz(<PrefetchKoprusu />);
    const h = onYukle(9);
    act(() => h.onMouseEnter!());
    act(() => h.onMouseLeave!());
    await bekleMs(NIYET_GECIKMESI_MS + 30);
    expect(casesApi.getCase).not.toHaveBeenCalled();
  });

  it("yeni çekilmiş karta tekrar gelişte yeniden istek atılmaz", async () => {
    casesApi.getCase.mockResolvedValue({ id: 9 });
    ciz(<PrefetchKoprusu />);
    act(() => onYukle(9).onMouseEnter!());
    await bekleMs(NIYET_GECIKMESI_MS + 30);
    act(() => onYukle(9).onMouseEnter!());
    await bekleMs(NIYET_GECIKMESI_MS + 30);
    expect(casesApi.getCase).toHaveBeenCalledTimes(1);
  });

  it("dokunmatikte gecikmesiz; QueryClient sağlayıcısı yoksa olay bağlanmaz", async () => {
    casesApi.getCase.mockResolvedValue({ id: 4 });
    ciz(<PrefetchKoprusu />);
    act(() => onYukle(4).onTouchStart!());
    await bekleMs(5);
    expect(casesApi.getCase).toHaveBeenCalledWith(4);

    act(() => root.render(<PrefetchKoprusu />));   // sağlayıcısız (izole bileşen testi)
    expect(onYukle(4)).toEqual({});
  });
});

describe("useDavaListesiIsitma (Faz 4)", () => {
  it("boşta Dava Listesi'nin varsayılan ilk sayfası + sayaçlar çekilir; liste açılınca veri hazır", async () => {
    casesApi.getCases.mockResolvedValue({ cases: [{ id: 1 }], total: 1 });
    casesApi.getCaseStats.mockResolvedValue({ total: 1 });
    function Isit() { useDavaListesiIsitma(); return null; }
    ciz(<Isit />);
    await bekle(() => queryClient.getQueryData(caseKeys.list(davaListesiFiltresi())) !== undefined);
    expect(queryClient.getQueryData(caseKeys.stats)).toEqual({ total: 1 });
    // Dava Listesi filtre durumunun varsayılanı (tüm seçimler "ALL", arama boş) AYNI anahtardır
    expect(caseKeys.list(davaListesiFiltresi({
      sayfa: 1, status: "ALL", lawyer: "ALL", q: "", fileType: "ALL", hizmetTuru: "ALL",
      tibbiSurec: "ALL", tibbiOlay: "ALL", urgentDays: undefined, missingRequired: false,
    }))).toEqual(caseKeys.list(davaListesiFiltresi()));
  });
});
