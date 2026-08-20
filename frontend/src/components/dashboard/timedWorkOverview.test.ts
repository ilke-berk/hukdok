// G086 (idari yarı) — "Süreli İşler" panelinin saf yardımcıları.
// Kilitlenen sözleşme: G087 uçlarının gövdesi tipli zarfa çevrilirken şekil
// bozukluğu HATADIR (null), geri sayım DAİMA due_date'ten hesaplanır, günü
// geçmiş satır DÜŞMEZ ve aynı sürenin ikinci bildirimi BİRLEŞTİRİLMEZ.
import { describe, expect, it } from "vitest";
import {
  OVERVIEW_DAYS,
  OVERVIEW_LIMIT,
  capNote,
  dueLabel,
  overviewSummary,
  parseOverviewEnvelope,
  parseUnresolvedEnvelope,
  readLabel,
  recipientLabel,
  timedWorkRows,
  titleLabel,
  unresolvedSummary,
  type OverviewNotification,
} from "./timedWorkOverview";

/** Bugünden N gün sonrası, uçtaki `due_date` biçiminde (yalın gün). */
function gunSonra(n: number): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + n);
  const ay = String(d.getMonth() + 1).padStart(2, "0");
  const gun = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${ay}-${gun}`;
}

function ucSatiri(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 7,
    type: "sure_yaklasti",
    severity: "info",
    title: "Süre yaklaşıyor: İstinaf başvuru süresi — 99 gün kaldı",
    recipient_email: "a.yilmaz@hanyaloglu-acar.av.tr",
    case_id: 4210,
    due_date: gunSonra(14),
    read_at: null,
    is_read: false,
    created_at: "2026-08-20T06:00:00+00:00",
    ...over,
  };
}

function bildirim(over: Partial<OverviewNotification> = {}): OverviewNotification {
  return {
    id: 7,
    type: "sure_yaklasti",
    severity: "info",
    title: "Süre yaklaşıyor: İstinaf başvuru süresi — 99 gün kaldı",
    recipient_email: "a.yilmaz@hanyaloglu-acar.av.tr",
    case_id: 4210,
    due_date: gunSonra(14),
    read_at: null,
    is_read: false,
    created_at: "2026-08-20T06:00:00+00:00",
    ...over,
  };
}

describe("parseOverviewEnvelope (G086 idari)", () => {
  it("uç gövdesini tipli zarfa çevirir", () => {
    const zarf = parseOverviewEnvelope({
      days: 30,
      limit: 100,
      total: 12,
      unread: 5,
      items: [ucSatiri()],
    });

    expect(zarf).not.toBeNull();
    expect(zarf!.total).toBe(12);
    expect(zarf!.unread).toBe(5);
    expect(zarf!.items).toHaveLength(1);
    expect(zarf!.items[0].recipient_email).toBe("a.yilmaz@hanyaloglu-acar.av.tr");
    expect(zarf!.items[0].case_id).toBe(4210);
    expect(zarf!.items[0].is_read).toBe(false);
  });

  it("read_at damgası varsa is_read TRUE olur — çelişkide damga kazanır", () => {
    const zarf = parseOverviewEnvelope({
      items: [ucSatiri({ is_read: false, read_at: "2026-08-20T09:00:00+00:00" })],
    });

    expect(zarf!.items[0].is_read).toBe(true);
  });

  it("sayaç alanları eksikse görünen satırlardan türetilir", () => {
    const zarf = parseOverviewEnvelope({
      items: [ucSatiri(), ucSatiri({ id: 8, read_at: "2026-08-20T09:00:00+00:00" })],
    });

    expect(zarf!.total).toBe(2);
    expect(zarf!.unread).toBe(1);
    expect(zarf!.days).toBe(OVERVIEW_DAYS);
    expect(zarf!.limit).toBe(OVERVIEW_LIMIT);
  });

  it("beklenmedik gövde HATADIR — boş listeye çevrilmez", () => {
    expect(parseOverviewEnvelope(null)).toBeNull();
    expect(parseOverviewEnvelope([])).toBeNull();
    expect(parseOverviewEnvelope({ unread: 3 })).toBeNull();
    expect(parseOverviewEnvelope({ items: [{ title: "id yok" }] })).toBeNull();
    expect(parseOverviewEnvelope({ items: ["satır değil"] })).toBeNull();
  });

  it("boş liste GEÇERLİ bir sonuçtur", () => {
    const zarf = parseOverviewEnvelope({ days: 30, limit: 100, total: 0, unread: 0, items: [] });
    expect(zarf).not.toBeNull();
    expect(zarf!.items).toEqual([]);
    expect(zarf!.total).toBe(0);
  });
});

describe("parseUnresolvedEnvelope (G080 hedefsiz sayacı)", () => {
  it("adları ve dava sayılarını okur", () => {
    const zarf = parseUnresolvedEnvelope({
      items: [
        { name: "Arşiv Dosya Yöneticisi", case_count: 93 },
        { name: "Asu Barış Karamık", case_count: 4 },
      ],
      total_names: 2,
      total_cases: 97,
    });

    expect(zarf!.items[0]).toEqual({ name: "Arşiv Dosya Yöneticisi", case_count: 93 });
    expect(zarf!.total_names).toBe(2);
    expect(zarf!.total_cases).toBe(97);
  });

  it("toplam alanları eksikse satırlardan hesaplanır", () => {
    const zarf = parseUnresolvedEnvelope({
      items: [{ name: "A", case_count: 3 }, { name: "B", case_count: 1 }],
    });

    expect(zarf!.total_names).toBe(2);
    expect(zarf!.total_cases).toBe(4);
  });

  it("şekil bozuksa null döner", () => {
    expect(parseUnresolvedEnvelope({ total_cases: 97 })).toBeNull();
    expect(parseUnresolvedEnvelope({ items: [{ case_count: 3 }] })).toBeNull();
    expect(parseUnresolvedEnvelope("97")).toBeNull();
  });

  it("hedefsiz dava yoksa boş zarf geçerlidir", () => {
    const zarf = parseUnresolvedEnvelope({ items: [], total_names: 0, total_cases: 0 });
    expect(zarf).toEqual({ items: [], total_names: 0, total_cases: 0 });
  });
});

describe("etiketler", () => {
  it("dueLabel ISO günü gg.aa.yyyy yazar", () => {
    expect(dueLabel("2026-09-03")).toBe("03.09.2026");
    expect(dueLabel("2026-09-03T00:00:00")).toBe("03.09.2026");
    expect(dueLabel(null)).toBe("—");
    expect(dueLabel("tarih değil")).toBe("—");
  });

  it("recipientLabel adresi AYNEN gösterir, yoksa dürüst yazar", () => {
    expect(recipientLabel("a.yilmaz@hanyaloglu-acar.av.tr")).toBe("a.yilmaz@hanyaloglu-acar.av.tr");
    expect(recipientLabel(null)).toBe("Alıcı yok");
    expect(recipientLabel("   ")).toBe("Alıcı yok");
  });

  it("readLabel okunma durumunu ve damgasını söyler", () => {
    expect(readLabel(bildirim())).toBe("Okunmadı");
    expect(readLabel(bildirim({ is_read: true, read_at: new Date().toISOString() }))).toContain(
      "Okundu · ",
    );
    expect(readLabel(bildirim({ is_read: true, read_at: null }))).toBe("Okundu");
  });

  it("titleLabel başlıktaki DONMUŞ geri sayımı düşürür", () => {
    expect(titleLabel("Süre yaklaşıyor: İstinaf başvuru süresi — 99 gün kaldı")).toBe(
      "Süre yaklaşıyor: İstinaf başvuru süresi",
    );
    expect(titleLabel("Duruşma yaklaşıyor: 22.08.2026 — son gün bugün")).toBe(
      "Duruşma yaklaşıyor: 22.08.2026",
    );
    // Anlam taşıyan tire korunur — kalıp yalnız geri sayım ekini tanır.
    expect(titleLabel("Süre yaklaşıyor: İstinaf — HMK m. 345/1")).toBe(
      "Süre yaklaşıyor: İstinaf — HMK m. 345/1",
    );
    expect(titleLabel(null)).toBe("Başlıksız uyarı");
  });

  it("overviewSummary sayaçları uçtan yazar", () => {
    expect(overviewSummary(12, 5)).toBe("12 uyarı · 5 okunmamış");
  });

  it("capNote yalnız tavana dayanıldığında çıkar", () => {
    expect(capNote(12, 12)).toBeNull();
    expect(capNote(3, 12)).toBeNull();
    expect(capNote(140, 100)).toBe("140 uyarının en yakın 100 tanesi listeleniyor.");
  });

  it("unresolvedSummary dava ve ad sayısını verir", () => {
    expect(unresolvedSummary({ items: [], total_names: 2, total_cases: 97 })).toBe(
      "97 dava · 2 sorumlu adı",
    );
  });
});

describe("timedWorkRows", () => {
  it("geri sayımı due_date'ten hesaplar — donmuş başlık metnini kullanmaz", () => {
    const [row] = timedWorkRows([bildirim()]);
    expect(row.daysLeft).toBe(14);
    expect(row.countdown).toBe("14 gün kaldı");
    expect(row.title).not.toContain("99 gün kaldı");
  });

  it("günü geçmiş satır DÜŞMEZ — takip görünümünün asıl işi budur", () => {
    const rows = timedWorkRows([bildirim({ due_date: gunSonra(-3) })]);
    expect(rows).toHaveLength(1);
    expect(rows[0].overdue).toBe(true);
    expect(rows[0].countdown).toBe("3 gün geçti");
  });

  it("tarihsiz satır listede kalır ve 0 gün diye gösterilmez", () => {
    const [row] = timedWorkRows([bildirim({ due_date: null })]);
    expect(row.daysLeft).toBeNull();
    expect(row.countdown).toBe("Tarihsiz");
    expect(row.dueLabel).toBe("—");
    expect(row.overdue).toBe(false);
  });

  it("uçtan gelen sıra BOZULMAZ", () => {
    const rows = timedWorkRows([
      bildirim({ id: 1, due_date: gunSonra(20) }),
      bildirim({ id: 2, due_date: gunSonra(2) }),
    ]);
    expect(rows.map((r) => r.item.id)).toEqual([1, 2]);
  });

  it("aynı sürenin ikinci bildirimi BİRLEŞTİRİLMEZ — okunma durumu kaybolmasın", () => {
    const rows = timedWorkRows([
      bildirim({ id: 1, is_read: true, read_at: "2026-08-10T09:00:00+00:00" }),
      bildirim({ id: 2, is_read: false, read_at: null }),
    ]);

    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.readLabel.startsWith("Okundu"))).toEqual([true, false]);
  });

  it("boş/eksik girdi boş liste üretir", () => {
    expect(timedWorkRows(null)).toEqual([]);
    expect(timedWorkRows([])).toEqual([]);
  });
});
