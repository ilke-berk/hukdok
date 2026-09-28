import { Loader2, Mic, Square } from "lucide-react";
import { sureEtiketi, type VoiceInput } from "@/hooks/useVoiceInput";

type MicButtonProps = {
    ses: VoiceInput;
    /** Kayıt BAŞLATMAYI engeller (ör. yanıt akarken); süren kayıt yine durdurulabilir. */
    disabled?: boolean;
    /** Sohbet kutusunun İÇİNDE (`SohbetGirdisi`): kenarlıksız yuvarlak simge düğmesi. */
    gomulu?: boolean;
    className?: string;
};

/**
 * Sohbet kutusunun yanındaki mikrofon düğmesi (G217). Desteklenmeyen ortamda (`ses.destekleniyor=false`)
 * hiç çizilmez. Boşta mikrofon ikonu ("Sesle yaz"); kayıtta kırmızı + `0:12` sayacı + `aria-pressed`
 * ("Kaydı durdur"); izin beklenirken ve yazıya çevrilirken dönen gösterge ve pasif.
 */
export function MicButton({ ses, disabled = false, gomulu = false, className = "" }: MicButtonProps) {
    if (!ses.destekleniyor) return null;
    const { durum } = ses;
    const kayitta = durum === "kayitta";
    const mesgul = durum === "izin_isteniyor" || durum === "cevriliyor";
    const pasif = mesgul || (!kayitta && disabled);

    const etiket = kayitta
        ? "Kaydı durdur ve yazıya çevir"
        : durum === "cevriliyor"
            ? "Ses yazıya çevriliyor"
            : durum === "izin_isteniyor"
                ? "Mikrofon izni bekleniyor"
                : "Sesle yaz (mikrofon)";

    const tikla = () => {
        if (kayitta) ses.durdur();
        else if (!pasif) void ses.baslat();
    };

    return (
        <button
            type="button"
            onClick={tikla}
            disabled={pasif}
            aria-pressed={kayitta}
            aria-label={etiket}
            title={etiket}
            data-testid="mic-button"
            data-durum={durum}
            className={[
                "shrink-0 inline-flex items-center justify-center gap-1.5 border text-[12px] font-medium tabular-nums transition-colors disabled:opacity-50 disabled:cursor-not-allowed",
                gomulu ? "h-9 rounded-full" : "rounded-[3px]",
                kayitta
                    ? "px-2.5 border-tone-danger bg-tone-danger text-white"
                    : gomulu
                        ? "w-9 border-transparent bg-transparent text-[var(--fg-muted)] hover:bg-[var(--bg)] hover:text-[var(--fg)]"
                        : "w-10 border-[var(--border-strong)] bg-[var(--bg)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--fg)]",
                className,
            ].join(" ")}
        >
            {mesgul ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : kayitta ? (
                <>
                    <Square className="w-3 h-3 fill-current" aria-hidden="true" />
                    <span data-testid="mic-sayac">{sureEtiketi(ses.gecenSn)}</span>
                </>
            ) : (
                <Mic className="w-4 h-4" aria-hidden="true" />
            )}
        </button>
    );
}

/** Kutunun altındaki durum/uyarı satırı: "Yazıya çevriliyor…" ya da `ses.uyari`; ikisi de yoksa çizilmez. */
export function MicDurumSatiri({ ses, className = "" }: { ses: VoiceInput; className?: string }) {
    if (!ses.destekleniyor) return null;
    const metin = ses.durum === "cevriliyor" ? "Yazıya çevriliyor…" : ses.uyari;
    if (!metin) return null;
    // Hata (izin reddi, sunucu 503…) kırmızı; "Ses anlaşılamadı" ve "çevriliyor" bilgi tonunda.
    const uyariMi = ses.durum === "hata";
    return (
        <p
            role="status"
            data-testid="mic-durum"
            className={[
                "text-[12px]",
                uyariMi ? "text-tone-danger" : "text-[var(--fg-subtle)]",
                className,
            ].join(" ")}
        >
            {metin}
        </p>
    );
}
