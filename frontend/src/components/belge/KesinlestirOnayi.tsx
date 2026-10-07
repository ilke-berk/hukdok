// Kesinleştirme ve "yeni sürüm taslağı" onayları (G285, plan K14, §6.3 `kesinlestir` / `yeni-surum-taslagi`).
// İkisi de idempotenttir: `istek_kimligi` diyalog AÇILIŞINDA üretilir, kapanana dek sabit kalır — hata sonrası tekrar
// deneme aynı kimlikle gider, sunucu işi bitirmişse `reused: true` döner. Kesinleşme tek yönlüdür (gönderilen değişmez);
// düzeltme yeni taslak olarak açılır. Diyaloglar `theme-classic` (portal kabuğun dışında).
import { useEffect, useState, type ReactNode } from "react";
import { AlertCircle, FileCheck2, FilePen, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FlowButton } from "@/components/flow/primitives";
import { BelgeYasamApiError, kesinlestir, yeniSurumTaslagi } from "@/lib/belgeYasamApi";
import { istekKimligiUret } from "@/lib/pdfAraclariApi";
import type { KesinlestirYaniti, YeniSurumTaslagiYaniti } from "@/types/belge";

export const KESINLESTIR_METNI =
  "Word'de kaydettiğinizden emin olun. Belge PDF/A olarak arşivlenir, karta giden olarak düşer, bir daha düzenlenemez; düzeltme için yeni sürüm taslağı açılır.";
export const ZATEN_KESIN_METNI = "Belge zaten kesinleşmiş; kart yenileniyor.";
export const MESGUL_METNI = "Dönüşüm hattı şu anda meşgul; birkaç dakika sonra aynı düğmeyle tekrar deneyin.";

type Belge = { id: number; ad: string };

function hataMetni(e: unknown): string {
  if (e instanceof BelgeYasamApiError) {
    if (e.status === 409 && e.errorKod === "zaten_kesin") return ZATEN_KESIN_METNI;
    if (e.status === 503) return MESGUL_METNI;
  }
  return e instanceof Error && e.message.trim() ? e.message : "İşlem tamamlanamadı.";
}

function OnayKabugu<T>({
  acik,
  testId,
  baslik,
  simge,
  aciklama,
  govde,
  dugme,
  belge,
  calistir,
  onKapat,
  onBasari,
  onZatenKesin,
}: {
  acik: boolean;
  testId: string;
  baslik: string;
  simge: ReactNode;
  aciklama: ReactNode;
  govde: ReactNode;
  dugme: string;
  belge: Belge | null;
  calistir: (id: number, istekKimligi: string) => Promise<T>;
  onKapat: () => void;
  onBasari: (yanit: T) => void;
  onZatenKesin?: () => void;
}) {
  const [istekKimligi, setIstekKimligi] = useState("");
  const [calisiyor, setCalisiyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    if (!acik) return;
    setIstekKimligi(istekKimligiUret());
    setHata(null);
    setCalisiyor(false);
  }, [acik]);

  const onayla = async () => {
    if (!belge || !istekKimligi || calisiyor) return;
    setCalisiyor(true);
    setHata(null);
    try {
      onBasari(await calistir(belge.id, istekKimligi));
    } catch (e) {
      setHata(hataMetni(e));
      if (e instanceof BelgeYasamApiError && e.status === 409 && e.errorKod === "zaten_kesin") onZatenKesin?.();
    } finally {
      setCalisiyor(false);
    }
  };

  return (
    <Dialog open={acik} onOpenChange={(v) => !v && !calisiyor && onKapat()}>
      <DialogContent
        data-testid={testId}
        className="theme-classic max-w-[520px] bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-[18px]">
            {simge}
            {baslik}
          </DialogTitle>
          <DialogDescription>{aciklama}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-1">
          {govde}
          {hata && (
            <div role="alert" className="flex items-start gap-2 rounded-[3px] border border-[rgb(var(--tone-danger-rgb))] bg-[var(--bg)] px-3 py-2 text-[13px] text-[var(--fg)]">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-[rgb(var(--tone-danger-rgb))]" />
              <span>{hata}</span>
            </div>
          )}
          <div className="flex items-center justify-end gap-2 pt-1">
            <FlowButton size="sm" variant="secondary" onClick={onKapat} disabled={calisiyor}>
              Vazgeç
            </FlowButton>
            <FlowButton size="sm" onClick={() => void onayla()} disabled={!belge || calisiyor}>
              {calisiyor && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              {dugme}
            </FlowButton>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type KesinlestirProps = {
  acik: boolean;
  belge: Belge | null;
  onKapat: () => void;
  onBasari: (yanit: KesinlestirYaniti) => void;
  /** 409 "zaten kesin": kart bayat — çağıran yeniler. */
  onZatenKesin?: () => void;
};

export function KesinlestirOnayi({ acik, belge, onKapat, onBasari, onZatenKesin }: KesinlestirProps) {
  return (
    <OnayKabugu<KesinlestirYaniti>
      acik={acik}
      testId="kesinlestir-onayi"
      baslik="Kesinleştir"
      simge={<FileCheck2 className="w-4 h-4 text-[var(--brand)]" />}
      aciklama={belge ? <span className="font-medium text-[var(--fg)] break-all">{belge.ad}</span> : null}
      govde={
        <p data-testid="kesinlestir-metni" className="text-[13px] leading-relaxed text-[var(--fg)]">
          Word'de kaydettiğinizden emin olun. Belge PDF/A olarak arşivlenir, karta <strong>giden</strong> olarak düşer, bir
          daha düzenlenemez; düzeltme için yeni sürüm taslağı açılır.
        </p>
      }
      dugme="Kesinleştir"
      belge={belge}
      calistir={kesinlestir}
      onKapat={onKapat}
      onZatenKesin={onZatenKesin}
      onBasari={(y) => {
        toast.success(y.reused ? "Belge zaten bu istekle kesinleşmişti" : "Belge kesinleşti", {
          description: "PDF/A arşive yükleniyor; kartta Giden listesinde.",
        });
        onBasari(y);
      }}
    />
  );
}

type YeniSurumProps = {
  acik: boolean;
  belge: Belge | null;
  onKapat: () => void;
  onBasari: (yanit: YeniSurumTaslagiYaniti) => void;
};

export function YeniSurumTaslagiOnayi({ acik, belge, onKapat, onBasari }: YeniSurumProps) {
  return (
    <OnayKabugu<YeniSurumTaslagiYaniti>
      acik={acik}
      testId="yeni-surum-onayi"
      baslik="Yeni sürüm taslağı"
      simge={<FilePen className="w-4 h-4 text-[var(--brand)]" />}
      aciklama={belge ? <span className="font-medium text-[var(--fg)] break-all">{belge.ad}</span> : null}
      govde={
        <p className="text-[13px] leading-relaxed text-[var(--fg)]">
          Kesinleşmiş belge değişmez ("ne gönderildi" korunur). Word aslının kopyası yeni bir <strong>taslak</strong> olarak
          açılır ve bu belgeye bağlanır.
        </p>
      }
      dugme="Yeni taslak aç"
      belge={belge}
      calistir={yeniSurumTaslagi}
      onKapat={onKapat}
      onBasari={(y) => {
        toast.success(y.reused ? "Bu istekle açılmış taslak zaten var" : "Yeni sürüm taslağı açıldı", {
          description: "Kartın Taslaklar listesinde.",
        });
        onBasari(y);
      }}
    />
  );
}
