import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send, Sparkles } from "lucide-react";
import type { AsistanEylemi, Katalog, RaporTanimi } from "@/lib/reports";
import {
    ASISTAN_KAPALI_MESAJI, AsistanFailedError, AsistanKapaliError, AsistanYetkiError,
    chatReport, ornekIstemler, sohbetGecmisi, type SohbetKaydi,
} from "@/lib/reportsChat";
import { FlowButton } from "@/components/flow/primitives";
import { AssistantThread } from "./AssistantThread";

type AssistantBarProps = {
    /** Anahtar henüz okunmadı (`null`) — iskelet; girdi yok, istek yok. */
    yukleniyor?: boolean;
    katalog: Katalog | null;
    /** Seçili veri kaynağı — örnek istem çipleri buna göre (`ornekIstemler`). */
    veriKaynagi: string;
    /** Oluşturucudaki geçerli tanım; geçersiz/boşken null gider (sunucu 422 yedirmemek için). */
    mevcutTanim: RaporTanimi | null;
    /** `/chat` 409 döndü — sayfa çubuğu kaldırır (anahtar bu oturumda kapatılmış). */
    onKapali: () => void;
    /**
     * Tanımı oluşturucuya koy (+ eylem varsa yürüt: önizle / indir). true = uygulandı
     * (kart "uygulandı" rozeti + "Geri al"); false = reddedildi (kaynak katalogda yok vb.).
     */
    onTanimUygula: (tanim: RaporTanimi, eylem: AsistanEylemi | null) => Promise<boolean> | boolean;
    /** Sayfada uygulamadan önceki taslak duruyor — son uygulanan balonda "Geri al" görünür. */
    geriAlinabilir: boolean;
    onGeriAl: () => void;
};

let kayitSayaci = 0;
const yeniKayitId = () => ++kayitSayaci;

export const ASISTAN_GIRDI_YER_TUTUCU = "Ne listelemek istiyorsunuz? Yazın, asistan raporu hazırlasın…";

/**
 * Rapor asistanı üst satırı (G143, plan §6.1): Rapor sekmesinin İLK öğesi — tam genişlik, marka
 * kenarlı kart; tek satır girdi (Enter gönderir), gönder düğmesi, seçili kaynağa göre örnek çipleri
 * (ilk tık girdiye yazar, aynı çipe ikinci tık gönderir), "veya aşağıdan seçin ↓" notu. Gönderince
 * konuşma alanı (`AssistantThread`) satırın altında açılır; "Kapat" alanı kapatır, geçmiş kalır (K6,
 * sayfa ömrü). Eski yan panel (`AssistantPanel`, G135) ve araç çubuğu düğmesi kalktı.
 *
 * Otomatik uygulama: `complete` + `tanim` → `onTanimUygula` düğme beklemeden (eylem olsun olmasın);
 * `tanim=null` + `eylem` (ör. "önizle") → oluşturucudaki tanımla eylem; `tanim=null` + eylem yok
 * (asistan soru sordu) → yalnız balon. İndirme daima sayfanın `/export` + `kaynak:"asistan"` yolu (K7).
 * Sohbet geçmişi yalnız bu bileşenin state'inde (K6): sunucu saklamaz, sayfa yenilenince sıfırlanır.
 */
