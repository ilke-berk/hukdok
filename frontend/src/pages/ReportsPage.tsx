import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useMsal } from "@azure/msal-react";
import { toast } from "sonner";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { ConfirmContext, type ConfirmOptions } from "@/hooks/useConfirm";
import { MessageSquareOff } from "lucide-react";
import { Eyebrow, HairlineCard } from "@/components/dashboard/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { AssistantBar } from "@/components/reports/AssistantBar";
import { TanimSeridi } from "@/components/reports/TanimSeridi";
import { PreviewTable } from "@/components/reports/PreviewTable";
import { TemplateBar, TemplatesTable } from "@/components/reports/TemplateBar";
import { SaveTemplateDialog, type SablonDiyalogModu, type SablonKunyesi } from "@/components/reports/SaveTemplateDialog";
import { ExportButtons } from "@/components/reports/ExportButtons";
import { FavoritePrompt } from "@/components/reports/FavoritePrompt";
import { RunsTable } from "@/components/reports/RunsTable";
import {
    filtreEkle, kaynakIcinBaslangic, seritiTemizle, seritteBosOge, siralamaDongusu, tanimOlustur, tanimdanDurum,
    type OlusturucuDurumu,
} from "@/components/reports/builderState";
import {
    createTemplate, deleteTemplate, downloadRun, dosyayiIndir, exportReport, filtredenKontrol, getCatalog, kolonOplari,
    kontrolDoluMu, listRuns, listTemplates, previewReport, sablonAdiOner, secenekEtiketi, tanimGecerliMi, updateTemplate,
    RAPOR_EXPORT_HATASI, RAPOR_KATALOG_HATASI, RAPOR_KOSU_INDIRME_HATASI, RAPOR_KOSU_LISTE_HATASI, RAPOR_ONIZLEME_HATASI,
    RAPOR_SABLON_KAYIT_HATASI, RAPOR_SABLON_LISTE_HATASI, RAPOR_SABLON_SILME_HATASI, RaporApiError,
    type AsistanEylemi, type Filtre, type Katalog, type KontrolDurumu, type OnizlemeCevabi, type RaporKosuListesi,
    type RaporKosusu, type RaporSablonu, type RaporTanimi,
} from "@/lib/reports";
import { ASISTAN_KAPALI_MESAJI, raporAsistaniAcikMi, tanimAyni } from "@/lib/reportsChat";

// Önizleme bir ÖRNEKTİR (kullanıcı kararı 07.09: "5-10 satırlık örnek + toplam kaç satır olduğu yeter");
// tam liste Excel/CSV'de. Kullanıcı 10/25/50 arasında değiştirebilir (PreviewTable alt çubuğu).
const VARSAYILAN_SAYFA_BOYU = 10;
const KOSU_SAYFA_BOYU = 50;
/** Yazarak girilen değerde (metin/sayı/tarih) önizleme bu kadar bekler; yapısal değişiklik hemen (§4.1 madde 5). */
export const ONIZLEME_GECIKME_MS = 600;

const BOS_DURUM: OlusturucuDurumu = { veri_kaynagi: "", kolonlar: [], serit: [], siralama: [] };

// Sekmeler — `TabsTrigger value` listesiyle birebir; URL'deki `?tab=` yalnız bu kümedeyse
// geçerlidir (AdminPage.tsx ADMIN_TABS deseni). Sekme değişince URL de güncellenir (replace).
const RAPOR_TABS = ["rapor", "sablonlar", "gecmis"] as const;
type RaporTab = (typeof RAPOR_TABS)[number];
const DEFAULT_TAB: RaporTab = "rapor";

function resolveTab(tab: string | null): RaporTab {
    return tab && (RAPOR_TABS as readonly string[]).includes(tab) ? (tab as RaporTab) : DEFAULT_TAB;
}

const TAB_TRIGGER_CLS =
    "rounded-none data-[state=active]:bg-[var(--brand-soft)] data-[state=active]:text-[var(--brand)] " +
    "data-[state=active]:shadow-none font-mono text-[11px] tracking-[0.06em] uppercase";

const ayniTanim = (a: RaporTanimi, b: RaporTanimi) => JSON.stringify(a) === JSON.stringify(b);

/** Yerel takvim günü `YYYY-MM-DD` (şeritteki tarih kısayolları için; `toISOString` UTC kaymasına düşmez). */
function yerelGun(d: Date): string {
    const ay = String(d.getMonth() + 1).padStart(2, "0");
    const gun = String(d.getDate()).padStart(2, "0");
    return `${d.getFullYear()}-${ay}-${gun}`;
}

/**
 * Provider dışında (izole render) `useConfirm` fırlatır; App.tsx her sayfayı
 * `ConfirmDialogProvider` ile sarar, yine de sayfa çökmesin diye tarayıcı onayına düşülür.
 */
async function yedekOnay(opts: ConfirmOptions): Promise<boolean> {
    const metin = [opts.title, typeof opts.body === "string" ? opts.body : ""].filter(Boolean).join("\n");
    return window.confirm(metin);
}

