import { ScanLine, Bot, Loader2, FileText } from "lucide-react";
import { HairlineCard, Eyebrow } from "@/components/dashboard/primitives";

interface AnalysisPendingProps {
  isAnalyzing?: boolean;
}

const STAGES = [
  { id: "ocr", label: "OCR", desc: "Metin çıkarımı" },
  { id: "match", label: "Eşleştir", desc: "Dava bağlama" },
  { id: "extract", label: "Metadata", desc: "Esas no, taraflar" },
  { id: "summary", label: "Özet", desc: "Konu özeti" },
] as const;

export const AnalysisPending = ({ isAnalyzing = false }: AnalysisPendingProps) => {
  return (
    <HairlineCard padded={false} className="h-full">
      <div className="px-5 py-4 border-b border-[var(--border)] flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-[var(--brand)]" />
          <Eyebrow tone="brand">02 · Analiz</Eyebrow>
          <h2 className="font-display text-[15px] font-medium text-[var(--fg)] tracking-[-0.005em]">
            {isAnalyzing ? "Çıkarımlar Yapılıyor" : "Analiz Bekleniyor"}
          </h2>
        </div>
        {isAnalyzing && (
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--brand)] inline-flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" />
            İşleniyor
          </span>
        )}
      </div>

      <div className="px-5 py-10 grid place-items-center gap-7 text-center">
        {/* Animasyon: scan effect ya da Wand ikon */}
        <div className="relative w-24 h-24 grid place-items-center">
          {isAnalyzing && (
            <span
              className="absolute inset-0 rounded-full border-2 border-[var(--brand)] opacity-50"
              style={{ animation: "hk-pulse-ring 1.6s ease-out infinite" }}
              aria-hidden="true"
            />
          )}
          <div className="relative w-16 h-16 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)]">
            {isAnalyzing ? (
              <ScanLine className="w-7 h-7" strokeWidth={1.6} style={{ animation: "hk-scan 2.4s ease-in-out infinite" }} />
            ) : (
              <FileText className="w-7 h-7" strokeWidth={1.5} />
            )}
          </div>
        </div>

        <div className="grid gap-2 max-w-[40ch]">
          <h3 className="font-display text-[20px] font-medium text-[var(--fg)] tracking-[-0.005em]">
            {isAnalyzing ? "Belgeniz inceleniyor" : "Analiz hazır olunca burada"}
          </h3>
          <p className="text-[13px] text-[var(--fg-muted)] leading-relaxed">
            {isAnalyzing
              ? "Yapay zeka belgenin metnini, taraflarını ve dava bilgilerini çıkarıyor. Bu işlem birkaç saniye sürebilir."
              : 'Sol taraftan bir dosya seçin ve "Analizi Başlat"a tıklayın. Sonuçlar bu alanda görünecek.'}
          </p>
        </div>

        {/* Stage göstergesi (sadece analiz sırasında) */}
        {isAnalyzing && (
          <div className="grid grid-cols-4 gap-3 max-w-[480px] w-full">
            {STAGES.map((s, i) => (
              <div key={s.id} className="flex flex-col items-center gap-1.5">
                <div className="relative w-full h-1 bg-[var(--bg-sunken)] overflow-hidden">
                  <span
                    className="absolute inset-y-0 left-0 bg-[var(--brand)]"
                    style={{
                      animation: `hk-stage 4.8s linear infinite`,
                      animationDelay: `${i * 1.2}s`,
                      width: "100%",
                      transformOrigin: "left",
                    }}
                  />
                </div>
                <div className="font-mono text-[9.5px] tracking-[0.16em] uppercase text-[var(--fg-muted)] font-semibold">
                  {s.label}
                </div>
                <div className="font-mono text-[9px] tracking-[0.04em] text-[var(--fg-subtle)]">
                  {s.desc}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes hk-pulse-ring {
          0% { transform: scale(0.85); opacity: 0.6; }
          100% { transform: scale(1.4); opacity: 0; }
        }
        @keyframes hk-scan {
          0%, 100% { transform: translateY(-4px); opacity: 0.7; }
          50% { transform: translateY(4px); opacity: 1; }
        }
        @keyframes hk-stage {
          0% { transform: scaleX(0); }
          25% { transform: scaleX(1); }
          100% { transform: scaleX(1); opacity: 0.3; }
        }
      `}</style>
    </HairlineCard>
  );
};
