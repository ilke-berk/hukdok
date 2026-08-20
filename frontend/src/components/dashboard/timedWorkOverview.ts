/**
 * G086 (idari yarı) — "04 · İnceleme · Süreli İşler" panelinin saf yardımcıları.
 *
 * Ayrı dosyada: bileşen dosyasından fonksiyon ihraç etmek
 * `react-refresh/only-export-components` uyarısı üretiyor (eslint.config.js) —
 * `deadlineBody.ts` ve `notifications/badge.ts` ile aynı gerekçe.
 *
 * Kaynak sözleşme G087'nin iki SALT OKUMA ucudur
 * (`backend/routes/notifications.py`):
 *   - `GET /api/notifications/overview` → `{days, limit, total, unread, items[]}`;
 *     satır alanları `id, type, severity, title, recipient_email, case_id,
 *     due_date, read_at, is_read, created_at`. Gövde (`body`) BİLİNÇLİ olarak
 *     yayınlanmaz — idari görünümün sorusu "kime gitti, okundu mu"dur.
 *   - `GET /api/notifications/unresolved-targets` →
 *     `{items:[{name, case_count}], total_names, total_cases}`.
 *
 * Tür süzmesi BURADA YAPILMAZ: uç kapsamı zaten süre/duruşma ile sınırlıyor
 * (`OVERVIEW_TYPES`) ve `total`/`unread` sayaçlarını da o kapsamdan üretiyor.
 * İstemcide ikinci bir süzgeç kurmak, görünen satırlarla sayaçları çelişkiye
 * düşürürdü — sayaç uçtan, satır uçtan.
 */
import { countdownLabel, daysUntil } from "@/components/dashboard/deadlineBody";
import { formatAgo } from "@/lib/relativeTime";

/** Uç varsayılanı 30; pencere `created_at` üzerindedir (uç docstring'i). */
export const OVERVIEW_DAYS = 30;

/** Uç tavanı 500; panel sayfalamaz, "en yakın N"i gösterir ve fazlasını yazar. */
export const OVERVIEW_LIMIT = 100;

export const OVERVIEW_ENDPOINT =
  `/api/notifications/overview?days=${OVERVIEW_DAYS}&limit=${OVERVIEW_LIMIT}`;
export const UNRESOLVED_ENDPOINT = "/api/notifications/unresolved-targets";

export const OVERVIEW_ERROR = "Süre bildirimleri alınamadı.";
export const UNRESOLVED_ERROR = "Hedefsiz dava sayacı alınamadı.";

export interface OverviewNotification {
  id: number;
  type: string;
  severity: string | null;
  title: string;
  recipient_email: string | null;
  case_id: number | null;
  due_date: string | null;
  read_at: string | null;
  is_read: boolean;
  created_at: string | null;
}

export interface OverviewEnvelope {
  days: number;
  limit: number;
  total: number;
  unread: number;
  items: OverviewNotification[];
}

export interface UnresolvedTarget {
  name: string;
  case_count: number;
}

export interface UnresolvedEnvelope {
  items: UnresolvedTarget[];
  total_names: number;
  total_cases: number;
}

