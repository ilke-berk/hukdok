// Koyu tema kontrast bekçisi — WCAG 2.2 AA (metin ≥4.5:1, ikincil/büyük ≥3:1).
// Eski koyu tema: bordo metin zemine 3.37:1, durum renkleri (#a8323b vb.) açık moda göre sabit
// yazılıydı → "koyu mod okunmuyor". Token değiştiren bu oranları korumak zorunda.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type RGB = [number, number, number];
const css = readFileSync(resolve(__dirname, "tokens.css"), "utf8")
  .replace(/\r/g, "") // Windows checkout'u (autocrlf) seçici eşleşmesini bozmasın
  .replace(/\/\*[\s\S]*?\*\//g, "");

// `secici { ... }` bloklarından, gövdesinde `icerir` geçen İLK bloğun renkleri (hex ya da `r g b` kanalı)
function blok(secici: string, icerir: string): Record<string, RGB> {
  const re = /([^{}]+)\{([^}]*)\}/g;
  for (const m of css.matchAll(re)) {
    if (m[1].trim() !== secici || !m[2].includes(icerir)) continue;
    const out: Record<string, RGB> = {};
    for (const d of m[2].matchAll(/--([a-z-]+?)(-rgb)?:\s*([^;]+);/g)) {
      const v = d[3].trim();
      if (d[2] && /^\d+ \d+ \d+$/.test(v)) out[d[1]] = v.split(" ").map(Number) as RGB;
      else if (/^#[0-9a-f]{6}$/i.test(v)) out[d[1]] = [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16)) as RGB;
    }
    return out;
  }
  throw new Error(`blok yok: ${secici} (${icerir})`);
}

const parlaklik = (c: RGB) =>
  c
    .map((v) => v / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((t, v, i) => t + v * [0.2126, 0.7152, 0.0722][i], 0);

const oran = (a: RGB, b: RGB) => {
  const [k, y] = [parlaklik(a), parlaklik(b)].sort((x, z) => x - z);
  return (y + 0.05) / (k + 0.05);
};

// `bg-tone-x/15` gibi yarı saydam zemin: rengin %a'sı, alttaki yüzeyin kalanı
const karistir = (on: RGB, alt: RGB, a: number): RGB => on.map((v, i) => Math.round(v * a + alt[i] * (1 - a))) as RGB;

const acik = { ...blok(":root", "--brand-rgb"), ...blok(".theme-classic", "--bg:") };
const koyu = { ...blok(".dark", "--brand-rgb"), ...blok(".theme-classic.dark,\n.dark .theme-classic", "--bg:") };
const TONLAR = ["tone-ok", "tone-caution", "tone-danger", "tone-urgent", "tone-info", "tone-violet"];

describe("koyu tema kontrastı (WCAG AA)", () => {
  const ciftler: Array<[string, string, number]> = [
    ["fg", "bg", 7],
    ["fg", "bg-elevated", 7],
    ["fg-muted", "bg", 4.5],
    ["fg-muted", "bg-elevated", 4.5],
    ["fg-subtle", "bg", 3],
    ["brand", "bg", 4.5],
    ["brand", "bg-elevated", 4.5],
    ["brand", "brand-soft", 4.5],
    ["brand-fg", "brand-solid", 4.5],
    ["brand-fg", "brand-solid-hover", 4.5],
    ...TONLAR.flatMap((t): Array<[string, string, number]> => [
      [t, "bg", 4.5],
      [t, "bg-elevated", 4.5],
    ]),
  ];
  it.each(ciftler)("%s / %s ≥ %s:1", (on, arka, asgari) => {
    expect(koyu[on], `--${on} tanımlı değil`).toBeDefined();
    expect(koyu[arka], `--${arka} tanımlı değil`).toBeDefined();
    expect(oran(koyu[on], koyu[arka])).toBeGreaterThanOrEqual(asgari);
  });

  it.each(TONLAR)("%s rozeti (%%15 kendi tonu üstünde) ≥ 4.5:1", (t) => {
    const zemin = karistir(koyu[t], koyu["bg-elevated"], 0.15);
    expect(oran(koyu[t], zemin)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("açık tema — dolgu ve bordo metin", () => {
  it.each([
    ["brand", "bg"],
    ["brand", "bg-elevated"],
    ["brand-fg", "brand-solid"],
  ])("%s / %s ≥ 4.5:1", (on, arka) => {
    expect(oran(acik[on], acik[arka])).toBeGreaterThanOrEqual(4.5);
  });
});
