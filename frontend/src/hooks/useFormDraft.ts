import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { SESSION_EXPIRED_EVENT } from "@/lib/api";
import {
  attachUnloadGuard,
  debounce,
  type DebouncedFn,
  type DraftStore,
  type LoadedDraft,
} from "@/lib/formDraft";

// =====================================================================
// Form taslağı React kancası (G004 · sertleştirme 4-C).
//
// Sözleşme:
//  - Taslak YALNIZ mount'ta bir kez okunur → `pending`. Geri yükleme SESSİZ
//    DEĞİLDİR: sayfa bir şerit gösterir, kullanıcı `restore()`/`dismiss()` der.
//  - Yazım yalnız `dirty` iken yapılır — dokunulmamış form, bekleyen taslağın
//    üzerine boş veri yazmaz.
//  - `beforeunload` yalnız `warnOnUnload` (varsayılan: `dirty`) iken bağlanır.
//  - `clear()` (kaydet/iptal) taslağı siler VE yeniden yazımı kilitler; veri
//    tekrar değişene dek "kaydedilmiş verinin hayaleti" geri yazılmaz.
// =====================================================================

const DEFAULT_DEBOUNCE_MS = 800;

export interface UseFormDraftOptions<T> {
  /** Diske yazılacak güncel anlık görüntü (her render'da yeniden kurulabilir). */
  data: T;
  /** Saklamaya/uyarmaya değer bir içerik var mı? */
  dirty: boolean;
  /** false ise taslak hiç okunmaz/yazılmaz (ör. düzenleme modu). */
  enabled?: boolean;
  debounceMs?: number;
  /** Sekme kapatma uyarısı koşulu. Varsayılan `dirty`. */
  warnOnUnload?: boolean;
}

export interface FormDraftHandle<T> {
  /** Mount'ta bulunan taslak — şerit bunu gösterir; yoksa null. */
  pending: LoadedDraft<T> | null;
  /** Şeridi kapatır ve taslak veriyi döner (sayfa state'e uygular). */
  restore: () => T | null;
  /** Şeridi kapatır ve taslağı siler ("yoksay"). */
  dismiss: () => void;
  /** Başarılı kayıt/iptal sonrası taslağı siler ve yazımı kilitler. */
  clear: () => void;
}

export function useFormDraft<T>(
  store: DraftStore<T>,
  options: UseFormDraftOptions<T>,
): FormDraftHandle<T> {
  const {
    data,
    dirty,
    enabled = true,
    debounceMs = DEFAULT_DEBOUNCE_MS,
    warnOnUnload = dirty,
  } = options;

  const [pending, setPending] = useState<LoadedDraft<T> | null>(() =>
    enabled ? store.load() : null,
  );

  // Yazıcı, render kimliğinden bağımsız olsun diye güncel değerleri ref'ten okur.
  const latest = useRef({ data, dirty, enabled });
  latest.current = { data, dirty, enabled };

  // clear() sonrası kilit: veri tekrar değişene dek yazma.
  const suppressed = useRef(false);

  // Tek debounce örneği — her render'da yenisi kurulsa bekleyen yazım düşerdi.
  const writerRef = useRef<DebouncedFn | null>(null);
  if (writerRef.current === null) {
    writerRef.current = debounce(() => {
      const current = latest.current;
      if (suppressed.current || !current.enabled || !current.dirty) return;
      store.save(current.data);
    }, debounceMs);
  }
  const writer = writerRef.current;

  // Değişiklik algısı referansa değil İÇERİĞE bağlı: `data` her render'da yeni
  // bir nesne olsa da effect yalnız içerik değişince koşar (aksi hâlde clear()
  // kilidi bir sonraki render'da anında açılırdı).
  const serialized = useMemo(() => {
    try {
      return JSON.stringify(data);
    } catch {
      return "";
    }
  }, [data]);

  useEffect(() => {
    if (!enabled || !dirty) return;
    suppressed.current = false;
    writer();
  }, [serialized, dirty, enabled, writer]);

  // Kaza navigasyonu (route değişimi) → unmount'ta bekleyen yazımı diske indir.
  useEffect(() => () => writer.flush(), [writer]);

  // Oturum düşmesi (401 → logout redirect) ve sekme gizlenmesi: bekletme yok.
  useEffect(() => {
    const flush = () => writer.flush();
    window.addEventListener(SESSION_EXPIRED_EVENT, flush);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, flush);
      window.removeEventListener("pagehide", flush);
    };
  }, [writer]);

  // beforeunload YALNIZ kirli durumda bağlanır (attachUnloadGuard testli).
  useEffect(() => attachUnloadGuard(warnOnUnload, () => writer.flush()), [warnOnUnload, writer]);

  const restore = useCallback(() => {
    const found = pending;
    setPending(null);
    return found ? found.data : null;
  }, [pending]);

  const dismiss = useCallback(() => {
    setPending(null);
    store.clear();
  }, [store]);

  const clear = useCallback(() => {
    suppressed.current = true;
    writer.cancel();
    store.clear();
    setPending(null);
  }, [store, writer]);

  return { pending, restore, dismiss, clear };
}
