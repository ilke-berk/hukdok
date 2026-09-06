import { ChevronLeft, ChevronRight, Download, History, Loader2, RefreshCw, Upload } from "lucide-react";
import type { RaporKosuListesi, RaporKosusu } from "@/lib/reports";
import { FORMAT_ETIKETLERI, KAYNAK_ETIKETLERI, boyutBicimle, tarihSaatBicimle } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { ICON_BTN_CLS } from "./ui";

type RunsTableProps = {
    liste: RaporKosuListesi | null;
    yukleniyor: boolean;
    /** Sunucu/ağ hatası — boş liste DEĞİL (DataErrorBanner). */
    hata: string | null;
    onRetry: () => void;
    limit: number;
    offset: number;
    onSayfa: (offset: number) => void;
    onIndir: (kosu: RaporKosusu) => void;
    /** Şu an indirilen koşu (spinner); yoksa null. */
    indirilenId: number | null;
    /** Koşunun tanımını oluşturucuya koyar ve Rapor sekmesine geçer. */
    onTanimiYukle: (kosu: RaporKosusu) => void;
};

const STICKY_ACTIONS = "text-right sticky right-0 bg-[var(--bg-elevated)] shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.15)]";
const TH_CLS = "text-left px-4 py-2.5 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold whitespace-nowrap";
const TD_CLS = "px-4 py-2 text-[12px] align-middle whitespace-nowrap text-[var(--fg)]";
const ROZET_CLS = "font-mono text-[9.5px] tracking-[0.12em] uppercase px-1.5 py-0.5 border";

export const SURESI_DOLDU_IPUCU = "Saklama süresi doldu — dosya artık sunucuda yok";

/** Kaynak rozeti: manuel (nötr) / asistan (marka). */
function KaynakRozeti({ kaynak }: { kaynak: RaporKosusu["kaynak"] }) {
    const asistan = kaynak === "asistan";
    return (
        <span
            data-testid="kaynak-rozeti"
            className={`${ROZET_CLS} ${asistan ? "border-[var(--brand)]/40 text-[var(--brand)] bg-[var(--brand-soft)]" : "border-[var(--border)] text-[var(--fg-muted)] bg-[var(--bg)]"}`}
        >
            {KAYNAK_ETIKETLERI[kaynak] ?? kaynak}
        </span>
    );
}

/**
 * "İndirme geçmişi" sekmesi (G134): sunucu sayfalı koşu listesi — zaman, kullanıcı, şablon,
 * veri kaynağı, format, kaynak, satır/kolon, dosya adı + boyut, İndir (dosya yoksa pasif +
 * ipucu), Tanımı yükle. Hata ≠ boş liste.
 */
