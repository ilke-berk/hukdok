import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send, Sparkles, Trash2, X } from "lucide-react";
import type { AsistanEylemi, Katalog, RaporTanimi } from "@/lib/reports";
import {
    ASISTAN_KAPALI_MESAJI, ORNEK_ISTEMLER, AsistanFailedError, AsistanKapaliError, AsistanYetkiError,
    chatReport, sohbetGecmisi, type SohbetKaydi,
} from "@/lib/reportsChat";
import { Textarea } from "@/components/ui/textarea";
import { FlowButton } from "@/components/flow/primitives";
import { AssistantMessage } from "./AssistantMessage";

type AssistantPanelProps = {
    acik: boolean;
    onKapat: () => void;
    katalog: Katalog | null;
    /** Oluşturucudaki geçerli tanım; geçersiz/boşken null gider (sunucu 422 yedirmemek için). */
    mevcutTanim: RaporTanimi | null;
    /** 409 görüldü (anahtar kapalı) — şerit + girdi kilitli. */
    kapali: boolean;
    /** `/chat` 409 döndü — sayfa düğmeyi pasifleştirir. */
    onKapali: () => void;
    /**
     * Tanımı oluşturucuya koy (+ eylem varsa yürüt: önizle / indir). true = uygulandı
     * (kart "uygulandı" rozetine döner); false = reddedildi (kaynak katalogda yok vb.).
     */
    onTanimUygula: (tanim: RaporTanimi, eylem: AsistanEylemi | null) => Promise<boolean> | boolean;
};

let kayitSayaci = 0;
const yeniKayitId = () => ++kayitSayaci;

/**
 * Rapor asistanı yan paneli (G135): mesaj listesi + akış durumu satırı + girdi. Sohbet geçmişi
 * yalnız bileşen state'inde (K6 — sayfa yenilenince sıfırlanır, bilinçli). Asistanın ürettiği
 * `tanim` "Oluşturucuya uygula" ile sol sütuna geçer; `eylem` doluysa uygulama otomatiktir ve
 * eylem `onTanimUygula` üzerinden yürütülür (indirme daima `/export` + `kaynak:"asistan"`, K7).
 * Panel `Sheet` yerine sabit sağ `aside`: modal değildir — kullanıcı oluşturucuyu görmeye devam eder.
 */
