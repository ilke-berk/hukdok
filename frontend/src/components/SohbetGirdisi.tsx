import { useLayoutEffect, useRef, type KeyboardEvent, type MutableRefObject, type ReactNode } from "react";
import { ArrowUp, Loader2, Square } from "lucide-react";
import { MicButton, MicDurumSatiri } from "@/components/MicButton";
import type { VoiceInput } from "@/hooks/useVoiceInput";

type SohbetGirdisiProps = {
    value: string;
    onChange: (metin: string) => void;
    /** Enter ya da gönder düğmesi; boş/yalnız boşluk metinde çağrılmaz. */
    onGonder: () => void;
    /** Yanıt beklenirken kutu kilitli; `onDurdur` varsa gönder yerine "Durdur", yoksa dönen gösterge. */
    gonderiliyor: boolean;
    onDurdur?: () => void;
    ses: VoiceInput;
    ariaLabel: string;
    placeholder: string;
    testId?: string;
    textareaRef?: MutableRefObject<HTMLTextAreaElement | null>;
    /** Kutunun büyüyebileceği en fazla satır; aşınca kutu kendi içinde kayar. */
    azamiSatir?: number;
    /** Kutunun altında, sağda ek not (ör. "veya aşağıdan seçin ↓"). */
    not?: ReactNode;
    autoFocus?: boolean;
};

const SATIR_PX = 21;   // text-[14px] leading-[1.5]

/**
 * Ortak sohbet yazı kutusu (Hukukbot `SoruKutusu` + rapor `AssistantBar`): tek yuvarlatılmış kap, içinde
 * kendiliğinden büyüyen metin alanı (1 satırdan `azamiSatir`'a), mikrofon ve gönder simgeleri. Enter gönderir,
 * Shift+Enter yeni satır, IME birleştirmesi sırasında Enter göndermez. Metin durumu çağıranda (kontrollü).
 */
export function SohbetGirdisi({
    value, onChange, onGonder, gonderiliyor, onDurdur, ses, ariaLabel, placeholder, testId, textareaRef,
    azamiSatir = 8, not, autoFocus,
}: SohbetGirdisiProps) {
    const icRef = useRef<HTMLTextAreaElement | null>(null);
    const bos = value.trim() === "";

    // Yükseklik içeriğe göre: önce sıfırla, sonra scrollHeight'a (tavan azamiSatir) çek.
    useLayoutEffect(() => {
        const el = icRef.current;
        if (!el) return;
        const tavan = azamiSatir * SATIR_PX + 16;
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, tavan)}px`;
        el.style.overflowY = el.scrollHeight > tavan ? "auto" : "hidden";
    }, [value, azamiSatir]);

    const gonder = () => {
        if (gonderiliyor || bos) return;
        onGonder();
    };

    const tus = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            gonder();
        }
    };

    const refBagla = (el: HTMLTextAreaElement | null) => {
        icRef.current = el;
        if (textareaRef) textareaRef.current = el;
    };

    return (
        <div className="min-w-0">
            <div className="flex items-end gap-1 pl-3.5 pr-1.5 py-1.5 rounded-[14px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] shadow-[0_2px_10px_-6px_rgba(0,0,0,0.25)] transition-colors focus-within:border-[var(--brand)]">
                <textarea
                    ref={refBagla}
                    rows={1}
                    value={value}
                    disabled={gonderiliyor}
                    onChange={e => onChange(e.target.value)}
                    onKeyDown={tus}
                    aria-label={ariaLabel}
                    data-testid={testId}
                    placeholder={placeholder}
                    autoComplete="off"
                    autoFocus={autoFocus}
                    className="flex-1 min-w-0 resize-none self-center py-2 bg-transparent text-[14px] leading-[1.5] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:outline-none disabled:opacity-60 disabled:cursor-not-allowed"
                />
                <MicButton ses={ses} disabled={gonderiliyor} gomulu />
                {gonderiliyor && onDurdur ? (
                    <button
                        type="button"
                        onClick={onDurdur}
                        aria-label="Durdur"
                        title="Yanıtı durdur"
                        className="w-9 h-9 shrink-0 grid place-items-center rounded-full border border-[var(--border-strong)] bg-[var(--bg)] text-[var(--fg)] hover:border-tone-danger hover:text-tone-danger transition-colors"
                    >
                        <Square className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
                        <span className="sr-only">Durdur</span>
                    </button>
                ) : (
                    <button
                        type="button"
                        onClick={gonder}
                        disabled={bos || gonderiliyor}
                        aria-label="Gönder"
                        title={gonderiliyor ? "Yanıt bekleniyor…" : "Gönder (Enter)"}
                        className="w-9 h-9 shrink-0 grid place-items-center rounded-full bg-brand-solid text-white hover:opacity-90 transition-opacity disabled:opacity-35 disabled:cursor-not-allowed"
                    >
                        {gonderiliyor
                            ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                            : <ArrowUp className="w-4 h-4" strokeWidth={2.2} aria-hidden="true" />}
                        <span className="sr-only">Gönder</span>
                    </button>
                )}
            </div>
            <div className="mt-1.5 px-1 flex flex-wrap items-start justify-between gap-x-3 gap-y-1 min-h-[16px]">
                <MicDurumSatiri ses={ses} />
                <span className="ml-auto text-[11px] text-[var(--fg-subtle)]">
                    {not ?? "Enter gönderir · Shift+Enter yeni satır"}
                </span>
            </div>
        </div>
    );
}
