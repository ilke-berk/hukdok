/**
 * G086 — "Süre Uyarıları" panelinin saf yardımcıları.
 *
 * Ayrı dosyada: bileşen dosyasından fonksiyon ihraç etmek
 * `react-refresh/only-export-components` uyarısı üretiyor (eslint.config.js) —
 * G083'ün `notifications/badge.ts` kararıyla aynı gerekçe.
 *
 * Kaynak sözleşme `backend/services/deadline_scanner.py`'dir: gece tarayıcısı
 * bildirim gövdesini `Etiket: değer` satırları hâlinde yazar (Dava / Aşama /
 * Tebliğ tarihi / Kural / Son gün / Kaydırma / Duruşma / Kaynak belge / Not),
 * sonuna `DİKKAT:` ile başlayan takvim uyarısını (varsa) ve HER ZAMAN şerhi
 * ekler. Panel bu satırları AYNEN gösterir — dayanağı görünmeyen uyarı olmasın.
 *
 * Geri sayım DAİMA `due_date`ten hesaplanır. `title` içindeki "N gün kaldı"
 * YAZIM ANINDA donar (dedupe mevcut satırı güncellemez, G085 notu) — taze sayım
 * yalnız tarihten gelir.
 */
import type { NotificationItem } from "@/hooks/useNotifications";

/** Gece tarayıcısının tür etiketleri (`deadline_scanner.SURE_TYPE` / `DURUSMA_TYPE`). */
export const SURE_TYPE = "sure_yaklasti";
export const DURUSMA_TYPE = "durusma_yaklasti";
export const DEADLINE_TYPES: readonly string[] = [SURE_TYPE, DURUSMA_TYPE];

/**
 * Kullanıcı şartı: şerh panelde BİR KEZ, görünür yerde durur. Gövdedeki kopyası
 * satırlardan ayıklanır (`deadline_scanner.SERH` ile birebir aynı metin).
 */
export const DEADLINE_DISCLAIMER = "Bu bilgilendirmedir, süre takibi yerine geçmez.";

/** Takvimi doğrulanmamış yıla düşen son gün uyarısının öneki (`TAKVIM_UYARISI`). */
const CALENDAR_WARNING_PREFIX = "DİKKAT";

/**
 * Gövdedeki "Son gün: … (14 gün kaldı)" / "Duruşma: … (son gün bugün)" ekleri
 * YAZIM ANINDA donar (`deadline_scanner._kalan_metni`). Panel geri sayımı taze
 * `due_date`ten hesapladığı için bu ek gösterimden düşürülür — aynı satırda iki
 * farklı sayı çelişkidir. Kalıp dar: "(YEREL, 1. karar)" ya da "(HMK m. 93)"
 * gibi anlam taşıyan parantezler korunur.
 */
const FROZEN_COUNTDOWN = /\s*\((?:son gün bugün|\d+ gün kaldı)\)\s*$/;

export function stripFrozenCountdown(value: string): string {
  return value.replace(FROZEN_COUNTDOWN, "").trim();
}

export interface DeadlineField {
  label: string;
  value: string;
}

export interface ParsedDeadlineBody {
  /** `Etiket: değer` satırları — gövdedeki sırayla. */
  fields: DeadlineField[];
  /** Takvim doğrulanmadı uyarısı (yoksa null) — satırda ayrıca belirtilir. */
  calendarWarning: string | null;
  /** Etiketsiz satırlar; sessizce yutulmasın diye taşınır. */
  extras: string[];
}

