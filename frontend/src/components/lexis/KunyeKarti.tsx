import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { BOS, tutarYaz } from "@/lib/lexisMetin";
import {
  ISKELET_BOLUMLERI,
  SIRKET_ADLARI,
  type DosyaGirdisi,
  type KunyeAlani,
  type KunyeOneriDurumu,
  type KunyeOnerisi,
  type LexisSirket,
  type RaporTuru,
  type YazilabilirIskelet,
} from "@/types/lexis";
import { KunyeOneriCipi } from "./KunyeOneriCipi";
import { BolgeBasligi } from "./ortak";
import { BAGLANTI_SINIFI } from "./yardimcilar";

export type KunyeSecimi = Partial<Pick<DosyaGirdisi, "sirket" | "rapor_turu" | "iskelet">>;

type KunyeKartiProps = {
  dosya: DosyaGirdisi;
  onDegistir: (secim: KunyeSecimi) => void;
  /** Ek raporda: dosyanın önceki raporunu okuyucuda açar. */
  onOncekiRapor?: () => void;
  kilitli?: boolean;
  /** Belgeden künye önerileri (Aşama 13): alan başına çip; reddedilen gösterilmez. Verilmezse çip çizilmez. */
  oneriler?: KunyeOnerisi[];
  onOneriKarar?: (oneri: KunyeOnerisi, durum: KunyeOneriDurumu) => void;
  belgeAdi?: (id: number) => string;
  /** Başlığın altındaki alan: "Belgelerden doldur" (`KunyeDoldur`). */
  ust?: ReactNode;
};

const ISKELET_ADLARI: Record<YazilabilirIskelet, string> = { ANADOLU: "Anadolu", ALTILI: "Altılı", KISA: "Kısa", EK: "Ek rapor" };

/** "Ek rapor (2 bölüm)" — künye raporun bölümü sayılmaz (ek raporda ekranda ayrı durur). */
function iskeletAdi(iskelet: YazilabilirIskelet): string {
  return `${ISKELET_ADLARI[iskelet]} (${ISKELET_BOLUMLERI[iskelet].filter((b) => b.kod !== "kunye").length} bölüm)`;
}

const SECIM_SINIFI =
  "w-full h-8 px-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[12.5px] text-[var(--fg)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none disabled:opacity-60";

/**
 * Dosyanın künyesi: raporun şirketi, türü ve iskeleti seçilir; kalan alanlar dava kartından gelir (salt okunur —
 * düzeltme dava kartında yapılır). Boş alan `[…]` ile gösterilir; kart ile belge çelişirse ikisi de yazılır.
 * Belgeden gelen öneri alanın altında çiptir: kabul edilen değer taslağın künyesine girer (karta yazılmaz, K34) ve
 * satırda "belgeden" işaretiyle görünür; kart değeri farklıysa çipte yanında durur.
 */
