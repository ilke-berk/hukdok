/**
 * predictDocType.ts
 *
 * Dosya adından belge türü tahmini (fuzzy). UYAP'tan/ofisten gelen dosya adları
 * genelde ya tür ADINI ya da tür KODUNU içerir:
 *   "2026_03_24_VEKALETNAME.pdf"        → Vekaletname        (ad, tam)
 *   "(2)_Adli_Tip_Raporu.udf"           → ATK Raporu         (ad, kısmi)
 *   "2026-01-28_ATK-RPR_23-1411.pdf"    → ATK Raporu         (kod: ATK-RPR)
 *   "ILKE_2_DAVA_DLK.udf"               → Dava Dilekçesi     (kod: DAVA-DLK)
 *
 * Hem türün adına hem koduna karşı eşleştirir; kök + Levenshtein toleransıyla
 * yazım/çekim farklarını yakalar. Anlık, backend gerektirmez.
 *
 * Öncelik (tier): tam ad eşleşmesi (3) > kod eşleşmesi (2) > kısmi ad eşleşmesi (1).
 */

import type { ConfigItem } from "@/hooks/useConfig";
import { levenshtein } from "@/lib/nameSimilarity";

// Türkçe karakter sadeleştir + alfanümerik dışını boşluğa çevir.
const foldTr = (s: string) =>
  s
    .toLocaleLowerCase("tr-TR")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ş/g, "s")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

const compact = (s: string) => foldTr(s).replace(/\s+/g, "");
const cleanCode = (code: string | undefined) => (code ?? "").replace(/_+$/, "");

// Tür adında anlam taşımayan kısa bağlaçlar.
const STOPWORDS = new Set(["veya", "ile", "icin", "ya"]);

// Bir tür-kelimesinin dosya adında geçip geçmediği.
// Kısa kelimeler (<=3 harf, ör. "tip") yalnız tam token eşleşir (substring yanlış
// pozitif üretir: "ek" → "dilekce"). Uzunlarda kök + Levenshtein toleransı.
function tokenMatches(tok: string, hay: string, hayTokens: string[]): boolean {
  if (tok.length <= 3) return hayTokens.includes(tok);
  const stem = tok.slice(0, Math.max(4, tok.length - 2));
  if (hay.includes(stem)) return true;
  const maxDist = tok.length <= 4 ? 1 : tok.length <= 7 ? 2 : 3;
  for (const ht of hayTokens) {
    if (ht.length >= 3 && levenshtein(tok, ht) <= maxDist) return true;
  }
  return false;
}

interface Candidate {
  code: string;
  tier: number;       // 3 tam ad · 2 kod · 1 kısmi ad
  exact: number;      // tam token eşleşme sayısı (tier 3 ayrımı)
  tokTotal: number;   // türün anlamlı kelime sayısı (azı daha spesifik)
  matchedLen: number; // eşleşen kelime uzunluğu toplamı
  codeLen: number;    // kod eşleşme uzunluğu (tier 2)
}

// a, b'den kesinlikle daha iyi mi?
function isBetter(a: Candidate, b: Candidate): boolean {
  if (a.tier !== b.tier) return a.tier > b.tier;
  if (a.tier === 3) {
    if (a.exact !== b.exact) return a.exact > b.exact;
    if (a.tokTotal !== b.tokTotal) return a.tokTotal < b.tokTotal; // daha az kelime = daha spesifik
    return a.matchedLen > b.matchedLen;
  }
  if (a.tier === 2) return a.codeLen > b.codeLen;
  return a.matchedLen > b.matchedLen;
}

/**
 * `filename` için en olası belge türü kodunu döndürür; güçlü eşleşme yoksa "".
 */
export function predictDocTypeFromName(filename: string, doctypes: ConfigItem[]): string {
  const base = filename.replace(/\.[^.]+$/, ""); // uzantıyı at
  const hay = foldTr(base);
  if (!hay) return "";
  const hayCompact = hay.replace(/\s+/g, "");
  const hayTokens = hay.split(" ").filter(Boolean);

  let best: Candidate | null = null;

  for (const dt of doctypes) {
    const code = cleanCode(dt.code);
    if (!code) continue;

    // --- İsim metrikleri ---
    const nameClean = foldTr(dt.name.replace(/\([^)]*\)/g, " ")); // parantez içini at
    const nameToks = nameClean
      .split(" ")
      .filter((t) => t.length >= 2 && !STOPWORDS.has(t) && !/^\d+$/.test(t));

    let matched = 0;
    let exact = 0;
    let matchedLen = 0;
    let hasLong = false;
    for (const tok of nameToks) {
      if (tokenMatches(tok, hay, hayTokens)) {
        matched++;
        matchedLen += tok.length;
        if (hayTokens.includes(tok)) exact++;
        if (tok.length >= 5) hasLong = true;
      }
    }
    const coverage = nameToks.length > 0 ? matched / nameToks.length : 0;

    let cand: Candidate | null = null;
    if (nameToks.length > 0 && coverage === 1) {
      cand = { code, tier: 3, exact, tokTotal: nameToks.length, matchedLen, codeLen: 0 };
    } else {
      // --- Kod metrikleri (tier 2) ---
      const codeCompact = compact(code);
      if (codeCompact.length >= 5 && hayCompact.includes(codeCompact)) {
        cand = { code, tier: 2, exact: 0, tokTotal: 0, matchedLen: 0, codeLen: codeCompact.length };
      } else {
        const codeToks = foldTr(code)
          .split(" ")
          .filter((t) => t.length >= 3 && !/^\d+$/.test(t));
        if (codeToks.length > 0 && codeToks.every((t) => hayCompact.includes(t))) {
          const codeLen = codeToks.reduce((a, t) => a + t.length, 0);
          cand = { code, tier: 2, exact: 0, tokTotal: 0, matchedLen: 0, codeLen };
        } else if (nameToks.length >= 2 && coverage >= 0.65 && hasLong) {
          cand = { code, tier: 1, exact, tokTotal: nameToks.length, matchedLen, codeLen: 0 };
        }
      }
    }

    if (cand && (!best || isBetter(cand, best))) best = cand;
  }

  return best ? best.code : "";
}
