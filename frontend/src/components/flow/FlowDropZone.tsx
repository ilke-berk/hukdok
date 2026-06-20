import { useCallback, useState } from "react";
import { Upload, FileText, X, FolderUp } from "lucide-react";
import { toast } from "sonner";
import { FlowButton } from "./primitives";

interface FlowDropZoneProps {
  onFileSelect: (files: File | File[]) => void;
  selectedFile: File | null;
  onClearFile: () => void;
  isAnalyzing?: boolean;
  isComplete?: boolean;
}

const VALID_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
  "text/plain",
  "application/xml",
  "text/xml",
  "application/zip",
];

function isValidFile(file: File): boolean {
  return VALID_TYPES.includes(file.type) || file.name.toLowerCase().endsWith(".udf");
}

function warnInvalidFiles(invalidNames: string[]) {
  if (invalidNames.length === 0) return;
  const preview = invalidNames.slice(0, 5).join(", ");
  const suffix = invalidNames.length > 5 ? ` (+${invalidNames.length - 5} dosya daha)` : "";
  toast.warning(
    `${invalidNames.length} dosya desteklenmeyen formatta atlandı: ${preview}${suffix}`,
    { duration: 6000 }
  );
}

export function FlowDropZone({
  onFileSelect,
  selectedFile,
  onClearFile,
  isAnalyzing = false,
  isComplete = false,
}: FlowDropZoneProps) {
  const [state, setState] = useState<"idle" | "dragover">("idle");
  const [dragCount, setDragCount] = useState(0);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setState("dragover");
    const count = e.dataTransfer?.items?.length ?? 0;
    setDragCount(count);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setState("dragover");
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.currentTarget === e.target) {
      setState("idle");
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setState("idle");
    setDragCount(0);

    const files = Array.from(e.dataTransfer.files);
    const validFiles: File[] = [];
    const invalidNames: string[] = [];
    for (const file of files) {
      if (isValidFile(file)) validFiles.push(file);
      else invalidNames.push(file.name);
    }
    warnInvalidFiles(invalidNames);
    if (validFiles.length === 0) return;
    if (validFiles.length === 1) onFileSelect(validFiles[0]);
    else onFileSelect(validFiles);
  }, [onFileSelect]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const allFiles = Array.from(e.target.files);
      const validFiles: File[] = [];
      const invalidNames: string[] = [];
      for (const file of allFiles) {
        if (isValidFile(file)) validFiles.push(file);
        else invalidNames.push(file.name);
      }
      warnInvalidFiles(invalidNames);
      if (validFiles.length > 0) onFileSelect(validFiles);
    }
  };

  const handleClick = () => {
    document.getElementById("hidden-file-input")?.click();
  };

  // FILE SELECTED — kart görünümü
  if (selectedFile) {
    return (
      <div className="bg-[var(--bg-elevated)] border border-[var(--border)] p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <div className="w-11 h-11 grid place-items-center bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
              <FileText className="w-5 h-5" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <p className="font-display font-medium text-[15px] text-[var(--fg)] break-all">
                {selectedFile.name}
              </p>
              <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] mt-1">
                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · {selectedFile.type || "Bilinmeyen tür"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClearFile}
            disabled={isAnalyzing}
            aria-label="Dosyayı kaldır"
            className="w-8 h-8 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors disabled:opacity-30"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="mt-4 pt-4 border-t border-[var(--border)] flex items-baseline gap-2">
          <span className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            Sonraki adım
          </span>
          <span className="text-[13px] text-[var(--fg-muted)] leading-snug">
            {isComplete
              ? "Sağdaki AI çıkarımlarını gözden geçirip onaylayın."
              : "Belge türünü seçip analizi başlatın."}
          </span>
        </div>
      </div>
    );
  }

  // EMPTY — drop zone idle/dragover
  const isDragover = state === "dragover";
  return (
    <div
      onClick={handleClick}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      className={[
        "relative cursor-pointer border-[1.5px] border-dashed text-center transition-all duration-200",
        isDragover
          ? "border-[var(--brand)] bg-[var(--brand-soft)] scale-[1.005]"
          : "border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)]/40",
      ].join(" ")}
      style={isDragover ? {
        backgroundImage: "repeating-linear-gradient(45deg, transparent 0 10px, var(--brand-soft) 10px 20px)",
      } : undefined}
    >
      <input
        id="hidden-file-input"
        type="file"
        className="hidden"
        multiple
        accept=".pdf,.docx,.doc,.txt,.udf"
        onChange={handleFileInput}
      />

      <div className="px-10 py-14 flex flex-col items-center gap-5">
        <div
          className={[
            "w-16 h-16 grid place-items-center transition-colors",
            isDragover ? "bg-[var(--brand)] text-[var(--brand-fg)]" : "bg-[var(--brand-soft)] text-[var(--brand)]",
          ].join(" ")}
        >
          <Upload className="w-7 h-7" strokeWidth={1.6} />
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="font-display text-[22px] font-medium tracking-[-0.01em] text-[var(--fg)]">
            {isDragover ? "Bırakın — dosyayı kuyruğa alalım" : "Belgeyi buraya sürükleyin"}
          </h3>
          <p className="font-sans text-[13px] text-[var(--fg-muted)] max-w-[44ch]">
            Veya alttaki butonlardan seçin. PDF, DOCX, DOC, TXT, UDF (UYAP) — maksimum 50 MB.
          </p>
        </div>

        {isDragover && dragCount > 0 && (
          <div className="inline-flex items-baseline gap-2 px-3 py-1.5 bg-[var(--brand)] text-[var(--brand-fg)]">
            <span className="font-display text-[18px] font-medium tabular-nums">{dragCount}</span>
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase">dosya</span>
          </div>
        )}

        {!isDragover && (
          <div className="flex flex-wrap items-center justify-center gap-3 pt-1">
            <FlowButton variant="primary" onClick={(e) => { e.stopPropagation(); handleClick(); }}>
              <Upload className="w-3.5 h-3.5" />
              Dosya Seç
            </FlowButton>
            <FlowButton variant="secondary" onClick={(e) => { e.stopPropagation(); handleClick(); }}>
              <FolderUp className="w-3.5 h-3.5" />
              Klasör Seç
            </FlowButton>
          </div>
        )}

        <div className="flex items-center gap-3 pt-2 font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] border-t border-dashed border-[var(--border)] pt-3 w-full justify-center">
          <span>OCR otomatik</span>
          <span className="h-3 w-px bg-[var(--border-strong)]" />
          <span>AI eşleştirme</span>
          <span className="h-3 w-px bg-[var(--border-strong)]" />
          <span>⌘V Yapıştır</span>
        </div>
      </div>
    </div>
  );
}