/** Gövdeyi etiketli satırlara ayırır; şerh ayıklanır, takvim uyarısı işaretlenir. */
export function parseDeadlineBody(body: string | null | undefined): ParsedDeadlineBody {
  const fields: DeadlineField[] = [];
  const extras: string[] = [];
  let calendarWarning: string | null = null;

  for (const raw of (body ?? "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line === DEADLINE_DISCLAIMER) continue;
    if (line.startsWith(CALENDAR_WARNING_PREFIX)) {
      calendarWarning = line;
      continue;
    }
    const match = /^([^:]+):\s*(.*)$/.exec(line);
    const value = match ? stripFrozenCountdown(match[2]) : "";
    if (match && value) {
      fields.push({ label: match[1].trim(), value });
    } else {
      extras.push(line);
    }
  }

  return { fields, calendarWarning, extras };
}

/** Etikete karşılık gelen İLK değer (yoksa null). Aynı etiket birden çok olabilir. */
export function fieldValue(parsed: ParsedDeadlineBody, label: string): string | null {
  const found = parsed.fields.find((f) => f.label === label);
  return found ? found.value : null;
}

/**
 * Satır başlığı: kural adı (dayanağın önündeki kısım) ya da tür karşılığı.
 * `title` alanı KULLANILMAZ — donmuş geri sayım metni taşıyor.
 */
export function deadlineHeadline(item: NotificationItem, parsed: ParsedDeadlineBody): string {
  if (item.type === DURUSMA_TYPE) return "Duruşma";
  const kural = fieldValue(parsed, "Kural");
  if (kural) return kural.split(" — ")[0].trim() || "Kanuni süre";
  return "Kanuni süre";
}

/** ISO tarihini (yalın gün ya da tam damga) yerel gün başlangıcına çevirir. */
export function parseDayStart(value: string | null | undefined): Date | null {
  if (!value) return null;
  const text = value.trim();
  if (!text) return null;
  const d = new Date(text.includes("T") ? text : `${text}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setHours(0, 0, 0, 0);
  return d;
}

/** Bugünden hedefe kalan tam gün sayısı (geçmiş için negatif); okunamazsa null. */
export function daysUntil(value: string | null | undefined, now: Date = new Date()): number | null {
  const target = parseDayStart(value);
  if (!target) return null;
  const today = new Date(now.getTime());
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/** Geri sayım etiketi — kullanıcı şartı: "14 gün kaldı". */
export function countdownLabel(daysLeft: number): string {
  if (daysLeft === 0) return "Bugün";
  if (daysLeft === 1) return "Yarın";
  if (daysLeft < 0) return `${Math.abs(daysLeft)} gün geçti`;
  return `${daysLeft} gün kaldı`;
}

/**
 * Aynı süreyi iki kez göstermeme anahtarı.
 *
 * Tarayıcı eşik daraldıkça (T-15 → T-7 → T-3 → T-1) YENİ satır açıyor
 * (`deadline_scanner` şerhi: dedupe mevcut satırı güncellemez). İki satır aynı
 * kaynağı anlatır; panel yalnız EN YENİSİNİ gösterir. `dedupe_key` uçtan
 * dönmediği için kimlik gövdedeki değişmez alanlardan kurulur — donmuş geri
 * sayım ekleri `parseDeadlineBody` içinde zaten ayıklanmış durumdadır.
 */
export function deadlineIdentity(item: NotificationItem, parsed: ParsedDeadlineBody): string {
  return [
    item.type,
    item.case_id ?? "-",
    item.due_date ?? "-",
    fieldValue(parsed, "Aşama") ?? "-",
    fieldValue(parsed, "Tebliğ tarihi") ?? "-",
    fieldValue(parsed, "Duruşma") ?? "-",
  ].join("|");
}

export interface DeadlineRow {
  item: NotificationItem;
  parsed: ParsedDeadlineBody;
  daysLeft: number;
  headline: string;
}

/**
 * Bildirim listesinden panel satırlarını süzer.
 *
 * - yalnız süre/duruşma türleri,
 * - `due_date`i okunabilen ve BUGÜN ya da SONRASI olanlar (panel "yaklaşan"ı
 *   anlatır; günü geçmiş uyarı zil panelinde durmaya devam eder),
 * - aynı kaynağın eski eşik satırları elenir (en yeni id kalır),
 * - en yakın tarih EN ÜSTTE.
 */
export function selectDeadlineRows(
  items: NotificationItem[] | null | undefined,
  now: Date = new Date(),
): DeadlineRow[] {
  const enYeni = new Map<string, DeadlineRow>();

  for (const item of items ?? []) {
    if (!DEADLINE_TYPES.includes(item.type)) continue;
    const daysLeft = daysUntil(item.due_date, now);
    if (daysLeft === null || daysLeft < 0) continue;

    const parsed = parseDeadlineBody(item.body);
    const key = deadlineIdentity(item, parsed);
    const mevcut = enYeni.get(key);
    if (mevcut && mevcut.item.id >= item.id) continue;
    enYeni.set(key, { item, parsed, daysLeft, headline: deadlineHeadline(item, parsed) });
  }

  return [...enYeni.values()].sort(
    (a, b) => a.daysLeft - b.daysLeft || a.item.id - b.item.id,
  );
}
