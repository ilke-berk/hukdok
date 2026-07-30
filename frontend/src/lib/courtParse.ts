// Mahkeme adı ayrıştırma — QuickCaseModal'daki parseCourt'un ortak yardımcıya
// çıkarılmış hali (otonom dava açma planı: court parser ortaklaştırma).
// "Samsun 2. Tüketici Mahkemesi" → base "Samsun Tüketici Mahkemesi" + daire "2".
//
// Türkçe İ/ı tuzağı: JS /i bayrağı U+0130 (İ) ↔ i ve U+0131 (ı) ↔ I
// katlamasını YAPMAZ; intake'ten gelen mahkeme adları çoğunlukla tam büyük
// harf ("MERSİN 3. TÜKETİCİ MAHKEMESİ") olduğundan kritik hecelerde açık
// karakter sınıfı ([iİ], [ıI]) kullanılır.

export interface ParsedCourt {
  base: string;
  daireNo: string;
}

const MAHKEMESI = "Mahkemes[iİ]";
const DAIRESI = "Da[iİ]res[iİ]";

// Pattern 1: "Samsun 2. Tüketici Mahkemesi" — şehir + sayı + mahkeme türü
const P1 = new RegExp(`^(\\S+)\\s+(\\d+)\\.\\s+(.+${MAHKEMESI})$`, "i");

// Pattern 2: "Ankara Bölge İdare Mahkemesi 10. İdari Dava Dairesi"
const P2 = new RegExp(`^(.+?${MAHKEMESI})\\s+(\\d+)\\.\\s*.+${DAIRESI}$`, "i");

// Pattern 3: sözel daire ("Üçüncü İdari Dava Dairesi") — sayıya dönüştür
const ORDINALS: Record<string, string> = {
  "b[iİ]r[iİ]nc[iİ]": "1",
  "[iİ]k[iİ]nc[iİ]": "2",
  "üçüncü": "3",
  "dördüncü": "4",
  "beş[iİ]nc[iİ]": "5",
  "alt[ıI]nc[ıI]": "6",
  "yed[iİ]nc[iİ]": "7",
  "sek[iİ]z[iİ]nc[iİ]": "8",
  "dokuzuncu": "9",
  "onuncu": "10",
};

export function parseCourt(raw: string): ParsedCourt {
  if (!raw) return { base: "", daireNo: "" };
  const trimmed = raw.trim();

  const p1 = trimmed.match(P1);
  if (p1) return { base: `${p1[1]} ${p1[3]}`, daireNo: p1[2] };

  const p2 = trimmed.match(P2);
  if (p2) return { base: p2[1], daireNo: p2[2] };

  for (const [pattern, num] of Object.entries(ORDINALS)) {
    const re = new RegExp(`${pattern}\\s+.*da[iİ]re`, "i");
    if (re.test(trimmed)) {
      const base = trimmed.replace(new RegExp(`\\s*${pattern}.*$`, "i"), "").trim();
      return { base: base || trimmed, daireNo: num };
    }
  }

  return { base: trimmed, daireNo: "" };
}
