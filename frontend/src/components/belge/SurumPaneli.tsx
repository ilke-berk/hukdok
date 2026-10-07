// Sürüm paneli (G285, plan K13, §6.3 `surum` / `surumler`): kart taslak satırı genişleyince sürüm defteri listelenir;
// "Sürüm kaydet" (+ opsiyonel not) SharePoint'teki son kaydedilmiş `.docx`'in sha'sını deftere yazar. Aynı sha →
// `degisti: false` ("Dosya değişmemiş, not kaydedildi" — satır yine açılır). SharePoint'in her otomatik kaydı sürüm
// DEĞİLDİR; sürüm yalnız bu düğmeyle ve kesinleşmede açılır.
import { useCallback, useEffect, useId, useState } from "react";
import { AlertCircle, History, Info, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { FlowButton } from "@/components/flow/primitives";
import { surumKaydet, surumler as surumleriGetir } from "@/lib/belgeYasamApi";
import type { BelgeSurumu } from "@/types/belge";

type Props = {
  documentId: number;
  /** Kaydedilince (kart `surum_sayisi` tazelensin). */
  onKaydedildi?: () => void;
  /** KESIN belgede kayıt formu yok — yalnız liste. */
  saltOkunur?: boolean;
};

export const DEGISMEDI_METNI = "Dosya değişmemiş, not kaydedildi.";

function tarihMetni(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
}

export function SurumPaneli({ documentId, onKaydedildi, saltOkunur = false }: Props) {
  const kimlik = useId();
  const [liste, setListe] = useState<BelgeSurumu[] | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [listeHatasi, setListeHatasi] = useState<string | null>(null);
  const [not, setNot] = useState("");
  const [kaydediliyor, setKaydediliyor] = useState(false);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    setYukleniyor(true);
    setListeHatasi(null);
    try {
      setListe(await surumleriGetir(documentId));
    } catch (e) {
      setListeHatasi(e instanceof Error && e.message ? e.message : "Sürüm listesi alınamadı.");
    } finally {
      setYukleniyor(false);
    }
  }, [documentId]);

  useEffect(() => {
    void yukle();
  }, [yukle]);

  const kaydet = async () => {
    if (kaydediliyor) return;
    setKaydediliyor(true);
    setHata(null);
    setBilgi(null);
    try {
      const y = await surumKaydet(documentId, not);
      if (y.degisti) {
        setBilgi(`Sürüm ${y.surum_no} kaydedildi.`);
        toast.success(`Sürüm ${y.surum_no} kaydedildi`);
      } else {
        setBilgi(DEGISMEDI_METNI);
      }
      setNot("");
      onKaydedildi?.();
      await yukle();
    } catch (e) {
      setHata(e instanceof Error && e.message ? e.message : "Sürüm kaydedilemedi.");
    } finally {
      setKaydediliyor(false);
    }
  };

  return (
    <section data-testid="surum-paneli" aria-label="Sürümler" className="flex flex-col gap-3 border-t border-[var(--border)] pt-3">
      <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">
        <History className="w-3.5 h-3.5" /> Sürüm defteri
      </div>

      {yukleniyor && liste === null ? (
        <p data-testid="surum-yukleniyor" className="flex items-center gap-2 text-[12px] text-[var(--fg-muted)]">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Sürümler yükleniyor…
        </p>
      ) : listeHatasi ? (
        <p role="alert" className="text-[12px] text-[rgb(var(--tone-danger-rgb))]">{listeHatasi}</p>
      ) : !liste || liste.length === 0 ? (
        <p data-testid="surum-bos" className="text-[12px] text-[var(--fg-muted)]">
          Henüz sürüm kaydedilmedi. Word'de kaydettikten sonra "Sürüm kaydet" ile bu hali deftere yazın.
        </p>
      ) : (
        <ol data-testid="surum-listesi" className="flex flex-col divide-y divide-[var(--border)] rounded-[3px] border border-[var(--border)]">
          {liste.map((s) => (
            <li key={s.surum_no} data-surum={s.surum_no} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-[12px] text-[var(--fg)]">
              <span className="font-mono font-semibold tabular-nums">v{s.surum_no}</span>
              <span className="text-[var(--fg-muted)] tabular-nums">{tarihMetni(s.olusturulma)}</span>
              {s.olusturan_email && <span className="text-[var(--fg-muted)] truncate">{s.olusturan_email}</span>}
              <span className="font-mono text-[10px] text-[var(--fg-subtle)]" title={s.sha256}>
                {s.sha256.slice(0, 8)}
              </span>
              {s.kesin && (
                <span className="rounded-full border border-[rgb(var(--tone-ok-rgb))] px-1.5 text-[10px] text-[rgb(var(--tone-ok-rgb))]">kesin</span>
              )}
              {s.not && <span className="basis-full text-[var(--fg-muted)] break-words">{s.not}</span>}
            </li>
          ))}
        </ol>
      )}

      {!saltOkunur && (
        <div className="flex flex-col gap-2">
          <label htmlFor={`${kimlik}-not`} className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">
            Sürüm notu (opsiyonel)
          </label>
          <textarea
            id={`${kimlik}-not`}
            rows={2}
            maxLength={2000}
            value={not}
            onChange={(e) => setNot(e.target.value)}
            placeholder="Ör. müvekkil düzeltmeleri işlendi"
            className="w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)]"
          />
          <div className="flex flex-wrap items-center gap-3">
            <FlowButton size="sm" onClick={() => void kaydet()} disabled={kaydediliyor}>
              {kaydediliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Sürüm kaydet
            </FlowButton>
            <span className="text-[11px] text-[var(--fg-subtle)]">Word'de kaydedilmemiş değişiklik sürüme girmez.</span>
          </div>
          {bilgi && (
            <p data-testid="surum-bilgi" className="flex items-center gap-1.5 text-[12px] text-[var(--fg-muted)]">
              <Info className="w-3.5 h-3.5" /> {bilgi}
            </p>
          )}
          {hata && (
            <p role="alert" className="flex items-center gap-1.5 text-[12px] text-[rgb(var(--tone-danger-rgb))]">
              <AlertCircle className="w-3.5 h-3.5" /> {hata}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