export function AssistantPanel({ acik, onKapat, katalog, mevcutTanim, kapali, onKapali, onTanimUygula }: AssistantPanelProps) {
    const [kayitlar, setKayitlar] = useState<SohbetKaydi[]>([]);
    const [girdi, setGirdi] = useState("");
    const [gonderiliyor, setGonderiliyor] = useState(false);
    const [akisDurumu, setAkisDurumu] = useState<string | null>(null);
    const listeRef = useRef<HTMLDivElement>(null);
    const girdiRef = useRef<HTMLTextAreaElement>(null);
    const iptalRef = useRef<AbortController | null>(null);

    // Yeni kayıt/akış satırı gelince listeyi dibe kaydır.
    useEffect(() => {
        const el = listeRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [kayitlar, akisDurumu]);

    // Panel kapanırken süren isteği bırak (cevap kapalı panele düşmesin).
    useEffect(() => {
        if (acik) return;
        iptalRef.current?.abort();
        iptalRef.current = null;
    }, [acik]);

    const kayitEkle = useCallback((k: Omit<SohbetKaydi, "id">) => {
        setKayitlar(prev => [...prev, { ...k, id: yeniKayitId() }]);
    }, []);

    const gonder = useCallback(async () => {
        const metin = girdi.trim();
        if (!metin || gonderiliyor || kapali) return;

        const kullaniciKaydi: SohbetKaydi = { id: yeniKayitId(), rol: "user", icerik: metin };
        const gecmis = sohbetGecmisi([...kayitlar, kullaniciKaydi]);
        setKayitlar(prev => [...prev, kullaniciKaydi]);
        setGirdi("");
        setGonderiliyor(true);
        setAkisDurumu("Gönderiliyor…");

        const controller = new AbortController();
        iptalRef.current = controller;
        try {
            const sonuc = await chatReport(gecmis, mevcutTanim, { onInfo: setAkisDurumu }, controller.signal);
            if (controller.signal.aborted) return;
            const kayit: Omit<SohbetKaydi, "id"> = {
                rol: "assistant",
                icerik: sonuc.cevap,
                tanim: sonuc.tanim,
                eylem: sonuc.eylem,
                uyarilar: sonuc.uyarilar,
            };
            if (sonuc.eylem) {
                // K7: eylem doluysa tanım otomatik uygulanır ve eylem yürütülür; tanım yoksa
                // (ör. "önizle" — mevcut tanımı kastediyor) oluşturucudaki tanımla yürür.
                const hedef = sonuc.tanim ?? mevcutTanim;
                if (hedef) {
                    setAkisDurumu("Eylem yürütülüyor…");
                    const ok = await onTanimUygula(hedef, sonuc.eylem);
                    if (sonuc.tanim) kayit.uygulandi = ok;
                }
            }
            kayitEkle(kayit);
        } catch (err) {
            if (controller.signal.aborted) return;
            if (err instanceof AsistanKapaliError) {
                onKapali();
                kayitEkle({ rol: "assistant", icerik: "", hata: { ozet: ASISTAN_KAPALI_MESAJI, kod: "asistan_kapali" } });
            } else if (err instanceof AsistanYetkiError) {
                kayitEkle({ rol: "assistant", icerik: "", hata: { ozet: err.message, kod: "yetki_yok" } });
            } else if (err instanceof AsistanFailedError) {
                // Nihai başarısızlık: sözleşme gereği TEK okunur mesaj, etiketten kısa ipucu.
                kayitEkle({ rol: "assistant", icerik: "", hata: { ozet: err.message, kod: err.kod } });
            } else {
                console.error(err);
                const mesaj = err instanceof Error ? err.message : "Asistan yanıt veremedi.";
                kayitEkle({ rol: "assistant", icerik: "", hata: { ozet: mesaj, kod: "analysis_error" } });
            }
        } finally {
            if (iptalRef.current === controller) iptalRef.current = null;
            setGonderiliyor(false);
            setAkisDurumu(null);
        }
    }, [girdi, gonderiliyor, kapali, kayitlar, mevcutTanim, onTanimUygula, onKapali, kayitEkle]);

    const onUygula = async (kayit: SohbetKaydi) => {
        if (!kayit.tanim) return;
        const ok = await onTanimUygula(kayit.tanim, null);
        if (ok) setKayitlar(prev => prev.map(k => (k.id === kayit.id ? { ...k, uygulandi: true } : k)));
    };

    const onTus = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        // Enter gönderir; Shift+Enter satır ekler.
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void gonder();
        }
    };

    const ornekSec = (metin: string) => {
        setGirdi(metin);
        girdiRef.current?.focus();
    };

    const temizle = () => {
        if (gonderiliyor) return;
        setKayitlar([]);
    };

    if (!acik) return null;

    const girdiKilitli = gonderiliyor || kapali;

    return (
        <aside
            role="complementary"
            aria-label="Rapor asistanı"
            data-testid="asistan-paneli"
            className="fixed inset-y-0 right-0 z-40 w-full sm:w-[420px] flex flex-col bg-[var(--bg-elevated)] border-l border-[var(--border)] shadow-[-12px_0_32px_-20px_rgba(0,0,0,0.35)]"
        >
            <header className="flex items-center justify-between gap-2 px-4 py-3 border-b border-[var(--border)]">
                <div className="flex items-center gap-2 min-w-0">
                    <Sparkles className="w-4 h-4 text-[var(--brand)] shrink-0" />
                    <div className="min-w-0">
                        <h2 className="font-display text-[15px] text-[var(--fg)] font-medium leading-tight">Rapor asistanı</h2>
                        <p className="text-[11px] text-[var(--fg-subtle)] truncate">
                            İstediğiniz raporu yazın; tanımı oluşturucuya uygulayın.
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                    <button
                        type="button"
                        onClick={temizle}
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
                        aria-label="Asistanı kapat"
                        title="Kapat"
                        className="w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--fg)] hover:bg-[var(--bg)] transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>
            </header>

            {kapali && (
                <div role="alert" data-testid="asistan-kapali-seridi" className="px-4 py-2 text-[12px] border-b border-amber-300 bg-amber-50 text-amber-900">
                    {ASISTAN_KAPALI_MESAJI}
                </div>
            )}

            <div ref={listeRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-4 grid content-start gap-3" aria-live="polite">
                {kayitlar.length === 0 && !gonderiliyor && (
                    <div className="grid gap-3" data-testid="asistan-bos">
                        <p className="text-[13px] text-[var(--fg-muted)]">
                            Rapor isteğinizi doğal dille yazın. Asistan veri kaynağı, kolon ve filtreleri seçer;
                            veri görmez — indirme ve önizleme her zaman sizin onayınızla, mevcut yollardan yapılır.
                        </p>
                        <div className="grid gap-1.5">
                            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">Örnek istemler</span>
                            {ORNEK_ISTEMLER.map(o => (
                                <button
                                    key={o}
                                    type="button"
                                    onClick={() => ornekSec(o)}
                                    data-testid="ornek-istem"
                                    className="text-left text-[12px] px-3 py-2 rounded-[4px] border border-[var(--border)] bg-[var(--bg)] text-[var(--fg)] hover:border-[var(--brand)] transition-colors"
                                >
                                    {o}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {kayitlar.map(k => (
                    <AssistantMessage key={k.id} kayit={k} katalog={katalog} onUygula={kayit => void onUygula(kayit)} />
                ))}

                {gonderiliyor && (
                    <div data-testid="akis-durumu" className="flex items-center gap-2 text-[12px] text-[var(--fg-muted)]">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>{akisDurumu ?? "Yanıt bekleniyor…"}</span>
                    </div>
                )}
            </div>

            <footer className="border-t border-[var(--border)] px-4 py-3 grid gap-2">
                <Textarea
                    ref={girdiRef}
                    value={girdi}
                    onChange={e => setGirdi(e.target.value)}
                    onKeyDown={onTus}
                    disabled={girdiKilitli}
                    aria-label="Asistana mesaj"
                    placeholder={kapali ? "Asistan kapalı" : "Örn. Derdest davaları ofis no ve konu ile listele… (Enter gönderir)"}
                    rows={3}
                    className="min-h-[72px] text-[13px] rounded-[4px] border-[var(--border)] bg-[var(--bg)] text-[var(--fg)] resize-none"
                />
                <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] text-[var(--fg-subtle)]">Enter gönderir · Shift+Enter satır</span>
                    <FlowButton
                        variant="primary"
                        size="sm"
                        onClick={() => void gonder()}
                        disabled={girdiKilitli || !girdi.trim()}
                        title={kapali ? ASISTAN_KAPALI_MESAJI : "Gönder"}
                    >
                        {gonderiliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                        Gönder
                    </FlowButton>
                </div>
            </footer>
        </aside>
    );
}
