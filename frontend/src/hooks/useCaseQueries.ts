import { useCallback, useContext, useEffect, useRef } from "react";
import { keepPreviousData, QueryClientContext, useQuery } from "@tanstack/react-query";
import { useCases } from "@/hooks/useCases";
import { sayfaParcasiniOnYukle } from "@/lib/sayfaOnYukleme";

// Dava okumalarının React Query katmanı (algılanan hız, Faz 3). Amaç: aynı veriye ikinci kez
// gelindiğinde iskelet/boş ekran yerine eldeki veri ANINDA çizilsin, tazesi arkada sessizce gelsin
// (stale-while-revalidate).
//
// - `staleTime: 0`: her mount'ta yeniden çekilir — önbellek yalnız "beklerken ne gösterelim"
//   sorusunun cevabıdır, tazelik kaynağı değildir. Bu yüzden yazma yollarına invalidate eklemek
//   doğruluk için şart değil; eski veri en fazla bir istek süresi görünür.
// - Odakta yeniden çekme global olarak kapalı (G184, App.tsx) — açık sayfa kendiliğinden yenilenmez,
//   kullanıcının yarım düzenlemesi arkaplan çekimiyle ezilmez. Yapısal paylaşım sayesinde değişmeyen
//   yanıt aynı nesne referansını korur (gereksiz yeniden çizim yok).
// - `retry: false`: hata şeridi (G002) gecikmesiz görünür; eski elle çekme davranışıyla aynı.
// - Ayrı modül: testler `@/hooks/useCases`'i modül olarak taklit eder; sorgular onun üstüne kurulur.

type GetCases = ReturnType<typeof useCases>["getCases"];
export type CaseListFilter = NonNullable<Parameters<GetCases>[0]>;

const ONBELLEK_SURESI_MS = 10 * 60_000;

export const caseKeys = {
  all: ["cases"] as const,
  list: (filter: CaseListFilter) => ["cases", "list", filter] as const,
  stats: ["cases", "stats"] as const,
  detail: (id: number) => ["cases", "detail", id] as const,
};

/** Panellerin "son dosyalar" listesi — Avukat ve İdari panel aynı anahtarı paylaşır. */
export const SON_DOSYALAR_FILTRESI: CaseListFilter = { limit: 8, offset: 0 };

/** Detay okunamadı (ağ ya da 404) — `getCase` null döner, sorgu hataya çevirir. */
export const CASE_DETAIL_ERROR = "Dava kartı alınamadı.";

export function useCaseListQuery<T = Record<string, unknown>>(
  filter: CaseListFilter,
  options: { keepPrevious?: boolean } = {},
) {
  const { getCases } = useCases();
  return useQuery({
    queryKey: caseKeys.list(filter),
    queryFn: () => getCases<T>(filter),
    // Filtre/sayfa değişiminde yeni yanıt gelene kadar eski satırlar yerinde kalır
    // (`isPlaceholderData` → liste soluklaşır); liste sökülüp sayfa zıplamaz.
    placeholderData: options.keepPrevious ? keepPreviousData : undefined,
    staleTime: 0,
    gcTime: ONBELLEK_SURESI_MS,
    retry: false,
  });
}

export function useCaseStatsQuery<T = Record<string, unknown>>() {
  const { getCaseStats } = useCases();
  return useQuery({
    queryKey: caseKeys.stats,
    queryFn: async () => (await getCaseStats()) as T,
    staleTime: 0,
    gcTime: ONBELLEK_SURESI_MS,
    retry: false,
  });
}

type GetCase = ReturnType<typeof useCases>["getCase"];

// Detay sorgusunun TEK tanımı: sayfa (`useCaseDetailQuery`) ve önden yükleme (`useCasePrefetch`)
// aynı anahtar + aynı queryFn'i kullanır, yoksa önbellek paylaşılmaz.
function caseDetailQueryOptions<T>(getCase: GetCase, id: number) {
  return {
    queryKey: caseKeys.detail(id),
    queryFn: async () => {
      const data = await getCase(id);
      // null'u hataya çevir: yenileme başarısızsa eski kart EKRANDA kalır (react-query hata
      // anında son başarılı veriyi korur); ilk yükleme başarısızsa "bulunamadı" görünümü.
      if (!data) throw new Error(CASE_DETAIL_ERROR);
      return data as T;
    },
    gcTime: ONBELLEK_SURESI_MS,
    retry: false as const,
  };
}

export function useCaseDetailQuery<T = Record<string, unknown>>(id: number | undefined) {
  const { getCase } = useCases();
  const gecerli = id !== undefined && Number.isFinite(id);
  return useQuery({
    ...caseDetailQueryOptions<T>(getCase, gecerli ? id : -1),
    enabled: gecerli,
    staleTime: 0,
  });
}

/**
 * Kartı önbellekte bayat işaretler (açık sayfa varsa yeniden çeker). G285: kartın DIŞINDAN yapılan yazmalar (tezgâhta
 * "Yeni belge") sonrası karta dönüşte eski belge listesi bir istek süresi bile görünmesin. Sağlayıcı yoksa no-op.
 */
export function useCaseDetailInvalidate(): (id: number) => Promise<void> {
  const queryClient = useContext(QueryClientContext);
  return useCallback(async (id: number) => {
    if (queryClient) await queryClient.invalidateQueries({ queryKey: caseKeys.detail(id) });
  }, [queryClient]);
}

// ---- Önden yükleme (Faz 4) ----