/**
 * /reports — yöneticiye özel (ProtectedAdminRoute, App.tsx). Sekmeler: "Rapor", "Şablonlar" (liste
 * tablosu), "İndirme geçmişi" (sunucu sayfalı koşular).
 *
 * G144 — favori önerisi (plan §6.2): başarılı export (manuel `ExportButtons` ya da asistan `indir_*`)
 * sonrasında taslak hiçbir kayıtlı şablonla birebir aynı değilse (`ayniTanim`) ve "Şimdi değil" denmemişse
 * araç çubuğunun altında `FavoritePrompt` çıkar; ad `sablonAdiOner` ile önerilir, Ekle → `createTemplate`
 * (`paylasimli:false`) + seçili. Şablon çubuğunda kalıcı "☆ Favorilere ekle" (reddi geçersiz kılar) /
 * "★ Kayıtlı: <ad>". Kart tanım değişince kapanır; yalnız Rapor sekmesi ağacındadır.
 *
 * G175 — SOHBET ÖNCELİKLİ yerleşim (kullanıcı kararı 11.09: "arayüz deli gibi sadeleşsin"). Rapor sekmesi
 * üç bloktur: `AssistantBar` (tek giriş noktası, G174 davranışı) → `TanimSeridi` (G173; uygulanan tanımın
 * şeffaf, yerinde düzenlenebilir çip şeridi — kaynak rozeti · kolonlar · filtreler · sıralama · Temizle) →
 * sayaç satırı ("N kayıt" · kompakt şablon çubuğu · Excel/CSV) → `FavoritePrompt` (koşullu) → `PreviewTable`.
 * Kaynak kartları, filtre şeridi (`QuickFilters`), "Kolonlar (N)" yan paneli ve `HairlineCard` sarmalı KALKTI.
 * Sayfa yine dolu açılır (G139: katalog gelince ilk kaynak + varsayılan kolonlar + filtresiz önizleme);
 * şeritteki her değişiklik `durumDegisti` üzerinden otomatik önizlemeyi tetikler (G138 sözleşmesi).
 * Anahtar kapalı / 409: sohbet birincil yol olduğundan sayfa boş kalmaz — asistan satırının yerinde tek satırlık
 * bilgi kartı (`asistan-kapali-karti`), şerit + tablo + şablonlar çalışır (şerit tam bir yedek kurucudur).
 * Asistanın liste balonunda (G174) tıklanan değer `onFiltreEkle` ile mevcut tanıma filtre olur (op: kolonda
 * `eq` varsa `eq`, yoksa `contains`; aynı alanın dolu çoklu seçimi varsa değere eklenir).
 *
 * G143 — asistan ÖN PLANDA (plan §6.1): Rapor sekmesinin ilk öğesi `AssistantBar` (tam genişlik,
 * marka kenarlı satır + inline konuşma); anahtar okunana dek iskelet. Asistan geçerli `tanim`
 * döndürünce `asistanTanimiUygula` tanımı DÜĞME BEKLEMEDEN taslağa koyar, önizleme kendiliğinden
 * yenilenir, toast "Rapor hazırlandı · N kayıt"; uygulamadan önceki taslak `oncekiTaslak`ta —
 * balondaki "Geri al" tek adım geri döner.
 *
 * G138 — önizleme OTOMATİKTİR: geçerli taslak son istenenden farklıysa yapısal değişiklikte hemen,
 * yazarak girilen değerde 600 ms sonra ya da odak çıkışında istenir (`gecikmeliRef`); geçersiz
 * tanımda istek gitmez; yarış koruması `reqIdRef`. Kaynak değişince eski cevap ANINDA düşer —
 * ekranda başka kaynağın satırı kalmaz. "Bayat" rozeti/Önizle düğmesi yok.
 * Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2 + §4 (lib/reports.ts, lib/reportsChat.ts).
 */
