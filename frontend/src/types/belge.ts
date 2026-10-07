// Kart belgesi sözleşmesi (G283; plan §6 K11-K12, §6.3 ilk satır) — `GET /api/cases/{id}` `documents[]` ile BİREBİR
// (`backend/managers/case_manager.get_case`, G282). Kapalı listeler `backend/constants.py`'deki `BELGE_YONLERI` /
// `BELGE_KAYNAKLARI` / `BELGE_DURUMLARI` ile aynıdır (pad'siz düz string). Eski yanıtta alanlar yoksa GELEN / BELGE_HATTI /
// KESIN varsayılır (`belgeYonu`, `belgeKaynagi`, `belgeDurumu`) — kart kırılmaz.

export const BELGE_YONLERI = ["GELEN", "GIDEN"] as const;
export type BelgeYonu = (typeof BELGE_YONLERI)[number];

export const BELGE_KAYNAKLARI = ["BELGE_HATTI", "PDF_ARACLARI", "WORD", "ARSIV_AKTARIM", "TESLIM"] as const;
export type BelgeKaynagi = (typeof BELGE_KAYNAKLARI)[number];

export const BELGE_DURUMLARI = ["TASLAK", "KESIN"] as const;
export type BelgeDurumu = (typeof BELGE_DURUMLARI)[number];

/** Kaynak etiketleri (ekran/`aria-label`; `BelgeDurumCipi`). */
export const KAYNAK_ETIKETLERI: Record<BelgeKaynagi, string> = {
  BELGE_HATTI: "Belge hattı (yükle → analiz → onay)",
  PDF_ARACLARI: "PDF tezgâhı",
  WORD: "Word taslağı",
  ARSIV_AKTARIM: "Arşiv aktarımı",
  TESLIM: "Veri teslimi",
};

export const VARSAYILAN_YON: BelgeYonu = "GELEN";
export const VARSAYILAN_KAYNAK: BelgeKaynagi = "BELGE_HATTI";
export const VARSAYILAN_DURUM: BelgeDurumu = "KESIN";

/** Kartın belge satırı (`documents[]`). `yon`/`kaynak`/`durum` yeni yanıtta her zaman dolu; eski yanıtta eksik olabilir. */
export interface KartBelgesi {
  id: number;
  original_filename: string;
  stored_filename: string;
  sharepoint_url?: string | null;
  belge_turu_kodu?: string | null;
  belge_turu_adi?: string | null;
  ai_summary?: string | null;
  uploaded_at?: string | null;
  case_party_id?: number | null;
  case_party_name?: string | null;
  yon?: string | null;
  kaynak?: string | null;
  durum?: string | null;
  /** Word taslağının SharePoint URL'si (K15; G285 "Word'de aç"). */
  word_url?: string | null;
  kesinlesme_tarihi?: string | null;
  /** `belge_surumleri` satır sayısı (K13). */
  surum_sayisi?: number | null;
  /** G285: yeni sürüm taslağının bağlı olduğu (kesinleşmiş) belge (K14). */
  onceki_document_id?: number | null;
}

// ── Word yaşam döngüsü (G285; plan §6.3, uçlar `backend/routes/belge_yasam.py`) ──────────────────────────────

/** `POST /api/cases/{id}/belgeler/yeni` gövdesi. `belge_turu_kodu` `_` pad'li gider (sunucu normalize eder). */
export interface YeniBelgeIstegi {
  belge_turu_kodu: string;
  ad: string;
  sablon?: "bos";
  case_party_id?: number;
}

/** `word_ac` = `ms-word:ofe|u|<word_url>` (masaüstü Word protokolü). */
export interface YeniBelgeYaniti {
  document_id: number;
  word_url: string;
  word_ac: string;
}

/** `POST /api/documents/{id}/surum` yanıtı; aynı sha → `degisti: false` (satır yine açılır — not için). */
export interface SurumKaydetYaniti {
  surum_no: number;
  sha256: string;
  degisti: boolean;
}

/** `GET /api/documents/{id}/surumler` satırı (`surum_no` artan; KESIN belgede son satır `kesin: true`). */
export interface BelgeSurumu {
  surum_no: number;
  sha256: string;
  not: string | null;
  olusturan_email: string | null;
  olusturulma: string | null;
  kesin: boolean;
}

/** `POST /api/documents/{id}/kesinlestir` yanıtı (aynı `istek_kimligi` → `reused: true`). */
export interface KesinlestirYaniti {
  document_id: number;
  reused: boolean;
}

/** `POST /api/documents/{id}/yeni-surum-taslagi` yanıtı (yeni TASLAK satırı; `reused` yanıtında URL'ler boş olabilir). */
export interface YeniSurumTaslagiYaniti {
  document_id: number;
  reused: boolean;
  word_url: string | null;
  word_ac: string | null;
}

/**
 * Yeni sürüm zinciri (K14): `onceki_document_id` bağını kartın belgeleri içinde geriye yürür. `no` = zincirdeki sıra
 * (bağsız belge 1), `onceki` = doğrudan önceki belge (kartta yoksa — silinmiş — `null`). Döngüye karşı sınırlı.
 */
export function surumZinciri<T extends Pick<KartBelgesi, "id" | "onceki_document_id">>(
  doc: Pick<KartBelgesi, "id" | "onceki_document_id">,
  belgeler: readonly T[],
): { no: number; onceki: T | null } {
  const harita = new Map(belgeler.map((b) => [b.id, b]));
  const onceki = doc.onceki_document_id != null ? harita.get(doc.onceki_document_id) ?? null : null;
  let no = 1;
  let imlec: number | null | undefined = doc.onceki_document_id;
  const gorulen = new Set<number>([doc.id]);
  while (imlec != null && !gorulen.has(imlec) && no < 100) {
    gorulen.add(imlec);
    no += 1;
    imlec = harita.get(imlec)?.onceki_document_id;
  }
  return { no, onceki };
}

type YonDurumKaynak = Pick<KartBelgesi, "yon" | "kaynak" | "durum">;

/** Büyük harf katlama: düz `toUpperCase` hem `i` hem `ı`yı `I` yapar (tr-TR katlaması `i → İ` verir, kodlar ASCII). */
function katla(v: string | null | undefined): string {
  return (v ?? "").trim().toUpperCase();
}

export function belgeYonu(doc: YonDurumKaynak): BelgeYonu {
  const v = katla(doc.yon);
  return (BELGE_YONLERI as readonly string[]).includes(v) ? (v as BelgeYonu) : VARSAYILAN_YON;
}

export function belgeKaynagi(doc: YonDurumKaynak): BelgeKaynagi {
  const v = katla(doc.kaynak);
  return (BELGE_KAYNAKLARI as readonly string[]).includes(v) ? (v as BelgeKaynagi) : VARSAYILAN_KAYNAK;
}

export function belgeDurumu(doc: YonDurumKaynak): BelgeDurumu {
  const v = katla(doc.durum);
  return (BELGE_DURUMLARI as readonly string[]).includes(v) ? (v as BelgeDurumu) : VARSAYILAN_DURUM;
}

export function taslakMi(doc: YonDurumKaynak): boolean {
  return belgeDurumu(doc) === "TASLAK";
}
