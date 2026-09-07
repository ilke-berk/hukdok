import { useEffect, useState } from "react";
import { Loader2, Star, X } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import { INPUT_CLS } from "./ui";

/** Şablon adı tavanı — SaveTemplateDialog ile aynı (plan §2.5). */
const AD_MAX = 120;

type FavoritePromptProps = {
    /** Önerilen ad (`sablonAdiOner`); girdi bununla açılır, değişince yeniden yazılır. */
    onerilenAd: string;
    /** "Ekle" / Enter — üst bileşen `createTemplate` çağırır; hata toast'ı da onundur (kart açık kalır). */
    onEkle: (ad: string) => Promise<void>;
    /** "Şimdi değil" — bu tanım için sayfa ömründe bir daha sorulmaz. */
    onSimdiDegil: () => void;
    /** × — "Şimdi değil" ile aynı sonuç (kapatma da ret sayılır). */
    onKapat: () => void;
    /** Kaydetme sürüyor: girdi + düğmeler kilitli. */
    kaydediliyor: boolean;
};

/**
 * Favori (şablon) önerisi kartı (G144, plan §6.2): araç çubuğunun altında TEK satır —
 * yıldız + "Bu formatı favorilere [ad] adıyla ekleyeyim mi?" + Ekle + Şimdi değil + ×.
 * Enter = Ekle; ad boşsa Ekle kapalı. Kaydetme başarısında üst bileşen kartı kapatır.
 */
export function FavoritePrompt({ onerilenAd, onEkle, onSimdiDegil, onKapat, kaydediliyor }: FavoritePromptProps) {
    const [ad, setAd] = useState(onerilenAd);
    // Başka bir tanım için açılınca (öneri değişince) girdi yeni öneriyle başlar.
    useEffect(() => {
        setAd(onerilenAd);
    }, [onerilenAd]);

    const adTemiz = ad.trim();
    const gecerli = adTemiz.length > 0 && adTemiz.length <= AD_MAX;

    const ekle = () => {
        if (!gecerli || kaydediliyor) return;
        void onEkle(adTemiz);
    };

    return (
        <form
            data-testid="favori-onerisi"
            className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-2.5 border-b border-[var(--brand)]/30 bg-[var(--brand-soft)] text-[12.5px] text-[var(--fg)]"
            onSubmit={e => { e.preventDefault(); ekle(); }}
        >
            <Star className="w-4 h-4 shrink-0 text-[var(--brand)]" aria-hidden="true" />
            <label htmlFor="favori-ad" className="shrink-0">Bu formatı favorilere</label>
            <input
                id="favori-ad"
                aria-label="Favori adı"
                className={`${INPUT_CLS} w-auto min-w-[220px] max-w-[420px] flex-1 h-7`}
                value={ad}
                maxLength={AD_MAX}
                disabled={kaydediliyor}
                onChange={e => setAd(e.target.value)}
                onKeyDown={e => {
                    if (e.key === "Enter") {
                        e.preventDefault();
                        ekle();
                    }
                }}
            />
            <span className="shrink-0">adıyla ekleyeyim mi?</span>
            <div className="flex items-center gap-1.5 ml-auto">
                <FlowButton type="submit" variant="primary" size="sm" disabled={!gecerli || kaydediliyor} title="Şablon olarak kaydet (Enter)">
                    {kaydediliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Star className="w-3.5 h-3.5" />}
                    Ekle
                </FlowButton>
                <FlowButton variant="ghost" size="sm" disabled={kaydediliyor} onClick={onSimdiDegil} title="Bu format için bir daha sorulmaz">
                    Şimdi değil
                </FlowButton>
                <button
                    type="button"
                    className="w-6 h-6 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--fg)] disabled:opacity-30"
                    aria-label="Öneriyi kapat"
                    disabled={kaydediliyor}
                    onClick={onKapat}
                >
                    <X className="w-3.5 h-3.5" />
                </button>
            </div>
        </form>
    );
}