/** İmleç satırda bu kadar kalırsa niyet sayılır — listeyi tarayan fare her satırı çekmesin. */
export const NIYET_GECIKMESI_MS = 100;
/** Bu süre içinde çekilmiş kart yeniden önden yüklenmez (aynı satıra tekrar tekrar gelmek). */
const ON_YUKLEME_TAZELIK_MS = 30_000;

export type PrefetchHandlers = {
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
  onTouchStart?: () => void;
};

/**
 * Dava kartına giden satır/düğme için önden yükleme. Kullanım: `<tr {...onYukle(c.id)}>`.
 * Fare satırda `NIYET_GECIKMESI_MS` durursa (ya da klavye odağı gelirse, dokunmatikte parmak değer
 * değmez) kart arkada çekilir; tıklayınca detay sayfası çoğu kez iskeletsiz açılır. Sayfa mount'ta
 * yine tazeler (staleTime 0) — çekim sürerken mount olursa react-query aynı isteği paylaşır.
 *
 * Bir iyileştirmedir, işlev değil: QueryClient sağlayıcısı yoksa (izole bileşen testi) sessizce
 * hiçbir şey yapmaz; hata yutulur (prefetchQuery fırlatmaz).
 */
export function useCasePrefetch(): (id: number | null | undefined) => PrefetchHandlers {
  const queryClient = useContext(QueryClientContext);
  const { getCase } = useCases();
  const zamanlayicilar = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  useEffect(() => {
    const bekleyenler = zamanlayicilar.current;
    return () => {
      bekleyenler.forEach(clearTimeout);
      bekleyenler.clear();
    };
  }, []);

  const onYukle = useCallback((id: number) => {
    if (!queryClient) return;
    sayfaParcasiniOnYukle("/cases/:id");   // ilk karta gidişte sayfa parçası da beklenmesin
    void queryClient.prefetchQuery({ ...caseDetailQueryOptions(getCase, id), staleTime: ON_YUKLEME_TAZELIK_MS });
  }, [queryClient, getCase]);

  return useCallback((id: number | null | undefined): PrefetchHandlers => {
    if (!queryClient || id == null || !Number.isFinite(id)) return {};
    const bekleyenler = zamanlayicilar.current;
    const basla = () => {
      if (bekleyenler.has(id)) return;
      bekleyenler.set(id, setTimeout(() => {
        bekleyenler.delete(id);
        onYukle(id);
      }, NIYET_GECIKMESI_MS));
    };
    const vazgec = () => {
      const t = bekleyenler.get(id);
      if (t !== undefined) {
        clearTimeout(t);
        bekleyenler.delete(id);
      }
    };
    return { onMouseEnter: basla, onMouseLeave: vazgec, onFocus: basla, onBlur: vazgec, onTouchStart: () => onYukle(id) };
  }, [queryClient, onYukle]);
}

// ---- Dava Listesi varsayılan sayfası (Faz 4 ısıtma) ----

export const DAVA_LISTESI_SAYFA_BOYU = 15;

/** Dava Listesi filtre durumundan sorgu filtresi — liste ve ısıtma AYNI anahtarı üretmeli. */
export function davaListesiFiltresi(f: {
  sayfa?: number;
  status?: string;
  lawyer?: string;
  q?: string;
  fileType?: string;
  hizmetTuru?: string;
  tibbiSurec?: string;
  tibbiOlay?: string;
  urgentDays?: number;
  missingRequired?: boolean;
} = {}): CaseListFilter {
  return {
    limit: DAVA_LISTESI_SAYFA_BOYU,
    offset: ((f.sayfa ?? 1) - 1) * DAVA_LISTESI_SAYFA_BOYU,
    status: f.status ?? "ALL",
    lawyer: f.lawyer ?? "ALL",
    q: f.q || undefined,
    fileType: f.fileType ?? "ALL",
    hizmetTuru: f.hizmetTuru ?? "ALL",
    tibbiSurec: f.tibbiSurec ?? "ALL",
    tibbiOlay: f.tibbiOlay ?? "ALL",
    urgentDays: f.urgentDays,
    missingRequired: f.missingRequired || undefined,
  };
}

/**
 * Panel açıkken tarayıcı boşa çıkınca Dava Listesi'nin ilk sayfasını + sayaçları arkada çeker:
 * menüden "Dava Dosyaları"na geçiş iskeletsiz açılır. Tek istek çifti; son 60 sn içinde çekildiyse
 * hiç istek atılmaz. Sağlayıcı yoksa no-op.
 */
export function useDavaListesiIsitma() {
  const queryClient = useContext(QueryClientContext);
  const { getCases, getCaseStats } = useCases();
  useEffect(() => {
    if (!queryClient) return;
    const isit = () => {
      const filtre = davaListesiFiltresi();
      void queryClient.prefetchQuery({
        queryKey: caseKeys.list(filtre),
        queryFn: () => getCases(filtre),
        staleTime: 60_000,
        gcTime: ONBELLEK_SURESI_MS,
        retry: false,
      });
      void queryClient.prefetchQuery({
        queryKey: caseKeys.stats,
        queryFn: () => getCaseStats(),
        staleTime: 60_000,
        gcTime: ONBELLEK_SURESI_MS,
        retry: false,
      });
    };
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number;
      cancelIdleCallback?: (h: number) => void;
    };
    if (w.requestIdleCallback) {
      const h = w.requestIdleCallback(isit, { timeout: 3000 });
      return () => w.cancelIdleCallback?.(h);
    }
    const t = setTimeout(isit, 1500);
    return () => clearTimeout(t);
    // Yalnız mount'ta bir kez; getCases kimliği değişse de yeniden ısıtma gerekmez.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);
}
