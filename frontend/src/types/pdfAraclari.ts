// PDF araçları sözleşmesi — `docs/plan/pdf-araclari-plani-2026-10-07.md` §3 (ve §6.3 son satır) ile BİREBİR.
// Alan adları sunucunun (`backend/routes/pdf_araclari.py`) Pydantic modelleriyle aynıdır; değişiklik önce planda yapılır.

/** Sayfa boyutu PDF puanı, döndürme uygulanmış görünür düzlem. */
export interface DosyaSayfasi {
  no: number;
  genislik: number;
  yukseklik: number;
}

/** Ortak dosya nesnesi (`Dosya`). `id` sahibine bağlıdır; başkasının id'si her uçta 404. */
export interface Dosya {
  id: string;
  ad: string;
  sayfa: number;
  boyut: number;
  sayfalar: DosyaSayfasi[];
  /** Yalnız `sikistir` çıktısında: 0-1 arası küçültme oranı (0 = girdi kopyası döndü). */
  kucultme?: number;
}

export const ISLEMLER = ["birlestir", "bol", "sayfa_duzenle", "sikistir", "karart", "damga", "not", "donustur"] as const;
export type Islem = (typeof ISLEMLER)[number];

/** `bol`: `araliklar` (1 tabanlı, kapalı) YA DA `her_n` — tam biri. */
export interface BolParametreleri {
  araliklar?: [number, number][];
  her_n?: number;
}

export type DondurmeAcisi = 0 | 90 | 180 | 270;

export interface SayfaKaydi {
  no: number;
  /** Mevcut döndürmeye EKLENİR. */
  dondur?: DondurmeAcisi;
}

/** `sayfa_duzenle`: listedeki sıra = yeni sıra; listede olmayan sayfa SİLİNİR; boş liste 422. */
export interface SayfaDuzenleParametreleri {
  sayfalar: SayfaKaydi[];
}

export const SIKISTIRMA_SEVIYELERI = ["ekran", "ebook", "yazici"] as const;
export type SikistirmaSeviyesi = (typeof SIKISTIRMA_SEVIYELERI)[number];

export interface SikistirParametreleri {
  seviye: SikistirmaSeviyesi;
}

/** PDF puanı, sol-üst orijin; sayfa dışına taşan alan kırpılır. */
export interface KarartmaAlani {
  sayfa: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface KarartParametreleri {
  alanlar: KarartmaAlani[];
}

export const DAMGA_KONUMLARI = ["sag-ust", "sol-ust", "sag-alt", "sol-alt", "orta"] as const;
export type DamgaKonumu = (typeof DAMGA_KONUMLARI)[number];

/** Metin ≤ 120 karakter; `renk` `#rrggbb`; `punto` 4-144. */
export interface DamgaParametreleri {
  metin: string;
  konum: DamgaKonumu;
  sayfalar?: "hepsi" | number[];
  punto?: number;
  renk?: string;
}

/** Yapışkan not; metin ≤ 2.000 karakter. */
export interface NotParametreleri {
  sayfa: number;
  x: number;
  y: number;
  metin: string;
}

export type IslemParametreleri =
  | { islem: "birlestir"; parametreler: Record<string, never> }
  | { islem: "bol"; parametreler: BolParametreleri }
  | { islem: "sayfa_duzenle"; parametreler: SayfaDuzenleParametreleri }
  | { islem: "sikistir"; parametreler: SikistirParametreleri }
  | { islem: "karart"; parametreler: KarartParametreleri }
  | { islem: "damga"; parametreler: DamgaParametreleri }
  | { islem: "not"; parametreler: NotParametreleri }
  | { islem: "donustur"; parametreler: Record<string, never> };

/** `POST /api/pdf-araclari/islem` gövdesi. `birlestir` dışında `girdiler` tek elemanlıdır. */
export type IslemIstegi = IslemParametreleri & {
  girdiler: string[];
  cikti_adi?: string;
};

export interface IslemYaniti {
  ciktilar: Dosya[];
}

// G283: yön/durum birlikleri tek yerde — `types/belge.ts` (kart belgesi sözleşmesi); burada yalnız yeniden dışa aktarılır.
import type { BelgeDurumu, BelgeYonu } from "./belge";
export type { BelgeDurumu, BelgeYonu } from "./belge";

/** `POST /api/pdf-araclari/karta-bagla` (§3 + §6.3; G273 kullanır). */
export interface KartaBaglaIstegi {
  id: string;
  case_id: number;
  belge_turu_kodu: string;
  dosya_adi: string;
  case_party_id?: number;
  /** UUID — aynı kimlikle tekrar istek yeni belge AÇMAZ (`reused: true`). */
  istek_kimligi: string;
  yon?: BelgeYonu;
  durum?: BelgeDurumu;
}

export interface KartaBaglaYaniti {
  document_id: number;
  reused: boolean;
}

/** `POST /api/pdf-araclari/karttan-al` — yanıt `Dosya`. */
export interface KarttanAlIstegi {
  document_id: number;
}

/**
 * G273 — tezgâhın kart bağlamı (sözleşme dışı, yalnız istemci): `CaseDetails`'ten `navigate("/belge-tezgahi", { state })`
 * ile gelen belge kimlikleri (açılışta sırayla `karttan-al`) ve "Karta bağla" diyaloğunda ön-seçili kart künyesi.
 */
export interface KartOzeti {
  id: number;
  tracking_no?: string | null;
  esas_no?: string | null;
  court?: string | null;
  status?: string | null;
  parties?: KartTarafi[];
}

export interface KartTarafi {
  id: number;
  party_type: string;
  name: string;
  role?: string;
}

export interface BelgeTezgahiGirisi {
  document_ids?: number[];
  case?: KartOzeti;
}

/** Sunucu hata gövdesi: `detail` düz metin (FastAPI) ya da `{mesaj, error_kod}` (PDF araçları `_hata`). */
export interface PdfAraclariHataDetayi {
  mesaj: string;
  error_kod: string;
}
