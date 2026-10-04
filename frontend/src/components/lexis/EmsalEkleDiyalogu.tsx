import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import { lexisApi } from "@/lib/lexisApi";
import type { KutuphaneKaydi } from "@/types/lexis";
import { BosDurum } from "./ortak";
import { hataMetni, iptalMi, raporKunyesi } from "./yardimcilar";

type EmsalEkleDiyaloguProps = {
  acik: boolean;
  /** Listede zaten olan raporlar gösterilmez. */
  haricSha: readonly string[];
  onSec: (kayit: KutuphaneKaydi) => void;
  onKapat: () => void;
};

/** Kütüphaneden elle emsal ekleme: metinle arar, seçilen rapor dosyaya göre puanlanıp listeye girer. */
export function EmsalEkleDiyalogu({ acik, haricSha, onSec, onKapat }: EmsalEkleDiyaloguProps) {
  const [metin, setMetin] = useState("");
  const [sonuclar, setSonuclar] = useState<KutuphaneKaydi[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    if (!acik) return;
    const ac = new AbortController();
    const zamanlayici = setTimeout(() => {
      lexisApi
        .kutuphaneAra({ metin }, ac.signal)
        .then((liste) => {
          setSonuclar(liste);
          setHata(null);
        })
        .catch((e: unknown) => {
          if (!iptalMi(e)) setHata(hataMetni(e));
        });
    }, metin ? 250 : 0);
    return () => {
      clearTimeout(zamanlayici);
      ac.abort();
    };
  }, [acik, metin]);

  const gorunen = sonuclar?.filter((k) => !haricSha.includes(k.okuma.sha256)) ?? null;

  return (
    <Dialog open={acik} onOpenChange={(o) => !o && onKapat()}>
      <DialogContent
        className="theme-classic max-w-xl max-h-[80vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none sm:rounded-none text-[var(--fg)]"
        data-testid="lexis-emsal-ekle"
      >
        <DialogHeader>
          <DialogTitle className="font-display text-[18px] font-medium text-[var(--fg)]">Kütüphaneden emsal ekle</DialogTitle>
          <DialogDescription className="text-[12.5px] text-[var(--fg-muted)]">
            Seçtiğiniz rapor bu dosyaya göre puanlanır ve taslak yazılırken bakılan raporlara eklenir.
          </DialogDescription>
        </DialogHeader>
        <label className="relative block">
          <span className="sr-only">Kütüphanede ara</span>
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)]" aria-hidden="true" />
          <input
            type="search"
            value={metin}
            onChange={(e) => setMetin(e.target.value)}
            placeholder="İşlem, olay, mahkeme ya da metin…"
            className="w-full h-9 pl-8 pr-2 border border-[var(--border)] bg-[var(--bg)] text-[13px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] rounded-[3px] focus:border-[var(--brand)] focus:outline-none"
          />
        </label>
        {hata && (
          <p role="alert" className="text-[12.5px] text-tone-danger">
            {hata}
          </p>
        )}
        {!hata && gorunen === null && <LineListSkeleton count={4} label="Kütüphane yükleniyor…" />}
        {gorunen && gorunen.length === 0 && <BosDurum>Eklenebilecek rapor bulunamadı.</BosDurum>}
        {gorunen && gorunen.length > 0 && (
          <ul className="grid gap-1.5">
            {gorunen.map((k) => (
              <li key={k.okuma.sha256}>
                <button
                  type="button"
                  onClick={() => onSec(k)}
                  className="w-full text-left border border-[var(--border)] bg-[var(--bg)] px-3 py-2 hover:border-[var(--brand)] transition-colors"
                >
                  <div className="text-[12.5px] font-medium text-[var(--fg)]">
                    {raporKunyesi(k.okuma)}
                    {k.etiketler.tibbi_islem && <span className="font-normal text-[var(--fg-muted)]"> · {k.etiketler.tibbi_islem}</span>}
                  </div>
                  <div className="text-[12px] leading-[1.45] text-[var(--fg-muted)]">{k.etiketler.iddia_ozeti}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
