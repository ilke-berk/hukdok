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
