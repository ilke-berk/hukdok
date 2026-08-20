// G086 — "Süre Uyarıları" panelinin saf yardımcıları.
// Sözleşme kaynağı `backend/services/deadline_scanner.py` gövde biçimidir:
// `Etiket: değer` satırları + (varsa) `DİKKAT:` takvim uyarısı + HER ZAMAN şerh.
import { describe, expect, it } from "vitest";
import type { NotificationItem } from "@/hooks/useNotifications";
import {
  DEADLINE_DISCLAIMER,
  countdownLabel,
  daysUntil,
  deadlineHeadline,
  deadlineIdentity,
  fieldValue,
  parseDayStart,
  parseDeadlineBody,
  selectDeadlineRows,
  stripFrozenCountdown,
} from "./deadlineBody";

/** Gece tarayıcısının gerçek gövde biçimi (deadline_scanner._sure_govdesi). */
const SURE_GOVDE = [
  "Dava: D1.H_YILMAZ..0002.HUKUK.00000 · 2024/118 · Ankara 5. Asliye Hukuk Mahkemesi",
  "Aşama: Yerel mahkeme (YEREL, 1. karar)",
  "Tebliğ tarihi: 12.08.2026",
  "Kural: İstinaf başvuru süresi — HMK m. 345/1 (iki hafta, ilamın tebliğinden itibaren)",
  "Son gün: 03.09.2026 (14 gün kaldı)",
  DEADLINE_DISCLAIMER,
].join("\n");

const DURUSMA_GOVDE = [
  "Dava: D1.M_KAYA....0001.IDARE.00000 · 2025/9 · İstanbul 2. İdare Mahkemesi",
  "Duruşma: 22.08.2026 10:30 (2 gün kaldı)",
  "Kaynak belge: durusma_zapti.pdf",
  DEADLINE_DISCLAIMER,
].join("\n");

function bildirim(over: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: 1,
    type: "sure_yaklasti",
    severity: "info",
    title: "Süre yaklaşıyor: İstinaf başvuru süresi — 14 gün kaldı",
    body: SURE_GOVDE,
    case_id: 4210,
    document_id: null,
    due_date: "2026-09-03",
    read_at: null,
    is_read: false,
    created_at: "2026-08-20T06:00:00",
    ...over,
  };
}

