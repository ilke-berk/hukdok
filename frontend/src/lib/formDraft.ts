// =====================================================================
// Genel form taslağı motoru (G004 · sertleştirme 4-C).
//
// intakeDraft.ts'te sihirbaza özel yazılmış desenin (sürümlü zarf +
// sessionStorage + debounce'lu yazım) sayfadan bağımsız hâli. Yeni dava
// formu (newCaseDraft.ts) ve belge yükleme akışı (uploadFlowDraft.ts)
// bunun üzerine kurulur; intakeDraft yerinde kalır, yalnız `debounce`
// buraya taşınıp oradan yeniden dışa verilir.
//
// KVKK: taslaklar sessionStorage'da tutulur — sekme kapanınca ölür. TC/isim
// içeren form verisi kalıcı localStorage'a YAZILMAZ.
// =====================================================================

/** Diske yazılan sürümlü zarf. Sürüm değişince eski taslak sessizce atılır. */
export interface DraftEnvelope<T> {
  version: number;
  savedAt: string; // ISO
  data: T;
}

/** Okunan taslak + yaşı (geri yükleme şeridi "12 dakika önce" yazabilsin). */
export interface LoadedDraft<T> {
  data: T;
  savedAt: Date;
  ageMs: number;
}

export interface DraftStoreOptions {
  key: string;
  version: number;
  /** Bu yaştan eski taslak BAYAT sayılır: okunmaz, silinir. */
  maxAgeMs: number;
  /** Şema denetimi — false dönen kayıt bozuk sayılıp silinir. */
  isValid?: (data: unknown) => boolean;
  /** Test/özelleştirme için depo sağlayıcı; varsayılan sessionStorage. */
  storage?: () => Storage | null;
}

export interface DraftStore<T> {
  readonly key: string;
  save(data: T, now?: number): void;
  load(now?: number): LoadedDraft<T> | null;
  clear(): void;
}

// ---------------------------------------------------------------------
// Logout bastırması (G004 denetim düzeltmesi — RET bulgusu).
//
// SORUN: Çıkış akışı `clearAppStorage()` ile taslakları siler, hemen ardından
// `logoutRedirect` navigasyonu `pagehide` + `beforeunload` tetikler; bu
// flush'lar taslağı sessionStorage'a GERİ yazardı. sessionStorage aynı
// sekmedeki AAD gidiş-dönüşünde hayatta kaldığı için sonraki kullanıcı,
// önceki kullanıcının TC içeren taslağını "geri yükle" şeridiyle görürdü.
//
// ÇÖZÜM: Sidebar, temizlikten ÖNCE `suppressAllDrafts()` çağırır. Bayrak
// kuruluyken (1) HİÇBİR DraftStore.save diske yazmaz, (2) attachUnloadGuard
// uyarı diyaloğu da flush da üretmez — tarayıcının "ayrılmak istiyor musunuz?"
// sorusu logout'un ortasına düşmez. Bayrak modül-içi bellektedir: redirect /
// reload sayfayı tazeleyince kendiliğinden sıfırlanır.
//
// DİKKAT: Oturum düşmesi (401 → SESSION_EXPIRED_EVENT) bu bayrağı KURMAZ —
// orada flush bilinçli bir özelliktir (aynı kullanıcı tekrar girince emeği
// geri gelir; depo da temizlenmez). Sayfaların kendi `clear()` kilidi
// (useFormDraft.suppressed) olduğu gibi durur; bu bayrak yalnız çıkışa özeldir.
// ---------------------------------------------------------------------

let allDraftsSuppressed = false;

/** Çıkış akışı: tüm taslak yazımlarını ve ayrılma uyarılarını sustur.
 *  `clearAppStorage()`'dan ÖNCE çağrılmalı. */
export function suppressAllDrafts(): void {
  allDraftsSuppressed = true;
}

/** Bastırmayı geri alır — logout kurulamayıp kullanıcı oturumda kaldığında
 *  (Sidebar catch yolu) ve test temizliğinde kullanılır. */
export function resumeAllDrafts(): void {
  allDraftsSuppressed = false;
}

export function areDraftsSuppressed(): boolean {
  return allDraftsSuppressed;
}

/** Storage erişimi engelli olabilir (gizli mod kısıtı vb.) — taslak özelliği
 *  o durumda sessizce devre dışı kalır, akış asla kırılmaz. */
export const sessionDraftStorage = (): Storage | null => {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
};

