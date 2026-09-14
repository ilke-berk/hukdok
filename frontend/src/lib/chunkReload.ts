/**
 * G182: route düzeyinde kod bölmenin (App.tsx `React.lazy`) deploy sonrası tuzağı.
 *
 * Her deploy yeni hash'li parça adları üretir; eski parçalar yeni imajda yoktur.
 * Açık kalmış bir sekme ESKİ index.html'in parça adlarıyla bir sayfaya geçerse
 * dinamik import 404 alır (nginx `/assets/` bloğu eksik parçada index.html'e
 * DÜŞMEZ, `=404` döner) ve tarayıcı "Failed to fetch dynamically imported module"
 * fırlatır. Çözüm: sayfayı BİR kez yenile — yeni index.html yeni parça adlarını getirir.
 *
 * Döngü bekçisi sessionStorage bayrağıdır: yenilemeden sonra da parça yüklenemiyorsa
 * (sunucu gerçekten erişilemez) ikinci kez yenilenmez, hata ErrorBoundary'ye düşer.
 * Bir parça başarıyla yüklenince bayrak silinir; sonraki deploy yine bir kez yenileyebilir.
 * Storage kapalıysa bayrak yazılamaz → döngü engellenemeyeceği için yenileme YAPILMAZ.
 *
 * Ayrı modül bilinçli: App.tsx'ten fonksiyon export etmek
 * `react-refresh/only-export-components` uyarısı üretir (lint tabanı 0 uyarı).
 */
export const CHUNK_RELOAD_FLAG = "hukudok:chunk-reload";

// Tarayıcı başına dinamik import başarısızlık mesajları + Vite'in CSS ön yükleme hatası.
const CHUNK_ERROR_PATTERNS: RegExp[] = [
  /Failed to fetch dynamically imported module/i, // Chromium
  /error loading dynamically imported module/i, // Firefox
  /Importing a module script failed/i, // Safari
  /Unable to preload CSS/i, // Vite __vitePreload
  /Loading (CSS )?chunk \S+ failed/i, // webpack uyumlu biçim (ChunkLoadError)
];

/** Hata, bir kod parçasının AĞDAN yüklenemediğini mi söylüyor? (modül içi çalışma hatası değil) */
export function isChunkLoadError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  if (error.name === "ChunkLoadError") return true;
  return CHUNK_ERROR_PATTERNS.some((pattern) => pattern.test(error.message));
}

/**
 * Dinamik import'u sarar: parça yüklenemezse bir kez sayfayı yeniler.
 * Yenileme başlatıldığında dönen söz HİÇ çözülmez — React Suspense fallback'inde
 * kalır, sayfa giderken hata ekranı yanıp sönmez.
 *
 * `reload` yalnız test için enjekte edilebilir (jsdom `location.reload`'u değiştirilemez).
 */
export async function importWithReload<T>(
  factory: () => Promise<T>,
  reload: () => void = () => window.location.reload(),
): Promise<T> {
  let mod: T;
  try {
    mod = await factory();
  } catch (error) {
    if (!isChunkLoadError(error)) throw error;

    let firstAttempt = false;
    try {
      firstAttempt = sessionStorage.getItem(CHUNK_RELOAD_FLAG) === null;
      if (firstAttempt) sessionStorage.setItem(CHUNK_RELOAD_FLAG, new Date().toISOString());
    } catch {
      // Bayrak okunamıyor/yazılamıyor → döngü engellenemez; yenileme yok, hata görünür kalsın.
      firstAttempt = false;
    }
    if (!firstAttempt) throw error;

    console.warn("Sayfa parçası yüklenemedi (büyük olasılıkla yeni sürüm yayında) — sayfa bir kez yenileniyor.", error);
    reload();
    return new Promise<T>(() => {});
  }

  try {
    sessionStorage.removeItem(CHUNK_RELOAD_FLAG);
  } catch {
    // Storage kapalı — bayrak zaten yazılamazdı.
  }
  return mod;
}