const ReportsPage = () => {
    useSetPageTitle("Raporlar", ["Raporlar"]);
    const confirm = useContext(ConfirmContext)?.confirm ?? yedekOnay;

    // Sahiplik: sunucu `olusturan`ı küçük harfli e-posta yazar; MSAL username aynı kimlik.
    const { instance, accounts } = useMsal();
    const kullanici = (instance.getActiveAccount() || accounts[0])?.username;

    const [searchParams, setSearchParams] = useSearchParams();
    const [tab, setTab] = useState<RaporTab>(() => resolveTab(searchParams.get("tab")));
    const sekmeyeGit = useCallback((hedef: RaporTab) => {
        setTab(hedef);
        setSearchParams(prev => {
            const next = new URLSearchParams(prev);
            if (hedef === DEFAULT_TAB) next.delete("tab");
            else next.set("tab", hedef);
            return next;
        }, { replace: true });
    }, [setSearchParams]);

    const [katalog, setKatalog] = useState<Katalog | null>(null);
    const [katalogHatasi, setKatalogHatasi] = useState<string | null>(null);
    const [katalogYukleniyor, setKatalogYukleniyor] = useState(true);

    const [durum, setDurum] = useState<OlusturucuDurumu>(BOS_DURUM);
    // Şeritteki tarih kısayolları için bugün (sayfa ömrü boyunca sabit; gece yarısı geçişi yeniden açılışta düzelir).
    const [bugun] = useState(() => yerelGun(new Date()));

    const [cevap, setCevap] = useState<OnizlemeCevabi | null>(null);
    const [onizlemeHatasi, setOnizlemeHatasi] = useState<string | null>(null);
    const [onizleniyor, setOnizleniyor] = useState(false);
    // Son BAŞARIYLA önizlenen tanım — sayfa değişimi bu tanımla gider (taslakla değil);
    // indirme toast'ındaki satır sayısı yalnız taslak buna eşitken yazılır.
    const [sonTanim, setSonTanim] = useState<RaporTanimi | null>(null);

    // Yarış koruması: geç dönen eski önizleme yenisini ezmesin (CaseList.tsx deseni).
    const reqIdRef = useRef(0);
    // Otomatik önizleme: son İSTENEN tanım (hata dönse de) — aynı tanım yeniden istenmez.
    const sonIstenenRef = useRef<RaporTanimi | null>(null);
    // Son durum değişikliği "yazarak" mı geldi (600 ms bekle) — efekt bir kez okur, sıfırlar.
    const gecikmeliRef = useRef(false);
    const zamanlayiciRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Odak çıkışında bekleyen isteği hemen atmak için güncel geçerli taslak.
    const taslakRef = useRef<RaporTanimi | null>(null);

    // ---- Şablonlar ----
    const [sablonlar, setSablonlar] = useState<RaporSablonu[]>([]);
    const [sablonHatasi, setSablonHatasi] = useState<string | null>(null);
    const [sablonYukleniyor, setSablonYukleniyor] = useState(true);
    const [seciliSablonId, setSeciliSablonId] = useState<number | null>(null);
    const [sablonIsleniyor, setSablonIsleniyor] = useState(false);
    const [diyalog, setDiyalog] = useState<{ mod: SablonDiyalogModu; hedef: RaporSablonu | null } | null>(null);

    // ---- Favori önerisi (G144, plan §6.2) ----
    // Kartın açıldığı tanım; taslak bundan ayrılınca kart kapanır (efekt aşağıda). null = kart yok.
    const [favoriOnerisi, setFavoriOnerisi] = useState<RaporTanimi | null>(null);
    // "Şimdi değil"/× denen tanımların JSON anahtarı — sayfa ömrü; "☆ Favorilere ekle" bunu geçersiz kılar.
    const reddedilenlerRef = useRef<Set<string>>(new Set());
    // Export cevabı beklerken şablon listesi değişmiş olabilir; karar anındaki listeyle bakılır.
    const sablonlarRef = useRef<RaporSablonu[]>([]);
    sablonlarRef.current = sablonlar;

    // ---- Koşular (İndirme geçmişi) ----
    const [kosular, setKosular] = useState<RaporKosuListesi | null>(null);
    const [kosuHatasi, setKosuHatasi] = useState<string | null>(null);
    const [kosuYukleniyor, setKosuYukleniyor] = useState(false);
    const [kosuOffset, setKosuOffset] = useState(0);
    const [indirilenKosuId, setIndirilenKosuId] = useState<number | null>(null);
    // Export sonrası geçmiş bayatlar: sekme açıkken hemen, değilse açılınca yenilenir.
    const [kosuSurumu, setKosuSurumu] = useState(0);
    const kosuReqRef = useRef(0);

    // ---- Asistan (G135 → G143) ----
    // Anahtar kapısı (K8): null = henüz okunmadı (satır iskelet), false = kapalı (satır yok), true = satır.
    const [asistanAnahtari, setAsistanAnahtari] = useState<boolean | null>(null);
    // `/chat` 409 döndü: anahtar bu oturumda kapatılmış — satır kalkar (toast ile bildirilir).
    const [asistan409, setAsistan409] = useState(false);
    // Asistan uygulamasından ÖNCEKİ taslak — "Geri al" tek adım (G143); başka her taslak yazımı düşürür.
    const [oncekiTaslak, setOncekiTaslak] = useState<OlusturucuDurumu | null>(null);
    // Otomatik uygulama sonrası ilk önizleme cevabında "Rapor hazırlandı · N kayıt" toast'ı.
    const asistanToastRef = useRef(false);

    const katalogYukle = useCallback(async () => {
        setKatalogYukleniyor(true);
        try {
            const k = await getCatalog();
            setKatalog(k);
            setKatalogHatasi(null);
            setDurum(prev => {
                if (prev.veri_kaynagi && k.veri_kaynaklari.some(v => v.anahtar === prev.veri_kaynagi)) return prev;
                const ilk = k.veri_kaynaklari[0];
                return ilk ? kaynakIcinBaslangic(ilk) : BOS_DURUM;
            });
        } catch (err) {
            const mesaj = err instanceof Error ? err.message : RAPOR_KATALOG_HATASI;
            setKatalogHatasi(mesaj);
            toast.error("Rapor kataloğu yüklenemedi", { description: mesaj });
        } finally {
            setKatalogYukleniyor(false);
        }
    }, []);

    const sablonlariYukle = useCallback(async () => {
        setSablonYukleniyor(true);
        try {
            const liste = await listTemplates();
            setSablonlar(liste);
            setSablonHatasi(null);
        } catch (err) {
            console.error(err);
            // Hata ≠ boş liste: çubukta şerit, toast yok (katalog toast'ını gölgelemesin).
            setSablonHatasi(err instanceof Error ? err.message : RAPOR_SABLON_LISTE_HATASI);
        } finally {
            setSablonYukleniyor(false);
        }
    }, []);

    // Sıra önemli: katalog ilk istek (G133 testleri `calls[0]`'a bakar), şablonlar ikinci.
    useEffect(() => {
        void katalogYukle();
    }, [katalogYukle]);
    useEffect(() => {
        void sablonlariYukle();
    }, [sablonlariYukle]);
    // Anahtar üçüncü istek: okunamazsa sessizce kapalı sayılır (toast yok; manuel akış etkilenmez).
    useEffect(() => {
        let iptal = false;
        void raporAsistaniAcikMi().then(acik => {
            if (!iptal) setAsistanAnahtari(acik);
        });
        return () => {
            iptal = true;
        };
    }, []);

    const kosulariYukle = useCallback(async (offset: number) => {
        const reqId = ++kosuReqRef.current;
        setKosuYukleniyor(true);
        try {
            const liste = await listRuns(KOSU_SAYFA_BOYU, offset);
            if (reqId !== kosuReqRef.current) return;
            setKosular(liste);
            setKosuHatasi(null);
        } catch (err) {
            if (reqId !== kosuReqRef.current) return;
            console.error(err);
            setKosuHatasi(err instanceof Error ? err.message : RAPOR_KOSU_LISTE_HATASI);
        } finally {
            if (reqId === kosuReqRef.current) setKosuYukleniyor(false);
        }
    }, []);

    // Geçmiş yalnız sekme açıkken çekilir (sayfa/sürüm değişince yeniden).
    useEffect(() => {
        if (tab !== "gecmis") return;
        void kosulariYukle(kosuOffset);
    }, [tab, kosuOffset, kosuSurumu, kosulariYukle]);

    const kaynak = useMemo(
        () => katalog?.veri_kaynaklari.find(k => k.anahtar === durum.veri_kaynagi),
        [katalog, durum.veri_kaynagi],
    );

    const tanim = useMemo(() => tanimOlustur(durum), [durum]);
    const tanimGecerli = tanimGecerliMi(tanim, kaynak);
    taslakRef.current = tanimGecerli ? tanim : null;
    // Asistana "mevcut tanım" yalnız kullanıcı dokunmuşsa gider (12.09 bulgusu): sayfa varsayılan kolonlarla dolu
    // açıldığı için model her isteği "mevcut tanımı değiştir" sayıyor, istenen kolonlar varsayılanların ÜSTÜNE
    // ekleniyordu. Kaynağın başlangıç tanımına birebir eşitse `mevcutVarsayilan` → AssistantBar sunucuya null yollar,
    // model isteği sıfırdan kurar; şerit/asistan değişikliği sonrası fark oluşunca yine mevcut tanım gider.
    const mevcutVarsayilan = useMemo(
        () => Boolean(tanimGecerli && kaynak && tanimAyni(tanim, tanimOlustur(kaynakIcinBaslangic(kaynak)))),
        [tanim, tanimGecerli, kaynak],
    );

    const [ornekBoyu, setOrnekBoyu] = useState<number>(VARSAYILAN_SAYFA_BOYU);
    const sayfaBoyu = Math.min(ornekBoyu, katalog?.limitler.onizleme_sayfa_boyu_max ?? ornekBoyu);

    const seciliSablon = useMemo(() => sablonlar.find(s => s.id === seciliSablonId) ?? null, [sablonlar, seciliSablonId]);
    // Koşuya şablon kimliği yalnız taslak şablonla birebir aynıyken yazılır (geçmişte "şablon adı" yanıltmasın).
    const exportSablonId = seciliSablon && ayniTanim(seciliSablon.tanim, tanim) ? seciliSablon.id : null;
    // Toast'taki satır sayısı yalnız görünen önizleme taslağa aitken.
    const onizlenenSatirSayisi = cevap && sonTanim && ayniTanim(sonTanim, tanim) ? cevap.toplam : null;
    // G144: taslakla birebir aynı tanımlı kayıtlı şablon (seçili olması şart değil) → çubukta "★ Kayıtlı", öneri yok.
    const kayitliSablon = useMemo(() => sablonlar.find(s => ayniTanim(s.tanim, tanim)) ?? null, [sablonlar, tanim]);
    // Kart yalnız açıldığı tanım taslakla aynıyken ve tanım kayıtlı değilken görünür.
    const favoriGorunur = favoriOnerisi !== null && !kayitliSablon && ayniTanim(favoriOnerisi, tanim);
    const favoriAdOnerisi = useMemo(
        () => (favoriOnerisi && katalog ? sablonAdiOner(favoriOnerisi, katalog, sablonlar.map(s => s.ad)) : ""),
        [favoriOnerisi, katalog, sablonlar],
    );
    // Tanım değişince kart kapanır (yeniden aynı tanıma dönülse de yeni bir export/bağlantı gerekir).
    useEffect(() => {
        if (favoriOnerisi && !ayniTanim(favoriOnerisi, tanim)) setFavoriOnerisi(null);
    }, [favoriOnerisi, tanim]);

    const onizlemeAl = useCallback(async (hedefTanim: RaporTanimi, sayfa: number) => {
        const reqId = ++reqIdRef.current;
        setOnizleniyor(true);
        try {
            const data = await previewReport(hedefTanim, sayfa, sayfaBoyu);
            if (reqId !== reqIdRef.current) return;
            setCevap(data);
            setOnizlemeHatasi(null);
            setSonTanim(hedefTanim);
            if (asistanToastRef.current) {
                // G143: asistan tanımı uygulandı ve önizleme geldi — satır sayısıyla tek toast.
                asistanToastRef.current = false;
                toast.success(`Rapor hazırlandı · ${data.toplam} kayıt`);
            }
        } catch (err) {
            if (reqId !== reqIdRef.current) return;
            console.error(err);
            // Önizleme düştü: "hazırlandı" toast'ı yok, şerit yeter.
            asistanToastRef.current = false;
            // Hata ≠ boş liste: tablo boşa düşmez, şerit çıkar (G002 kuralı).
            setOnizlemeHatasi(err instanceof Error ? err.message : RAPOR_ONIZLEME_HATASI);
        } finally {
            if (reqId === reqIdRef.current) setOnizleniyor(false);
        }
    }, [sayfaBoyu]);

    // Örnek boyu değişince (10/25/50) görünen önizleme 1. sayfadan yenilenir; ilk render'da istek yok.
    const oncekiSayfaBoyuRef = useRef(sayfaBoyu);
    useEffect(() => {
        if (oncekiSayfaBoyuRef.current === sayfaBoyu) return;
        oncekiSayfaBoyuRef.current = sayfaBoyu;
        const taslak = taslakRef.current;
        if (taslak) void onizlemeAl(taslak, 1);
    }, [sayfaBoyu, onizlemeAl]);

    const zamanlayiciyiDurdur = useCallback(() => {
        if (zamanlayiciRef.current) {
            clearTimeout(zamanlayiciRef.current);
            zamanlayiciRef.current = null;
        }
    }, []);

    // ---- Otomatik önizleme (§4.1 madde 5) ----
    useEffect(() => {
        zamanlayiciyiDurdur();
        if (!kaynak || !tanimGecerli) return;
        if (sonIstenenRef.current && ayniTanim(sonIstenenRef.current, tanim)) return;
        const gecikmeli = gecikmeliRef.current;
        gecikmeliRef.current = false;
        const iste = () => {
            zamanlayiciRef.current = null;
            sonIstenenRef.current = tanim;
            void onizlemeAl(tanim, 1);
        };
        if (!gecikmeli) {
            iste();
            return;
        }
        zamanlayiciRef.current = setTimeout(iste, ONIZLEME_GECIKME_MS);
        return zamanlayiciyiDurdur;
    }, [tanim, tanimGecerli, kaynak, onizlemeAl, zamanlayiciyiDurdur]);

    /** Odak çıkışı: bekleyen gecikmeli istek varsa hemen at. */
    const hemenOnizle = useCallback(() => {
        if (!zamanlayiciRef.current) return;
        zamanlayiciyiDurdur();
        const t = taslakRef.current;
        if (!t) return;
        sonIstenenRef.current = t;
        void onizlemeAl(t, 1);
    }, [onizlemeAl, zamanlayiciyiDurdur]);

    /**
     * Tek durum yazma yolu. Kaynak değişiyorsa eski önizleme ANINDA düşer (cevap null, süren
     * istek yok sayılır) — efekt yeni kaynağın varsayılan tanımını hemen ister.
     */
    const durumDegisti = (next: OlusturucuDurumu, gecikmeli = false) => {
        gecikmeliRef.current = gecikmeli;
        // Her taslak yazımı asistanın "Geri al" adımını düşürür (asistan uygulaması ardından yeniden koyar).
        setOncekiTaslak(null);
        if (next.veri_kaynagi !== durum.veri_kaynagi) {
            reqIdRef.current += 1;
            zamanlayiciyiDurdur();
            sonIstenenRef.current = null;
            setCevap(null);
            setOnizlemeHatasi(null);
            setSonTanim(null);
            setOnizleniyor(false);
        }
        setDurum(next);
    };

    const onSayfa = (sayfa: number) => {
        if (!sonTanim) return;
        void onizlemeAl(sonTanim, sayfa);
    };

    const onRetry = () => {
        // Hata anındaki tanımla tekrar; hiç istek yoksa geçerli taslakla.
        const hedef = sonIstenenRef.current ?? (tanimGecerli ? tanim : null);
        if (!hedef) return;
        sonIstenenRef.current = hedef;
        void onizlemeAl(hedef, cevap?.sayfa ?? 1);
    };

    const onSirala = (alan: string) =>
        durumDegisti({ ...durum, siralama: siralamaDongusu(durum.siralama, alan) });

    const siralanabilirMi = (anahtar: string) => kaynak?.kolonlar.find(k => k.anahtar === anahtar)?.siralanabilir ?? false;

    /** Kart tıklaması: taslak yeni kaynağın varsayılanına döner (aynı kart yeniden tıklanırsa hiçbir şey olmaz). */
    const onKaynakSec = (anahtar: string) => {
        const yeni = katalog?.veri_kaynaklari.find(k => k.anahtar === anahtar);
        if (!yeni || yeni.anahtar === durum.veri_kaynagi) return;
        durumDegisti(kaynakIcinBaslangic(yeni));
    };

    /** Boş sonuç kısayolu: şerit boşalır (yuvalar boş kontrole, eklenen alanlar kalkar), önizleme hemen yenilenir. */
    const onFiltreleriTemizle = () => {
        if (!kaynak) return;
        durumDegisti({ ...durum, serit: seritiTemizle(durum.serit, kaynak) });
    };

    /**
     * G175 — asistanın liste balonunda (G174) tıklanan değer mevcut tanıma filtre olur: op kolonda `eq` varsa
     * `eq`, yoksa `contains`; kontrol `filtredenKontrol` ile doğal çipe çözülür (liste → çoklu seçim, metin →
     * tam eşitlik). Aynı alanın DOLU çoklu seçimi varsa değer ona eklenir (`in`); başka dolu kontrol varsa
     * değeri değişir; yoksa boş yuva/eklenen öğe `filtreEkle` ile doldurulur. Önizleme `durumDegisti` ile
     * hemen; toast "Filtre eklendi · <kolon>: <değer>". Filtre tavanı dolu ya da alan filtrelenemezse uyarı.
     */
    const onFiltreEkle = (alan: string, deger: string) => {
        const kolon = kaynak?.kolonlar.find(k => k.anahtar === alan);
        if (!kaynak || !kolon || !kolon.filtrelenebilir) {
            toast.error("Filtre eklenemedi", { description: `Bu alan filtrelenemez: ${alan}` });
            return;
        }
        const op = kolonOplari(kolon).includes("eq") ? "eq" : "contains";
        const filtre: Filtre = { alan, op, deger };
        const etiket = `${kolon.etiket}: ${secenekEtiketi(kolon, deger)}`;
        const mevcut = durum.serit.find(o => o.durum.alan === alan && kontrolDoluMu(o.durum));
        let serit = durum.serit;
        if (mevcut) {
            const d = mevcut.durum;
            const yeni: KontrolDurumu = d.kontrol === "coklu_secim"
                ? { ...d, secili: d.secili.includes(deger) ? d.secili : [...d.secili, deger] }
                : filtredenKontrol(filtre, kolon, mevcut.sunum);
            serit = durum.serit.map(o => (o.id === mevcut.id ? { ...o, durum: yeni } : o));
        } else {
            const eklenmis = filtreEkle(durum, kolon);
            const bos = seritteBosOge(eklenmis.serit, alan);
            if (!bos) {
                toast.error("Filtre eklenemedi", { description: "Filtre tavanına ulaşıldı — önce bir filtreyi kaldırın." });
                return;
            }
            const cozulen = filtredenKontrol(filtre, kolon, bos.sunum);
            // Yuvanın sunumuna oturmayan çözüm (ör. var/yok yuvası) gelişmiş çip olarak korunur — filtre kaybolmaz.
            const yeni: KontrolDurumu = kontrolDoluMu(cozulen) ? cozulen : { kontrol: "gelismis", alan, op, deger };
            serit = eklenmis.serit.map(o => (o.id === bos.id ? { ...o, durum: yeni } : o));
        }
        durumDegisti({ ...durum, serit });
        toast.success(`Filtre eklendi · ${etiket}`);
    };

    // ---- Tanım yükleme (şablon / koşu) ----
    /**
     * Tanımı oluşturucuya koyar: veri kaynağı katalogda yoksa reddeder; kaynak değişiyorsa
     * kullanıcıya sorar (kolon/filtre/sıralama seçimleri tümüyle değişir). true = yüklendi.
     * Filtreler şeride `tanimdanDurum` ile çözülür; çözülemeyen op gelişmiş çip olarak kalır.
     */
    const tanimiYukle = async (hedef: RaporTanimi, etiket: string): Promise<boolean> => {
        const hedefKaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === hedef.veri_kaynagi);
        if (!katalog || !hedefKaynak) {
            toast.error("Tanım yüklenemedi", { description: `Veri kaynağı katalogda yok: ${hedef.veri_kaynagi}` });
            return false;
        }
        if (durum.veri_kaynagi && durum.veri_kaynagi !== hedef.veri_kaynagi) {
            const ok = await confirm({
                tone: "warning",
                title: "Veri kaynağı değişecek",
                body: `"${etiket}" farklı bir veri kaynağı kullanıyor (${hedef.veri_kaynagi}). Oluşturucudaki kolon, filtre ve sıralama seçimleri bu tanımla değiştirilecek.`,
                confirmLabel: "Yükle",
            });
            if (!ok) return false;
        }
        durumDegisti(tanimdanDurum(hedef, hedefKaynak));
        return true;
    };

    const onSablonYukle = async (sablon: RaporSablonu) => {
        const ok = await tanimiYukle(sablon.tanim, sablon.ad);
        if (!ok) return;
        setSeciliSablonId(sablon.id);
        if (tab !== "rapor") sekmeyeGit("rapor");
        toast.success(`Şablon yüklendi: ${sablon.ad}`);
    };

    const onKosuTanimiYukle = async (kosu: RaporKosusu) => {
        const etiket = kosu.sablon_adi ?? kosu.dosya_adi;
        const ok = await tanimiYukle(kosu.tanim, etiket);
        if (!ok) return;
        setSeciliSablonId(kosu.sablon_id !== null && sablonlar.some(s => s.id === kosu.sablon_id) ? kosu.sablon_id : null);
        sekmeyeGit("rapor");
        toast.success(`Tanım yüklendi: ${etiket}`);
    };

    // ---- Şablon yazma ----
    const diyalogKaydet = async (kunye: SablonKunyesi) => {
        if (!diyalog) return;
        setSablonIsleniyor(true);
        try {
            if (diyalog.mod === "yeni") {
                const yeni = await createTemplate({ ...kunye, tanim });
                setSablonlar(prev => [yeni, ...prev]);
                setSeciliSablonId(yeni.id);
                toast.success(`Şablon kaydedildi: ${yeni.ad}`);
            } else if (diyalog.hedef) {
                const guncel = await updateTemplate(diyalog.hedef.id, { ...kunye, tanim: diyalog.hedef.tanim });
                setSablonlar(prev => prev.map(s => (s.id === guncel.id ? guncel : s)));
                toast.success(`Şablon güncellendi: ${guncel.ad}`);
            }
            setDiyalog(null);
        } catch (err) {
            console.error(err);
            toast.error(RAPOR_SABLON_KAYIT_HATASI, { description: err instanceof Error ? err.message : undefined });
        } finally {
            setSablonIsleniyor(false);
        }
    };

    /** Çubuktaki "Güncelle": seçili şablonun TANIMI taslakla değişir (künye aynı kalır). */
    const onSablonGuncelle = async (sablon: RaporSablonu) => {
        if (!tanimGecerli) return;
        const ok = await confirm({
            tone: "info",
            title: "Şablonu güncelle",
            body: `"${sablon.ad}" şablonunun rapor tanımı oluşturucudaki taslakla değiştirilecek.`,
            confirmLabel: "Güncelle",
        });
        if (!ok) return;
        setSablonIsleniyor(true);
        try {
            const guncel = await updateTemplate(sablon.id, {
                ad: sablon.ad, aciklama: sablon.aciklama, paylasimli: sablon.paylasimli, tanim,
            });
            setSablonlar(prev => prev.map(s => (s.id === guncel.id ? guncel : s)));
            toast.success(`Şablon güncellendi: ${guncel.ad}`);
        } catch (err) {
            console.error(err);
            toast.error(RAPOR_SABLON_KAYIT_HATASI, { description: err instanceof Error ? err.message : undefined });
        } finally {
            setSablonIsleniyor(false);
        }
    };

    const onSablonSil = async (sablon: RaporSablonu) => {
        const ok = await confirm({
            tone: "destructive",
            title: "Şablonu sil",
            body: `"${sablon.ad}" silinecek. ${sablon.paylasimli ? "Paylaşımlı olduğu için diğer yöneticilerin listesinden de kalkar." : ""}`.trim(),
            irreversible: true,
        });
        if (!ok) return;
        setSablonIsleniyor(true);
        try {
            await deleteTemplate(sablon.id);
            setSablonlar(prev => prev.filter(s => s.id !== sablon.id));
            setSeciliSablonId(prev => (prev === sablon.id ? null : prev));
            toast.success(`Şablon silindi: ${sablon.ad}`);
        } catch (err) {
            console.error(err);
            toast.error(RAPOR_SABLON_SILME_HATASI, { description: err instanceof Error ? err.message : undefined });
        } finally {
            setSablonIsleniyor(false);
        }
    };

    // ---- Koşu indirme ----
    const onKosuIndir = async (kosu: RaporKosusu) => {
        if (!kosu.dosya_mevcut || indirilenKosuId !== null) return;
        setIndirilenKosuId(kosu.id);
        try {
            const dosya = await downloadRun(kosu.id);
            dosyayiIndir(dosya);
            toast.success(`İndirildi: ${dosya.dosyaAdi}`);
        } catch (err) {
            console.error(err);
            toast.error(RAPOR_KOSU_INDIRME_HATASI, { description: err instanceof Error ? err.message : undefined });
            // 410: sunucu dosyayı temizlemiş — satırı yerinde pasifleştir (liste yeniden çekilene dek).
            if (err instanceof RaporApiError && err.status === 410) {
                setKosular(prev => prev
                    ? { ...prev, kosular: prev.kosular.map(k => (k.id === kosu.id ? { ...k, dosya_mevcut: false } : k)) }
                    : prev);
            }
        } finally {
            setIndirilenKosuId(null);
        }
    };

    // ---- Favori önerisi (G144) ----
    /**
     * Öneri kartını açar: tanım kayıtlı bir şablonla birebir aynıysa açılmaz; `zorla` değilse
     * "Şimdi değil" denmiş tanım da açılmaz (export tetiği). "☆ Favorilere ekle" `zorla` ile gelir.
     */
    const favoriOner = (hedef: RaporTanimi, zorla = false) => {
        if (sablonlarRef.current.some(s => ayniTanim(s.tanim, hedef))) return;
        if (!zorla && reddedilenlerRef.current.has(JSON.stringify(hedef))) return;
        setFavoriOnerisi(hedef);
    };

    /** "Şimdi değil" / ×: bu tanım için sayfa ömründe bir daha sorulmaz. */
    const favoriReddet = () => {
        if (favoriOnerisi) reddedilenlerRef.current.add(JSON.stringify(favoriOnerisi));
        setFavoriOnerisi(null);
    };

    /** "Ekle" / Enter: `POST /templates` ({ad, aciklama:"", tanim, paylasimli:false}); listeye eklenir ve seçili olur. */
    const favoriEkle = async (ad: string) => {
        if (!favoriOnerisi || sablonIsleniyor) return;
        setSablonIsleniyor(true);
        try {
            const yeni = await createTemplate({ ad, aciklama: "", tanim: favoriOnerisi, paylasimli: false });
            setSablonlar(prev => [yeni, ...prev]);
            setSeciliSablonId(yeni.id);
            setFavoriOnerisi(null);
            toast.success("Favorilere eklendi", { description: yeni.ad });
        } catch (err) {
            console.error(err);
            // Kart açık kalır: kullanıcı adı düzeltip yeniden deneyebilir.
            toast.error(RAPOR_SABLON_KAYIT_HATASI, { description: err instanceof Error ? err.message : undefined });
        } finally {
            setSablonIsleniyor(false);
        }
    };

    const onIndirildi = () => {
        // Sekme açıksa efekt yeniden çeker; kapalıysa açılınca çeker (sürüm bağımlılığı).
        setKosuSurumu(v => v + 1);
        // G144: başarılı manuel export → kayıtsız tanım için favori önerisi (tanım export edilenle aynı: aynı render).
        favoriOner(tanim);
    };

    // ---- Asistan köprüsü (G135 / G138 / G143) ----
    /**
     * Asistan tanımını oluşturucuya koyar (onay sorulmaz — asistan tanım üretti, G143 otomatik yol);
     * şablon seçimi düşer; uygulamadan önceki taslak `oncekiTaslak`a alınır ("Geri al", tek adım).
     * Uygulanan tanım OTOMATİK önizlenir (`eylem=null` olsa da, §4.1 madde 8) ve önizleme gelince
     * "Rapor hazırlandı · N kayıt" toast'ı çıkar; `eylem:"onizle"` mevcut tanımla da olsa yeniden ister;
     * `indir_*` → `/export` + `kaynak:"asistan"` (K7, tek log yolu; indirme toast'ı yeter).
     * true = tanım uygulandı (eylem başarısız olsa bile); false = kaynak katalogda yok, hiçbir şey değişmedi.
     */
    const asistanTanimiUygula = async (hedef: RaporTanimi, eylem: AsistanEylemi | null): Promise<boolean> => {
        const hedefKaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === hedef.veri_kaynagi);
        if (!katalog || !hedefKaynak) {
            toast.error("Asistan tanımı uygulanamadı", { description: `Veri kaynağı katalogda yok: ${hedef.veri_kaynagi}` });
            return false;
        }
        const onceki = durum;
        const uygulanan = tanimdanDurum(hedef, hedefKaynak);
        durumDegisti(uygulanan);
        // durumDegisti geri-al adımını düşürür; asistan yolu hemen ardından koyar (aynı batch, son yazım kazanır).
        setOncekiTaslak(onceki);
        setSeciliSablonId(null);
        if (tab !== "rapor") sekmeyeGit("rapor");
        if (!tanimGecerliMi(hedef, hedefKaynak)) {
            toast.error("Asistan tanımı eksik", {
                description: "Tanım oluşturucuya kondu ama eksik/geçersiz — düzeltin, önizleme kendiliğinden yenilenir.",
            });
            return true;
        }
        if (!eylem || eylem === "onizle") {
            // Aynı tanım daha önce istenmiş olsa da yeniden önizle: efekt "son istenen"i boş görür.
            if (eylem === "onizle") sonIstenenRef.current = null;
            asistanToastRef.current = true;
            return true;
        }
        const format = eylem === "indir_xlsx" ? "xlsx" : "csv";
        try {
            const sonuc = await exportReport(hedef, format, null, "asistan");
            dosyayiIndir(sonuc);
            toast.success(`İndirildi: ${sonuc.dosyaAdi}`);
            setKosuSurumu(v => v + 1);
            // G144: asistan indirmesi de tetikler — kartın tanımı oluşturucunun derleyeceği tanımdır
            // (şeride çözülüp geri derlenen hal; `tanim` memo'su bir sonraki render'da buna eşittir).
            favoriOner(tanimOlustur(uygulanan));
        } catch (err) {
            console.error(err);
            const mesaj = err instanceof Error ? err.message : RAPOR_EXPORT_HATASI;
            if (err instanceof RaporApiError && err.status === 413) {
                toast.error("Rapor satır tavanını aşıyor", { description: mesaj });
            } else {
                toast.error("Rapor indirilemedi", { description: mesaj });
            }
        }
        return true;
    };

    /**
     * G168: sohbetten şablon kaydı — `ad` yoksa `sablonAdiOner`; `POST /templates` (favoriEkle ile aynı gövde);
     * listeye eklenir ve seçili olur; hata → toast + null (asistan satırı "kaydedilemedi" yazar).
     */
    const asistanSablonKaydet = async (hedef: RaporTanimi, ad: string | null): Promise<string | null> => {
        if (!katalog) return null;
        const mevcutAdlar = sablonlarRef.current.map(s => s.ad);
        const kesinAd = (ad ?? "").trim() || sablonAdiOner(hedef, katalog, mevcutAdlar);
        setSablonIsleniyor(true);
        try {
            const yeni = await createTemplate({ ad: kesinAd, aciklama: "", tanim: hedef, paylasimli: false });
            setSablonlar(prev => [yeni, ...prev]);
            setSeciliSablonId(yeni.id);
            setFavoriOnerisi(null);
            toast.success("Şablon kaydedildi", { description: yeni.ad });
            return yeni.ad;
        } catch (err) {
            console.error(err);
            toast.error(RAPOR_SABLON_KAYIT_HATASI, { description: err instanceof Error ? err.message : undefined });
            return null;
        } finally {
            setSablonIsleniyor(false);
        }
    };

    /** "Geri al": asistan uygulamasından önceki taslak geri gelir; efekt önizlemeyi kendiliğinden yeniler. */
    const asistanGeriAl = () => {
        if (!oncekiTaslak) return;
        durumDegisti(oncekiTaslak);
        setSeciliSablonId(null);
    };

    // 409: anahtar bu oturumda kapatılmış — satır kalkar; kullanıcıya tek toast (manuel akış etkilenmez).
    const onAsistanKapali = useCallback(() => {
        setAsistan409(true);
        toast.error("Rapor asistanı kapalı", { description: ASISTAN_KAPALI_MESAJI });
    }, []);

    // Satır: anahtar okunana dek iskelet (null); kapalı (false) ya da 409 → yerinde bilgi kartı (G175).
    const asistanSatiriGorunur = asistanAnahtari !== false && !asistan409;

    const raporSekmesi = katalogHatasi ? (
        <DataErrorBanner description={katalogHatasi} onRetry={katalogYukle} isRetrying={katalogYukleniyor} />
    ) : !katalog ? (
        <HairlineCard>
            <p className="text-[13px] text-[var(--fg-subtle)]">Rapor kataloğu yükleniyor…</p>
        </HairlineCard>
    ) : (
        <section data-testid="rapor-sekmesi" className="grid gap-5 min-w-0">
            {/* 0. Asistan satırı (G143/G174) — sekmenin ilk öğesi; anahtar kapalı/409 → tek satırlık bilgi kartı (G175) */}
            {asistanSatiriGorunur ? (
                <AssistantBar
                    yukleniyor={asistanAnahtari === null}
                    katalog={katalog}
                    veriKaynagi={durum.veri_kaynagi}
                    mevcutTanim={tanimGecerli ? tanim : null}
                    mevcutVarsayilan={mevcutVarsayilan}
                    onKapali={onAsistanKapali}
                    onTanimUygula={asistanTanimiUygula}
                    geriAlinabilir={oncekiTaslak !== null}
                    onGeriAl={asistanGeriAl}
                    onizlemeSonucu={cevap && sonTanim ? { tanim: sonTanim, toplam: cevap.toplam } : null}
                    onSablonKaydet={asistanSablonKaydet}
                    onFiltreEkle={onFiltreEkle}
                />
            ) : (
                <div
                    data-testid="asistan-kapali-karti"
                    role="note"
                    title={ASISTAN_KAPALI_MESAJI}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2.5 border border-dashed border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[12px] text-[var(--fg-muted)] min-w-0"
                >
                    <MessageSquareOff className="w-3.5 h-3.5 shrink-0 text-[var(--fg-subtle)]" aria-hidden="true" />
                    <span className="font-medium text-[var(--fg)]">Rapor asistanı kapalı</span>
                    <span className="min-w-0">
                        — yönetici panelinden <code className="font-mono text-[11px]">rapor_asistani</code> anahtarını açın.
                        Tanım şeridi ve tablo çalışmaya devam eder.
                    </span>
                </div>
            )}

            {/* 1. Tanım şeridi (G173) — uygulanan tanım; her düzenleme `durumDegisti` → otomatik önizleme */}
            {kaynak && (
                <TanimSeridi
                    katalog={katalog}
                    durum={durum}
                    onChange={durumDegisti}
                    onHemen={hemenOnizle}
                    onKaynakSec={onKaynakSec}
                    bugun={bugun}
                />
            )}

            {/* 2. Sayaç satırı: "N kayıt" · kompakt şablon çubuğu · Excel/CSV (lg altında sarar) */}
            <div data-testid="sayac-satiri" className="flex flex-wrap items-center gap-x-4 gap-y-2 min-w-0">
                <span
                    data-testid="kayit-sayaci"
                    title="Raporun tamamındaki kayıt sayısı; tablo yalnız bir örnek gösterir, tam liste Excel/CSV'de"
                    className="font-mono text-[11px] tracking-[0.12em] uppercase text-[var(--fg)] font-semibold tabular-nums shrink-0"
                >
                    {cevap && !onizlemeHatasi ? `${cevap.toplam.toLocaleString("tr-TR")} kayıt` : onizleniyor ? "sayılıyor…" : "— kayıt"}
                </span>
                <div className="min-w-0 flex-1">
                    <TemplateBar
                        sablonlar={sablonlar}
                        yukleniyor={sablonYukleniyor}
                        hata={sablonHatasi}
                        onRetry={sablonlariYukle}
                        kullanici={kullanici}
                        seciliId={seciliSablonId}
                        onSecim={setSeciliSablonId}
                        onYukle={s => void onSablonYukle(s)}
                        onKaydet={() => setDiyalog({ mod: "yeni", hedef: null })}
                        onGuncelle={s => void onSablonGuncelle(s)}
                        onSil={s => void onSablonSil(s)}
                        taslakGecerli={tanimGecerli}
                        isleniyor={sablonIsleniyor}
                        kayitli={kayitliSablon}
                        onFavoriEkle={() => favoriOner(tanim, true)}
                    />
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-auto">
                    <ExportButtons
                        tanim={tanim}
                        aktif={tanimGecerli}
                        sablonId={exportSablonId}
                        satirSayisi={onizlenenSatirSayisi}
                        onIndirildi={onIndirildi}
                    />
                </div>
            </div>

            {/* 2b. Favori önerisi (G144) — sayaç satırının altında tek satır; yalnız Rapor sekmesinde (bu ağaç) */}
            {favoriGorunur && (
                <FavoritePrompt
                    onerilenAd={favoriAdOnerisi}
                    onEkle={favoriEkle}
                    onSimdiDegil={favoriReddet}
                    onKapat={favoriReddet}
                    kaydediliyor={sablonIsleniyor}
                />
            )}

            {/* 3. Önizleme — tam genişlik, kendi çerçevesinde */}
            <div className="border border-[var(--border)] bg-[var(--bg-elevated)] min-w-0">
                <PreviewTable
                    cevap={cevap}
                    yukleniyor={onizleniyor}
                    hata={onizlemeHatasi}
                    onRetry={onRetry}
                    onSayfa={onSayfa}
                    sayfaBoyu={sayfaBoyu}
                    onSayfaBoyu={setOrnekBoyu}
                    gecersiz={!tanimGecerli}
                    siralama={durum.siralama}
                    siralanabilirMi={siralanabilirMi}
                    onSirala={onSirala}
                    filtreVar={tanim.filtreler.length > 0}
                    onFiltreleriTemizle={onFiltreleriTemizle}
                />
            </div>
        </section>
    );

    return (
        <div className="grid gap-7">
            {/* Üst başlık — kısa; kullanım ipucu başlığın title'ında (metin azaltma, §4.1 madde 7) */}
            <div>
                <Eyebrow>01 · Raporlar</Eyebrow>
                <h1
                    className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium"
                    title="Ne istediğinizi asistana yazın ya da tanım şeridinden düzenleyin; önizleme kendiliğinden yenilenir. Test aşaması — yalnız yöneticiler."
                >
                    Raporlar
                </h1>
            </div>

            <Tabs value={tab} onValueChange={v => sekmeyeGit(resolveTab(v))} className="w-full">
                <TabsList className="flex flex-wrap h-auto gap-1 justify-start mb-5 p-1 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
                    <TabsTrigger className={TAB_TRIGGER_CLS} value="rapor">Rapor</TabsTrigger>
                    <TabsTrigger className={TAB_TRIGGER_CLS} value="sablonlar">Şablonlar</TabsTrigger>
                    <TabsTrigger className={TAB_TRIGGER_CLS} value="gecmis">İndirme geçmişi</TabsTrigger>
                </TabsList>

                <TabsContent value="rapor" className="mt-0">
                    {raporSekmesi}
                </TabsContent>

                <TabsContent value="sablonlar" className="mt-0">
                    <HairlineCard padded={false} className="min-w-0">
                        <TemplatesTable
                            sablonlar={sablonlar}
                            yukleniyor={sablonYukleniyor}
                            hata={sablonHatasi}
                            onRetry={sablonlariYukle}
                            kullanici={kullanici}
                            onYukle={s => void onSablonYukle(s)}
                            onDuzenle={s => setDiyalog({ mod: "duzenle", hedef: s })}
                            onSil={s => void onSablonSil(s)}
                            isleniyor={sablonIsleniyor}
                        />
                    </HairlineCard>
                </TabsContent>

                <TabsContent value="gecmis" className="mt-0">
                    <HairlineCard padded={false} className="min-w-0">
                        <RunsTable
                            liste={kosular}
                            yukleniyor={kosuYukleniyor}
                            hata={kosuHatasi}
                            onRetry={() => void kosulariYukle(kosuOffset)}
                            limit={KOSU_SAYFA_BOYU}
                            offset={kosuOffset}
                            onSayfa={setKosuOffset}
                            onIndir={k => void onKosuIndir(k)}
                            indirilenId={indirilenKosuId}
                            onTanimiYukle={k => void onKosuTanimiYukle(k)}
                        />
                    </HairlineCard>
                </TabsContent>
            </Tabs>

            <SaveTemplateDialog
                open={diyalog !== null}
                onOpenChange={o => { if (!o) setDiyalog(null); }}
                mod={diyalog?.mod ?? "yeni"}
                baslangic={diyalog?.hedef ? { ad: diyalog.hedef.ad, aciklama: diyalog.hedef.aciklama, paylasimli: diyalog.hedef.paylasimli } : null}
                onSubmit={diyalogKaydet}
                kaydediliyor={sablonIsleniyor}
            />
        </div>
    );
};

export default ReportsPage;
