// =====================================================================
// Uygulama depolama anahtarlarının TEK envanteri (G004 · sertleştirme 4-C).
//
// Çıkışta eskiden `sessionStorage.clear()` + `localStorage.clear()` çağrılıyordu.
// Bu iki çağrı AYNI ORIGIN'deki HER ŞEYİ siler: MSAL'ın kendi oturum kayıtları,
// başka bir sekmede açık uygulamanın verisi, tarayıcı eklentilerinin origin
// kayıtları... Artık yalnız aşağıda sayılan HUKDOK anahtarları silinir.
//
// MSAL: kendi anahtarlarını kendisi yönetir (msalConfig cacheLocation =
// sessionStorage). Oturum temizliği `instance.logoutRedirect()` ile yapılır;
// MSAL anahtarlarına ELLE dokunulmaz — yarım silinmiş bir MSAL cache'i
// "interaction_in_progress" gibi kilitli durumlar üretir.
//
// YENİ ANAHTAR EKLERKEN: ya `hukdok.` / `hukudok-` / `hukudok.` önekiyle
// adlandır (otomatik kapsanır) ya da APP_STORAGE_KEYS listesine ekle.
// =====================================================================

/** Önekli anahtarlar otomatik kapsanır (yeni taslaklar bu öneki kullanır). */
export const APP_STORAGE_PREFIXES = ["hukdok.", "hukudok.", "hukudok-"] as const;

/** Öneksiz, tarihsel anahtarlar. Yeniden adlandırmak kullanıcı verisini
 *  düşüreceği için oldukları gibi bırakılıp burada sayılıyorlar. */
export const APP_STORAGE_KEYS = ["yetki_belgesi_avukat_cache"] as const;

export function isAppStorageKey(key: string): boolean {
  if ((APP_STORAGE_KEYS as readonly string[]).includes(key)) return true;
  return APP_STORAGE_PREFIXES.some(prefix => key.startsWith(prefix));
}

/** Depodaki uygulama anahtarlarını listeler (silmeden). */
export function appStorageKeys(storage: Storage): string[] {
  const keys: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key !== null && isAppStorageKey(key)) keys.push(key);
  }
  return keys;
}

/**
 * Yalnız uygulama anahtarlarını siler; MSAL ve yabancı anahtarlar korunur.
 * Depo erişimi engelliyse (gizli mod kısıtı) sessizce boş döner.
 *
 * @returns silinen anahtarlar (log/teşhis için)
 */
export function clearAppStorage(storages?: Storage[]): string[] {
  let targets = storages;
  if (!targets) {
    try {
      targets = [window.sessionStorage, window.localStorage];
    } catch {
      return [];
    }
  }

  const removed: string[] = [];
  for (const storage of targets) {
    try {
      for (const key of appStorageKeys(storage)) {
        storage.removeItem(key);
        removed.push(key);
      }
    } catch {
      // tek bir depo erişilemezse diğeri yine temizlensin
    }
  }
  return removed;
}
