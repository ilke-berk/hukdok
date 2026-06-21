import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CalendarPlus, ChevronLeft, ChevronRight, Gavel, Trash2, Clock, User, Printer, FileBarChart, FileText, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { SectionHeader, HairlineCard } from "@/components/dashboard/primitives";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

interface Hearing {
  id?: number;
  case_id: number;
  esas_no?: string;
  tracking_no?: string;
  hearing_date: string;
  hearing_time?: string;
  court?: string;
  note?: string;
  lawyer_name?: string;
}

interface ReportRow {
  date_str: string;
  time: string;
  type: string;
  title: string;
  esas_no: string;
  court: string;
  client: string;
  counter: string;
  lawyer: string;
  case_id: number | null;
}

interface CalEvent {
  id: number;
  title: string;
  event_date: string;
  event_time?: string;
  created_by?: string;
}

interface AgendaItem {
  kind: "hearing" | "event";
  id: number;
  date: string;
  time?: string;
  label: string;
  sub?: string;
  caseId?: number;
  lawyer?: string;
}

const WEEKDAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

function parseDate(date: string): Date {
  return new Date(date + (date.includes("T") ? "" : "T00:00:00"));
}

function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type Props = {
  eyebrow?: string;
  layout?: "compact" | "full";
};

export function DashboardCalendar({ eyebrow = "Takvim", layout = "compact" }: Props) {
  const navigate = useNavigate();
  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [events, setEvents] = useState<CalEvent[]>([]);

  // Takvimde seçili gün (detay kutusu için) — varsayılan bugün
  const [selectedDay, setSelectedDay] = useState<string>(toISODate(now));

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [formDate, setFormDate] = useState<string>(toISODate(now));
  const [formTime, setFormTime] = useState<string>("");
  const [formTitle, setFormTitle] = useState<string>("");
  const [saving, setSaving] = useState(false);

  // Rapor modal state
  const [reportOpen, setReportOpen] = useState(false);
  const [reportStart, setReportStart] = useState<string>(toISODate(now));
  const [reportEnd, setReportEnd] = useState<string>(toISODate(now));
  const [downloading, setDownloading] = useState<null | "pdf" | "excel">(null);
  const [previewRows, setPreviewRows] = useState<ReportRow[] | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const applyPreset = (preset: "week" | "month") => {
    const base = new Date();
    if (preset === "week") {
      const offset = (base.getDay() + 6) % 7; // Pazartesi = 0
      const monday = new Date(base.getFullYear(), base.getMonth(), base.getDate() - offset);
      const sunday = new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
      setReportStart(toISODate(monday));
      setReportEnd(toISODate(sunday));
    } else {
      const first = new Date(base.getFullYear(), base.getMonth(), 1);
      const last = new Date(base.getFullYear(), base.getMonth() + 1, 0);
      setReportStart(toISODate(first));
      setReportEnd(toISODate(last));
    }
  };

  const openReport = () => {
    applyPreset("month");
    setReportOpen(true);
  };

  const downloadReport = async (format: "pdf" | "excel") => {
    if (!reportStart || !reportEnd) {
      toast.error("Lütfen tarih aralığı seçin.");
      return;
    }
    setDownloading(format);
    try {
      const res = await apiClient.fetch(
        `/api/calendar-report?start=${reportStart}&end=${reportEnd}&format=${format}`,
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Rapor oluşturulamadı.");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `takvim-raporu-${reportStart}_${reportEnd}.${format === "excel" ? "xlsx" : "pdf"}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`${format === "excel" ? "Excel" : "PDF"} raporu indirildi.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rapor indirilemedi.");
    } finally {
      setDownloading(null);
    }
  };

  // Önizleme — rapor modalı açıkken aralık değiştikçe JSON çek
  useEffect(() => {
    if (!reportOpen || !reportStart || !reportEnd) return;
    let cancelled = false;
    setPreviewLoading(true);
    apiClient.fetch(`/api/calendar-report?start=${reportStart}&end=${reportEnd}&format=json`)
      .then(r => r.ok ? r.json() : Promise.resolve({ rows: [] }))
      .then((data: { rows?: ReportRow[] }) => {
        if (cancelled) return;
        setPreviewRows(Array.isArray(data.rows) ? data.rows : []);
      })
      .catch(() => { if (!cancelled) setPreviewRows([]); })
      .finally(() => { if (!cancelled) setPreviewLoading(false); });
    return () => { cancelled = true; };
  }, [reportOpen, reportStart, reportEnd]);

  const printReport = () => {
    const rows = previewRows || [];
    const esc = (v: unknown) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const fmtRange = `${reportStart.split("-").reverse().join(".")} – ${reportEnd.split("-").reverse().join(".")}`;
    const body = rows.length === 0
      ? `<p class="empty">Bu aralıkta kayıt bulunamadı.</p>`
      : `<table>
          <thead><tr>
            <th>Tarih</th><th>Saat</th><th>Tür</th><th>Açıklama</th><th>Esas No</th>
            <th>Mahkeme</th><th>Müvekkil</th><th>Karşı Taraf</th><th>Sorumlu Avukat</th>
          </tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td>${esc(r.date_str)}</td><td>${esc(r.time)}</td><td>${esc(r.type)}</td>
            <td>${esc(r.title)}</td><td>${esc(r.esas_no)}</td><td>${esc(r.court)}</td>
            <td>${esc(r.client)}</td><td>${esc(r.counter)}</td><td>${esc(r.lawyer)}</td>
          </tr>`).join("")}</tbody>
        </table>`;
    const html = `<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>Takvim Raporu</title>
      <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; margin: 24px; color: #1a1a1a; }
        h1 { font-size: 18px; color: #4A1530; margin: 0 0 2px; }
        .sub { font-size: 12px; color: #666; margin: 0 0 16px; }
        table { width: 100%; border-collapse: collapse; font-size: 11px; }
        th, td { border: 1px solid #d8cfc4; padding: 5px 7px; text-align: left; vertical-align: top; }
        th { background: #4A1530; color: #fff; }
        tbody tr:nth-child(even) { background: #faf6f0; }
        .empty { color: #666; font-size: 13px; }
        @media print { body { margin: 8mm; } }
      </style></head>
      <body onload="window.print()">
        <h1>Takvim Raporu</h1>
        <p class="sub">${fmtRange} · ${rows.length} kayıt</p>
        ${body}
      </body></html>`;
    const w = window.open("", "_blank", "width=1000,height=700");
    if (!w) { toast.error("Yazdırma penceresi açılamadı (açılır pencere engelleyiciyi kontrol edin)."); return; }
    w.document.open();
    w.document.write(html);
    w.document.close();
  };

  const loadHearings = useCallback(() => {
    apiClient.fetch("/api/hearing-dates")
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then((data: unknown) => setHearings(Array.isArray(data) ? (data as Hearing[]) : []))
      .catch(() => setHearings([]));
  }, []);

  const loadEvents = useCallback(() => {
    apiClient.fetch("/api/calendar-events")
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then((data: unknown) => setEvents(Array.isArray(data) ? (data as CalEvent[]) : []))
      .catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    loadHearings();
    loadEvents();
  }, [loadHearings, loadEvents]);

  const openModal = (isoDate?: string) => {
    setFormDate(isoDate || toISODate(new Date()));
    setFormTime("");
    setFormTitle("");
    setModalOpen(true);
  };

  const handleSave = async () => {
    const title = formTitle.trim();
    if (!title) {
      toast.error("Lütfen ne olduğunu yazın.");
      return;
    }
    if (!formDate) {
      toast.error("Lütfen bir tarih seçin.");
      return;
    }
    setSaving(true);
    try {
      const res = await apiClient.fetch("/api/calendar-events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          event_date: formDate,
          event_time: formTime || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Tarih işareti kaydedilemedi.");
      }
      toast.success("Takvime eklendi.");
      setModalOpen(false);
      loadEvents();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Kayıt başarısız.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteEvent = async (id: number) => {
    try {
      const res = await apiClient.fetch(`/api/calendar-events/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      setEvents(prev => prev.filter(e => e.id !== id));
      toast.success("İşaret kaldırıldı.");
    } catch {
      toast.error("Silme başarısız.");
    }
  };

  // --- Takvim hücreleri (görüntülenen ay) ---
  const calendar = useMemo(() => {
    const todayObj = new Date();
    const isCurrentMonth =
      todayObj.getFullYear() === viewYear && todayObj.getMonth() === viewMonth;
    const todayNum = todayObj.getDate();
    const firstOffset = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7; // Pzt=0
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();

    // Gün → işaret açıklamaları (tooltip için) + tür bayrakları
    const dayInfo = new Map<number, { hearing: boolean; event: boolean; lines: string[] }>();
    const ensure = (day: number) => {
      let v = dayInfo.get(day);
      if (!v) { v = { hearing: false, event: false, lines: [] }; dayInfo.set(day, v); }
      return v;
    };
    for (const h of hearings) {
      const d = parseDate(h.hearing_date);
      if (d.getFullYear() !== viewYear || d.getMonth() !== viewMonth) continue;
      const v = ensure(d.getDate());
      v.hearing = true;
      const parts = [`Duruşma${h.hearing_time ? " " + h.hearing_time : ""}`];
      const where = h.court || h.note;
      if (where) parts.push(where);
      if (h.esas_no || h.tracking_no) parts.push(`№ ${h.esas_no || h.tracking_no}`);
      v.lines.push(parts.join(" — "));
    }
    for (const e of events) {
      const d = parseDate(e.event_date);
      if (d.getFullYear() !== viewYear || d.getMonth() !== viewMonth) continue;
      const v = ensure(d.getDate());
      v.event = true;
      v.lines.push(`İşaret${e.event_time ? " " + e.event_time : ""} — ${e.title}`);
    }

    type Cell = { num: number; muted: boolean; today: boolean; hearing: boolean; event: boolean; tooltip: string };
    const empty: Cell = { num: 0, muted: true, today: false, hearing: false, event: false, tooltip: "" };
    const cells: Cell[] = [];
    for (let i = 0; i < firstOffset; i++) cells.push({ ...empty });
    for (let d = 1; d <= daysInMonth; d++) {
      const info = dayInfo.get(d);
      cells.push({
        num: d,
        muted: false,
        today: isCurrentMonth && d === todayNum,
        hearing: !!info?.hearing,
        event: !!info?.event,
        tooltip: info ? info.lines.join("\n") : "",
      });
    }
    while (cells.length % 7 !== 0) cells.push({ ...empty });
    const monthLabel = new Date(viewYear, viewMonth, 1).toLocaleDateString("tr-TR", { month: "long", year: "numeric" });
    return { cells, monthLabel };
  }, [viewYear, viewMonth, hearings, events]);

  const goPrevMonth = () => {
    const d = new Date(viewYear, viewMonth - 1, 1);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  };
  const goNextMonth = () => {
    const d = new Date(viewYear, viewMonth + 1, 1);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  };

  // --- Seçili güne ait kayıtlar (detay kutusu) ---
  const dayItems = useMemo<AgendaItem[]>(() => {
    if (!selectedDay) return [];
    const items: AgendaItem[] = [];
    for (const h of hearings) {
      if (h.hearing_date.slice(0, 10) !== selectedDay) continue;
      items.push({
        kind: "hearing",
        id: h.id ?? h.case_id,
        date: h.hearing_date,
        time: h.hearing_time,
        label: h.court || "Duruşma",
        sub: h.esas_no || h.tracking_no,
        caseId: h.case_id,
        lawyer: h.lawyer_name,
      });
    }
    for (const e of events) {
      if (e.event_date.slice(0, 10) !== selectedDay) continue;
      items.push({
        kind: "event",
        id: e.id,
        date: e.event_date,
        time: e.event_time,
        label: e.title,
      });
    }
    return items.sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  }, [selectedDay, hearings, events]);

  const selectedLabel = selectedDay
    ? parseDate(selectedDay).toLocaleDateString("tr-TR", { day: "numeric", month: "long", weekday: "long" })
    : "";

  const calendarCard = (
    <HairlineCard>
      {/* Ay navigasyonu */}
      <div className="flex items-center justify-between pb-3">
        <button
          type="button"
          onClick={goPrevMonth}
          className="w-7 h-7 grid place-items-center border border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors"
          aria-label="Önceki ay"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <span className="font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
          {calendar.monthLabel}
        </span>
        <button
          type="button"
          onClick={goNextMonth}
          className="w-7 h-7 grid place-items-center border border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors"
          aria-label="Sonraki ay"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {WEEKDAYS.map(d => (
          <div key={d} className="text-center font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] pb-2">
            {d}
          </div>
        ))}
        {calendar.cells.map((c, i) => {
          if (c.muted) {
            return <div key={i} className="aspect-square" />;
          }
          const isoDate = toISODate(new Date(viewYear, viewMonth, c.num));
          const marked = c.hearing || c.event;
          const isSelected = isoDate === selectedDay;
          const cellTone = c.today
            ? "bg-[var(--brand)] text-[var(--brand-fg)] border-[var(--brand)] font-semibold"
            : marked
              ? "bg-[var(--brand-soft)] text-[var(--fg)] border-[var(--brand)]/45 font-semibold hover:border-[var(--brand)]"
              : "text-[var(--fg)] border-transparent hover:border-[var(--border-strong)] hover:bg-[var(--bg)]";
          const selectedRing = isSelected && !c.today ? " ring-2 ring-[var(--brand)] ring-offset-1 ring-offset-[var(--bg-elevated)]" : "";
          return (
            <button
              key={i}
              type="button"
              onClick={() => setSelectedDay(isoDate)}
              title={c.tooltip ? c.tooltip : "Bu gün için kayıt yok"}
              className={`relative aspect-square grid place-items-center font-mono text-[12px] border transition-colors ${cellTone}${selectedRing}`}
            >
              <span className="leading-none">{c.num}</span>
            </button>
          );
        })}
      </div>
    </HairlineCard>
  );

  const dayPanel = (
    <HairlineCard padded={false} className="h-full">
      {/* Seçili gün başlığı */}
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-[var(--border)]">
        <span className="font-display font-medium text-[15px] text-[var(--fg)]">
          {selectedLabel || "Bir gün seçin"}
        </span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-[9.5px] tracking-[0.12em] uppercase px-2 py-1 border border-[var(--border-strong)] bg-[var(--bg)] text-[var(--fg-muted)]">
            {dayItems.length} Kayıt
          </span>
          <button
            type="button"
            onClick={() => openModal(selectedDay)}
            title="Bu güne işaret ekle"
            className="w-7 h-7 grid place-items-center border border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors"
          >
            <CalendarPlus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {dayItems.length === 0 ? (
        <div className="p-7 grid place-items-center gap-2 text-center text-[var(--fg-subtle)]">
          <CalendarPlus className="w-7 h-7 opacity-40" />
          <p className="text-[13px]">Bu gün için kayıt yok.</p>
          <button
            type="button"
            onClick={() => openModal(selectedDay)}
            className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1.5 mt-1 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)] transition-colors"
          >
            <CalendarPlus className="w-3.5 h-3.5" /> İşaret Ekle
          </button>
        </div>
      ) : (
        <div className="flex flex-col px-4 py-1">
          {dayItems.map((it, idx) => (
            <div
              key={`${it.kind}-${it.id}-${idx}`}
              className={`grid grid-cols-[auto_1fr_auto] gap-3 items-center py-3 ${idx > 0 ? "border-t border-[var(--border)]" : ""}`}
            >
              <div className="w-9 h-9 grid place-items-center border border-[var(--border-strong)] bg-[var(--bg)] shrink-0">
                {it.kind === "hearing" ? (
                  <Gavel className="w-4 h-4 text-[var(--brand)]" />
                ) : (
                  <Clock className="w-4 h-4 text-[#c47a1e]" />
                )}
              </div>
              <button
                type="button"
                onClick={() => it.kind === "hearing" && it.caseId ? navigate(`/cases/${it.caseId}`) : openModal(it.date)}
                className="min-w-0 text-left"
              >
                <div className="flex items-baseline gap-2 min-w-0">
                  {it.sub && (
                    <span className="font-mono text-[11px] tracking-[0.04em] text-[var(--brand)] shrink-0">№ {it.sub}</span>
                  )}
                  <span className="font-display font-medium text-[14px] text-[var(--fg)] truncate">{it.label}</span>
                </div>
                <div className="flex items-center gap-3 mt-1 text-[11px] text-[var(--fg-subtle)]">
                  {it.time && (
                    <span className="inline-flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3" /> Saat {it.time}
                    </span>
                  )}
                  {it.lawyer && (
                    <span className="inline-flex items-center gap-1 truncate">
                      <User className="w-3 h-3 shrink-0" /> {it.lawyer}
                    </span>
                  )}
                </div>
              </button>
              {it.kind === "event" ? (
                <button
                  type="button"
                  onClick={() => handleDeleteEvent(it.id)}
                  title="İşareti kaldır"
                  className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[#c0392b] transition-colors shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              ) : (
                <span className="w-7 shrink-0" />
              )}
            </div>
          ))}
        </div>
      )}
    </HairlineCard>
  );

  const headerActions = (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={openReport}
        className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1.5 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)] transition-colors"
      >
        <FileBarChart className="w-3.5 h-3.5" /> Rapor
      </button>
      <button
        type="button"
        onClick={() => openModal()}
        className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1.5 pb-1 border-b border-[var(--border)] hover:border-[var(--brand)] transition-colors"
      >
        <CalendarPlus className="w-3.5 h-3.5" /> Tarih İşaretle
      </button>
    </div>
  );

  return (
    <>
      <SectionHeader eyebrow={eyebrow} title="Takvim" italic="— ajanda ve işaretler" meta={headerActions} />
      <div className="mt-3">
        {layout === "full" ? (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 items-start">
            <div className="lg:col-span-2">{calendarCard}</div>
            <div className="lg:col-span-3">{dayPanel}</div>
          </div>
        ) : (
          <div className="grid gap-4">
            {calendarCard}
            {dayPanel}
          </div>
        )}
      </div>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="font-display">Takvime Tarih İşaretle</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-1">
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label htmlFor="cal-date" className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  Tarih
                </Label>
                <Input
                  id="cal-date"
                  type="date"
                  value={formDate}
                  onChange={(e) => setFormDate(e.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="cal-time" className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  Saat (opsiyonel)
                </Label>
                <Input
                  id="cal-time"
                  type="time"
                  value={formTime}
                  onChange={(e) => setFormTime(e.target.value)}
                />
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="cal-title" className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                Ne olduğu
              </Label>
              <Input
                id="cal-title"
                type="text"
                placeholder="Örn. Müvekkil görüşmesi, süre sonu, icra takibi…"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !saving) handleSave(); }}
                autoFocus
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setModalOpen(false)} disabled={saving}>
              Vazgeç
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Kaydediliyor…" : "Ekle"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Rapor modalı — tarih aralığı seç, önizle, PDF/Excel indir, yazdır */}
      <Dialog open={reportOpen} onOpenChange={setReportOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="font-display">Takvim Raporu</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-1">
            {/* Aralık seçimi */}
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => applyPreset("week")}
                  className="px-3 py-2 font-mono text-[10px] tracking-[0.12em] uppercase border border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors"
                >
                  Bu Hafta
                </button>
                <button
                  type="button"
                  onClick={() => applyPreset("month")}
                  className="px-3 py-2 font-mono text-[10px] tracking-[0.12em] uppercase border border-[var(--border)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--brand)] transition-colors"
                >
                  Bu Ay
                </button>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rep-start" className="font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  Başlangıç
                </Label>
                <Input id="rep-start" type="date" value={reportStart} onChange={(e) => setReportStart(e.target.value)} className="w-[160px]" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="rep-end" className="font-mono text-[9px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  Bitiş
                </Label>
                <Input id="rep-end" type="date" value={reportEnd} onChange={(e) => setReportEnd(e.target.value)} className="w-[160px]" />
              </div>
            </div>

            {/* Önizleme */}
            <div className="border border-[var(--border)] bg-[var(--bg)]">
              <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--border)]">
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">Önizleme</span>
                <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-muted)]">
                  {previewLoading ? "Yükleniyor…" : `${previewRows?.length ?? 0} kayıt`}
                </span>
              </div>
              <div className="max-h-[320px] overflow-auto">
                {previewLoading ? (
                  <div className="p-8 text-center text-[13px] text-[var(--fg-subtle)]">Önizleme hazırlanıyor…</div>
                ) : (previewRows && previewRows.length > 0) ? (
                  <table className="w-full text-left border-collapse">
                    <thead className="sticky top-0 bg-[var(--bg-elevated)]">
                      <tr className="font-mono text-[9px] tracking-[0.1em] uppercase text-[var(--fg-subtle)]">
                        <th className="px-2 py-2 font-medium">Tarih</th>
                        <th className="px-2 py-2 font-medium">Saat</th>
                        <th className="px-2 py-2 font-medium">Tür</th>
                        <th className="px-2 py-2 font-medium">Açıklama</th>
                        <th className="px-2 py-2 font-medium">Esas No</th>
                        <th className="px-2 py-2 font-medium">Mahkeme</th>
                        <th className="px-2 py-2 font-medium">Müvekkil</th>
                        <th className="px-2 py-2 font-medium">Karşı Taraf</th>
                        <th className="px-2 py-2 font-medium">Sorumlu Avukat</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((r, i) => (
                        <tr key={i} className="border-t border-[var(--border)] text-[11px] text-[var(--fg)] align-top">
                          <td className="px-2 py-1.5 font-mono whitespace-nowrap">{r.date_str}</td>
                          <td className="px-2 py-1.5 font-mono whitespace-nowrap">{r.time || "—"}</td>
                          <td className="px-2 py-1.5 whitespace-nowrap">{r.type}</td>
                          <td className="px-2 py-1.5">{r.title}</td>
                          <td className="px-2 py-1.5 font-mono whitespace-nowrap text-[var(--brand)]">{r.esas_no || "—"}</td>
                          <td className="px-2 py-1.5">{r.court || "—"}</td>
                          <td className="px-2 py-1.5">{r.client || "—"}</td>
                          <td className="px-2 py-1.5">{r.counter || "—"}</td>
                          <td className="px-2 py-1.5">{r.lawyer || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="p-8 text-center text-[13px] text-[var(--fg-subtle)]">Bu aralıkta kayıt bulunamadı.</div>
                )}
              </div>
            </div>

            <p className="text-[11px] text-[var(--fg-subtle)] leading-relaxed">
              Davaya bağlı kayıtlarda müvekkil, karşı taraf, mahkeme, esas no ve sorumlu avukat bilgisi otomatik eklenir.
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            <Button variant="outline" onClick={printReport} disabled={previewLoading}>
              <Printer className="w-4 h-4" />
              Yazdır
            </Button>
            <Button variant="outline" onClick={() => downloadReport("excel")} disabled={downloading !== null || previewLoading}>
              <FileSpreadsheet className="w-4 h-4" />
              {downloading === "excel" ? "Hazırlanıyor…" : "Excel"}
            </Button>
            <Button onClick={() => downloadReport("pdf")} disabled={downloading !== null || previewLoading}>
              <FileText className="w-4 h-4" />
              {downloading === "pdf" ? "Hazırlanıyor…" : "PDF"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
