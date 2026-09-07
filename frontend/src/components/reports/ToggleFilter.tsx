import type { VarYokDurumu } from "@/lib/reports";
import { BOS_ETIKETI, sayiRozeti } from "@/lib/reports";

const ETIKET_CLS = "font-mono text-[9.5px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] whitespace-nowrap";
const CHECK_CLS = "w-3.5 h-3.5 accent-[var(--brand)] cursor-pointer";

type SayiRozetiProps = {
    /** Kayıt sayısı; `null` (eski katalog / türetilmiş kolon) → hiç basılmaz. */
    sayi: number | null;
    /** "<etiket> · N" biçimi (kutucuk); yoksa yalnız sayı (çip/satır rozeti). */
    ayrac?: boolean;
};

/**
 * §7.1 sayı rozeti: tr-TR binlik ("1.443"), ince mono; `data-testid="sayi-rozeti"`. Sayı yoksa hiçbir
 * şey basılmaz — katalog vermiyorsa ekran rozetsiz çalışır.
 */
export function SayiRozeti({ sayi, ayrac = false }: SayiRozetiProps) {
    if (sayi === null) return null;
    return (
        <span data-testid="sayi-rozeti" className="font-mono text-[10px] tabular-nums text-[var(--fg-subtle)] whitespace-nowrap">
            {ayrac ? " · " : ""}{sayiRozeti(sayi)}
        </span>
    );
}

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

type BosKutucuguProps = {
    /** Kutucuk metni (`HizliFiltre.etiket`, ör. "E-postası yok"). */
    etiket: string;
    acik: boolean;
    /** §7.2 `bos_sayisi` rozeti ("E-postası yok · 12"); null → rozetsiz. */
    sayi?: number | null;
    onChange: (acik: boolean) => void;
};

/** Tek kutucuk (§5.3 `bos_anahtari`, başlıksız): açık = `is_null`; "Eksik bilgi" hücresinde yan yana dizilir. */
export function BosKutucugu({ etiket, acik, sayi = null, onChange }: BosKutucuguProps) {
    return (
        <label className="inline-flex items-center gap-2 h-7 text-[12px] text-[var(--fg)] cursor-pointer select-none whitespace-nowrap">
            <input
                type="checkbox"
                aria-label={etiket}
                checked={acik}
                onChange={e => onChange(e.target.checked)}
                className={CHECK_CLS}
            />
            <span>
                {etiket}
                <SayiRozeti sayi={sayi} ayrac />
            </span>
        </label>
    );
}

type BosAnahtariProps = BosKutucuguProps;

/** Başlıklı tek kutucuk (§5.3 `bos_anahtari`) — şeritte tek başına kalan yuva için; QuickFilters yuvaları "Eksik bilgi" hücresinde toplar. */
export function BosAnahtari({ etiket, acik, sayi = null, onChange }: BosAnahtariProps) {
    return (
        <div className="flex flex-col gap-1 min-w-0">
            <span className={ETIKET_CLS}>{etiket}</span>
            <BosKutucugu etiket={etiket} acik={acik} sayi={sayi} onChange={onChange} />
        </div>
    );
}

type BosCipiProps = {
    /** Kolon etiketi — erişilebilir ad "<etiket> boş". */
    etiket: string;
    acik: boolean;
    /** §7.2 `bos_sayisi` rozeti; null → rozetsiz. */
    sayi?: number | null;
    onChange: (acik: boolean) => void;
};

/**
 * §7.1 madde 3 — tarih/sayı/metin kontrolünde girdinin sağındaki "Boş" toggle çipi (`aria-pressed`):
 * açık = `is_null`, girdiler kilitlenir (değerleri durumda kalır; kapatınca geri gelir). Rozet `bos_sayisi`.
 */
export function BosCipi({ etiket, acik, sayi = null, onChange }: BosCipiProps) {
    return (
        <button
            type="button"
            aria-pressed={acik}
            aria-label={`${etiket} boş`}
            title="Yalnız bu alanı boş olan kayıtlar"
            onClick={() => onChange(!acik)}
            className={[
                "inline-flex items-center gap-1 px-2 h-7 text-[11.5px] italic border rounded-[3px] transition-colors whitespace-nowrap",
                acik
                    ? "border-[var(--brand)] bg-[var(--brand-soft)] text-[var(--brand)]"
                    : "border-dashed border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] hover:text-[var(--fg)] hover:border-[var(--fg-muted)]",
                sayi === 0 ? "opacity-60" : "",
            ].join(" ")}
        >
            {BOS_ETIKETI}
            <SayiRozeti sayi={sayi} />
        </button>
    );
}
