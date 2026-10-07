// Belge tezgâhı yükleyicisi (G270): sürükle-bırak + dosya seçici (`ACCEPT_ATTRIBUTE`), çoklu seçimde dosyalar
// SIRAYLA ayrı ayrı yüklenir (K8; sıralama `usePdfTezgah.yukleHepsini`), her satırın durumu burada listelenir.
// Geçersiz uzantı istemcide elenir (backend magic-byte asıl kapı).
import { useCallback, useId, useRef, useState } from "react";
import { AlertCircle, Check, Loader2, Upload } from "lucide-react";
import { ACCEPT_ATTRIBUTE, isValidFile } from "@/lib/fileValidation";
import type { YuklemeDurumu } from "./usePdfTezgah";

type Props = {
  onDosyalar: (files: File[]) => void;
  yuklemeler: YuklemeDurumu[];
  yukleniyor: boolean;
  onTemizle?: () => void;
};

export function PdfYukleyici({ onDosyalar, yuklemeler, yukleniyor, onTemizle }: Props) {
  const girdiId = useId();
  const girdiRef = useRef<HTMLInputElement>(null);
  const [surukleme, setSurukleme] = useState(false);
  const [atlananlar, setAtlananlar] = useState<string[]>([]);

  const dosyalariAl = useCallback(
    (liste: FileList | File[] | null) => {
      const hepsi = Array.from(liste ?? []);
      const gecerli = hepsi.filter(isValidFile);
      setAtlananlar(hepsi.filter((f) => !isValidFile(f)).map((f) => f.name));
      if (gecerli.length > 0) onDosyalar(gecerli);
    },
    [onDosyalar],
  );

  return (
    <div className="flex flex-col gap-2" data-testid="pdf-yukleyici">
      <div
        role="button"
        tabIndex={0}
        aria-label="Dosya yükle"
        onClick={() => girdiRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            girdiRef.current?.click();
          }
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setSurukleme(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setSurukleme(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          if (e.currentTarget === e.target) setSurukleme(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setSurukleme(false);
          dosyalariAl(e.dataTransfer.files);
        }}
        className={[
          "cursor-pointer border-[1.5px] border-dashed rounded-[3px] px-4 py-5 text-center transition-colors",
          surukleme
            ? "border-[var(--brand)] bg-[var(--brand-soft)]"
            : "border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--brand)]",
        ].join(" ")}
      >
        <input
          id={girdiId}
          ref={girdiRef}
          data-testid="pdf-yukleyici-girdi"
          type="file"
          multiple
          accept={ACCEPT_ATTRIBUTE}
          className="hidden"
          onChange={(e) => {
            dosyalariAl(e.target.files);
            e.target.value = "";
          }}
        />
        <div className="mx-auto w-9 h-9 grid place-items-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]">
          {yukleniyor ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" strokeWidth={1.6} />}
        </div>
        <p className="mt-2 font-display text-[14px] font-medium text-[var(--fg)]">
          {surukleme ? "Bırakın" : "Dosyaları buraya sürükleyin"}
        </p>
        <p className="mt-1 text-[12px] text-[var(--fg-muted)]">
          ya da tıklayıp seçin · PDF, Word, Excel, TIFF, JPG, PNG, UDF — her biri PDF olarak tezgâha gelir
        </p>
      </div>

      {atlananlar.length > 0 && (
        <p role="status" className="text-[12px] text-[rgb(var(--tone-caution-rgb))]">
          Desteklenmeyen format atlandı: {atlananlar.slice(0, 3).join(", ")}
          {atlananlar.length > 3 ? ` (+${atlananlar.length - 3})` : ""}
        </p>
      )}

      {yuklemeler.length > 0 && (
        <ul aria-label="Yükleme durumu" className="flex flex-col gap-1 text-[12px]">
          {yuklemeler.map((y) => (
            <li key={y.anahtar} className="flex items-start gap-2 min-w-0" data-durum={y.durum}>
              {y.durum === "yukleniyor" && <Loader2 className="w-3.5 h-3.5 mt-0.5 animate-spin text-[var(--fg-subtle)] shrink-0" />}
              {y.durum === "tamam" && <Check className="w-3.5 h-3.5 mt-0.5 text-[rgb(var(--tone-ok-rgb))] shrink-0" />}
              {y.durum === "hata" && <AlertCircle className="w-3.5 h-3.5 mt-0.5 text-[rgb(var(--tone-danger-rgb))] shrink-0" />}
              <span className="min-w-0">
                <span className="text-[var(--fg)] break-all">{y.ad}</span>
                {y.durum === "yukleniyor" && <span className="text-[var(--fg-subtle)]"> · yükleniyor</span>}
                {y.durum === "hata" && <span className="block text-[rgb(var(--tone-danger-rgb))]">{y.mesaj}</span>}
              </span>
            </li>
          ))}
          {!yukleniyor && onTemizle && (
            <li>
              <button type="button" onClick={onTemizle} className="text-[11px] text-[var(--fg-subtle)] hover:text-[var(--fg)] underline-offset-2 hover:underline">
                Listeyi temizle
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
