/**
 * Dava kartının "Hizmetler" paneli (G252; 01.10 + 02.10 kullanıcı kararları).
 *
 * Kartta HER müvekkil için hangi hizmetlerin verildiği görünür — muhasebe ayrımı müvekkil
 * başınadır, bu yüzden satırlar müvekkile göre grupludur ve her müvekkilin kümesi AYRI yazılır.
 *
 * - Föy (veri paketi) kaynaklı satır salt okunurdur: çipte yalnız kilit simgesi (03.10: "paket ·
 *   föy no" yazısı kalktı — kullanıcının kafasını karıştırıyordu), kaldırma yok; seçicide kilitli
 *   görünür ve `PUT` gövdesine girmez. Müvekkilin aynı hizmeti taşıyan föyleri TEK çipte toplanır
 *   (föy numaraları ipucunda).
 * - "Hizmet ekle" (müvekkilin elle hizmeti varsa "Hizmetleri düzenle") o müvekkilin seçicisini
 *   açar (çoklu); **Uygula** TEK
 *   `PUT /api/cases/{id}/hizmetler/{case_party_id}` atar (gövde = elle küme). Seçim
 *   değişmediyse istek atılmaz.
 * - 2+ müvekkilde "Tüm müvekkillere aynı hizmetleri uygula": bir kez seçilir, her müvekkile
 *   sırayla `PUT` atılır; yazılamayan müvekkil adıyla gösterilir, yazılanlar geri alınmaz.
 * - `service_types` listesinde olmayan (eski adlı) hizmet amber "liste dışı" damgasıyla görünür;
 *   seçicide seçenek olarak sunulmaz (sunucu listede olmayan adı 422 ile reddeder — uygulanınca
 *   elle satır düşer, satırda bunu söyleyen uyarı çıkar).
 *
 * Bilinçli seçimler (CaseNotesPanel deseni): iyimser güncelleme YOK — yazma sonrası liste
 * sunucudan yeniden çekilir ve `onDegisti` ile kart sorgusu tazelenir (özet + tarihçe).
 */
import { useCallback, useEffect, useState } from "react";
import { Lock, PackageCheck, Pencil, Plus } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import { HizmetSecici } from "@/components/HizmetSecici";
import { useConfigList } from "@/hooks/useConfig";
import { closedListState } from "@/lib/caseCardFields";
import {
    type CaseHizmeti,
    type HizmetMuvekkili,
    type MuvekkilHizmetGrubu,
    ayniKume,
    kumeyiYaz,
    listele,
    muvekkileGoreGrupla,
    tekilAdlar,
} from "@/lib/caseHizmetleri";

const hataMesaji = (err: unknown, varsayilan: string): string =>
    err instanceof Error && err.message ? err.message : varsayilan;

const LISTE_DISI_IPUCU = "Bu değer kapalı listede yok — aktarımdan gelmiş olabilir";
const cipSinifi = "inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium border";
// Elle çip: bordo ÇERÇEVE + yumuşak zemin, yazı normal metin rengi — koyu temada bordo yazı
// bordo zeminde okunmuyordu (03.10 kullanıcı geri bildirimi; bordo tonu açılmaz, yazı değişir).
const elleCipSinifi = "bg-[var(--brand-soft)] text-[var(--fg)] border-brand/50";

/** Aynı hizmeti taşıyan föy satırları tek çipte: müvekkilin dört föyü dört çip basmasın. */
interface FoyCipi {
    hizmet: string;
    /** İlk satırın id'si — React anahtarı. */
    id: number;
    /** Föy numaraları (SistemNo), görülme sırasıyla; numarasız föy listeye girmez. */
    sistemNolari: string[];
    adet: number;
}

function foyCipleri(foy: CaseHizmeti[]): FoyCipi[] {
    const cipler = new Map<string, FoyCipi>();
    for (const s of foy) {
        const cip = cipler.get(s.hizmet_turu) ?? { hizmet: s.hizmet_turu, id: s.id, sistemNolari: [], adet: 0 };
        cip.adet += 1;
        if (s.sistem_no) cip.sistemNolari.push(s.sistem_no);
        cipler.set(s.hizmet_turu, cip);
    }
    return Array.from(cipler.values());
}