export function RunsTable({ liste, yukleniyor, hata, onRetry, limit, offset, onSayfa, onIndir, indirilenId, onTanimiYukle }: RunsTableProps) {
    const toplam = liste?.toplam ?? 0;
    const sayfa = Math.floor(offset / limit) + 1;
    const toplamSayfa = Math.max(1, Math.ceil(toplam / limit));

    return (
        <div className="flex flex-col">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
                <div className="flex items-center gap-3 min-w-0">
                    <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
                        <History className="w-3.5 h-3.5 text-[var(--fg-muted)]" />
                        İndirme geçmişi
                    </span>
                    {liste && !hata && (
                        <span
                            data-testid="kosu-toplam-rozeti"
                            className={`${ROZET_CLS} border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] tabular-nums`}
                        >
                            Toplam {toplam.toLocaleString("tr-TR")} koşu
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {yukleniyor && <Loader2 className="w-4 h-4 animate-spin text-[var(--fg-subtle)]" aria-label="Yükleniyor" />}
                    <button type="button" className={ICON_BTN_CLS} onClick={onRetry} disabled={yukleniyor} aria-label="Geçmişi yenile" title="Yenile">
                        <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>

            {hata ? (
                <div className="p-4">
                    <DataErrorBanner description={hata} onRetry={onRetry} isRetrying={yukleniyor} />
                </div>
            ) : !liste ? (
                <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Geçmiş yükleniyor…</p>
            ) : liste.kosular.length === 0 ? (
                <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">Henüz indirme yok.</p>
            ) : (
                <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
                    <table className="w-full border-collapse">
                        <thead>
                            <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                                <th className={TH_CLS}>Zaman</th>
                                <th className={TH_CLS}>Kullanıcı</th>
                                <th className={TH_CLS}>Şablon</th>
                                <th className={TH_CLS}>Veri kaynağı</th>
                                <th className={TH_CLS}>Format</th>
                                <th className={TH_CLS}>Kaynak</th>
                                <th className={`${TH_CLS} text-right`}>Satır / Kolon</th>
                                <th className={TH_CLS}>Dosya</th>
                                <th className={`${TH_CLS} ${STICKY_ACTIONS}`}>İşlemler</th>
                            </tr>
                        </thead>
                        <tbody>
                            {liste.kosular.map(k => {
                                const indiriliyor = indirilenId === k.id;
                                return (
                                    <tr key={k.id} data-testid="kosu-satiri" data-kosu-id={k.id} className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] transition-colors">
                                        <td className={`${TD_CLS} font-mono text-[11px] tabular-nums`}>{tarihSaatBicimle(k.baslangic)}</td>
                                        <td className={`${TD_CLS} max-w-[220px] truncate`} title={k.kullanici}>{k.kullanici}</td>
                                        <td className={`${TD_CLS} max-w-[220px] truncate ${k.sablon_adi ? "" : "text-[var(--fg-subtle)]"}`} title={k.sablon_adi ?? undefined}>
                                            {k.sablon_adi ?? "—"}
                                        </td>
                                        <td className={`${TD_CLS} font-mono text-[11px]`}>{k.veri_kaynagi}</td>
                                        <td className={TD_CLS}>
                                            <span className={`${ROZET_CLS} border-[var(--border)] text-[var(--fg)] bg-[var(--bg)]`}>{FORMAT_ETIKETLERI[k.format] ?? k.format}</span>
                                        </td>
                                        <td className={TD_CLS}><KaynakRozeti kaynak={k.kaynak} /></td>
                                        <td className={`${TD_CLS} text-right tabular-nums`}>
                                            {k.satir_sayisi.toLocaleString("tr-TR")} <span className="text-[var(--fg-subtle)]">/ {k.kolon_sayisi}</span>
                                        </td>
                                        <td className={`${TD_CLS} max-w-[280px]`}>
                                            <div className="truncate font-mono text-[11px]" title={k.dosya_adi}>{k.dosya_adi}</div>
                                            <div className="text-[11px] text-[var(--fg-subtle)] tabular-nums">
                                                {boyutBicimle(k.dosya_boyutu)}
                                                {!k.dosya_mevcut && <span className="ml-1.5 text-[var(--brand)]" data-testid="dosya-yok">· süresi doldu</span>}
                                            </div>
                                        </td>
                                        <td className={`${TD_CLS} ${STICKY_ACTIONS}`}>
                                            <div className="inline-flex items-center gap-1">
                                                <button
                                                    type="button"
                                                    className={ICON_BTN_CLS}
                                                    onClick={() => onIndir(k)}
                                                    disabled={!k.dosya_mevcut || indiriliyor}
                                                    aria-label={`Koşu ${k.id} indir`}
                                                    title={k.dosya_mevcut ? "Saklanan çıktıyı indir" : SURESI_DOLDU_IPUCU}
                                                >
                                                    {indiriliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                                                </button>
                                                <button
                                                    type="button"
                                                    className={ICON_BTN_CLS}
                                                    onClick={() => onTanimiYukle(k)}
                                                    aria-label={`Koşu ${k.id} tanımını yükle`}
                                                    title="Tanımı oluşturucuya yükle"
                                                >
                                                    <Upload className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {liste && !hata && toplam > limit && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
                    <Eyebrow>Sayfa boyu {limit}</Eyebrow>
                    <div className="flex items-center gap-2">
                        <FlowButton variant="ghost" size="sm" disabled={sayfa <= 1 || yukleniyor} onClick={() => onSayfa(Math.max(0, offset - limit))}>
                            <ChevronLeft className="w-3.5 h-3.5" />
                            Geri
                        </FlowButton>
                        <span className="font-mono text-[11px] tabular-nums px-2.5 py-1 border border-[var(--border)] bg-[var(--bg-elevated)]">
                            {sayfa} / {toplamSayfa}
                        </span>
                        <FlowButton variant="ghost" size="sm" disabled={sayfa >= toplamSayfa || yukleniyor} onClick={() => onSayfa(offset + limit)}>
                            İleri
                            <ChevronRight className="w-3.5 h-3.5" />
                        </FlowButton>
                    </div>
                </div>
            )}
        </div>
    );
}
