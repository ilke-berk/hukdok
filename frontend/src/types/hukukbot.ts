// Hukukbot API sözleşmesi (karar 021, G204) — hukbot `app/schemas.py` + `app/api.py`'den
// OKUNARAK yazıldı (../hukukbot-ui, d02401c). Alan adları sunucuyla birebir (snake_case);
// sunucu değişirse burası da değişir. İstemci: `lib/hukukbotApi.ts`.

/** Mesaj rolü — kanonik "user" | "model" (eski kayıtlardaki "assistant" sunucuda "model"e çevrilir). */
export type HukukbotRol = "user" | "model";

/**
 * Kaynak kartı — `rag_core._build_final_sources` çıktısı. `download_url` hukbot'a göre
 * görelidir (`/download/<ad>`); tarayıcıdan DOĞRUDAN kullanılmaz — indirme
 * `hukukbotApi.indir(filename)` ile (Authorization başlığı gerekir).
 */
export interface HukukbotKaynak {
  file_display_name: string;
  filename: string;
  text_preview: string;
  metadata?: Record<string, unknown> | null;
  download_url?: string;
  /**
   * HUKDOK belge numarası — belge HUKDOK'tan aktarıldıysa dolu (hukbot `rag_core._hukdok_id`).
   * Doluysa PDF HUKDOK'un `/api/documents/{id}/download` ucundan (SharePoint arşivi) açılır;
   * yoksa eski `/download/{filename}`. Alan eklenmeden önce kaydedilmiş mesajlarda yoktur.
   */
  hukdok_id?: number | null;
  /**
   * Atıf doğrulaması (hukbot `app/citation_check.py`, 28.09). Alan eklenmeden önceki mesajlarda yoktur.
   * `aramada_getirildi`: belge bu cevap için aramada gerçekten getirildi mi — `false` = yalnız modelin
   * metninde anıldı (uydurma şüphesi); `null` = model arama izi döndürmedi, hüküm yok.
   */
  aramada_getirildi?: boolean | null;
  /** Cevapta "(Kaynak: ...)" ile anıldı mı — `false` = aramada geldi ama cevapta kullanılmadı. */
  metinde_atif?: boolean;
  /** Bu belgeye atfedilen `[Alıntı: "..."]`'ler ve belge metninde birebir bulunup bulunmadıkları. */
  alintilar?: HukukbotAlinti[];
}

export interface HukukbotAlinti {
  metin: string;
  /** `true` belge metninde bulundu · `false` bulunamadı · `null` denetlenemedi (çok kısa / arama izi yok). */
  dogrulandi: boolean | null;
  /** Yalnız bulunamayanlarda: alıntının belgede birebir geçen oranı (0-1). */
  benzerlik?: number;
}

/** `schemas.MessageBase` — sunucudaki `sources` serbest sözlük listesidir; pratikte `HukukbotKaynak`. */
export interface HukukbotMesaj {
  role: HukukbotRol;
  content: string;
  sources?: HukukbotKaynak[] | null;
}

/** `schemas.ChatSessionListItem` — `GET /sessions` satırı (mesaj gövdesi yok, son mesaj önizlemesi var). */
export interface HukukbotOturumOzeti {
  id: string;
  title: string;
  created_at: string;
  is_pinned: boolean;
  preview?: string | null;
}

/** `schemas.ChatSessionResponse` — `GET /sessions/{id}` (mesajlarıyla), `POST` ve `PATCH` yanıtı. */
export interface HukukbotOturum {
  id: string;
  title: string;
  created_at: string;
  is_pinned: boolean;
  messages: HukukbotMesaj[];
}

/** `schemas.ChatSessionUpdate` — `PATCH /sessions/{id}`; verilmeyen alan değişmez. */
export interface HukukbotOturumGuncelleme {
  title?: string;
  is_pinned?: boolean;
}

/** `schemas.AskRequest` — `POST /ask` gövdesi. Oturum gövdede DEĞİL, `session-id` başlığında gider. */
export interface HukukbotSoru {
  question: string;
  history?: HukukbotMesaj[] | null;
}

/**
 * `/ask` NDJSON akış olayı — `api.py::response_generator`:
 * - `content`: cevap metninin sıradaki parçası (birleştirilerek gösterilir),
 * - `sources`: kaynak listesi (akışın sonunda, bir kez; boş liste olabilir),
 * - `status`: arama sürerken ara durum metni (ilk `content`'ten önce, sıfır ya da daha çok kez),
 * - `error`: akış sırasında sunucu istisnası (`data` = hata metni); sonrasında olay gelmez.
 */
export type HukukbotAkisOlayi =
  | { type: "content"; data: string }
  | { type: "sources"; data: HukukbotKaynak[] }
  /** Arama sürerken ara durum ("Arşiv taranıyor: …") — hukbot 28.09; kaydedilmez, ilk metin parçasına dek gösterilir. */
  | { type: "status"; data: string }
  | { type: "error"; data: string };
