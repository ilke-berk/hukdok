// Belge durum çipi (G283, plan §6 K11/K12): kart belge satırında yön + kaynak + durum ilk bakışta okunsun.
// Durum: Taslak (caution/sarı) · Kesin (ok/yeşil); yön oku ↓ gelen · ↑ giden; kaynak simgesi (belge hattı, PDF tezgâhı,
// Word, arşiv aktarımı, teslim). Alanlar eksikse GELEN / BELGE_HATTI / KESIN varsayılır (`types/belge.ts`). Renkler
// tema token'larıyla (`--tone-*-rgb`), koyu temada aynı değişkenler. Türkçe `aria-label`; simgeler `aria-hidden`.
import { ArchiveRestore, ArrowDownLeft, ArrowUpRight, FileText, Inbox, PenLine, Wrench } from "lucide-react";
import { KAYNAK_ETIKETLERI, belgeDurumu, belgeKaynagi, belgeYonu, type BelgeKaynagi, type KartBelgesi } from "@/types/belge";

type Props = {
  doc: Pick<KartBelgesi, "yon" | "kaynak" | "durum">;
  className?: string;
};

const KAYNAK_SIMGELERI: Record<BelgeKaynagi, typeof FileText> = {
  BELGE_HATTI: FileText,
  PDF_ARACLARI: Wrench,
  WORD: PenLine,
  ARSIV_AKTARIM: ArchiveRestore,
  TESLIM: Inbox,
};

export function BelgeDurumCipi({ doc, className = "" }: Props) {
  const yon = belgeYonu(doc);
  const kaynak = belgeKaynagi(doc);
  const durum = belgeDurumu(doc);
  const KaynakSimgesi = KAYNAK_SIMGELERI[kaynak];
  const YonSimgesi = yon === "GIDEN" ? ArrowUpRight : ArrowDownLeft;
  const yonEtiketi = yon === "GIDEN" ? "Giden belge" : "Gelen belge";
  const durumEtiketi = durum === "TASLAK" ? "Taslak" : "Kesin";

  return (
    <span
      data-testid="belge-durum-cipi"
      data-yon={yon}
      data-kaynak={kaynak}
      data-durum={durum}
      className={["inline-flex items-center gap-1 align-middle", className].join(" ")}
    >
      <span
        role="img"
        aria-label={durumEtiketi}
        title={durum === "TASLAK" ? "Taslak: PDF/A yok, Hukukbot'a gitmez, bildirim üretmez" : "Kesinleşmiş belge"}
        className={[
          "inline-flex items-center rounded-[2px] border px-1.5 py-0.5 font-mono text-[10px] tracking-[0.08em] uppercase",
          durum === "TASLAK"
            ? "border-[rgb(var(--tone-caution-rgb))] bg-[rgb(var(--tone-caution-rgb)/0.12)] text-[rgb(var(--tone-caution-rgb))]"
            : "border-[rgb(var(--tone-ok-rgb))] bg-[rgb(var(--tone-ok-rgb)/0.12)] text-[rgb(var(--tone-ok-rgb))]",
        ].join(" ")}
      >
        {durumEtiketi}
      </span>
      <span role="img" aria-label={yonEtiketi} title={yonEtiketi} className="inline-flex items-center text-[var(--fg-muted)]">
        <YonSimgesi aria-hidden="true" className="w-3.5 h-3.5" />
      </span>
      <span role="img" aria-label={`Kaynak: ${KAYNAK_ETIKETLERI[kaynak]}`} title={KAYNAK_ETIKETLERI[kaynak]} className="inline-flex items-center text-[var(--fg-subtle)]">
        <KaynakSimgesi aria-hidden="true" className="w-3.5 h-3.5" />
      </span>
    </span>
  );
}
