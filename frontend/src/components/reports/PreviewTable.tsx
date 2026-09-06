import { ChevronLeft, ChevronRight, Loader2, Table2 } from "lucide-react";
import type { OnizlemeCevabi } from "@/lib/reports";
import { hucreBicimle } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";

type PreviewTableProps = {
    cevap: OnizlemeCevabi | null;
    yukleniyor: boolean;
    /** Sunucu/ağ hatası — boş liste DEĞİL, DataErrorBanner (G002 kuralı). */
    hata: string | null;
    onRetry: () => void;
    onSayfa: (sayfa: number) => void;
    bayat: boolean;
};

const TH_CLS = "text-left px-4 py-2.5 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold whitespace-nowrap";
const SAGA_YASLI = new Set(["sayi", "para"]);

/**
 * Önizleme tablosu (sağ sütun): başlıklar katalog etiketiyle, tarih dd.MM.yyyy, para tr-TR,
 * `null` "—"; sayfalayıcı CaseList kalıbı. Araç çubuğu düğmelerini (kaydet/indir) G134 ekler.
 */
export function PreviewTable({ cevap, yukleniyor, hata, onRetry, onSayfa, bayat }: PreviewTableProps) {
    const toplamSayfa = cevap ? Math.ceil(cevap.toplam / cevap.sayfa_boyu) || 1 : 1;

    return (
        <div className="flex flex-col">
            {/* Araç çubuğu */}
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
                <div className="flex items-center gap-3 min-w-0">
                    <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
                        <Table2 className="w-3.5 h-3.5 text-[var(--fg-muted)]" />
                        Önizleme
                    </span>
                    {cevap && !hata && (
                        <span
                            data-testid="toplam-rozeti"
                            className="font-mono text-[10px] tracking-[0.12em] uppercase px-1.5 py-0.5 border border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] tabular-nums"
                        >
                            Toplam {cevap.toplam.toLocaleString("tr-TR")} kayıt
                        </span>
                    )}
                    {bayat && cevap && (
                        <span className="font-mono text-[9.5px] tracking-[0.12em] uppercase text-[var(--brand)]">
                            tanım değişti — yeniden önizleyin
                        </span>
                    )}
                </div>
                {yukleniyor && <Loader2 className="w-4 h-4 animate-spin text-[var(--fg-subtle)]" aria-label="Yükleniyor" />}
            </div>

            {hata ? (
                <div className="p-4">
                    <DataErrorBanner description={hata} onRetry={onRetry} isRetrying={yukleniyor} />
                </div>
            ) : !cevap ? (
                <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
                    <Table2 className="w-9 h-9 opacity-30" />
                    <p className="text-[13px]">
                        {yukleniyor ? "Önizleme alınıyor…" : "Veri kaynağı ve kolonları seçip Önizle'ye basın."}
                    </p>
                </div>
            ) : cevap.satirlar.length === 0 ? (
                <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
                    <Table2 className="w-9 h-9 opacity-30" />
                    <p className="text-[13px]">Bu kriterlere uyan kayıt yok.</p>
                </div>
            ) : (
                <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
                    <table className="w-full border-collapse">
                        <thead>
                            <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                                {cevap.kolonlar.map(k => (
                                    <th key={k.anahtar} className={`${TH_CLS} ${SAGA_YASLI.has(k.tip) ? "text-right" : ""}`}>
                                        {k.etiket}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {cevap.satirlar.map((satir, i) => (
                                <tr key={i} className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] transition-colors">
                                    {cevap.kolonlar.map(k => {
                                        const metin = hucreBicimle(satir[k.anahtar], k.tip);
                                        const bos = metin === "—";
                                        return (
                                            <td
                                                key={k.anahtar}
                                                className={[
                                                    "px-4 py-2 text-[12px] align-top whitespace-nowrap max-w-[320px] truncate",
                                                    SAGA_YASLI.has(k.tip) ? "text-right tabular-nums" : "",
                                                    k.tip === "tarih" ? "font-mono text-[11px] tabular-nums" : "",
                                                    bos ? "text-[var(--fg-subtle)]" : "text-[var(--fg)]",
                                                ].join(" ")}
                                                title={bos ? undefined : metin}
                                            >
                                                {metin}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {cevap && !hata && cevap.toplam > 0 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
                    <Eyebrow>
                        Sayfa boyu {cevap.sayfa_boyu}
                    </Eyebrow>
                    <div className="flex items-center gap-2">
                        <FlowButton
                            variant="ghost"
                            size="sm"
                            disabled={cevap.sayfa <= 1 || yukleniyor}
                            onClick={() => onSayfa(cevap.sayfa - 1)}
                        >
                            <ChevronLeft className="w-3.5 h-3.5" />
                            Geri
                        </FlowButton>
                        <span className="font-mono text-[11px] tabular-nums px-2.5 py-1 border border-[var(--border)] bg-[var(--bg-elevated)]">
                            {cevap.sayfa} / {toplamSayfa}
                        </span>
                        <FlowButton
                            variant="ghost"
                            size="sm"
                            disabled={cevap.sayfa >= toplamSayfa || yukleniyor}
                            onClick={() => onSayfa(cevap.sayfa + 1)}
                        >
                            İleri
                            <ChevronRight className="w-3.5 h-3.5" />
                        </FlowButton>
                    </div>
                </div>
            )}
        </div>
    );
}
