import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { Eyebrow, HairlineCard } from "@/components/dashboard/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { ReportBuilder } from "@/components/reports/ReportBuilder";
import { PreviewTable } from "@/components/reports/PreviewTable";
import { kaynakIcinBaslangic, tanimOlustur, type OlusturucuDurumu } from "@/components/reports/builderState";
import {
    getCatalog, previewReport, tanimGecerliMi,
    RAPOR_KATALOG_HATASI, RAPOR_ONIZLEME_HATASI,
    type Katalog, type OnizlemeCevabi, type RaporTanimi,
} from "@/lib/reports";

const VARSAYILAN_SAYFA_BOYU = 50;

const BOS_DURUM: OlusturucuDurumu = { veri_kaynagi: "", kolonlar: [], filtreler: [], siralama: [] };

/**
 * /reports — yöneticiye özel (ProtectedAdminRoute, App.tsx). Sol: Rapor Oluşturucu,
 * sağ: sunucu sayfalı önizleme. Şablon/indirme (G134) ve asistan (G135) bu iskelete eklenir.
 * Sözleşme: docs/plan/raporlama-plani-2026-09-06.md §2 (lib/reports.ts).
 */
const ReportsPage = () => {
    useSetPageTitle("Raporlar", ["Raporlar"]);

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

    useEffect(() => {
        void katalogYukle();
    }, [katalogYukle]);

    const kaynak = useMemo(
        () => katalog?.veri_kaynaklari.find(k => k.anahtar === durum.veri_kaynagi),
        [katalog, durum.veri_kaynagi],
    );

    const tanim = useMemo(() => tanimOlustur(durum), [durum]);
    const tanimGecerli = tanimGecerliMi(tanim, kaynak);

    const sayfaBoyu = Math.min(VARSAYILAN_SAYFA_BOYU, katalog?.limitler.onizleme_sayfa_boyu_max ?? VARSAYILAN_SAYFA_BOYU);

    const bayat = sonTanim !== null && JSON.stringify(sonTanim) !== JSON.stringify(tanim);

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
                        Veri kaynağı ve kolonları seçin, filtreleyin, sunucudan önizleyin. Test aşaması — yalnız yöneticiler.
                    </p>
                </div>
            </div>

            {katalogHatasi ? (
                <DataErrorBanner description={katalogHatasi} onRetry={katalogYukle} isRetrying={katalogYukleniyor} />
            ) : !katalog ? (
                <HairlineCard>
                    <p className="text-[13px] text-[var(--fg-subtle)]">Rapor kataloğu yükleniyor…</p>
                </HairlineCard>
            ) : (
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
                        />
                    </HairlineCard>
                </section>
            )}
        </div>
    );
};

export default ReportsPage;
