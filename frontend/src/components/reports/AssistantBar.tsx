import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Loader2, Send } from "lucide-react";
import type { AsistanEylemi, Katalog, KatalogKolon, RaporTanimi } from "@/lib/reports";
import { secenekEtiketi } from "@/lib/reports";
import {
    ASISTAN_KAPALI_MESAJI, AsistanFailedError, AsistanKapaliError, AsistanYetkiError, DEGER_LISTESI_MAX,
    chatReport, degerEsle, filtreDegeriDegistir, kaydetNiyeti, listeNiyeti, onayNiyeti, ornekIstemler, sohbetGecmisi,
    sonucSatiri, tanimAyni, type DegerSorunu, type SohbetKaydi,
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
    /** `mevcutTanim` kaynağın DOKUNULMAMIŞ başlangıç tanımıysa true (12.09 bulgusu): sunucuya "mevcut tanım" olarak
     *  null gider, model isteği sıfırdan kurar — varsayılan kolonlar istenen kolonların üstüne binmez. Yerel yollar
     *  (onizle yeniden önizleme, şablon kaydı) `mevcutTanim`i yine kullanır. */
    mevcutVarsayilan?: boolean;
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
    /** G168: sayfanın son önizleme sonucu (hangi tanım, kaç kayıt) — uygulama sonrası sonuç satırı bundan yazılır. */
    onizlemeSonucu?: { tanim: RaporTanimi; toplam: number } | null;
    /** G168: tanımı şablon olarak kaydet; `ad` null → sayfa ad önerir. Kaydedilen ad döner, hata → null (toast sayfada). */
    onSablonKaydet?: (tanim: RaporTanimi, ad: string | null) => Promise<string | null>;
    /**
     * G174 (isteğe bağlı, G175 bağlar): liste balonunda tıklanan değer mevcut tanıma filtre olarak eklenir.
     * Verilmezse değer girdi kutusuna yazılır (kullanıcı gönderir).
     */
    onFiltreEkle?: (alan: string, deger: string) => void;
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
 * G174 — OTOMATİK UYGULAMA (G167 teyit döngüsünün geri alınması; 11.09 sadeleşme kararı): `complete` + `tanim`
 * → değerler kataloğa uyuyorsa (`degerEsle.temiz`) tanım DÜĞME BEKLEMEDEN `onTanimUygula(tanim, eylem ?? "onizle")`
 * ile uygulanır (G143 davranışı; sayfa `oncekiTaslak` + "Geri al" tutar, tanım şeridi G173 zaten ekranda). Kart
 * yalnız şu hâllerde BEKLER (`bekleyenTanim`): (1) metin filtre değeri katalog önerilerine uymadı → sorun
 * satırları + ≤5 aday çipi ("Kataloğda bulunamadı — şunlardan biri mi?"); aday tıklanınca değer katalog yazımıyla
 * tanıma yazılır (`filtreDegeriDegistir`) ve sorun kalmadıysa tanım o an uygulanır; "Yine de uygula" ham tanımı
 * uygular. (2) Sayfa uygulamayı reddetti (kaynak katalogda yok) ya da kullanıcı "Geri al" dedi → "Onayla ve uygula".
 * Bekleyen tanım varken sonraki mesajlar sunucuya `mevcut_tanim` olarak onu taşır; YEREL ONAY (`onayNiyeti`,
 * G167) ve sözle onay (aynı tanım + eylem, `tanimAyni`) korunur. `tanim=null` + eylem → bekleyen (yoksa
 * oluşturucudaki) tanımla eylem; `tanim=null` + eylem yok → soru, yalnız balon.
 * LİSTE BALONU (G174, Gemini'siz): "hangi mahkemeler var" gibi mesaj (`listeNiyeti`) katalogdan `DegerListesi`
 * balonu açar (tek kolon) ya da "Hangisi?" çipleri (çok kolon); değer tıkı `onFiltreEkle` (verilmişse) ya da
 * girdiye yazım. Eşleşme yoksa mesaj Gemini'ye gider.
 * İndirme daima sayfanın `/export` + `kaynak:"asistan"` yolu (K7).
 */
export function AssistantBar({
    yukleniyor = false, katalog, veriKaynagi, mevcutTanim, mevcutVarsayilan = false, onKapali, onTanimUygula, geriAlinabilir,
    onGeriAl, onizlemeSonucu = null, onSablonKaydet, onFiltreEkle,
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
    // G168: uygulandı, önizleme sonucu bekleniyor — sonuç gelince "N kayıt bulundu" / boş-sonuç satırı düşer.
    const [sonucBeklenen, setSonucBeklenen] = useState<RaporTanimi | null>(null);
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

    // G168: önizleme sonucu uygulanan tanıma aitse sonuç satırı (yalnız bir kez).
    useEffect(() => {
        if (!sonucBeklenen || !onizlemeSonucu || !tanimAyni(onizlemeSonucu.tanim, sonucBeklenen)) return;
        kayitEkle({ id: yeniKayitId(), rol: "assistant", yerel: true, icerik: sonucSatiri(sonucBeklenen, onizlemeSonucu.toplam, katalog) });
        setSonucBeklenen(null);
    }, [onizlemeSonucu, sonucBeklenen, katalog, kayitEkle]);

    /** Uygulama (önizleme yolu) sonrası sonuç satırını bekle; indirme yolunda beklenmez (toast yeter). */
    const sonucBekle = useCallback((tanim: RaporTanimi, eylem: AsistanEylemi | null) => {
        if (eylem === null || eylem === "onizle") setSonucBeklenen(tanim);
    }, []);

    /** Uygulama sonrası ortak muhasebe: kayıt rozeti, Geri al kimliği, bekleyen tanımın düşmesi. */
    const uygulandiIsaretle = useCallback((kayitId: number, tanim: RaporTanimi) => {
        setKayitlar(prev => prev.map(k => (k.id === kayitId ? { ...k, uygulandi: true } : k)));
        setSonUygulananId(kayitId);
        setBekleyenTanim(prev => (tanimAyni(prev, tanim) ? null : prev));
    }, []);

    const kaynakBul = useCallback(
        (anahtar: string) => katalog?.veri_kaynaklari.find(v => v.anahtar === anahtar),
        [katalog],
    );

    /** G174: liste balonu kaydı — kolonun değerleri katalogdan; yerel satır, geçmişe kısa metniyle girer. */
    const listeKaydi = useCallback((kolon: KatalogKolon): SohbetKaydi => {
        const degerler = kolon.oneriler && kolon.oneriler.length > 0 ? kolon.oneriler : (kolon.secenekler ?? []);
        const sayi = Math.min(degerler.length, DEGER_LISTESI_MAX);
        const kesik = kolon.oneri_kesik || degerler.length > DEGER_LISTESI_MAX;
        return {
            id: yeniKayitId(), rol: "assistant", yerel: true, liste: kolon,
            icerik: `${kolon.etiket} için kayıtlı ${sayi}${kesik ? "+" : ""} değer aşağıda; tıklayınca filtre olarak eklenir.`,
        };
    }, []);

    /**
     * G174: bir kartın tanımını uygular (aday seçimi / yine de uygula). Başarıda kart rozet alır, bekleyen düşer,
     * önizleme sonucu beklenir; sayfa reddederse kart bekler (Onayla düğmesiyle).
     */
    const kartiUygula = useCallback(async (kayitId: number, tanim: RaporTanimi, eylem: AsistanEylemi) => {
        setGonderiliyor(true);
        setAkisDurumu(eylem === "onizle" ? "Rapor uygulanıyor…" : "İndiriliyor…");
        try {
            const ok = await onTanimUygula(tanim, eylem);
            if (ok) {
                uygulandiIsaretle(kayitId, tanim);
                setBekleyenTanim(null);
                sonucBekle(tanim, eylem);
            }
            return ok;
        } finally {
            setGonderiliyor(false);
            setAkisDurumu(null);
        }
    }, [onTanimUygula, uygulandiIsaretle, sonucBekle]);

    const gonder = useCallback(async (hamMetin?: string) => {
        const metin = (hamMetin ?? girdi).trim();
        if (!metin || gonderiliyor) return;

        const kullaniciKaydi: SohbetKaydi = { id: yeniKayitId(), rol: "user", icerik: metin };
        const gecmis = sohbetGecmisi([...kayitlar, kullaniciKaydi]);
        setKayitlar(prev => [...prev, kullaniciKaydi]);
        setGirdi("");
        setAcik(true);

        // ŞABLON KAYDI (G168): "bunu haftalık rapor olarak kaydet" / "kaydet" — bekleyen (yoksa oluşturucudaki)
        // tanım sayfanın /templates yoluyla kaydedilir; Gemini'ye gitmez.
        const kaydet = kaydetNiyeti(metin);
        const kaydedilecek = bekleyenTanim ?? mevcutTanim;
        if (kaydet && kaydedilecek && onSablonKaydet) {
            setGonderiliyor(true);
            setAkisDurumu("Şablon kaydediliyor…");
            try {
                const ad = await onSablonKaydet(kaydedilecek, kaydet.ad);
                kayitEkle({
                    id: yeniKayitId(), rol: "assistant", yerel: true,
                    icerik: ad
                        ? `"${ad}" adıyla şablonlara kaydedildi; Şablonlar'dan seçebilir, adını değiştirebilirsiniz.`
                        : "Şablon kaydedilemedi; sayfadaki uyarıya bakın.",
                });
            } finally {
                setGonderiliyor(false);
                setAkisDurumu(null);
            }
            return;
        }

        // YEREL ONAY (G167, 10.09 prod dersi): bekleyen tanım varken "tamam / uygula / excel indir" gibi kısa
        // onay mesajı Gemini'ye GİTMEZ — model tanımı değiştirip karta geri düşürebiliyordu. Bekleyen tanım
        // olduğu gibi uygulanır/indirilir; sohbete yerel bir asistan satırı düşer (geçmişe de girer).
        const yerelEylem = bekleyenTanim ? onayNiyeti(metin) : null;
        if (bekleyenTanim && yerelEylem) {
            setGonderiliyor(true);
            setAkisDurumu(yerelEylem === "onizle" ? "Rapor uygulanıyor…" : "İndiriliyor…");
            try {
                const ok = await onTanimUygula(bekleyenTanim, yerelEylem);
                const sahip = [...kayitlar].reverse().find(k => k.rol === "assistant" && tanimAyni(k.tanim, bekleyenTanim));
                kayitEkle({
                    id: yeniKayitId(), rol: "assistant", yerel: true,
                    icerik: !ok ? "Tanım uygulanamadı; karttaki uyarıya bakın."
                        : yerelEylem === "onizle" ? "Onaylandı, rapor oluşturucuya uygulandı ve önizleme getirildi."
                        : `Onaylandı, ${yerelEylem === "indir_xlsx" ? "Excel" : "CSV"} indiriliyor.`,
                });
                if (ok) {
                    if (sahip) uygulandiIsaretle(sahip.id, bekleyenTanim);
                    else setBekleyenTanim(null);
                    sonucBekle(bekleyenTanim, yerelEylem);
                }
            } finally {
                setGonderiliyor(false);
                setAkisDurumu(null);
            }
            return;
        }

        // LİSTE BALONU (G174, Gemini'siz): "hangi mahkemeler var" → katalogdan yerel liste (K6: sunucuya gitmez).
        // Kaynak: bekleyen tanımınki, yoksa oluşturucudaki. Eşleşme yoksa mesaj normal yoldan Gemini'ye gider.
        const listeAdaylari = listeNiyeti(metin, kaynakBul(bekleyenTanim?.veri_kaynagi ?? veriKaynagi));
        if (listeAdaylari && listeAdaylari.length > 0) {
            kayitEkle(listeAdaylari.length === 1
                ? listeKaydi(listeAdaylari[0])
                : {
                    id: yeniKayitId(), rol: "assistant", yerel: true, kolonAdaylari: listeAdaylari,
                    icerik: "Hangisini listeleyeyim? " + listeAdaylari.map(k => k.etiket).join(" · "),
                });
            return;
        }

        setGonderiliyor(true);
        setAkisDurumu("Gönderiliyor…");

        const controller = new AbortController();
        iptalRef.current = controller;
        try {
            // Düzeltmeler teyit bekleyen tanım üzerinde: sunucuya "mevcut tanım" olarak o gider; dokunulmamış
            // varsayılan tanım GİTMEZ (null) — model isteği sıfırdan kurar (`mevcutVarsayilan`).
            const sunucuTanimi = bekleyenTanim ?? (mevcutVarsayilan ? null : mevcutTanim);
            const sonuc = await chatReport(gecmis, sunucuTanimi, { onInfo: setAkisDurumu }, controller.signal);
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
                // Sözle onay (bekleyen tanım aynen + eylem) eşleme istemez; yeni tanımda değerler kataloğa bakılır (G174).
                const sozleOnay = Boolean(sonuc.eylem) && tanimAyni(sonuc.tanim, bekleyenTanim);
                const esleme = sozleOnay ? null : degerEsle(sonuc.tanim, katalog);
                if (sozleOnay || esleme?.temiz) {
                    // OTOMATİK UYGULAMA (G174): düğme beklemeden; eylem yoksa önizleme.
                    const eylem: AsistanEylemi = sonuc.eylem ?? "onizle";
                    setAkisDurumu(eylem === "onizle" ? "Rapor uygulanıyor…" : "İndiriliyor…");
                    kayit.uygulandi = await onTanimUygula(sonuc.tanim, eylem);
                    kayitEkle(kayit);
                    if (kayit.uygulandi) {
                        uygulandiIsaretle(kayit.id, sonuc.tanim);
                        setBekleyenTanim(null);
                        sonucBekle(sonuc.tanim, eylem);
                    } else {
                        // Sayfa reddetti (kaynak katalogda yok vb.): kart bekler, düzeltme bu tanım üzerinde.
                        setBekleyenTanim(sonuc.tanim);
                    }
                    return;
                }
                // Değer kataloğa uymadı: kart bekler, sorun satırları + aday çipleri (G174).
                kayit.uygulandi = false;
                kayit.sorunlar = esleme?.sorunlar ?? [];
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
    }, [girdi, gonderiliyor, kayitlar, bekleyenTanim, mevcutTanim, mevcutVarsayilan, onTanimUygula, onKapali, kayitEkle, uygulandiIsaretle,
        onSablonKaydet, sonucBekle, katalog, veriKaynagi, kaynakBul, listeKaydi]);

    /** Kartta "Onayla ve uygula": tanım oluşturucuya konur, önizleme gelir. */
    const onOnayla = async (kayit: SohbetKaydi) => {
        if (!kayit.tanim || gonderiliyor) return;
        const ok = await onTanimUygula(kayit.tanim, null);
        if (ok) {
            uygulandiIsaretle(kayit.id, kayit.tanim);
            sonucBekle(kayit.tanim, null);
        }
    };

    /** Kartta "Excel indir" / "CSV indir": tanım uygulanır ve indirilir (sayfanın /export yolu, K7). */
    const onIndir = async (kayit: SohbetKaydi, format: IndirmeFormati) => {
        if (!kayit.tanim || gonderiliyor) return;
        const ok = await onTanimUygula(kayit.tanim, format === "xlsx" ? "indir_xlsx" : "indir_csv");
        if (ok) uygulandiIsaretle(kayit.id, kayit.tanim);
    };

    /**
     * G174 aday çipi: sorunlu filtrenin değeri katalog yazımıyla tanıma yazılır (op: kolonda `eq` varsa `eq`,
     * yoksa `contains`); başka sorun kalmadıysa tanım o an uygulanır, kaldıysa kart kalan adaylarla bekler.
     */
    const onAdaySec = async (kayit: SohbetKaydi, sorun: DegerSorunu, aday: string) => {
        if (!kayit.tanim || gonderiliyor) return;
        const kolon = kaynakBul(kayit.tanim.veri_kaynagi)?.kolonlar.find(k => k.anahtar === sorun.alan);
        const yeni = filtreDegeriDegistir(kayit.tanim, sorun.indeks, aday, kolon);
        const kalan = (kayit.sorunlar ?? []).filter(s => s.indeks !== sorun.indeks);
        setKayitlar(prev => prev.map(k => (k.id === kayit.id ? { ...k, tanim: yeni, sorunlar: kalan } : k)));
        setBekleyenTanim(yeni);
        if (kalan.length === 0) await kartiUygula(kayit.id, yeni, kayit.eylem ?? "onizle");
    };

    /** G174 "Yine de uygula": ham değerlerle uygulanır (asistanın eylemi varsa o, yoksa önizleme). */
    const onYineDeUygula = async (kayit: SohbetKaydi) => {
        if (!kayit.tanim || gonderiliyor) return;
        await kartiUygula(kayit.id, kayit.tanim, kayit.eylem ?? "onizle");
    };

    /**
     * G174 liste balonu değer tıkı: `onFiltreEkle` verilmişse (G175) mevcut tanıma filtre olarak eklenir ve sohbete
     * yerel satır düşer; verilmemişse girdiye doğal cümle yazılır, kullanıcı gönderir.
     */
    const onListeSec = (kolon: KatalogKolon, deger: string) => {
        const metin = secenekEtiketi(kolon, deger);
        if (onFiltreEkle) {
            onFiltreEkle(kolon.anahtar, deger);
            kayitEkle({ id: yeniKayitId(), rol: "assistant", yerel: true, icerik: `${kolon.etiket} · ${metin} filtre olarak eklendi.` });
            return;
        }
        setGirdi(`${kolon.etiket} "${metin}" olanlar`);
        girdiRef.current?.focus();
    };

    /** G174 "Hangisi?" kolon çipi: seçilen kolonun liste balonu. */
    const onKolonSec = (_kayit: SohbetKaydi, kolon: KatalogKolon) => {
        kayitEkle(listeKaydi(kolon));
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
        setSonucBeklenen(null);
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
                    onAdaySec={(kayit, sorun, aday) => void onAdaySec(kayit, sorun, aday)}
                    onYineDeUygula={kayit => void onYineDeUygula(kayit)}
                    onListeSec={onListeSec}
                    onKolonSec={onKolonSec}
                />
            )}
        </div>
    );
}
