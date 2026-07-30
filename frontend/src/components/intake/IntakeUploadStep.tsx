import { FileText, Sparkles, X } from "lucide-react";
import { toast } from "sonner";

import { FlowButton, FlowCard } from "@/components/flow/primitives";
import { FlowDropZone } from "@/components/flow/FlowDropZone";
import { ANALYZE_SECONDS_PER_DOC, MAX_INTAKE_FILES, type IntakeFile } from "@/hooks/useCaseIntake";

interface IntakeUploadStepProps {
  files: IntakeFile[];
  onAddFiles: (files: File[]) => void;
  onRemoveFile: (id: string) => void;
  onStart: () => void;
}

const formatEta = (count: number): string => {
  const totalSec = count * ANALYZE_SECONDS_PER_DOC;
  if (totalSec < 90) return `~${totalSec} sn`;
  return `~${Math.round(totalSec / 60)} dk`;
};

/**
 * Adım 1 — Yükleme: çoklu dosya dropzone (max 15, /process uzantı beyaz
 * listesi). "Analiz Et"e basılana kadar hiçbir işlem başlamaz.
 */
export function IntakeUploadStep({ files, onAddFiles, onRemoveFile, onStart }: IntakeUploadStepProps) {
  const handleSelect = (incoming: File | File[]) => {
    const list = Array.isArray(incoming) ? incoming : [incoming];
    const room = MAX_INTAKE_FILES - files.length;
    if (list.length > room) {
      toast.warning(`En fazla ${MAX_INTAKE_FILES} belge yüklenebilir — ${Math.max(0, room)} boş yer var.`);
    }
    onAddFiles(list);
  };

  return (
    <div className="grid gap-5">
      <FlowDropZone
        onFileSelect={handleSelect}
        selectedFile={null}
        onClearFile={() => { /* çoklu liste aşağıda yönetilir */ }}
      />

      {files.length > 0 && (
        <FlowCard padded={false}>
          <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
              Seçilen belgeler · <span className="text-[var(--fg)] font-semibold">{files.length}</span>/{MAX_INTAKE_FILES}
            </span>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              {files.length} belge × ~{ANALYZE_SECONDS_PER_DOC} sn ≈ {formatEta(files.length)}
            </span>
          </div>
          <ul className="divide-y divide-[var(--border)]">
            {files.map(f => (
              <li key={f.id} className="px-5 py-2.5 flex items-center gap-3">
                <FileText className="w-4 h-4 text-[var(--fg-subtle)] shrink-0" strokeWidth={1.5} />
                <span className="text-[13px] text-[var(--fg)] break-all min-w-0 flex-1">{f.file.name}</span>
                <span className="font-mono text-[10px] text-[var(--fg-subtle)] shrink-0">
                  {(f.file.size / 1024 / 1024).toFixed(2)} MB
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveFile(f.id)}
                  aria-label={`${f.file.name} dosyasını kaldır`}
                  className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <div className="px-5 py-4 border-t border-[var(--border)] flex items-center justify-between gap-4">
            <p className="text-[12px] text-[var(--fg-muted)] leading-snug">
              Dava dilekçesi, tensip zaptı, poliçe, atama yazısı… — aynı davanın
              belgelerini birlikte yükleyin; sistem tek dava kartı taslağı çıkarır.
            </p>
            <FlowButton variant="primary" onClick={onStart} disabled={files.length === 0}>
              <Sparkles className="w-3.5 h-3.5" />
              Analiz Et
            </FlowButton>
          </div>
        </FlowCard>
      )}
    </div>
  );
}