describe("parseDeadlineBody (G086)", () => {
  it("gövdeyi etiketli satırlara ayırır, sırayı korur", () => {
    const parsed = parseDeadlineBody(SURE_GOVDE);
    expect(parsed.fields.map((f) => f.label)).toEqual([
      "Dava",
      "Aşama",
      "Tebliğ tarihi",
      "Kural",
      "Son gün",
    ]);
    expect(fieldValue(parsed, "Tebliğ tarihi")).toBe("12.08.2026");
    expect(fieldValue(parsed, "Aşama")).toBe("Yerel mahkeme (YEREL, 1. karar)");
  });

  it("şerhi satırlardan ayıklar (panelde bir kez gösterilir)", () => {
    const parsed = parseDeadlineBody(SURE_GOVDE);
    expect(parsed.fields.some((f) => f.value.includes("süre takibi yerine geçmez"))).toBe(false);
    expect(parsed.extras).toEqual([]);
  });

  it("değerdeki iki nokta üst üste kaybolmaz (saatli duruşma)", () => {
    const parsed = parseDeadlineBody(DURUSMA_GOVDE);
    expect(fieldValue(parsed, "Duruşma")).toBe("22.08.2026 10:30");
    expect(fieldValue(parsed, "Kaynak belge")).toBe("durusma_zapti.pdf");
  });

  it("donmuş geri sayım ekini düşürür, anlamlı parantezi korur", () => {
    // Panel taze sayımı due_date'ten yazıyor; aynı satırda iki farklı sayı çelişkidir.
    const parsed = parseDeadlineBody(SURE_GOVDE);
    expect(fieldValue(parsed, "Son gün")).toBe("03.09.2026");
    expect(fieldValue(parsed, "Aşama")).toBe("Yerel mahkeme (YEREL, 1. karar)");
    expect(stripFrozenCountdown("Son gün: 20.08.2026 (son gün bugün)")).toBe(
      "Son gün: 20.08.2026",
    );
    expect(stripFrozenCountdown("adli tatil → 2026-09-07 (HMK m. 93)")).toBe(
      "adli tatil → 2026-09-07 (HMK m. 93)",
    );
  });

  it("takvim doğrulanmadı uyarısını ayrı alanda işaretler", () => {
    const uyari =
      "DİKKAT: son günün yılı için resmî tatil takvimi doğrulanmadı — " +
      "hafta sonu/resmî tatil kaydırması UYGULANMADI, son gün elle teyit edilmeli.";
    const parsed = parseDeadlineBody(`${SURE_GOVDE}\n${uyari}`);
    expect(parsed.calendarWarning).toBe(uyari);
    expect(parsed.fields.some((f) => f.label.startsWith("DİKKAT"))).toBe(false);
  });

  it("uyarı yoksa calendarWarning null kalır", () => {
    expect(parseDeadlineBody(SURE_GOVDE).calendarWarning).toBeNull();
  });

  it("kaydırma satırları etiketiyle korunur (birden çok olabilir)", () => {
    const govde = [
      "Son gün: 07.09.2026 (18 gün kaldı)",
      "Kaydırma: adli tatil → 2026-09-07 (HMK m. 102)",
      "Kaydırma: hafta sonu → 2026-09-07 (HMK m. 93)",
      DEADLINE_DISCLAIMER,
    ].join("\n");
    const parsed = parseDeadlineBody(govde);
    expect(parsed.fields.filter((f) => f.label === "Kaydırma")).toHaveLength(2);
  });

  it("etiketsiz satır sessizce yutulmaz", () => {
    const parsed = parseDeadlineBody(`serbest bir satır\n${DEADLINE_DISCLAIMER}`);
    expect(parsed.extras).toEqual(["serbest bir satır"]);
  });

  it("boş/null gövde çökmez", () => {
    expect(parseDeadlineBody(null)).toEqual({ fields: [], calendarWarning: null, extras: [] });
    expect(parseDeadlineBody("")).toEqual({ fields: [], calendarWarning: null, extras: [] });
  });
});

describe("deadlineHeadline (G086)", () => {
  it("kural adını dayanaktan ayırır — donmuş title KULLANILMAZ", () => {
    const item = bildirim();
    const headline = deadlineHeadline(item, parseDeadlineBody(item.body));
    expect(headline).toBe("İstinaf başvuru süresi");
    expect(headline).not.toContain("gün kaldı");
  });

  it("duruşma türünde sabit başlık verir", () => {
    const item = bildirim({ type: "durusma_yaklasti", body: DURUSMA_GOVDE });
    expect(deadlineHeadline(item, parseDeadlineBody(item.body))).toBe("Duruşma");
  });

  it("kural satırı yoksa nötr başlığa düşer", () => {
    const item = bildirim({ body: "Dava: X\n" + DEADLINE_DISCLAIMER });
    expect(deadlineHeadline(item, parseDeadlineBody(item.body))).toBe("Kanuni süre");
  });
});

describe("daysUntil / countdownLabel (G086)", () => {
  const bugun = new Date("2026-08-20T15:40:00");

  it("kalan günü due_date'ten hesaplar", () => {
    expect(daysUntil("2026-09-03", bugun)).toBe(14);
    expect(daysUntil("2026-08-20", bugun)).toBe(0);
    expect(daysUntil("2026-08-19", bugun)).toBe(-1);
  });

  it("tam zaman damgasını da kabul eder", () => {
    expect(daysUntil("2026-08-22T00:00:00", bugun)).toBe(2);
  });

  it("okunamayan tarihte null döner", () => {
    expect(daysUntil(null, bugun)).toBeNull();
    expect(daysUntil("", bugun)).toBeNull();
    expect(daysUntil("tarih-değil", bugun)).toBeNull();
    expect(parseDayStart("tarih-değil")).toBeNull();
  });

  it("geri sayım etiketi kullanıcı şartındaki biçimi verir", () => {
    expect(countdownLabel(14)).toBe("14 gün kaldı");
    expect(countdownLabel(1)).toBe("Yarın");
    expect(countdownLabel(0)).toBe("Bugün");
    expect(countdownLabel(-2)).toBe("2 gün geçti");
  });
});