function metin(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function sayi(value: unknown, yedek: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : yedek;
}

/**
 * Uç gövdesini tipli zarfa çevirir; şekil beklenmedikse **null** döner.
 *
 * null = HATA (G002 dersi): boş listeye çevirmek "bildirim yok" der ve gerçek
 * kesintiyi gizlerdi. Çağıran tarafın bunu hata şeridiyle göstermesi beklenir.
 */
export function parseOverviewEnvelope(data: unknown): OverviewEnvelope | null {
  if (!data || typeof data !== "object") return null;
  const zarf = data as Record<string, unknown>;
  if (!Array.isArray(zarf.items)) return null;

  const items: OverviewNotification[] = [];
  for (const ham of zarf.items) {
    if (!ham || typeof ham !== "object") return null;
    const r = ham as Record<string, unknown>;
    if (typeof r.id !== "number") return null;
    const readAt = metin(r.read_at);
    items.push({
      id: r.id,
      type: typeof r.type === "string" ? r.type : "",
      severity: metin(r.severity),
      title: typeof r.title === "string" ? r.title : "",
      recipient_email: metin(r.recipient_email),
      case_id: typeof r.case_id === "number" ? r.case_id : null,
      due_date: metin(r.due_date),
      read_at: readAt,
      // Uç ikisini de yolluyor; `read_at` varsa okunmuştur — iki alan
      // çeliştiğinde damga kazanır (okunma anının kanıtı odur).
      is_read: r.is_read === true || readAt !== null,
      created_at: metin(r.created_at),
    });
  }

  // Sayaçlar uçtan gelir ve `limit` UYGULANMADAN hesaplanmıştır; alan eksikse
  // görünen satırlardan türetilir — uydurma değil, EKSİK sayım olur ve üst
  // sınır notu (`capNote`) da o zaman görünmez.
  return {
    days: sayi(zarf.days, OVERVIEW_DAYS),
    limit: sayi(zarf.limit, OVERVIEW_LIMIT),
    total: sayi(zarf.total, items.length),
    unread: sayi(zarf.unread, items.filter((x) => !x.is_read).length),
    items,
  };
}

/** Hedefsiz sayacı zarfı; şekil beklenmedikse null (bkz. `parseOverviewEnvelope`). */
export function parseUnresolvedEnvelope(data: unknown): UnresolvedEnvelope | null {
  if (!data || typeof data !== "object") return null;
  const zarf = data as Record<string, unknown>;
  if (!Array.isArray(zarf.items)) return null;

  const items: UnresolvedTarget[] = [];
  for (const ham of zarf.items) {
    if (!ham || typeof ham !== "object") return null;
    const r = ham as Record<string, unknown>;
    const name = metin(r.name);
    if (!name) return null;
    items.push({ name, case_count: sayi(r.case_count, 0) });
  }

  return {
    items,
    total_names: sayi(zarf.total_names, items.length),
    total_cases: sayi(zarf.total_cases, items.reduce((t, x) => t + x.case_count, 0)),
  };
}

/** ISO günü (`2026-09-03`) → `03.09.2026`; okunamazsa "—". */
export function dueLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const text = value.trim();
  const d = new Date(text.includes("T") ? text : `${text}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  const gun = String(d.getDate()).padStart(2, "0");
  const ay = String(d.getMonth() + 1).padStart(2, "0");
  return `${gun}.${ay}.${d.getFullYear()}`;
}

/**
 * Başlıktaki DONMUŞ geri sayım eki (`deadline_scanner`:
 * `"Süre yaklaşıyor: {kural} — {N gün kaldı}"`) yazım anında dondu; dedupe
 * mevcut satırı güncellemiyor. Panel geri sayımı taze `due_date`ten hesapladığı
 * için ek başlıktan düşürülür — aynı satırda iki farklı sayı çelişkidir.
 * Kalıp dar: yalnız SONDAKİ "— N gün kaldı" / "— son gün bugün" düşer.
 */
const FROZEN_TITLE_COUNTDOWN = /\s+[—–]\s+(?:son gün bugün|\d+ gün kaldı)\s*$/;

export function titleLabel(title: string | null | undefined): string {
  const text = (title ?? "").trim();
  if (!text) return "Başlıksız uyarı";
  return text.replace(FROZEN_TITLE_COUNTDOWN, "").trim() || text;
}

/**
 * Alıcı etiketi. Adres AYNEN gösterilir — idari görünümün sorusu "kime"dir ve
 * kısaltmak (yalnız yerel kısım) iki alan adı arasında karışıklık üretirdi.
 */
export function recipientLabel(email: string | null | undefined): string {
  return metin(email) ?? "Alıcı yok";
}

/** Okunma durumu: damgalıysa göreli zamanıyla ("Okundu · 3 sa"). */
export function readLabel(item: OverviewNotification): string {
  if (!item.is_read) return "Okunmadı";
  return item.read_at ? `Okundu · ${formatAgo(item.read_at)}` : "Okundu";
}

/** Üst şerit sayacı — sayılar uçtan gelir, satırlardan sayılmaz. */
export function overviewSummary(total: number, unread: number): string {
  return `${total} uyarı · ${unread} okunmamış`;
}

/** Tavana dayanıldığında dürüst not; dayanılmadıysa null. */
export function capNote(total: number, shown: number): string | null {
  if (total <= shown) return null;
  return `${total} uyarının en yakın ${shown} tanesi listeleniyor.`;
}

/** Hedefsiz sayacı başlığı (G080): "97 dava · 2 sorumlu adı". */
export function unresolvedSummary(env: UnresolvedEnvelope): string {
  return `${env.total_cases} dava · ${env.total_names} sorumlu adı`;
}

export interface TimedWorkRow {
  item: OverviewNotification;
  /** `due_date`ten TAZE hesaplanır; tarihsiz satırda null. */
  daysLeft: number | null;
  countdown: string;
  overdue: boolean;
  title: string;
  dueLabel: string;
  recipient: string;
  readLabel: string;
}

/**
 * Uç satırlarını panel satırlarına çevirir.
 *
 * Sıra UÇTAN gelir (`coalesce(due_date) ASC, id ASC`) ve BOZULMAZ — ikinci bir
 * sıralama kuralı ikinci bir doğruluk kaynağı olurdu.
 *
 * Günü geçmiş satır DÜŞÜRÜLMEZ (avukat panelinin tersi): takip görünümünün asıl
 * işi "süresi geçti ve hâlâ okunmadı"yı göstermektir. Aynı sürenin eşik daraldıkça
 * açılan ikinci satırı da elenmez — her satır GÖNDERİLMİŞ bir bildirimdir ve
 * kendi okunma durumunu taşır; birleştirmek okunmamış bir bildirimi gizlerdi.
 */
export function timedWorkRows(
  items: OverviewNotification[] | null | undefined,
  now: Date = new Date(),
): TimedWorkRow[] {
  return (items ?? []).map((item) => {
    const daysLeft = daysUntil(item.due_date, now);
    return {
      item,
      daysLeft,
      countdown: daysLeft === null ? "Tarihsiz" : countdownLabel(daysLeft),
      overdue: daysLeft !== null && daysLeft < 0,
      title: titleLabel(item.title),
      dueLabel: dueLabel(item.due_date),
      recipient: recipientLabel(item.recipient_email),
      readLabel: readLabel(item),
    };
  });
}
