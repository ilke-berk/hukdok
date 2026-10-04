import { AlertTriangle } from "lucide-react";
import { BOS, tutarYaz } from "@/lib/lexisMetin";
import { SIRKET_ADLARI, type DosyaGirdisi, type LexisSirket, type RaporTuru, type YazilabilirIskelet } from "@/types/lexis";
import { BolgeBasligi } from "./ortak";
import { BAGLANTI_SINIFI } from "./yardimcilar";

export type KunyeSecimi = Partial<Pick<DosyaGirdisi, "sirket" | "rapor_turu" | "iskelet">>;

type KunyeKartiProps = {
  dosya: DosyaGirdisi;
  onDegistir: (secim: KunyeSecimi) => void;
  /** Ek raporda: dosyanın önceki raporunu okuyucuda açar. */
  onOncekiRapor?: () => void;
  kilitli?: boolean;
};

const ISKELET_ADLARI: Record<YazilabilirIskelet, string> = {
  ANADOLU: "Anadolu (8 bölüm)",
  ALTILI: "Altılı (6 bölüm)",
  KISA: "Kısa (4 bölüm)",
  EK: "Ek rapor (2 bölüm)",
};

const SECIM_SINIFI =
  "w-full h-8 px-2 border border-[var(--border)] bg-[var(--bg-elevated)] text-[12.5px] text-[var(--fg)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none disabled:opacity-60";

/**
 * Dosyanın künyesi: raporun şirketi, türü ve iskeleti seçilir; kalan alanlar dava kartından gelir (salt okunur —
 * düzeltme dava kartında yapılır). Boş alan `[…]` ile gösterilir; kart ile belge çelişirse ikisi de yazılır.
 */
export function KunyeKarti({ dosya, onDegistir, onOncekiRapor, kilitli = false }: KunyeKartiProps) {
  const satirlar: [string, string | null][] = [
    ["Mahkeme", dosya.mahkeme],
    ["Esas no", dosya.esas_no],
    ["Hasar no", dosya.hasar_no],
    ["Poliçe no", dosya.police_no],
    ["Teminat limiti", dosya.teminat_limiti === null ? null : tutarYaz(dosya.teminat_limiti)],
    ["Talep (maddi)", dosya.talep_maddi === null ? null : tutarYaz(dosya.talep_maddi)],
    ["Talep (manevi)", dosya.talep_manevi === null ? null : tutarYaz(dosya.talep_manevi)],
    ["Uzmanlık", dosya.uzmanlik],
    ["Sigortalı", dosya.sigortali],
    ["Hasta", dosya.magdur],
    ["Hastane", dosya.hastane],
  ];

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
                {ISKELET_ADLARI[kod]}
              </option>
            ))}
          </select>
        </label>
      </div>

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12.5px]">
        {satirlar.map(([etiket, deger]) => (
          <div key={etiket} className="contents">
            <dt className="text-[var(--fg-subtle)] whitespace-nowrap">{etiket}</dt>
            <dd className={deger ? "text-[var(--fg)] break-words" : "text-tone-caution font-mono"}>{deger ?? BOS}</dd>
          </div>
        ))}
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