export function AssistantBar({
    yukleniyor = false, katalog, veriKaynagi, mevcutTanim, onKapali, onTanimUygula, geriAlinabilir, onGeriAl,
}: AssistantBarProps) {
    const [kayitlar, setKayitlar] = useState<SohbetKaydi[]>([]);
    const [girdi, setGirdi] = useState("");
    const [gonderiliyor, setGonderiliyor] = useState(false);
    const [akisDurumu, setAkisDurumu] = useState<string | null>(null);
    const [acik, setAcik] = useState(false);
    // Son otomatik uygulanan asistan kaydı — "Geri al" yalnız bunda (tek adım).
    const [sonUygulananId, setSonUygulananId] = useState<number | null>(null);
    const girdiRef = useRef<HTMLInputElement>(null);
    const iptalRef = useRef<AbortController | null>(null);

    // Bileşen kalkarken (anahtar 409 / sayfa değişimi) süren isteği bırak.
    useEffect(() => () => {
        iptalRef.current?.abort();
        iptalRef.current = null;
    }, []);

    const kayitEkle = useCallback((k: SohbetKaydi) => {
        setKayitlar(prev => [...prev, k]);
    }, []);

    const gonder = useCallback(async (hamMetin?: string) => {
        const metin = (hamMetin ?? girdi).trim();
        if (!metin || gonderiliyor) return;

        const kullaniciKaydi: SohbetKaydi = { id: yeniKayitId(), rol: "user", icerik: metin };
        const gecmis = sohbetGecmisi([...kayitlar, kullaniciKaydi]);
        setKayitlar(prev => [...prev, kullaniciKaydi]);
        setGirdi("");
        setGonderiliyor(true);
        setAkisDurumu("Gönderiliyor…");
        setAcik(true);

        const controller = new AbortController();
        iptalRef.current = controller;
        try {
            const sonuc = await chatReport(gecmis, mevcutTanim, { onInfo: setAkisDurumu }, controller.signal);
            if (controller.signal.aborted) return;
            const kayit: SohbetKaydi = {
                id: yeniKayitId(),
                rol: "assistant",
                icerik: sonuc.cevap,
                tanim: sonuc.tanim,
                eylem: sonuc.eylem,
                uyarilar: sonuc.uyarilar,
            };
            // G143: geçerli tanım düğme beklemeden uygulanır; tanım yoksa eylem (ör. "önizle")
            // oluşturucudaki tanımla yürür; ikisi de yoksa asistan soru sormuştur — yalnız balon.
            const hedef = sonuc.tanim ?? (sonuc.eylem ? mevcutTanim : null);
            if (hedef) {
                setAkisDurumu(sonuc.tanim ? "Rapor uygulanıyor…" : "Eylem yürütülüyor…");
                const ok = await onTanimUygula(hedef, sonuc.eylem);
                if (sonuc.tanim) kayit.uygulandi = ok;
            }
            kayitEkle(kayit);
            if (kayit.uygulandi) setSonUygulananId(kayit.id);
        } catch (err) {
            if (controller.signal.aborted) return;
            if (err instanceof AsistanKapaliError) {
                // 409: anahtar kapalı — sayfa çubuğu kaldırır; kayıt yine düşer (bileşen kalırsa okunur).
                kayitEkle({ id: yeniKayitId(), rol: "assistant", icerik: "", hata: { ozet: ASISTAN_KAPALI_MESAJI, kod: "asistan_kapali" } });
                onKapali();
            } else if (err instanceof AsistanYetkiError) {
                kayitEkle({ id: yeniKayitId(), rol: "assistant", icerik: "", hata: { ozet: err.message, kod: "yetki_yok" } });
            } else if (err instanceof AsistanFailedError) {
                // Nihai başarısızlık: sözleşme gereği TEK okunur mesaj, etiketten kısa ipucu.
                kayitEkle({ id: yeniKayitId(), rol: "assistant", icerik: "", hata: { ozet: err.message, kod: err.kod } });
            } else {
                console.error(err);
                const mesaj = err instanceof Error ? err.message : "Asistan yanıt veremedi.";
                kayitEkle({ id: yeniKayitId(), rol: "assistant", icerik: "", hata: { ozet: mesaj, kod: "analysis_error" } });
            }
        } finally {
            if (iptalRef.current === controller) iptalRef.current = null;
            setGonderiliyor(false);
            setAkisDurumu(null);
        }
    }, [girdi, gonderiliyor, kayitlar, mevcutTanim, onTanimUygula, onKapali, kayitEkle]);

    /** Otomatik uygulama reddedilmişse (kaynak katalogda yok) balondaki düğmeyle yeniden dene. */
    const onUygula = async (kayit: SohbetKaydi) => {
        if (!kayit.tanim) return;
        const ok = await onTanimUygula(kayit.tanim, null);
        if (!ok) return;
        setKayitlar(prev => prev.map(k => (k.id === kayit.id ? { ...k, uygulandi: true } : k)));
        setSonUygulananId(kayit.id);
    };

    /** "Geri al": sayfa eski taslağı geri koyar; balon yeniden "Oluşturucuya uygula" düğmesine döner. */
    const geriAl = () => {
        onGeriAl();
        const id = sonUygulananId;
        if (id !== null) setKayitlar(prev => prev.map(k => (k.id === id ? { ...k, uygulandi: false } : k)));
        setSonUygulananId(null);
    };

    const onTus = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            e.preventDefault();
            void gonder();
        }
    };

    /** Çip: ilk tık girdiye yazar (odak girdiye), aynı çipe ikinci tık gönderir. */
    const ornekSec = (metin: string) => {
        if (girdi === metin) {
            void gonder(metin);
            return;
        }
        setGirdi(metin);
        girdiRef.current?.focus();
    };

    const temizle = () => {
        if (gonderiliyor) return;
        setKayitlar([]);
        setSonUygulananId(null);
    };

    if (yukleniyor) {
        return (
            <div
                data-testid="asistan-iskelet"
                aria-hidden="true"
                className="h-[104px] border border-[var(--border)] bg-[var(--bg-elevated)] animate-pulse"
            />
        );
    }

    const ornekler = ornekIstemler(veriKaynagi);
    const gonderilebilir = girdi.trim().length > 0 && !gonderiliyor;

    return (
        <div
            data-testid="asistan-satiri"
            className="min-w-0 border border-[var(--brand)] bg-[var(--bg-elevated)] rounded-none shadow-[0_8px_24px_-18px_rgba(109,36,52,0.45)]"
        >
            <div className="px-5 py-4 grid gap-3 bg-[var(--brand-soft)]">
                <div className="flex items-center gap-3">
                    <Sparkles className="w-5 h-5 text-[var(--brand)] shrink-0" aria-hidden="true" />
                    <input
                        ref={girdiRef}
                        type="text"
                        value={girdi}
                        onChange={e => setGirdi(e.target.value)}
                        onKeyDown={onTus}
                        disabled={gonderiliyor}
                        aria-label="Asistana mesaj"
                        placeholder={ASISTAN_GIRDI_YER_TUTUCU}
                        autoComplete="off"
                        className="flex-1 min-w-0 h-10 px-3 text-[14px] rounded-[4px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-60"
                    />
                    <FlowButton
                        variant="primary"
                        size="md"
                        onClick={() => void gonder()}
                        disabled={!gonderilebilir}
                        title={gonderiliyor ? "Asistan çalışıyor…" : "Gönder (Enter)"}
                        className="shrink-0"
                    >
                        {gonderiliyor ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                        Gönder
                    </FlowButton>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 pl-8">
                    <div className="flex flex-wrap items-center gap-1.5 min-w-0">
                        {ornekler.map(o => (
                            <button
                                key={o}
                                type="button"
                                onClick={() => ornekSec(o)}
                                disabled={gonderiliyor}
                                data-testid="ornek-istem"
                                title={girdi === o ? "Tekrar tıklayın: gönderir" : "Girdiye yaz"}
                                className={[
                                    "text-left text-[12px] px-2.5 py-1 rounded-full border transition-colors disabled:opacity-50",
                                    girdi === o
                                        ? "border-[var(--brand)] bg-[var(--brand)] text-white"
                                        : "border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--fg)]",
                                ].join(" ")}
                            >
                                {o}
                            </button>
                        ))}
                    </div>
                    <span className="text-[11px] text-[var(--fg-subtle)] shrink-0 ml-auto" data-testid="asistan-notu">
                        veya aşağıdan seçin ↓
                    </span>
                </div>
            </div>

            {acik && (
                <AssistantThread
                    kayitlar={kayitlar}
                    gonderiliyor={gonderiliyor}
                    akisDurumu={akisDurumu}
                    katalog={katalog}
                    onUygula={kayit => void onUygula(kayit)}
                    geriAlKaydiId={geriAlinabilir ? sonUygulananId : null}
                    onGeriAl={geriAl}
                    onTemizle={temizle}
                    onKapat={() => setAcik(false)}
                />
            )}
        </div>
    );
}
