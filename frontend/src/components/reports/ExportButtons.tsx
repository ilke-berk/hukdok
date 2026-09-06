import { useState } from "react";
import { FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { RaporFormati, RaporTanimi } from "@/lib/reports";
import { RAPOR_EXPORT_HATASI, RaporApiError, dosyayiIndir, exportReport } from "@/lib/reports";
import { FlowButton } from "@/components/flow/primitives";

type ExportButtonsProps = {
    tanim: RaporTanimi;
    /** Tanım geçersizken iki düğme de kapalı. */
    aktif: boolean;
    /** Taslak yüklü şablonla birebir aynıysa koşuya şablon kimliği yazılır; aksi halde null. */
    sablonId: number | null;
    /** Önizlemeden bilinen toplam satır (toast için); yoksa null. */
    satirSayisi: number | null;
    /** Koşu tamamlandı — İndirme geçmişi bayatladı. */
    onIndirildi?: (kosuId: number | null) => void;
};

const KAYNAK = "manuel" as const;

/**
 * Önizleme araç çubuğundaki "Excel indir" / "CSV indir" (G134). Gövde §2.4 birebir
 * (`exportReport`), dosya adı sunucunun `Content-Disposition`'ından; 413'te tavan mesajı +
 * filtre daraltma önerisi (`raporHatasiCevir`).
 */
export function ExportButtons({ tanim, aktif, sablonId, satirSayisi, onIndirildi }: ExportButtonsProps) {
    const [indiriliyor, setIndiriliyor] = useState<RaporFormati | null>(null);

    const indir = async (format: RaporFormati) => {
        if (!aktif || indiriliyor) return;
        setIndiriliyor(format);
        try {
            const sonuc = await exportReport(tanim, format, sablonId, KAYNAK);
            dosyayiIndir(sonuc);
            const satir = satirSayisi !== null ? ` · ${satirSayisi.toLocaleString("tr-TR")} satır` : "";
            toast.success(`İndirildi: ${sonuc.dosyaAdi}${satir}`);
            onIndirildi?.(sonuc.kosuId);
        } catch (err) {
            console.error(err);
            const mesaj = err instanceof Error ? err.message : RAPOR_EXPORT_HATASI;
            if (err instanceof RaporApiError && err.status === 413) {
                toast.error("Rapor satır tavanını aşıyor", { description: mesaj });
            } else {
                toast.error("Rapor indirilemedi", { description: mesaj });
            }
        } finally {
            setIndiriliyor(null);
        }
    };

    const baslik = aktif ? undefined : "İndirmek için geçerli bir tanım gerekir (en az bir kolon, filtreler tam)";

    return (
        <div className="flex items-center gap-1.5">
            <FlowButton
                variant="secondary"
                size="sm"
                disabled={!aktif || indiriliyor !== null}
                onClick={() => void indir("xlsx")}
                title={baslik ?? "Excel (.xlsx) olarak indir"}
            >
                {indiriliyor === "xlsx" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileSpreadsheet className="w-3.5 h-3.5" />}
                Excel indir
            </FlowButton>
            <FlowButton
                variant="secondary"
                size="sm"
                disabled={!aktif || indiriliyor !== null}
                onClick={() => void indir("csv")}
                title={baslik ?? "CSV olarak indir"}
            >
                {indiriliyor === "csv" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
                CSV indir
            </FlowButton>
        </div>
    );
}
