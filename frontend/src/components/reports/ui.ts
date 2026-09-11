// Raporlar sayfası ortak sınıf dizileri (G133) — redesign token'larıyla (tokens.css)
// hizalı; Radix Select yerine bilinçli native <select>: filtre satırında kompakt
// kalır ve jsdom testinde `change` olayıyla sürülebilir (CaseTrackingPanel deseni).
// G138: şerit açılırları (çoklu seçim, combobox, alan seçici, çip menüsü) portal'sız,
// yerinde `absolute` paneldir — jsdom'da `container` içinde kalır; kapanış bu kancayla.
import { useEffect, useRef } from "react";

/** `acik` iken dışarı tıklama ya da Escape → `kapat`. Dönen ref panel köküne verilir. */
export function useDisariTiklama<T extends HTMLElement>(acik: boolean, kapat: () => void) {
    const ref = useRef<T>(null);
    useEffect(() => {
        if (!acik) return;
        const tik = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) kapat();
        };
        const tus = (e: KeyboardEvent) => {
            if (e.key === "Escape") kapat();
        };
        document.addEventListener("mousedown", tik);
        document.addEventListener("keydown", tus);
        return () => {
            document.removeEventListener("mousedown", tik);
            document.removeEventListener("keydown", tus);
        };
    }, [acik, kapat]);
    return ref;
}

export const INPUT_CLS =
    "w-full h-8 px-2.5 text-[12px] rounded-[3px] border border-[var(--border)] bg-[var(--bg)] text-[var(--fg)] " +
    "placeholder:text-[var(--fg-subtle)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-50";

export const SELECT_CLS = INPUT_CLS + " cursor-pointer";

export const ICON_BTN_CLS =
    "w-6 h-6 grid place-items-center rounded-[3px] border border-transparent text-[var(--fg-subtle)] " +
    "hover:text-[var(--fg)] hover:border-[var(--border)] disabled:opacity-30 disabled:hover:border-transparent " +
    "disabled:hover:text-[var(--fg-subtle)] disabled:cursor-not-allowed transition-colors";

export const LINK_BTN_CLS =
    "font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] " +
    "transition-colors disabled:opacity-40 disabled:hover:text-[var(--fg-subtle)] disabled:cursor-not-allowed";

// ---------------------------------------------------------------------------
// G173 — tanım şeridinde kaynak rengi: ana kaynak + her bağlı ilişki (G166 `bag`) ayrı renk çubuğu.
// Tema token'larıyla (tokens.css); ilişki sayısı paleti aşarsa döner. Renkler yalnız AYIRT EDİCİ
// ipucudur — anlam metinde ("<İlişki> · <Kolon>") de taşınır, renge bağımlı bilgi yok.
// ---------------------------------------------------------------------------

/** Ana kaynağın çubuk rengi (CSS değeri). */
export const ANA_KAYNAK_RENGI = "var(--brand)";

/** Bağlı ilişkiler için sırayla dağıtılan çubuk renkleri (ana kaynaktan ayrık; tema token'ı + sabit ton). */
export const BAG_RENKLERI: readonly string[] = [
    "var(--fg-muted)",
    "var(--burgundy-400)",
    "var(--border-strong)",
    "var(--fg-subtle)",
];

/**
 * İlişki anahtarı → çubuk rengi. `iliskiAnahtarlari` kaynağın `iliskiler` sırasıdır (katalogdan, sabit);
 * `bag` boşsa ana kaynak rengi; listede olmayan (eski katalog) ilk bağ rengini alır.
 */
export function kaynakRengi(bag: string | null | undefined, iliskiAnahtarlari: readonly string[]): string {
    if (!bag) return ANA_KAYNAK_RENGI;
    const i = iliskiAnahtarlari.indexOf(bag);
    return BAG_RENKLERI[(i < 0 ? 0 : i) % BAG_RENKLERI.length];
}
