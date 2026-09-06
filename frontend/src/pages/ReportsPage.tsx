import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { useMsal } from "@azure/msal-react";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { ConfirmContext, type ConfirmOptions } from "@/hooks/useConfirm";
import { Eyebrow, HairlineCard } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { ReportBuilder } from "@/components/reports/ReportBuilder";
import { AssistantPanel } from "@/components/reports/AssistantPanel";
import { PreviewTable } from "@/components/reports/PreviewTable";
import { TemplateBar, TemplatesTable } from "@/components/reports/TemplateBar";
import { SaveTemplateDialog, type SablonDiyalogModu, type SablonKunyesi } from "@/components/reports/SaveTemplateDialog";
import { ExportButtons } from "@/components/reports/ExportButtons";
import { RunsTable } from "@/components/reports/RunsTable";
import { kaynakIcinBaslangic, tanimOlustur, yeniSatirId, type OlusturucuDurumu } from "@/components/reports/builderState";
import {
    createTemplate, deleteTemplate, downloadRun, dosyayiIndir, exportReport, getCatalog, listRuns, listTemplates,
    previewReport, tanimGecerliMi, updateTemplate,
    RAPOR_EXPORT_HATASI, RAPOR_KATALOG_HATASI, RAPOR_KOSU_INDIRME_HATASI, RAPOR_KOSU_LISTE_HATASI, RAPOR_ONIZLEME_HATASI,
    RAPOR_SABLON_KAYIT_HATASI, RAPOR_SABLON_LISTE_HATASI, RAPOR_SABLON_SILME_HATASI, RaporApiError,
    type AsistanEylemi, type Katalog, type OnizlemeCevabi, type RaporKosuListesi, type RaporKosusu, type RaporSablonu,
    type RaporTanimi,
} from "@/lib/reports";
import { ASISTAN_KAPALI_MESAJI, raporAsistaniAcikMi } from "@/lib/reportsChat";

const VARSAYILAN_SAYFA_BOYU = 50;
const KOSU_SAYFA_BOYU = 50;

const BOS_DURUM: OlusturucuDurumu = { veri_kaynagi: "", kolonlar: [], filtreler: [], siralama: [] };

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

/** Sunucu tanımı → oluşturucu durumu (filtre satırlarına yalnız React key için `id`). */
function tanimdanDurum(tanim: RaporTanimi): OlusturucuDurumu {
    return {
        veri_kaynagi: tanim.veri_kaynagi,
        kolonlar: [...tanim.kolonlar],
        filtreler: tanim.filtreler.map(f => ({ ...f, id: yeniSatirId() })),
        siralama: tanim.siralama.map(s => ({ alan: s.alan, yon: s.yon })),
    };
}

const ayniTanim = (a: RaporTanimi, b: RaporTanimi) => JSON.stringify(a) === JSON.stringify(b);

/**
 * Provider dışında (izole render) `useConfirm` fırlatır; App.tsx her sayfayı
 * `ConfirmDialogProvider` ile sarar, yine de sayfa çökmesin diye tarayıcı onayına düşülür.
 */
async function yedekOnay(opts: ConfirmOptions): Promise<boolean> {
    const metin = [opts.title, typeof opts.body === "string" ? opts.body : ""].filter(Boolean).join("\n");
    return window.confirm(metin);
}

