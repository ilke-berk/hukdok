import { useEffect, useRef } from "react";
import { Loader2, Trash2, X } from "lucide-react";
import type { Katalog, KatalogKolon } from "@/lib/reports";
import type { DegerSorunu, SohbetKaydi } from "@/lib/reportsChat";
import { AssistantMessage, type IndirmeFormati } from "./AssistantMessage";

type AssistantThreadProps = {
    kayitlar: SohbetKaydi[];
    gonderiliyor: boolean;
    /** `info` olayı — canlı akış durumu satırı (gönderim sürerken). */
    akisDurumu: string | null;
    katalog: Katalog | null;
    /** "Onayla ve uygula" (bekleyen kart: uygulama reddedilmiş / geri alınmış). */
    onOnayla: (kayit: SohbetKaydi) => void;
    /** "Excel indir" / "CSV indir" — kartın tanımıyla doğrudan indirme. */
    onIndir: (kayit: SohbetKaydi, format: IndirmeFormati) => void;
    /** "Geri al" bağlantısı yalnız bu kayıtta görünür (son uygulama, tek adım); null = yok. */
    geriAlKaydiId: number | null;
    onGeriAl: () => void;
    onTemizle: () => void;
    /** Alanı kapatır — geçmiş kalır (K6: sayfa ömrü boyunca), çubuk yerinde durur. */
    onKapat: () => void;
    /** G174: sorunlu değer kartı — aday çipi / "Yine de uygula". */
    onAdaySec: (kayit: SohbetKaydi, sorun: DegerSorunu, aday: string) => void;
    onYineDeUygula: (kayit: SohbetKaydi) => void;
    /** G174: liste balonu değer tıkı / "Hangisi?" kolon çipi. */
    onListeSec: (kolon: KatalogKolon, deger: string) => void;
    onKolonSec: (kayit: SohbetKaydi, kolon: KatalogKolon) => void;
};

/**
 * Inline konuşma alanı (G143): AssistantBar'ın altında açılır — eski yan panelin (`AssistantPanel`,
 * G135) mesaj listesi/akış durumu buraya taşındı; mantık `reportsChat.ts` ve AssistantBar'da.
 * Kullanıcı/asistan balonları `AssistantMessage`; `warning` sarı şerit, `failed` kırmızı kutu +
 * `error_kod` ipucu balonun içinde. Modal değildir: kullanıcı kartları/şeridi/önizlemeyi görmeye
 * devam eder. Sohbet geçmişi yalnız bileşen state'inde (üst bileşen), sayfa yenilenince sıfırlanır.
 */
export function AssistantThread({
    kayitlar, gonderiliyor, akisDurumu, katalog, onOnayla, onIndir, geriAlKaydiId, onGeriAl, onTemizle, onKapat,
    onAdaySec, onYineDeUygula, onListeSec, onKolonSec,
}: AssistantThreadProps) {
    const listeRef = useRef<HTMLDivElement>(null);

    // Yeni kayıt/akış satırı gelince listeyi dibe kaydır.
    useEffect(() => {
        const el = listeRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [kayitlar, akisDurumu]);

    return (
        <section
            role="region"
            aria-label="Rapor asistanı konuşması"
            data-testid="asistan-konusmasi"
            className="border-t border-[var(--border)] bg-[var(--bg-elevated)]"
        >
            <div className="flex items-center justify-between gap-2 px-4 py-2">
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">Konuşma</span>
                <div className="flex items-center gap-1">
                    <button
                        type="button"
                        onClick={onTemizle}
                        disabled={kayitlar.length === 0 || gonderiliyor}
                        aria-label="Sohbeti temizle"
                        title="Sohbeti temizle"
                        className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--fg)] hover:bg-[var(--bg)] disabled:opacity-30 disabled:hover:bg-transparent transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                    <button
                        type="button"
                        onClick={onKapat}
                        aria-label="Konuşmayı kapat"
                        title="Kapat (geçmiş kalır)"
                        className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--fg)] hover:bg-[var(--bg)] transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div
                ref={listeRef}
                className="max-h-[420px] overflow-y-auto px-4 pb-4 grid content-start gap-3"
                aria-live="polite"
            >
                {kayitlar.length === 0 && !gonderiliyor && (
                    <p data-testid="asistan-bos" className="text-[13px] text-[var(--fg-muted)]">
                        Henüz mesaj yok. Yukarıya isteğinizi yazın; asistan tanımı hazırlayıp uygular, yanlışsa yazarak düzeltir ya da geri alırsınız.
                    </p>
                )}

                {kayitlar.map(k => (
                    <AssistantMessage
                        key={k.id}
                        kayit={k}
                        katalog={katalog}
                        onOnayla={onOnayla}
                        onIndir={onIndir}
                        onGeriAl={k.id === geriAlKaydiId ? onGeriAl : undefined}
                        onAdaySec={onAdaySec}
                        onYineDeUygula={onYineDeUygula}
                        onListeSec={onListeSec}
                        onKolonSec={onKolonSec}
                    />
                ))}

                {gonderiliyor && (
                    <div data-testid="akis-durumu" className="flex items-center gap-2 text-[12px] text-[var(--fg-muted)]">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>{akisDurumu ?? "Yanıt bekleniyor…"}</span>
                    </div>
                )}
            </div>
        </section>
    );
}
