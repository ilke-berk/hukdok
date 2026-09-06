// Raporlar sayfası ortak sınıf dizileri (G133) — redesign token'larıyla (tokens.css)
// hizalı; Radix Select yerine bilinçli native <select>: filtre satırında kompakt
// kalır ve jsdom testinde `change` olayıyla sürülebilir (CaseTrackingPanel deseni).
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
