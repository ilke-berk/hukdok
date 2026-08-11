/**
 * Hata beacon'ı (Faz 2-C): yakalanmayan tarayıcı hatalarını backend'in
 * auth'suz `/api/client-error` ucuna raporlar (orada severity=ERROR ile
 * loglanır → GCP ERROR-oranı alarmı sayar). Konsol prod'da susturulduğu
 * için (main.tsx) "ekran boş" tipi hataların sunucudan görünür olmasının
 * tek yolu budur.
 *
 * Tasarım sınırları:
 * - Beacon asla hata BÜYÜTMEZ: her yol try/catch'li, fetch hatası yutulur
 *   (unhandledrejection döngüsü olmaz).
 * - Kısma: aynı imza DEDUP_WINDOW_MS içinde bir kez, oturum başına toplam
 *   SESSION_CAP rapor (hata döngüsü sunucuyu boğmasın; backend'de ayrıca
 *   IP başına hız limiti var).
 * - Gövde düz string gider (text/plain): application/json CORS preflight
 *   gerektirirdi, sendBeacon preflight yapamaz; backend gövdeyi ham okur.
 */

export interface ClientErrorReport {
  kind: "error" | "unhandledrejection";
  message: string;
  stack?: string;
  url?: string;
  line?: number;
  col?: number;
}

const REPORT_PATH = "/api/client-error";
const SESSION_CAP = 20;
const DEDUP_WINDOW_MS = 30_000;
// Backend beyaz listesiyle hizalı kırpma — gövde 16 KB tavanının altında kalır.
const MAX_MESSAGE = 2000;
const MAX_STACK = 8000;
const MAX_URL = 1000;

let sentCount = 0;
const lastSentAt = new Map<string, number>();

/** Test izolasyonu: modül durumu sıfırlanır. */
export function _resetForTests(): void {
  sentCount = 0;
  lastSentAt.clear();
}

function truncate(value: unknown, max: number): string {
  return String(value ?? "").slice(0, max);
}

export function buildFromErrorEvent(event: ErrorEvent): ClientErrorReport {
  return {
    kind: "error",
    message: truncate(event.message || event.error?.message || "bilinmeyen hata", MAX_MESSAGE),
    stack: event.error?.stack ? truncate(event.error.stack, MAX_STACK) : undefined,
    url: truncate(event.filename || window.location.href, MAX_URL),
    line: typeof event.lineno === "number" ? event.lineno : undefined,
    col: typeof event.colno === "number" ? event.colno : undefined,
  };
}

export function buildFromRejection(event: PromiseRejectionEvent): ClientErrorReport {
  const reason: unknown = event.reason;
  const asError = reason instanceof Error ? reason : undefined;
  let message: string;
  try {
    message = asError?.message ?? (typeof reason === "string" ? reason : JSON.stringify(reason));
  } catch {
    message = String(reason);
  }
  return {
    kind: "unhandledrejection",
    message: truncate(message || "bilinmeyen rejection", MAX_MESSAGE),
    stack: asError?.stack ? truncate(asError.stack, MAX_STACK) : undefined,
    url: truncate(window.location.href, MAX_URL),
  };
}

/** Kısma kararı: cap dolmadıysa ve imza pencere içinde gönderilmediyse true. */
export function shouldSend(signature: string, now: number): boolean {
  if (sentCount >= SESSION_CAP) return false;
  const last = lastSentAt.get(signature);
  if (last !== undefined && now - last < DEDUP_WINDOW_MS) return false;
  sentCount += 1;
  lastSentAt.set(signature, now);
  return true;
}

export function sendReport(report: ClientErrorReport): void {
  try {
    const base = import.meta.env.VITE_API_URL || "";
    const url = `${base}${REPORT_PATH}`;
    const body = JSON.stringify(report);
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      navigator.sendBeacon(url, body);
    } else {
      // keepalive: sayfa kapanırken de gitsin (sendBeacon'ın asıl avantajı)
      fetch(url, { method: "POST", body, keepalive: true }).catch(() => {});
    }
  } catch {
    // beacon hiçbir koşulda kendi hatasını üretmez
  }
}

function handle(report: ClientErrorReport): void {
  try {
    const signature = `${report.kind}|${report.message}|${report.line ?? ""}|${report.col ?? ""}`;
    if (!shouldSend(signature, Date.now())) return;
    sendReport(report);
  } catch {
    // yut — bkz. modül üstü sözleşme
  }
}

export function initErrorBeacon(): void {
  window.addEventListener("error", (event) => handle(buildFromErrorEvent(event)));
  window.addEventListener("unhandledrejection", (event) =>
    handle(buildFromRejection(event as PromiseRejectionEvent)),
  );
}

/**
 * Faz 4.4: React render hataları window "error" olayına DÜŞMEZ (React yakalayıp
 * boundary'ye verir) — ErrorBoundary.componentDidCatch buradan elle raporlar.
 * Aynı kısma/dedup kuralları geçerli; kind backend beyaz listesindeki "error"
 * kalır (yeni kind "unknown"a düşerdi), ayrım "[ErrorBoundary]" önekiyle.
 */
export function reportCaughtRenderError(error: unknown, componentStack?: string): void {
  try {
    const asError = error instanceof Error ? error : undefined;
    let message: string;
    try {
      message = asError?.message ?? (typeof error === "string" ? error : JSON.stringify(error));
    } catch {
      message = String(error);
    }
    const stack = asError?.stack || componentStack;
    handle({
      kind: "error",
      message: truncate(`[ErrorBoundary] ${message || "bilinmeyen render hatası"}`, MAX_MESSAGE),
      stack: stack ? truncate(stack, MAX_STACK) : undefined,
      url: truncate(window.location.href, MAX_URL),
    });
  } catch {
    // beacon hiçbir koşulda kendi hatasını üretmez
  }
}
