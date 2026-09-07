import type { VarYokDurumu } from "@/lib/reports";

const ETIKET_CLS = "font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] whitespace-nowrap";
const CHECK_CLS = "w-3.5 h-3.5 accent-[var(--brand)] cursor-pointer";

const VAR_YOK_SECENEKLERI: Array<{ durum: VarYokDurumu; metin: string }> = [
    { durum: "hepsi", metin: "Hepsi" },
    { durum: "var", metin: "Var" },
    { durum: "yok", metin: "Yok" },
];

type VarYokProps = {
    /** Anahtar metni (`HizliFiltre.etiket`, ör. "Davası var"); yoksa kolon etiketi. */
    etiket: string;
    durum: VarYokDurumu;
    onChange: (durum: VarYokDurumu) => void;
};

/**
 * Üçlü anahtar (§5.3 `var_yok`): hepsi = filtre yok, var = `gte 1`, yok = `eq 0`. Segmentli düğme
 * (`aria-pressed`), sayı kolonunda; başka aralık isteyen "+ Başka alan"dan sayı aralığı ekler.
 */
export function VarYokAnahtari({ etiket, durum, onChange }: VarYokProps) {
    return (
        <div className="flex flex-col gap-1 min-w-0">
            <span className={ETIKET_CLS}>{etiket}</span>
            <div role="group" aria-label={etiket} className="inline-flex h-7 border border-[var(--border)] rounded-[3px] overflow-hidden bg-[var(--bg)]">
                {VAR_YOK_SECENEKLERI.map(s => {
                    const secili = s.durum === durum;
                    return (
                        <button
                            key={s.durum}
                            type="button"
                            aria-pressed={secili}
                            aria-label={`${etiket}: ${s.metin.toLocaleLowerCase("tr-TR")}`}
                            onClick={() => onChange(s.durum)}
                            className={[
                                "px-2.5 text-[11.5px] border-r border-[var(--border)] last:border-r-0 transition-colors",
                                secili
                                    ? "bg-[var(--brand-soft)] text-[var(--brand)] font-medium"
                                    : "text-[var(--fg-muted)] hover:text-[var(--fg)]",
                            ].join(" ")}
                        >
                            {s.metin}
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

type BosAnahtariProps = {
    /** Kutucuk metni (`HizliFiltre.etiket`, ör. "E-postası yok"). */
    etiket: string;
    acik: boolean;
    onChange: (acik: boolean) => void;
};

/** Tek kutucuk (§5.3 `bos_anahtari`): açık = `is_null`. */
export function BosAnahtari({ etiket, acik, onChange }: BosAnahtariProps) {
    return (
        <div className="flex flex-col gap-1 min-w-0">
            <span className={ETIKET_CLS}>{etiket}</span>
            <label className="inline-flex items-center gap-2 h-7 text-[12px] text-[var(--fg)] cursor-pointer select-none whitespace-nowrap">
                <input
                    type="checkbox"
                    aria-label={etiket}
                    checked={acik}
                    onChange={e => onChange(e.target.checked)}
                    className={CHECK_CLS}
                />
                {etiket}
            </label>
        </div>
    );
}
