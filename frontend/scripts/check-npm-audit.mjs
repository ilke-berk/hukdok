#!/usr/bin/env node
// ADR-013 K3 — npm audit (--omit=dev) sonucunu audit-ignore.txt'e karşı denetler.
// npm'in kendi CLI'ı --ignore-vuln taşımadığı için bu betik pip-audit'in
// aynı desenini (dated ignore list) buraya taşır. Her satır:
//   <GHSA-id>  # gerekçe ... Gözden geçirme: YYYY-MM-DD
// Süresi geçmiş satır ya da ignore listesinde olmayan yeni bir advisory
// bulunursa süreç 1 ile çıkar (CI kırmızı).

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const today = new Date().toISOString().slice(0, 10);

const ignored = new Map();
for (const raw of readFileSync("audit-ignore.txt", "utf8").split("\n")) {
  const line = raw.trim();
  if (!line || line.startsWith("#")) continue;
  const id = line.split(/\s+/)[0];
  const match = line.match(/Gözden geçirme: (\d{4}-\d{2}-\d{2})/);
  if (!match) {
    console.error(`audit-ignore.txt satırında tarih yok: ${line}`);
    process.exit(1);
  }
  if (match[1] < today) {
    console.error(`SÜRESİ GEÇMİŞ ignore satırı (gözden geçirilmeli): ${line}`);
    process.exit(1);
  }
  ignored.set(id, line);
}

let stdout;
try {
  // shell: true — Windows'ta npm bir .cmd dosyasıdır, shell'siz execFileSync
  // spawn hatası verir (stdout/status kaybolur); Linux'ta (CI) zararsız.
  stdout = execFileSync("npm", ["audit", "--omit=dev", "--json"], { encoding: "utf8", shell: true });
} catch (err) {
  // npm audit, açık bulunca non-zero exit döner; JSON stdout'ta yine de var.
  stdout = err.stdout ? err.stdout.toString() : "{}";
}

const data = JSON.parse(stdout || "{}");
const found = new Set();
for (const vuln of Object.values(data.vulnerabilities ?? {})) {
  for (const via of vuln.via ?? []) {
    if (typeof via === "object" && via.url) {
      found.add(via.url.replace(/\/+$/, "").split("/").pop());
    }
  }
}

const unignored = [...found].filter((id) => !ignored.has(id));
if (unignored.length > 0) {
  console.error("Ignore listesinde olmayan npm advisory:", unignored.join(", "));
  process.exit(1);
}

console.log(
  `npm audit (prod) temiz: ${found.size} bilinen açığın tamamı gerekçeli/tarihli ignore listesinde (audit-ignore.txt).`,
);
