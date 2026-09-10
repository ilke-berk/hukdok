import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send } from "lucide-react";
import type { AsistanEylemi, Katalog, RaporTanimi } from "@/lib/reports";
import {
    ASISTAN_KAPALI_MESAJI, AsistanFailedError, AsistanKapaliError, AsistanYetkiError,
    chatReport, ornekIstemler, sohbetGecmisi, tanimAyni, type SohbetKaydi,
} from "@/lib/reportsChat";
import { FlowButton } from "@/components/flow/primitives";
import { AssistantThread } from "./AssistantThread";
import type { IndirmeFormati } from "./AssistantMessage";

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
 * sayfa ömrü). Sohbet geçmişi yalnız bu bileşenin state'inde (K6): sunucu saklamaz, sayfa yenilenince sıfırlanır.
 *
 * G167 — TEYİT DÖNGÜSÜ (G143'ün otomatik uygulaması kalktı): `complete` + `tanim` → tanım UYGULANMAZ,
 * teyit kartı çıkar ve `bekleyenTanim` olur; sonraki mesajlar sunucuya `mevcut_tanim` olarak BEKLEYEN tanımı
 * taşır (kullanıcı "telefonu da ekle" derse asistan onu günceller, oluşturucudakini değil). Onay üç yolla:
 * (a) kartta "Onayla ve uygula" → `onTanimUygula(tanim, null)`; (b) kartta "Excel/CSV indir" →
 * `onTanimUygula(tanim, indir_*)` (uygulanır + indirilir, K7 tek log yolu); (c) SÖZLE — kullanıcı "tamam /
 * uygula / indir" yazar, asistan bekleyen tanımı AYNEN (`tanimAyni`) + eylemle döndürürse eylem hemen yürür.
 * `tanim=null` + eylem → bekleyen (yoksa oluşturucudaki) tanımla eylem; `tanim=null` + eylem yok → soru, yalnız balon.
 * İndirme daima sayfanın `/export` + `kaynak:"asistan"` yolu (K7).
 */
export function AssistantBar({
    yukleniyor = false, katalog, veriKaynagi, mevcutTanim, onKapali, onTanimUygula, geriAlinabilir, onGeriAl,
}: AssistantBarProps) {
    const [kayitlar, setKayitlar] = useState<SohbetKaydi[]>([]);
    const [girdi, setGirdi] = useState("");
    const [gonderiliyor, setGonderiliyor] = useState(false);
    const [akisDurumu, setAkisDurumu] = useState<string | null>(null);
    const [acik, setAcik] = useState(false);
    // Son uygulanan asistan kaydı — "Geri al" yalnız bunda (tek adım).
    const [sonUygulananId, setSonUygulananId] = useState<number | null>(null);
    // G167: teyit bekleyen (henüz uygulanmamış) son asistan tanımı — düzeltmeler bunun üzerinde çalışır.
    const [bekleyenTanim, setBekleyenTanim] = useState<RaporTanimi | null>(null);
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

    /** Uygulama sonrası ortak muhasebe: kayıt rozeti, Geri al kimliği, bekleyen tanımın düşmesi. */
    const uygulandiIsaretle = useCallback((kayitId: number, tanim: RaporTanimi) => {
        setKayitlar(prev => prev.map(k => (k.id === kayitId ? { ...k, uygulandi: true } : k)));
        setSonUygulananId(kayitId);
        setBekleyenTanim(prev => (tanimAyni(prev, tanim) ? null : prev));
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
            // Düzeltmeler teyit bekleyen tanım üzerinde: sunucuya "mevcut tanım" olarak o gider.
            const sonuc = await chatReport(gecmis, bekleyenTanim ?? mevcutTanim, { onInfo: setAkisDurumu }, controller.signal);
            if (controller.signal.aborted) return;
            const kayit: SohbetKaydi = {
                id: yeniKayitId(),
                rol: "assistant",
                icerik: sonuc.cevap,
                tanim: sonuc.tanim,
                eylem: sonuc.eylem,
                uyarilar: sonuc.uyarilar,
            };
            if (sonuc.tanim) {
                if (sonuc.eylem && tanimAyni(sonuc.tanim, bekleyenTanim)) {
                    // Sözle onay: bekleyen tanım aynen + eylemle döndü → eylem hemen yürür.
                    setAkisDurumu(sonuc.eylem === "onizle" ? "Rapor uygulanıyor…" : "İndiriliyor…");
                    kayit.uygulandi = await onTanimUygula(sonuc.tanim, sonuc.eylem);
                    kayitEkle(kayit);
                    if (kayit.uygulandi) uygulandiIsaretle(kayit.id, sonuc.tanim);
                    return;
                }
                // Yeni/değişmiş tanım: teyit kartı, uygulama YOK (G167)
                kayit.uygulandi = false;
                kayitEkle(kayit);
                setBekleyenTanim(sonuc.tanim);
                return;
            }
            if (sonuc.eylem) {
                // Tanımsız eylem ("önizle", "indir"): bekleyen tanım varsa o, yoksa oluşturucudaki
                const hedef = bekleyenTanim ?? mevcutTanim;
                if (hedef) {
                    setAkisDurumu("Eylem yürütülüyor…");
                    const ok = await onTanimUygula(hedef, sonuc.eylem);
                    kayitEkle(kayit);
                    if (ok && bekleyenTanim) {
                        const sahip = [...kayitlar].reverse().find(k => k.rol === "assistant" && tanimAyni(k.tanim, bekleyenTanim));
                        if (sahip) uygulandiIsaretle(sahip.id, bekleyenTanim);
                        else setBekleyenTanim(null);
                    }
                    return;
                }
            }
            kayitEkle(kayit);      // soru ya da yürütülecek bir şey yok
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
    }, [girdi, gonderiliyor, kayitlar, bekleyenTanim, mevcutTanim, onTanimUygula, onKapali, kayitEkle, uygulandiIsaretle]);

    /** Kartta "Onayla ve uygula": tanım oluşturucuya konur, önizleme gelir. */
    const onOnayla = async (kayit: SohbetKaydi) => {
        if (!kayit.tanim || gonderiliyor) return;
        const ok = await onTanimUygula(kayit.tanim, null);
        if (ok) uygulandiIsaretle(kayit.id, kayit.tanim);
    };

    /** Kartta "Excel indir" / "CSV indir": tanım uygulanır ve indirilir (sayfanın /export yolu, K7). */
    const onIndir = async (kayit: SohbetKaydi, format: IndirmeFormati) => {
        if (!kayit.tanim || gonderiliyor) return;
        const ok = await onTanimUygula(kayit.tanim, format === "xlsx" ? "indir_xlsx" : "indir_csv");
        if (ok) uygulandiIsaretle(kayit.id, kayit.tanim);
    };

    /** "Geri al": sayfa eski taslağı geri koyar; balon yeniden onay bekleyen hâle döner. */
    const geriAl = () => {
        onGeriAl();
        const id = sonUygulananId;
        if (id !== null) {
            setKayitlar(prev => prev.map(k => (k.id === id ? { ...k, uygulandi: false } : k)));
            const kayit = kayitlar.find(k => k.id === id);
            if (kayit?.tanim) setBekleyenTanim(kayit.tanim);
        }
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
        setBekleyenTanim(null);
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
                    <input
                        ref={girdiRef}
                        type="text"
                        value={girdi}
                        onChange={e => setGirdi(e.target.value)}
                        onKeyDown={onTus}
                        disabled={gonderiliyor}
                        aria-label="Asistana mesaj"
                        placeholder={bekleyenTanim ? "Düzeltme yazın ya da karttan onaylayın…" : ASISTAN_GIRDI_YER_TUTUCU}
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
                    onOnayla={kayit => void onOnayla(kayit)}
                    onIndir={(kayit, format) => void onIndir(kayit, format)}
                    geriAlKaydiId={geriAlinabilir ? sonUygulananId : null}
                    onGeriAl={geriAl}
                    onTemizle={temizle}
                    onKapat={() => setAcik(false)}
                />
            )}
        </div>
    );
}