describe("selectDeadlineRows (G086)", () => {
  const bugun = new Date("2026-08-20T09:00:00");

  it("en yakın tarih en üstte sıralanır", () => {
    const rows = selectDeadlineRows(
      [
        bildirim({ id: 1, due_date: "2026-09-03", case_id: 1 }),
        bildirim({ id: 2, due_date: "2026-08-21", case_id: 2 }),
        bildirim({ id: 3, due_date: "2026-08-27", case_id: 3 }),
      ],
      bugun,
    );
    expect(rows.map((r) => r.daysLeft)).toEqual([1, 7, 14]);
    expect(rows.map((r) => r.item.case_id)).toEqual([2, 3, 1]);
  });

  it("süre/duruşma dışı bildirimleri süzer", () => {
    const rows = selectDeadlineRows(
      [
        bildirim({ id: 1 }),
        bildirim({ id: 2, type: "belge_islendi", case_id: 99 }),
        bildirim({ id: 3, type: "durusma_yaklasti", body: DURUSMA_GOVDE, due_date: "2026-08-22", case_id: 5 }),
      ],
      bugun,
    );
    expect(rows.map((r) => r.item.id)).toEqual([3, 1]);
  });

  it("günü geçmiş süre panelde listelenmez", () => {
    const rows = selectDeadlineRows([bildirim({ id: 1, due_date: "2026-08-19" })], bugun);
    expect(rows).toEqual([]);
  });

  it("son günü BUGÜN olan süre listelenir", () => {
    const rows = selectDeadlineRows([bildirim({ id: 1, due_date: "2026-08-20" })], bugun);
    expect(rows).toHaveLength(1);
    expect(rows[0].daysLeft).toBe(0);
  });

  it("due_date'i olmayan bildirim geri sayamayacağı için düşer", () => {
    expect(selectDeadlineRows([bildirim({ id: 1, due_date: null })], bugun)).toEqual([]);
  });

  it("aynı sürenin eski eşik satırı elenir, en yenisi kalır", () => {
    // Tarayıcı T-15 → T-7 daralınca YENİ satır açar; ikisi aynı kaynağı anlatır.
    const t15 = bildirim({
      id: 10,
      due_date: "2026-08-27",
      body: SURE_GOVDE.replace("(14 gün kaldı)", "(15 gün kaldı)"),
    });
    const t7 = bildirim({
      id: 20,
      due_date: "2026-08-27",
      body: SURE_GOVDE.replace("(14 gün kaldı)", "(7 gün kaldı)"),
    });
    const rows = selectDeadlineRows([t15, t7], bugun);
    expect(rows).toHaveLength(1);
    expect(rows[0].item.id).toBe(20);
  });

  it("farklı aşamaların aynı son günü birleştirilmez", () => {
    const a = bildirim({ id: 10, due_date: "2026-08-27" });
    const b = bildirim({
      id: 11,
      due_date: "2026-08-27",
      body: SURE_GOVDE.replace("Tebliğ tarihi: 12.08.2026", "Tebliğ tarihi: 11.08.2026"),
    });
    expect(selectDeadlineRows([a, b], bugun)).toHaveLength(2);
  });

  it("kimlik anahtarı duruşma satırındaki donmuş geri sayımı dışarıda bırakır", () => {
    // "Duruşma: 22.08.2026 10:30 (2 gün kaldı)" — parantez içi eşiğe göre değişir,
    // kimlik ondan etkilenmemeli; yoksa T-3 ve T-1 satırı iki kez çizilirdi.
    const t3 = bildirim({ id: 1, type: "durusma_yaklasti", due_date: "2026-08-22", body: DURUSMA_GOVDE });
    const t1 = bildirim({
      id: 2,
      type: "durusma_yaklasti",
      due_date: "2026-08-22",
      body: DURUSMA_GOVDE.replace("(2 gün kaldı)", "(1 gün kaldı)"),
    });
    expect(deadlineIdentity(t3, parseDeadlineBody(t3.body))).toBe(
      deadlineIdentity(t1, parseDeadlineBody(t1.body)),
    );
    expect(selectDeadlineRows([t3, t1], bugun).map((r) => r.item.id)).toEqual([2]);
  });

  it("null/boş girdi çökmez", () => {
    expect(selectDeadlineRows(null, bugun)).toEqual([]);
    expect(selectDeadlineRows([], bugun)).toEqual([]);
  });
});
