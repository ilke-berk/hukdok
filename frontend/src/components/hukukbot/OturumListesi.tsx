import { useState, type KeyboardEvent } from "react";
import { Check, Loader2, MessageSquare, Pencil, Pin, PinOff, Plus, Trash2, X } from "lucide-react";
import type { HukukbotOturumOzeti } from "@/types/hukukbot";

type OturumListesiProps = {
  /** Sıralı liste (sabitlenenler üstte — `oturumlariSirala`). */
  oturumlar: HukukbotOturumOzeti[];
  seciliId: string | null;
  yukleniyor: boolean;
  hata: string | null;
  onSec: (id: string) => void;
  onYeni: () => void;
  onYenidenAdlandir: (id: string, baslik: string) => void;
  onSabitle: (oturum: HukukbotOturumOzeti) => void;
  /** Onay diyaloğu sayfada sorulur (useConfirm) — burası yalnız isteği iletir. */
  onSil: (oturum: HukukbotOturumOzeti) => void;
};

const IKON_DUGME =
  "w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors shrink-0";

/**
 * Sol sütun (G205): "Yeni sohbet" + sohbet listesi. Sabitlenenler ayrı başlık altında üstte;
 * her satırda başlık düzenleme (satır içi; Enter kaydeder, Esc vazgeçer), sabitle/çöz, sil.
 */
export function OturumListesi({
  oturumlar,
  seciliId,
  yukleniyor,
  hata,
  onSec,
  onYeni,
  onYenidenAdlandir,
  onSabitle,
  onSil,
}: OturumListesiProps) {
  const [duzenlenen, setDuzenlenen] = useState<string | null>(null);
  const [taslak, setTaslak] = useState("");

  const duzenlemeyiBaslat = (o: HukukbotOturumOzeti) => {
    setDuzenlenen(o.id);
    setTaslak(o.title);
  };
  const duzenlemeyiBitir = (o: HukukbotOturumOzeti, kaydet: boolean) => {
    const yeni = taslak.trim();
    setDuzenlenen(null);
    if (kaydet && yeni && yeni !== o.title) onYenidenAdlandir(o.id, yeni);
  };
  const duzenlemeTusu = (e: KeyboardEvent<HTMLInputElement>, o: HukukbotOturumOzeti) => {
    if (e.key === "Enter") {
      e.preventDefault();
      duzenlemeyiBitir(o, true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      duzenlemeyiBitir(o, false);
    }
  };

  const sabitler = oturumlar.filter((o) => o.is_pinned);
  const digerleri = oturumlar.filter((o) => !o.is_pinned);

  const satir = (o: HukukbotOturumOzeti) => {
    const secili = o.id === seciliId;
    const duzenleniyor = duzenlenen === o.id;
    return (
      <li
        key={o.id}
        data-testid="hukukbot-oturum"
        data-oturum-id={o.id}
        data-sabit={o.is_pinned ? "1" : "0"}
        className={[
          "group flex items-start gap-1 px-2 py-2 rounded-[3px] border transition-colors",
          secili
            ? "bg-[var(--brand-soft)] border-[var(--brand)]"
            : "border-transparent hover:bg-[var(--bg-sunken)]",
        ].join(" ")}
      >
        {duzenleniyor ? (
          <div className="flex-1 min-w-0 flex items-center gap-1">
            <input
              autoFocus
              aria-label="Sohbet başlığı"
              value={taslak}
              maxLength={200}
              onChange={(e) => setTaslak(e.target.value)}
              onKeyDown={(e) => duzenlemeTusu(e, o)}
              onBlur={() => duzenlemeyiBitir(o, true)}
              className="flex-1 min-w-0 h-8 px-2 bg-[var(--bg)] border border-[var(--brand)] rounded-[3px] text-[13px] text-[var(--fg)] focus:outline-none"
            />
            <button
              type="button"
              aria-label="Başlığı kaydet"
              className={IKON_DUGME}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => duzenlemeyiBitir(o, true)}
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              aria-label="Düzenlemeden vazgeç"
              className={IKON_DUGME}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => duzenlemeyiBitir(o, false)}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onSec(o.id)}
              aria-current={secili ? "page" : undefined}
              className="flex-1 min-w-0 text-left grid gap-0.5 cursor-pointer"
            >
              <span className="flex items-center gap-1.5 min-w-0">
                {o.is_pinned && <Pin className="w-3 h-3 shrink-0 text-[var(--brand)]" aria-label="Sabitlenmiş" />}
                <span
                  data-testid="hukukbot-oturum-baslik"
                  className={[
                    "truncate text-[13px]",
                    secili ? "text-[var(--fg)] font-medium" : "text-[var(--fg)]",
                  ].join(" ")}
                >
                  {o.title || "Adsız sohbet"}
                </span>
              </span>
              {o.preview && (
                <span className="truncate text-[11.5px] text-[var(--fg-subtle)]">{o.preview}</span>
              )}
            </button>
            <div className="flex items-center opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 transition-opacity">
              <button
                type="button"
                aria-label={`Başlığı düzenle: ${o.title}`}
                className={IKON_DUGME}
                onClick={() => duzenlemeyiBaslat(o)}
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                aria-label={o.is_pinned ? `Sabitlemeyi kaldır: ${o.title}` : `Sabitle: ${o.title}`}
                className={IKON_DUGME}
                onClick={() => onSabitle(o)}
              >
                {o.is_pinned ? <PinOff className="w-3.5 h-3.5" /> : <Pin className="w-3.5 h-3.5" />}
              </button>
              <button
                type="button"
                aria-label={`Sil: ${o.title}`}
                className={`${IKON_DUGME} hover:!text-tone-danger`}
                onClick={() => onSil(o)}
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </>
        )}
      </li>
    );
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 border-b border-[var(--border)]">
        <button
          type="button"
          onClick={onYeni}
          className="w-full h-9 inline-flex items-center justify-center gap-2 rounded-[3px] border border-[var(--brand)] bg-brand-solid text-white text-[13px] font-medium tracking-[0.03em] hover:opacity-90 transition-opacity"
        >
          <Plus className="w-4 h-4" />
          Yeni sohbet
        </button>
      </div>
      <nav aria-label="Sohbetler" className="flex-1 min-h-0 overflow-y-auto p-2">
        {yukleniyor && (
          <div role="status" className="flex items-center gap-2 px-2 py-3 text-[12.5px] text-[var(--fg-muted)]">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            Sohbetler yükleniyor...
          </div>
        )}
        {!yukleniyor && hata && (
          <p role="alert" className="px-2 py-3 text-[12.5px] text-tone-danger">
            {hata}
          </p>
        )}
        {!yukleniyor && !hata && oturumlar.length === 0 && (
          <div className="px-2 py-6 grid justify-items-center gap-2 text-center text-[12.5px] text-[var(--fg-muted)]">
            <MessageSquare className="w-5 h-5 text-[var(--fg-subtle)]" aria-hidden="true" />
            Henüz sohbet yok.
          </div>
        )}
        {sabitler.length > 0 && (
          <>
            <h3 className="px-2 pt-1 pb-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
              Sabitlenenler
            </h3>
            <ul className="grid gap-0.5 mb-3" data-testid="hukukbot-sabitler">
              {sabitler.map(satir)}
            </ul>
          </>
        )}
        {digerleri.length > 0 && (
          <>
            {sabitler.length > 0 && (
              <h3 className="px-2 pt-1 pb-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                Sohbetler
              </h3>
            )}
            <ul className="grid gap-0.5">{digerleri.map(satir)}</ul>
          </>
        )}
      </nav>
    </div>
  );
}