interface Props {
    caseId: number;
    /** Kartın CLIENT tarafları (`cases.parties` içinden) — satır başına bir müvekkil. */
    muvekkiller: HizmetMuvekkili[];
    /** Kartı düzenleyemeyen kullanıcıda `false`: "Hizmet ekle" ve toplu uygulama görünmez. */
    duzenlenebilir?: boolean;
    /** Yazma sonrası çağrılır — kart sorgusu tazelensin (türetilmiş özet + tarihçe). */
    onDegisti?: () => void;
}

interface TopluHata {
    muvekkilAdi: string;
    mesaj: string;
}

export default function CaseHizmetPanel({ caseId, muvekkiller, duzenlenebilir = true, onDegisti }: Props) {
    const { data: serviceTypes } = useConfigList("serviceTypes");
    const [satirlar, setSatirlar] = useState<CaseHizmeti[]>([]);
    const [yukleniyor, setYukleniyor] = useState(true);
    const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
    // Tek müvekkil düzenleme: açık satırın tarafı + taslak küme (+ açılıştaki küme: "değişti mi").
    const [duzenlenen, setDuzenlenen] = useState<number | null>(null);
    const [taslak, setTaslak] = useState<string[]>([]);
    const [baslangic, setBaslangic] = useState<string[]>([]);
    // Toplu uygulama: ayrı taslak; hata listesi bir sonraki işleme dek ekranda kalır.
    const [topluAcik, setTopluAcik] = useState(false);
    const [topluTaslak, setTopluTaslak] = useState<string[]>([]);
    const [topluHatalar, setTopluHatalar] = useState<TopluHata[]>([]);
    const [yaziliyor, setYaziliyor] = useState(false);

    const yenile = useCallback(async () => {
        try {
            const liste = await listele(caseId);
            setSatirlar(liste);
            setYuklemeHatasi(null);
        } catch (err) {
            setYuklemeHatasi(hataMesaji(err, "Hizmetler yüklenemedi."));
        } finally {
            setYukleniyor(false);
        }
    }, [caseId]);

    useEffect(() => {
        setYukleniyor(true);
        void yenile();
    }, [yenile]);

    const gruplar = muvekkileGoreGrupla(muvekkiller, satirlar);
    const listeAdlari = serviceTypes.map(s => s.name);
    const listeDisi = (ad: string) => closedListState(ad, serviceTypes) === "off-list";
    // Seçiciye yalnız listede olan elle adlar girer (liste gelmediyse/boşsa süzülmez).
    const secilebilir = (ad: string) => listeAdlari.length === 0 || listeAdlari.includes(ad);

    const duzenlemeyiAc = (grup: MuvekkilHizmetGrubu) => {
        const foyAdlari = new Set(grup.foy.map(s => s.hizmet_turu));
        const ilk = tekilAdlar(grup.elle.map(s => s.hizmet_turu)).filter(ad => secilebilir(ad) && !foyAdlari.has(ad));
        setTopluAcik(false);
        setTopluHatalar([]);
        setDuzenlenen(grup.casePartyId);
        setTaslak(ilk);
        setBaslangic(ilk);
    };

    const duzenlemeyiKapat = () => {
        setDuzenlenen(null);
        setTaslak([]);
        setBaslangic([]);
    };

    const yazmaSonrasi = async () => {
        await yenile();
        onDegisti?.();
    };

    const handleUygula = async (grup: MuvekkilHizmetGrubu) => {
        if (yaziliyor) return;
        // Seçim değişmediyse istek atılmaz.
        if (ayniKume(taslak, baslangic)) {
            duzenlemeyiKapat();
            return;
        }
        setYaziliyor(true);
        try {
            await kumeyiYaz(caseId, grup.casePartyId, taslak);
            duzenlemeyiKapat();
            await yazmaSonrasi();
        } catch (err) {
            toast.error(hataMesaji(err, "Hizmetler kaydedilemedi."));
        } finally {
            setYaziliyor(false);
        }
    };

    const handleTopluUygula = async () => {
        if (yaziliyor || topluTaslak.length === 0) return;
        setYaziliyor(true);
        const hatalar: TopluHata[] = [];
        let yazilan = 0;
        // Sırayla: her müvekkil kendi PUT'unu alır; başarısız olan adıyla raporlanır,
        // yazılanlar geri alınmaz (sunucu kümesi idempotent — tekrar denemek güvenli).
        for (const m of muvekkiller) {
            try {
                await kumeyiYaz(caseId, m.id, topluTaslak);
                yazilan += 1;
            } catch (err) {
                hatalar.push({ muvekkilAdi: m.name, mesaj: hataMesaji(err, "Hizmetler kaydedilemedi.") });
            }
        }
        setTopluHatalar(hatalar);
        if (hatalar.length === 0) {
            setTopluAcik(false);
            setTopluTaslak([]);
        } else {
            toast.error(`${hatalar.length} müvekkile hizmet yazılamadı.`);
        }
        try {
            if (yazilan > 0) await yazmaSonrasi();
        } finally {
            setYaziliyor(false);
        }
    };

    const topluDugmesi = duzenlenebilir && muvekkiller.length >= 2 && !yukleniyor && !yuklemeHatasi;
    // Başlıktaki sayı ekrandaki çip sayısıdır (aynı hizmetin föyleri tek çip).
    const toplam = gruplar.reduce((n, g) => n + foyCipleri(g.foy).length + g.elle.length, 0);

    return (
        <Card className="bg-[var(--bg-elevated)] border-[var(--border)] rounded-none" data-testid="case-hizmet-panel">
            <CardHeader className="pb-2">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                        <CardTitle className="text-lg flex items-center gap-2">
                            <PackageCheck className="w-4 h-4 text-brand" />
                            Hizmetler
                            {toplam > 0 && (
                                <span className="text-xs font-normal text-muted-foreground">({toplam})</span>
                            )}
                        </CardTitle>
                        <CardDescription>Müvekkil başına verilen hizmetler</CardDescription>
                    </div>
                    {topluDugmesi && !topluAcik && (
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={yaziliyor}
                            onClick={() => {
                                duzenlemeyiKapat();
                                setTopluHatalar([]);
                                setTopluTaslak([]);
                                setTopluAcik(true);
                            }}
                            data-testid="case-hizmet-toplu-ac"
                        >
                            Tüm müvekkillere aynı hizmetleri uygula
                        </Button>
                    )}
                </div>
            </CardHeader>
            <CardContent className="space-y-3">
                {topluAcik && topluDugmesi && (
                    <div className="p-3 border border-[var(--border)] bg-[var(--bg)] space-y-2" data-testid="case-hizmet-toplu">
                        <p className="text-xs text-[var(--fg-muted)]">
                            Seçilen hizmetler {muvekkiller.length} müvekkilin her birine ayrı ayrı yazılır; müvekkilin
                            elle seçilmiş diğer hizmetleri kalkar, kilitli hizmetler değişmez.
                        </p>
                        <HizmetSecici
                            value={topluTaslak}
                            onChange={setTopluTaslak}
                            disabled={yaziliyor}
                            defaultOpen
                            aria-label="Tüm müvekkiller için hizmetler"
                        />
                        <div className="flex items-center justify-end gap-2">
                            <Button
                                variant="ghost"
                                size="sm"
                                disabled={yaziliyor}
                                onClick={() => { setTopluAcik(false); setTopluTaslak([]); }}
                                data-testid="case-hizmet-toplu-vazgec"
                            >
                                Vazgeç
                            </Button>
                            <Button
                                size="sm"
                                disabled={yaziliyor || topluTaslak.length === 0}
                                onClick={() => void handleTopluUygula()}
                                data-testid="case-hizmet-toplu-uygula"
                            >
                                {yaziliyor ? "Uygulanıyor…" : "Tümüne uygula"}
                            </Button>
                        </div>
                    </div>
                )}

                {topluHatalar.length > 0 && (
                    <div
                        role="alert"
                        className="p-3 border border-tone-danger/40 bg-tone-danger/10 text-sm"
                        data-testid="case-hizmet-toplu-hata"
                    >
                        <p className="font-medium text-tone-danger">
                            Şu müvekkillere hizmet yazılamadı (diğerlerine yazıldı):
                        </p>
                        <ul className="mt-1 space-y-0.5">
                            {topluHatalar.map((h, i) => (
                                <li key={i} data-testid="case-hizmet-toplu-hata-satiri">
                                    <span className="font-medium">{h.muvekkilAdi}</span>
                                    <span className="mx-1.5">—</span>
                                    {h.mesaj}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {yukleniyor ? (
                    <LineListSkeleton count={2} label="Hizmetler yükleniyor…" />
                ) : yuklemeHatasi ? (
                    <p className="text-sm text-tone-danger" data-testid="case-hizmet-error">{yuklemeHatasi}</p>
                ) : (
                    <>
                        {muvekkiller.length === 0 && (
                            <p className="text-sm text-[var(--fg-muted)]" data-testid="case-hizmet-muvekkil-yok">
                                Bu kartta müvekkil tarafı yok
                            </p>
                        )}
                        {gruplar.length > 0 && (
                            <ul className="space-y-2" data-testid="case-hizmet-list">
                                {gruplar.map(grup => {
                                    const acik = duzenlenen === grup.casePartyId;
                                    const bos = grup.foy.length === 0 && grup.elle.length === 0;
                                    const dusecekler = grup.elle
                                        .map(s => s.hizmet_turu)
                                        .filter(ad => !secilebilir(ad));
                                    return (
                                        <li
                                            key={grup.casePartyId}
                                            className="p-3 border border-[var(--border)] bg-[var(--bg)]"
                                            data-testid="case-hizmet-muvekkil"
                                            data-party-id={grup.casePartyId}
                                        >
                                            <div className="flex flex-wrap items-start justify-between gap-3">
                                                <div className="min-w-0 space-y-1.5">
                                                    <p className="text-sm font-medium break-words" data-testid="case-hizmet-muvekkil-adi">
                                                        {grup.muvekkilAdi}
                                                    </p>
                                                    {bos ? (
                                                        <p className="text-sm text-[var(--fg-muted)]" data-testid="case-hizmet-bos">
                                                            Hizmet girilmemiş
                                                        </p>
                                                    ) : (
                                                        <div className="flex flex-wrap gap-1.5">
                                                            {foyCipleri(grup.foy).map(cip => (
                                                                <span
                                                                    key={cip.id}
                                                                    className={`${cipSinifi} ${listeDisi(cip.hizmet) ? "border-amber-500/40 text-amber-700 dark:text-amber-400" : "border-[var(--border-strong)] text-[var(--fg)]"}`}
                                                                    title={[
                                                                        cip.sistemNolari.length > 0 ? `Föy ${cip.sistemNolari.join(", ")}` : null,
                                                                        "kayıtlı hizmet, buradan değiştirilemez",
                                                                        listeDisi(cip.hizmet) ? LISTE_DISI_IPUCU : null,
                                                                    ].filter(Boolean).join(" — ")}
                                                                    data-testid="case-hizmet-cip"
                                                                    data-kaynak="foy"
                                                                    data-adet={cip.adet}
                                                                    data-liste-disi={listeDisi(cip.hizmet) ? "true" : "false"}
                                                                >
                                                                    <span data-testid="case-hizmet-cip-adi">{cip.hizmet}</span>
                                                                    {listeDisi(cip.hizmet) && (
                                                                        <span className="font-mono text-[9.5px] uppercase tracking-[0.08em]" data-testid="case-hizmet-liste-disi">
                                                                            liste dışı
                                                                        </span>
                                                                    )}
                                                                    {/* Yalnız kilit simgesi (03.10 kullanıcı kararı): "paket · föy no" yazısı
                                                                        kullanıcının kafasını karıştırıyordu; föy numaraları ipucunda durur. */}
                                                                    <Lock
                                                                        className="w-3 h-3 shrink-0 text-[var(--fg-muted)]"
                                                                        aria-hidden="true"
                                                                        data-testid="case-hizmet-kilit"
                                                                    />
                                                                </span>
                                                            ))}
                                                            {grup.elle.map(s => (
                                                                <span
                                                                    key={s.id}
                                                                    className={`${cipSinifi} ${listeDisi(s.hizmet_turu) ? "border-amber-500/40 text-amber-700 dark:text-amber-400" : elleCipSinifi}`}
                                                                    title={listeDisi(s.hizmet_turu) ? LISTE_DISI_IPUCU : undefined}
                                                                    data-testid="case-hizmet-cip"
                                                                    data-kaynak="elle"
                                                                    data-liste-disi={listeDisi(s.hizmet_turu) ? "true" : "false"}
                                                                >
                                                                    <span data-testid="case-hizmet-cip-adi">{s.hizmet_turu}</span>
                                                                    {listeDisi(s.hizmet_turu) && (
                                                                        <span className="font-mono text-[9.5px] uppercase tracking-[0.08em]" data-testid="case-hizmet-liste-disi">
                                                                            liste dışı
                                                                        </span>
                                                                    )}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>
                                                {duzenlenebilir && !grup.kartDisi && !acik && (
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        disabled={yaziliyor}
                                                        onClick={() => duzenlemeyiAc(grup)}
                                                        aria-label={`${grup.muvekkilAdi} için ${grup.elle.length > 0 ? "hizmetleri düzenle" : "hizmet ekle"}`}
                                                        data-testid="case-hizmet-sec"
                                                    >
                                                        {/* Etiket işi söyler (03.10): "Hizmet seç" ekleme yolu olarak okunmuyordu. */}
                                                        {grup.elle.length > 0 ? (
                                                            <><Pencil className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />Hizmetleri düzenle</>
                                                        ) : (
                                                            <><Plus className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />Hizmet ekle</>
                                                        )}
                                                    </Button>
                                                )}
                                            </div>

                                            {acik && duzenlenebilir && (
                                                <div className="mt-3 space-y-2" data-testid="case-hizmet-duzenle">
                                                    <HizmetSecici
                                                        value={taslak}
                                                        onChange={setTaslak}
                                                        kilitli={tekilAdlar(grup.foy.map(s => s.hizmet_turu))}
                                                        disabled={yaziliyor}
                                                        defaultOpen
                                                        aria-label={`${grup.muvekkilAdi} için hizmetler`}
                                                    />
                                                    {dusecekler.length > 0 && (
                                                        <p className="text-xs text-amber-700 dark:text-amber-400" data-testid="case-hizmet-dusecek">
                                                            Liste dışı {tekilAdlar(dusecekler).map(ad => `"${ad}"`).join(", ")} seçilemez;
                                                            seçim değiştirilip uygulanırsa kaldırılır.
                                                        </p>
                                                    )}
                                                    <div className="flex items-center justify-end gap-2">
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            disabled={yaziliyor}
                                                            onClick={duzenlemeyiKapat}
                                                            data-testid="case-hizmet-vazgec"
                                                        >
                                                            Vazgeç
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            disabled={yaziliyor}
                                                            onClick={() => void handleUygula(grup)}
                                                            data-testid="case-hizmet-uygula"
                                                        >
                                                            {yaziliyor ? "Uygulanıyor…" : "Uygula"}
                                                        </Button>
                                                    </div>
                                                </div>
                                            )}
                                        </li>
                                    );
                                })}
                            </ul>
                        )}
                    </>
                )}
            </CardContent>
        </Card>
    );
}
