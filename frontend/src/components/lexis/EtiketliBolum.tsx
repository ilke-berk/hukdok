import { BOS } from "@/lib/lexisMetin";
import type { BolumKodu, DegerKaynagi, EtiketliSatir } from "@/types/lexis";
import { alanKimligi } from "./yardimcilar";

type EtiketliBolumProps = {
  bolum: BolumKodu;
  satirlar: EtiketliSatir[];
  onDegistir: (alan: string, deger: string) => void;
  /** Alandan çıkınca (yeniden denetim). */
  onBlur?: () => void;
  /** Uyarıdan gelinen satır kısa süre vurgulanır. */
  vurguluAlan?: string | null;
  kilitli?: boolean;
};

const KAYNAK_ADLARI: Record<DegerKaynagi, string> = { KART: "kart", BELGE: "belge", ELLE: "elle" };

/**
 * Etiketli bölüm (hasar bilgileri, hastane, sulh): satırları model değil KOD doldurur — değer dava kartından ya
 * da dosyanın belgesinden gelir, kaynağı satırda yazar. Zorunlu boş alan `[…]` ile vurgulanır.
 */
export function EtiketliBolum({ bolum, satirlar, onDegistir, onBlur, vurguluAlan, kilitli = false }: EtiketliBolumProps) {
  return (
    <div className="grid gap-px bg-[var(--border)] border border-[var(--border)]">
      {satirlar.map((s) => {
        const bos = !s.deger?.trim();
        const eksik = bos && s.zorunlu;
        const kimlik = alanKimligi(bolum, s.alan);
        return (
          <div
            key={s.alan}
            id={kimlik}
            className={`grid sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-3 py-1 transition-colors ${
              vurguluAlan === s.alan ? "bg-[var(--brand-soft)]" : "bg-[var(--bg)]"
            }`}
          >
            <label htmlFor={`${kimlik}-girdi`} className="text-[12.5px] text-[var(--fg-muted)]">
              {s.etiket}
            </label>
            <input
              id={`${kimlik}-girdi`}
              type="text"
              value={s.deger ?? ""}
              disabled={kilitli}
              placeholder={eksik ? BOS : "-"}
              aria-invalid={eksik || undefined}
              onChange={(e) => onDegistir(s.alan, e.target.value)}
              onBlur={onBlur}
              className={`w-full h-7 px-2 -mx-2 bg-transparent border rounded-[3px] text-[13px] text-[var(--fg)] focus:border-[var(--brand)] focus:bg-[var(--bg-elevated)] focus:outline-none ${
                eksik
                  ? "border-tone-caution/50 placeholder:text-tone-caution placeholder:font-mono"
                  : "border-transparent hover:border-[var(--border)] placeholder:text-[var(--fg-subtle)]"
              }`}
            />
            <span className="font-mono text-[9.5px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] justify-self-end" title="Değerin geldiği yer">
              {s.kaynak ? KAYNAK_ADLARI[s.kaynak] : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
