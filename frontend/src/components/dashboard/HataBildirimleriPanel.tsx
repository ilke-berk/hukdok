import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { BellRing, CheckCircle2, Gavel, User2 } from "lucide-react";
import { CardListSkeleton } from "@/components/skeletons/Skeletons";
import { HairlineCard } from "@/components/dashboard/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { formatAgo } from "@/lib/relativeTime";
import { type HataBildirimi, alicilarMetni, guvenliIcYol, kisiEtiketi, listele } from "@/lib/hataBildirimleri";

export const HATA_PANO_HATASI = "Hata bildirimleri alınamadı — sunucuya ulaşılamadı.";

/**
 * İdari pano "Hata Bildirimleri" (02.10.2026): avukatların kartlardaki zilden bildirdiği,
 * henüz kapatılmamış hatalar — dava ve müvekkil kartları birlikte, en yeni üstte.
 *
 * Zil bildirimi okunduktan sonra iş unutulmasın diye ayrı listedir: satır, bildirim
 * KAPATILANA dek burada durur (okundu işaretinden bağımsız). Satıra tıklamak ilgili
 * kartı açar; düzeltme ve kapatma kartın üstündeki şeritten yapılır.
 *
 * Hata boş listeye ÇEVRİLMEZ (G002 dersi): "açık bildirim yok" ekranı ulaşılamayan
 * sunucuyu maskelememeli.
 */
export function HataBildirimleriPanel() {
  const navigate = useNavigate();
  const [liste, setListe] = useState<HataBildirimi[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [yukleniyor, setYukleniyor] = useState(true);
  const [tur, setTur] = useState(0);

  const tekrarDene = useCallback(() => setTur((t) => t + 1), []);

  useEffect(() => {
    let iptal = false;
    setYukleniyor(true);
    listele()
      .then((satirlar) => {
        if (iptal) return;
        setListe(satirlar);
        setHata(null);
      })
      .catch(() => {
        if (iptal) return;
        setListe(null);
        setHata(HATA_PANO_HATASI);
      })
      .finally(() => {
        if (!iptal) setYukleniyor(false);
      });
    return () => {
      iptal = true;
    };
  }, [tur]);

  return (
    <HairlineCard className="mt-3" padded={false}>
      {yukleniyor ? (
        <CardListSkeleton count={2} itemClassName="h-14" className="p-4" label="Hata bildirimleri yükleniyor…" />
      ) : hata ? (
        <DataErrorBanner description={hata} onRetry={tekrarDene} className="border-0" />
      ) : !liste || liste.length === 0 ? (
        <div className="grid place-items-center gap-2 py-7 text-center text-[var(--fg-subtle)]" data-testid="hata-pano-bos">
          <CheckCircle2 className="w-7 h-7 opacity-40" />
          <p className="text-[13px] text-[var(--fg-muted)] font-medium">Açık hata bildirimi yok</p>
          <p className="text-[11px] max-w-[40ch] leading-relaxed">
            Avukatların dava ve müvekkil kartlarındaki zilden bildirdiği hatalar burada listelenir.
          </p>
        </div>
      ) : (
        <>
          <div className="px-4 py-2 border-b border-[var(--border)] font-mono text-[10px] tracking-[0.1em] uppercase text-[var(--fg-subtle)]">
            {liste.length} açık bildirim
          </div>
          <div className="flex flex-col">
            {liste.map((b) => {
              const Hedef = b.case_id != null ? Gavel : User2;
              const yol = guvenliIcYol(b.link);
              return (
                <button
                  key={b.id}
                  type="button"
                  disabled={!yol}
                  onClick={() => { if (yol) navigate(yol); }}
                  data-testid="hata-pano-satiri"
                  className="grid grid-cols-[auto_1fr_auto] gap-3 items-start px-4 py-3 text-left border-t border-[var(--border)] first:border-t-0 transition-colors hover:bg-[var(--bg)]"
                >
                  <BellRing className="w-3.5 h-3.5 mt-0.5 shrink-0 text-tone-danger" strokeWidth={2} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="font-display font-medium text-[13.5px] text-[var(--fg)] truncate">
                        {b.alan_etiketi}
                      </span>
                      {b.hedef_etiketi && (
                        <span className="inline-flex items-center gap-1 min-w-0 text-[11.5px] text-[var(--fg-muted)]">
                          <Hedef className="w-3 h-3 shrink-0" />
                          <span className="truncate">{b.hedef_etiketi}</span>
                        </span>
                      )}
                    </span>
                    {(b.dogru_deger || b.aciklama) && (
                      <span className="block mt-0.5 text-[11.5px] text-[var(--fg-muted)] line-clamp-2">
                        {b.dogru_deger ? `Doğrusu: ${b.dogru_deger}` : ""}
                        {b.dogru_deger && b.aciklama ? " — " : ""}
                        {b.aciklama ?? ""}
                      </span>
                    )}
                    <span className="block mt-1 text-[11px] text-[var(--fg-subtle)]">
                      {kisiEtiketi(b.bildiren_ad, b.bildiren_email)}
                      {b.alicilar?.length > 0 && ` → ${alicilarMetni(b.alicilar)}`}
                    </span>
                  </span>
                  <span className="font-mono text-[10px] text-[var(--fg-subtle)] shrink-0">{formatAgo(b.created_at)}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </HairlineCard>
  );
}

export default HataBildirimleriPanel;