export function KunyeKarti({ dosya, onDegistir, onOncekiRapor, kilitli = false, oneriler = [], onOneriKarar, belgeAdi, ust }: KunyeKartiProps) {
  const satirlar: [string, string | null, KunyeAlani | null][] = [
    ["Mahkeme", dosya.mahkeme, null],
    ["Esas no", dosya.esas_no, null],
    ["Hasar no", dosya.hasar_no, "hasar_no"],
    ["Poliçe no", dosya.police_no, "police_no"],
    ["Teminat limiti", dosya.teminat_limiti === null ? null : tutarYaz(dosya.teminat_limiti), "teminat_limiti"],
    ["Talep (maddi)", dosya.talep_maddi === null ? null : tutarYaz(dosya.talep_maddi), "talep_maddi"],
    ["Talep (manevi)", dosya.talep_manevi === null ? null : tutarYaz(dosya.talep_manevi), "talep_manevi"],
    ["Uzmanlık", dosya.uzmanlik, "uzmanlik"],
    ["Sigortalı", dosya.sigortali, "sigortali"],
    ["Hasta", dosya.magdur, "hasta"],
    ["Hastane", dosya.hastane, "hastane"],
  ];
  const gorunen = oneriler.filter((o) => o.durum !== "ret");
  // Kartta karşılığı olmayan alanlar yalnız önerisi varsa satır olur.
  for (const [etiket, alan] of [["Olay tarihi", "olay_tarihi"], ["Davalı", "davali"]] as const) {
    if (gorunen.some((o) => o.alan === alan)) satirlar.push([etiket, null, alan]);
  }
  const ad = belgeAdi ?? ((id: number) => `belge ${id}`);

  return (
    <section aria-label="Künye" data-testid="lexis-kunye" className="grid gap-2.5">
      <BolgeBasligi>Künye</BolgeBasligi>
      <div className="grid grid-cols-2 gap-2">
        <label className="grid gap-1 col-span-2">
          <span className="text-[11px] text-[var(--fg-subtle)]">Şirket</span>
          <select
            className={SECIM_SINIFI}
            value={dosya.sirket ?? ""}
            disabled={kilitli}
            onChange={(e) => onDegistir({ sirket: (e.target.value || null) as LexisSirket | null })}
          >
            <option value="">Seçin…</option>
            {(Object.keys(SIRKET_ADLARI) as LexisSirket[]).map((kod) => (
              <option key={kod} value={kod}>
                {SIRKET_ADLARI[kod]}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] text-[var(--fg-subtle)]">Rapor türü</span>
          <select
            className={SECIM_SINIFI}
            value={dosya.rapor_turu}
            disabled={kilitli}
            onChange={(e) => onDegistir({ rapor_turu: e.target.value as RaporTuru })}
          >
            <option value="ANA">Ana rapor</option>
            <option value="EK">Ek rapor</option>
          </select>
        </label>
        <label className="grid gap-1">
          <span className="text-[11px] text-[var(--fg-subtle)]">İskelet</span>
          <select
            className={SECIM_SINIFI}
            value={dosya.iskelet}
            disabled={kilitli}
            onChange={(e) => onDegistir({ iskelet: e.target.value as YazilabilirIskelet })}
          >
            {(Object.keys(ISKELET_ADLARI) as YazilabilirIskelet[]).map((kod) => (
              <option key={kod} value={kod}>
                {iskeletAdi(kod)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {ust}

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12.5px]">
        {satirlar.map(([etiket, kartDegeri, alan]) => {
          const alanOnerileri = alan ? gorunen.filter((o) => o.alan === alan) : [];
          const kabuller = alanOnerileri.filter((o) => o.durum === "kabul");
          // Kabul edilen değer kartın yerine geçer (iki farklı tutar kabul edilmişse servis seçmez: kart kalır).
          const deger = kabuller.length ? [...new Set(kabuller.map((o) => o.deger))].join(", ") : kartDegeri;
          return (
            <div key={etiket} className="contents">
              <dt className="text-[var(--fg-subtle)] whitespace-nowrap">{etiket}</dt>
              <dd className="grid gap-1 min-w-0">
                <span className={deger ? "text-[var(--fg)] break-words" : "text-tone-caution font-mono"}>
                  {deger ?? BOS}
                  {kabuller.length > 0 && <span className="ml-1.5 text-[10.5px] text-tone-ok">belgeden</span>}
                </span>
                {onOneriKarar && alanOnerileri.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {alanOnerileri.map((o) => (
                      <KunyeOneriCipi key={o.id} oneri={o} belgeAdi={ad} onKarar={onOneriKarar} kilitli={kilitli} />
                    ))}
                  </span>
                )}
              </dd>
            </div>
          );
        })}
      </dl>

      {dosya.celiskiler.map((c) => (
        <div
          key={c.alan}
          role="note"
          className="flex items-start gap-2 border border-tone-caution/40 bg-tone-caution/10 px-2.5 py-2 text-[12px] leading-[1.5] text-[var(--fg)]"
        >
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-tone-caution" aria-hidden="true" />
          <span>
            <span className="font-medium">{c.etiket}</span> — kartta {c.kart}, belgede {c.belge}. İkisi de saklanır; rapora hangisinin
            gireceğini siz belirlersiniz.
          </span>
        </div>
      ))}

      {dosya.onceki_rapor && onOncekiRapor && (
        <button
          type="button"
          onClick={onOncekiRapor}
          className={`justify-self-start text-left text-[12.5px] ${BAGLANTI_SINIFI}`}
        >
          Bu dosyanın önceki raporunu oku
        </button>
      )}
    </section>
  );
}
