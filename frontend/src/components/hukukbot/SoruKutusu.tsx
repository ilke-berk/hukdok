import { useState, type KeyboardEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";

type SoruKutusuProps = {
  /** Yanıt akarken kutu kilitlidir; gönder düğmesinin yerinde "Durdur" durur. */
  gonderiliyor: boolean;
  onGonder: (soru: string) => void;
  onDurdur: () => void;
};

/**
 * Giriş kutusu (G205): Enter gönderir, Shift+Enter yeni satır (IME birleştirmesi sırasında Enter
 * gönderMEZ); boş/yalnız boşluk soru gönderilmez; gönderim sürerken textarea kilitli.
 */
export function SoruKutusu({ gonderiliyor, onGonder, onDurdur }: SoruKutusuProps) {
  const [metin, setMetin] = useState("");
  const bos = metin.trim() === "";

  const gonder = () => {
    if (gonderiliyor || bos) return;
    onGonder(metin.trim());
    setMetin("");
  };

  const tus = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      gonder();
    }
  };

  return (
    <div className="border-t border-[var(--border)] bg-[var(--bg-elevated)] p-3">
      <div className="flex items-end gap-2">
        <textarea
          aria-label="Hukukbot'a soru"
          data-testid="hukukbot-soru"
          rows={2}
          value={metin}
          disabled={gonderiliyor}
          onChange={(e) => setMetin(e.target.value)}
          onKeyDown={tus}
          placeholder={gonderiliyor ? "Yanıt bekleniyor..." : "Sorunuzu yazın (Enter gönderir, Shift+Enter yeni satır)"}
          className="flex-1 min-w-0 resize-none max-h-40 min-h-[44px] px-3 py-2.5 bg-[var(--bg)] border border-[var(--border)] rounded-[3px] text-[13.5px] leading-[1.5] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-60 disabled:cursor-not-allowed"
        />
        {gonderiliyor ? (
          <button
            type="button"
            onClick={onDurdur}
            className="h-11 shrink-0 inline-flex items-center gap-2 px-3.5 rounded-[3px] border border-[var(--border-strong)] bg-[var(--bg)] text-[13px] font-medium text-[var(--fg)] hover:border-tone-danger hover:text-tone-danger transition-colors"
          >
            <Square className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
            Durdur
          </button>
        ) : (
          <button
            type="button"
            onClick={gonder}
            disabled={bos}
            aria-label="Gönder"
            className="h-11 shrink-0 inline-flex items-center gap-2 px-3.5 rounded-[3px] border border-[var(--brand)] bg-brand-solid text-white text-[13px] font-medium hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <SendHorizontal className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Gönder</span>
          </button>
        )}
      </div>
    </div>
  );
}
