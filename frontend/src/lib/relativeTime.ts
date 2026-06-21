// Göreli zaman: "az önce" / "12 dk" / "3 sa" / "5 Haz".
// ISO string, Date veya epoch ms kabul eder. Geçersiz/boş girdide "—" döner.
export function formatAgo(input: string | number | Date | null | undefined): string {
  if (input == null) return "—";
  const ts =
    input instanceof Date
      ? input.getTime()
      : typeof input === "number"
        ? input
        : new Date(input).getTime();
  if (!Number.isFinite(ts)) return "—";

  const diffMs = Date.now() - ts;
  if (diffMs < 0) return "az önce"; // gelecek tarih — saçma görünmesin
  const min = Math.floor(diffMs / 60000);
  if (min < 1) return "az önce";
  if (min < 60) return `${min} dk`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} sa`;
  const days = Math.floor(hr / 24);
  if (days < 7) return `${days} g`;
  return new Date(ts).toLocaleDateString("tr-TR", { day: "numeric", month: "short" });
}