export function createDraftStore<T>(options: DraftStoreOptions): DraftStore<T> {
  const { key, version, maxAgeMs, isValid, storage = sessionDraftStorage } = options;

  // Depo sağlayıcısı da patlayabilir (gizli mod / kısıtlı origin) — taslak
  // özelliği hiçbir koşulda çağıran akışı kırmaz.
  const safeStorage = (): Storage | null => {
    try {
      return storage();
    } catch {
      return null;
    }
  };

  const drop = () => {
    try {
      safeStorage()?.removeItem(key);
    } catch {
      /* yoksay */
    }
  };

  return {
    key,

    save(data: T, now: number = Date.now()): void {
      // Çıkış bastırması: temizlik ile redirect arasındaki pagehide/unmount
      // flush'ları silinen taslağı diriltmesin (en derin boğaz noktası —
      // debounce'lu yazıcı dahil TÜM yazım yolları buradan geçer).
      if (allDraftsSuppressed) return;
      const store = safeStorage();
      if (!store) return;
      const envelope: DraftEnvelope<T> = {
        version,
        savedAt: new Date(now).toISOString(),
        data,
      };
      try {
        store.setItem(key, JSON.stringify(envelope));
      } catch {
        // kota dolu / serileştirilemez — taslak best-effort, akışı asla kırmaz
      }
    },

    load(now: number = Date.now()): LoadedDraft<T> | null {
      const store = safeStorage();
      if (!store) return null;
      const raw = store.getItem(key);
      if (!raw) return null;

      let envelope: DraftEnvelope<T>;
      try {
        envelope = JSON.parse(raw) as DraftEnvelope<T>;
      } catch {
        drop();
        return null;
      }

      if (
        !envelope ||
        envelope.version !== version ||
        typeof envelope.savedAt !== "string" ||
        envelope.data == null
      ) {
        drop(); // sürüm/şema uyuşmazlığı → bayat taslak atılır
        return null;
      }

      const savedMs = Date.parse(envelope.savedAt);
      if (!Number.isFinite(savedMs)) {
        drop();
        return null;
      }

      const ageMs = now - savedMs;
      if (ageMs > maxAgeMs) {
        drop(); // "eski/bayat taslak" sınırı — dünkü form bugün diriltilmez
        return null;
      }

      if (isValid && !isValid(envelope.data)) {
        drop();
        return null;
      }

      // Saat geri alınmışsa yaş negatif çıkabilir; 0'a çekilir.
      return { data: envelope.data, savedAt: new Date(savedMs), ageMs: Math.max(0, ageMs) };
    },

    clear: drop,
  };
}

/** Geri yükleme şeridi metni: "az önce" · "12 dakika önce" · "3 saat önce". */
export function describeDraftAge(ageMs: number): string {
  const minutes = Math.floor(Math.max(0, ageMs) / 60_000);
  if (minutes < 1) return "az önce";
  if (minutes < 60) return `${minutes} dakika önce`;
  const hours = Math.floor(minutes / 60);
  return `${hours} saat önce`;
}

/**
 * Kirli formda tarayıcının "sayfadan ayrılmak istediğinize emin misiniz?"
 * uyarısını bağlar. `active=false` iken HİÇBİR dinleyici bağlanmaz — temiz
 * formda kullanıcı boş yere uyarı görmez.
 *
 * Dönüş: sökme fonksiyonu (useEffect cleanup'ında çağrılır).
 */
export function attachUnloadGuard(active: boolean, onFlush?: () => void): () => void {
  if (!active || typeof window === "undefined") return () => { /* bağlanmadı */ };
  const handler = (event: BeforeUnloadEvent) => {
    // Çıkış bastırması OLAY ANINDA denetlenir (söküm React render'ı bekler,
    // logout navigasyonu beklemez): uyarı diyaloğu logoutRedirect'in ortasına
    // düşmez, flush da silinen taslağı geri yazmaz.
    if (allDraftsSuppressed) return;
    onFlush?.(); // ayrılmadan önce bekleyen taslak yazımını diske indir
    event.preventDefault();
    // Eski tarayıcı sözleşmesi: returnValue dolu olmadan uyarı çıkmaz.
    event.returnValue = "";
  };
  window.addEventListener("beforeunload", handler);
  return () => window.removeEventListener("beforeunload", handler);
}

export interface DebouncedFn {
  (): void;
  /** Bekleyen çağrıyı iptal eder (unmount temizliği). */
  cancel: () => void;
  /** Bekletmeden hemen çalıştırır (oturum düşmesi / pagehide flush'ı). */
  flush: () => void;
}

export function debounce(fn: () => void, ms: number): DebouncedFn {
  let timer: ReturnType<typeof setTimeout> | null = null;
  const cancel = () => {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };
  const debounced = () => {
    cancel();
    timer = setTimeout(() => {
      timer = null;
      fn();
    }, ms);
  };
  debounced.cancel = cancel;
  debounced.flush = () => {
    cancel();
    fn();
  };
  return debounced;
}