/**
 * /reports — yöneticiye özel (ProtectedAdminRoute, App.tsx). Sekmeler: "Rapor" (oluşturucu +
 * önizleme + şablon çubuğu + indirme, G133/G134), "Şablonlar" (liste tablosu), "İndirme geçmişi"
 * (sunucu sayfalı koşular). Asistan (G135): başlıktaki "Asistan" düğmesi yalnız `rapor_asistani`
 * anahtarı açıkken görünür; sağ panel tanımı `asistanTanimiUygula` ile oluşturucuya köprüler.
 * Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2 (lib/reports.ts, lib/reportsChat.ts).
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

    const [cevap, setCevap] = useState<OnizlemeCevabi | null>(null);
    const [onizlemeHatasi, setOnizlemeHatasi] = useState<string | null>(null);
    const [onizleniyor, setOnizleniyor] = useState(false);
    // Son önizlenen tanım — sayfa değişimi BU tanımla gider (oluşturucudaki taslakla değil);
    // bayat rozeti taslağın bundan ayrıldığını söyler.
    const [sonTanim, setSonTanim] = useState<RaporTanimi | null>(null);

    // Yarış koruması: geç dönen eski önizleme yenisini ezmesin (CaseList.tsx deseni).
    const reqIdRef = useRef(0);

    // ---- Şablonlar ----
    const [sablonlar, setSablonlar] = useState<RaporSablonu[]>([]);
    const [sablonHatasi, setSablonHatasi] = useState<string | null>(null);
    const [sablonYukleniyor, setSablonYukleniyor] = useState(true);
    const [seciliSablonId, setSeciliSablonId] = useState<number | null>(null);
    const [sablonIsleniyor, setSablonIsleniyor] = useState(false);
    const [diyalog, setDiyalog] = useState<{ mod: SablonDiyalogModu; hedef: RaporSablonu | null } | null>(null);

    // ---- Koşular (İndirme geçmişi) ----
    const [kosular, setKosular] = useState<RaporKosuListesi | null>(null);
    const [kosuHatasi, setKosuHatasi] = useState<string | null>(null);
    const [kosuYukleniyor, setKosuYukleniyor] = useState(false);
    const [kosuOffset, setKosuOffset] = useState(0);
    const [indirilenKosuId, setIndirilenKosuId] = useState<number | null>(null);
    // Export sonrası geçmiş bayatlar: sekme açıkken hemen, değilse açılınca yenilenir.
    const [kosuSurumu, setKosuSurumu] = useState(0);
    const kosuReqRef = useRef(0);

    // ---- Asistan (G135) ----
    // Anahtar kapısı (K8): null = henüz okunmadı (düğme gizli), false = kapalı (gizli), true = görünür.
    const [asistanAnahtari, setAsistanAnahtari] = useState<boolean | null>(null);
    const [asistanAcik, setAsistanAcik] = useState(false);
    // `/chat` 409 döndü: anahtar bu oturumda kapatılmış — düğme pasif + ipucu, panelde şerit.
    const [asistan409, setAsistan409] = useState(false);

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

    const sayfaBoyu = Math.min(VARSAYILAN_SAYFA_BOYU, katalog?.limitler.onizleme_sayfa_boyu_max ?? VARSAYILAN_SAYFA_BOYU);

    const bayat = sonTanim !== null && !ayniTanim(sonTanim, tanim);

    const seciliSablon = useMemo(() => sablonlar.find(s => s.id === seciliSablonId) ?? null, [sablonlar, seciliSablonId]);
    // Koşuya şablon kimliği yalnız taslak şablonla birebir aynıyken yazılır (geçmişte "şablon adı" yanıltmasın).
    const exportSablonId = seciliSablon && ayniTanim(seciliSablon.tanim, tanim) ? seciliSablon.id : null;

    const onizlemeAl = useCallback(async (hedefTanim: RaporTanimi, sayfa: number) => {
        const reqId = ++reqIdRef.current;
        setOnizleniyor(true);
        try {
            const data = await previewReport(hedefTanim, sayfa, sayfaBoyu);
            if (reqId !== reqIdRef.current) return;
            setCevap(data);
            setOnizlemeHatasi(null);
            setSonTanim(hedefTanim);
        } catch (err) {
            if (reqId !== reqIdRef.current) return;
            console.error(err);
            // Hata ≠ boş liste: tablo boşa düşmez, şerit çıkar (G002 kuralı).
            setOnizlemeHatasi(err instanceof Error ? err.message : RAPOR_ONIZLEME_HATASI);
        } finally {
            if (reqId === reqIdRef.current) setOnizleniyor(false);
        }
    }, [sayfaBoyu]);

    const onOnizle = () => {
        if (!tanimGecerli) return;
        void onizlemeAl(tanim, 1);
    };

    const onSayfa = (sayfa: number) => {
        if (!sonTanim) return;
        void onizlemeAl(sonTanim, sayfa);
    };

    const onRetry = () => {
        // Hata anındaki tanımla tekrar; hiç başarılı önizleme yoksa taslakla.
        const hedef = sonTanim ?? (tanimGecerli ? tanim : null);
        if (!hedef) return;
        void onizlemeAl(hedef, cevap?.sayfa ?? 1);
    };

    // ---- Tanım yükleme (şablon / koşu) ----
    /**
     * Tanımı oluşturucuya koyar: veri kaynağı katalogda yoksa reddeder; kaynak değişiyorsa
     * kullanıcıya sorar (kolon/filtre/sıralama seçimleri tümüyle değişir). true = yüklendi.
     */
    const tanimiYukle = useCallback(async (hedef: RaporTanimi, etiket: string): Promise<boolean> => {
        if (!katalog || !katalog.veri_kaynaklari.some(v => v.anahtar === hedef.veri_kaynagi)) {
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
        setDurum(tanimdanDurum(hedef));
        return true;
    }, [katalog, durum.veri_kaynagi, confirm]);

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

    const onIndirildi = () => {
        // Sekme açıksa efekt yeniden çeker; kapalıysa açılınca çeker (sürüm bağımlılığı).
        setKosuSurumu(v => v + 1);
    };

    // ---- Asistan köprüsü (G135) ----
    /**
     * Asistan tanımını oluşturucuya koyar (onay sorulmaz — kullanıcı "uygula"ya bastı ya da
     * asistan `eylem` döndürdü); şablon seçimi düşer, önizleme varsa bayat rozeti kendiliğinden çıkar.
     * `eylem`: `onizle` → mevcut önizleme yolu; `indir_*` → `/export` + `kaynak:"asistan"` (K7, tek log yolu).
     * true = tanım uygulandı (eylem başarısız olsa bile); false = kaynak katalogda yok, hiçbir şey değişmedi.
     */
    const asistanTanimiUygula = useCallback(async (hedef: RaporTanimi, eylem: AsistanEylemi | null): Promise<boolean> => {
        const hedefKaynak = katalog?.veri_kaynaklari.find(v => v.anahtar === hedef.veri_kaynagi);
        if (!katalog || !hedefKaynak) {
            toast.error("Asistan tanımı uygulanamadı", { description: `Veri kaynağı katalogda yok: ${hedef.veri_kaynagi}` });
            return false;
        }
        setDurum(tanimdanDurum(hedef));
        setSeciliSablonId(null);
        if (tab !== "rapor") sekmeyeGit("rapor");
        if (!eylem) {
            toast.success("Asistan tanımı oluşturucuya uygulandı");
            return true;
        }
        if (!tanimGecerliMi(hedef, hedefKaynak)) {
            toast.error("Asistan tanımı eksik", {
                description: "Tanım oluşturucuya kondu ama eksik/geçersiz — düzeltip Önizle'ye basın.",
            });
            return true;
        }
        if (eylem === "onizle") {
            void onizlemeAl(hedef, 1);
            return true;
        }
        const format = eylem === "indir_xlsx" ? "xlsx" : "csv";
        try {
            const sonuc = await exportReport(hedef, format, null, "asistan");
            dosyayiIndir(sonuc);
            toast.success(`İndirildi: ${sonuc.dosyaAdi}`);
            setKosuSurumu(v => v + 1);
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
    }, [katalog, tab, sekmeyeGit, onizlemeAl]);

    const onAsistanKapali = useCallback(() => setAsistan409(true), []);

    const asistanDugmesiGorunur = asistanAnahtari === true;

    const raporSekmesi = katalogHatasi ? (
        <DataErrorBanner description={katalogHatasi} onRetry={katalogYukle} isRetrying={katalogYukleniyor} />
    ) : !katalog ? (
        <HairlineCard>
            <p className="text-[13px] text-[var(--fg-subtle)]">Rapor kataloğu yükleniyor…</p>
        </HairlineCard>
    ) : (
        <div className="grid gap-5">
            <HairlineCard>
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
                />
            </HairlineCard>
            <section className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-5 items-start min-w-0">
                <HairlineCard className="xl:sticky xl:top-2">
                    <ReportBuilder
                        katalog={katalog}
                        durum={durum}
                        onChange={setDurum}
                        onOnizle={onOnizle}
                        onizleAktif={tanimGecerli}
                        onizleniyor={onizleniyor}
                        bayat={bayat}
                    />
                </HairlineCard>
                <HairlineCard padded={false} className="min-w-0">
                    <PreviewTable
                        cevap={cevap}
                        yukleniyor={onizleniyor}
                        hata={onizlemeHatasi}
                        onRetry={onRetry}
                        onSayfa={onSayfa}
                        bayat={bayat}
                        araclar={
                            <ExportButtons
                                tanim={tanim}
                                aktif={tanimGecerli}
                                sablonId={exportSablonId}
                                satirSayisi={cevap && !bayat ? cevap.toplam : null}
                                onIndirildi={onIndirildi}
                            />
                        }
                    />
                </HairlineCard>
            </section>
        </div>
    );

    return (
        <div className="grid gap-7 max-w-[1600px]">
            {/* Üst başlık */}
            <div className="flex items-baseline justify-between gap-4">
                <div>
                    <Eyebrow>01 · Raporlar</Eyebrow>
                    <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
                        Raporlar
                    </h1>
                    <p className="mt-1 text-[12px] text-[var(--fg-muted)]">
                        Veri kaynağı ve kolonları seçin, filtreleyin, sunucudan önizleyin; şablon olarak kaydedin, Excel/CSV indirin. Test aşaması — yalnız yöneticiler.
                    </p>
                </div>
                {asistanDugmesiGorunur && (
                    <FlowButton
                        variant={asistanAcik ? "primary" : "secondary"}
                        size="sm"
                        onClick={() => setAsistanAcik(v => !v)}
                        disabled={asistan409}
                        title={asistan409 ? ASISTAN_KAPALI_MESAJI : "Rapor asistanı — isteğinizi yazın, tanımı oluşturucuya uygulayın"}
                        className="shrink-0"
                    >
                        <Sparkles className="w-3.5 h-3.5" />
                        Asistan
                    </FlowButton>
                )}
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

            <AssistantPanel
                acik={asistanDugmesiGorunur && asistanAcik}
                onKapat={() => setAsistanAcik(false)}
                katalog={katalog}
                mevcutTanim={tanimGecerli ? tanim : null}
                kapali={asistan409}
                onKapali={onAsistanKapali}
                onTanimUygula={asistanTanimiUygula}
            />
        </div>
    );
};

export default ReportsPage;
