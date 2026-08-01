import type { MergeDraft, MergeFieldEnrich } from "@/lib/caseIntake";
import { INTAKE_FIELDS, type IntakeFieldDef, type IntakeFieldState } from "@/lib/caseIntakeFields";

// =====================================================================
// Zenginleştirme modu (Faz 7) — fark listesi saf yardımcıları.
// Review, enrich modunda yalnız FARK gösterir: fill/conflict alanları satır
// olur, confirm alanları "teyit edildi" özetine katlanır, keep / iki-taraf-boş
// alanlar gizlenir. Tik semantiği bu modda ONAY değil UYGULA'dır: tik'lenen
// alan apply'a gider, tik'lenmeyen alan davada DOKUNULMAZ.
// =====================================================================

export type EnrichRowGroup = "action" | "confirmed" | "hidden";

/** Alanın enrich bilgisi (draftKey'siz alanlarda yok). */
export function enrichInfoFor(def: IntakeFieldDef, draft: MergeDraft): MergeFieldEnrich | null {
  if (!def.draftKey) return null;
  return draft.fields[def.draftKey]?.enrich ?? null;
}

/** Kayıtlı davadaki mevcut değerin string hali (editor/karşılaştırma için). */
export function enrichCurrentString(def: IntakeFieldDef, draft: MergeDraft): string {
  const current = enrichInfoFor(def, draft)?.current;
  return current == null ? "" : String(current);
}

/**
 * Fark listesi grubu. draftKey'siz alanlar (elle girilen: klasör no, kabul
 * tarihi, avukatlar, notlar…) enrich'te gizlidir — bunlar dava kartı düzenleme
 * formunun işi. enrich bilgisi olmayan draftKey'li alan iki tarafı da boş
 * demektir → gizli.
 */
export function enrichRowGroup(def: IntakeFieldDef, draft: MergeDraft): EnrichRowGroup {
  const info = enrichInfoFor(def, draft);
  if (!info) return "hidden";
  if (info.status === "fill" || info.status === "conflict") return "action";
  if (info.status === "confirm") return "confirmed";
  return "hidden"; // keep — kayıtlı değer korunur, belge önerisi yok
}

/**
 * Apply'a gidecek kısmi alan yükü: yalnız action grubundaki, TİK'Lİ ve kayıtlı
 * değerden gerçekten FARKLI alanlar. Boş string → null (alan silme); money
 * alanları sayıya çevrilir ve sayısal karşılaştırılır (50000 == "50000.0").
 */
export function buildEnrichFields(
  states: Record<string, IntakeFieldState>,
  draft: MergeDraft,
  defs: IntakeFieldDef[] = INTAKE_FIELDS,
): Record<string, string | number | null> {
  const out: Record<string, string | number | null> = {};
  for (const def of defs) {
    if (enrichRowGroup(def, draft) !== "action") continue;
    const state = states[def.key];
    if (!state?.approved) continue;
    const value = state.value.trim();
    const current = enrichCurrentString(def, draft).trim();
    if (def.widget === "money") {
      const num = value === "" ? null : Number(value);
      if (num !== null && Number.isNaN(num)) continue;
      const curNum = current === "" ? 0 : Number(current);
      if ((num ?? 0) !== curNum) out[def.key] = num;
    } else if (value !== current) {
      out[def.key] = value === "" ? null : value;
    }
  }
  return out;
}

/** Teyit özet çipleri: confirm grubundaki alanların etiketleri. */
export function confirmedFieldLabels(draft: MergeDraft, defs: IntakeFieldDef[] = INTAKE_FIELDS): string[] {
  return defs
    .filter(def => def.enabled && enrichRowGroup(def, draft) === "confirmed")
    .map(def => def.label);
}

/**
 * Eklenecek taraf seçimi: davada zaten kayıtlı olmayan (existingId yok),
 * tik'li ve adı dolu satırlar. Mevcut taraflara asla dokunulmaz (yalnız EKLEME).
 */
export function selectEnrichParties<
  T extends { approved: boolean; name: string; existingId?: number | null },
>(parties: T[]): T[] {
  return parties.filter(p => p.existingId == null && p.approved && p.name.trim() !== "");
}

/** Sonuç ekranı / geçmiş için alan etiketi (bilinmeyen anahtar aynen döner). */
export function enrichFieldLabel(key: string): string {
  return INTAKE_FIELDS.find(f => f.key === key)?.label ?? key;
}

/** Kaydet çubuğu özeti: "2 alan uygulanacak · 1 taraf eklenecek · 3 belge arşivlenecek". */
export function enrichApplySummary(counts: {
  fields: number;
  parties: number;
  documents: number;
  policies: number;
}): string {
  const parts: string[] = [];
  if (counts.fields > 0) parts.push(`${counts.fields} alan uygulanacak`);
  if (counts.parties > 0) parts.push(`${counts.parties} taraf eklenecek`);
  if (counts.documents > 0) parts.push(`${counts.documents} belge arşivlenecek`);
  if (counts.policies > 0) parts.push(`${counts.policies} poliçe kaydedilecek`);
  return parts.length > 0
    ? parts.join(" · ")
    : "Uygulanacak değişiklik seçilmedi — tik'lenen öneriler davaya işlenir.";
}
