import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { LineListSkeleton } from "@/components/skeletons/Skeletons";
import {
  Check,
  Menu,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import type { HukukbotOturumOzeti } from "@/types/hukukbot";
import { oturumlariSuz, tariheGoreGrupla } from "@/components/hukukbot/yardimcilar";

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
  /** HukuDok menüsünü açar (odak modunda Topbar'daki ☰'nin yeri burasıdır). */
  onMenu?: () => void;
  /** Masaüstü: listeyi 48 px raya daraltır / geri açar. */
  onDaraltAc?: () => void;
  /** Mobil çekmece: listeyi kapatır. */
  onKapat?: () => void;
  /** true → yalnız ikon rayı (☰, aç, yeni sohbet). */
  daraltilmis?: boolean;
};

const IKON_DUGME =
  "w-7 h-7 grid place-items-center rounded-[3px] text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors shrink-0";

const RAY_DUGME =
  "w-8 h-8 grid place-items-center rounded-[3px] border border-[var(--border)] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors shrink-0";

const GRUP_BASLIGI =
  "px-2 pt-2 pb-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]";

/** `grid` DEĞİL: grid öğesinin min-width'i içerik kadardır, uzun başlık satırı taşırır (truncate çalışmaz). */
const LISTE = "flex flex-col gap-px min-w-0";

const MENU_OGE =
  "w-full flex items-center gap-2 px-2.5 py-1.5 text-left text-[12.5px] text-[var(--fg)] hover:bg-[var(--bg-sunken)] transition-colors";

/**
 * Sol sütun (G205; 28.09 yeniden tasarım): üst satırda HukuDok menüsü ☰ + "Hukukbot" + daralt düğmesi,
 * "Yeni sohbet", arama kutusu (başlık/önizleme, Türkçe harf duyarsız), sabitlenenler üstte, geri kalanı
 * tarih gruplarında (Bugün / Dün / Son 7 gün / Son 30 gün / Daha eski). Satır eylemleri (başlık düzenle —
 * satır içi, Enter kaydeder, Esc vazgeçer —, sabitle/çöz, sil) "⋯" menüsündedir. `daraltilmis` iken yalnız
 * ikon rayı çizilir.
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
  onMenu,
  onDaraltAc,
  onKapat,
  daraltilmis = false,
}: OturumListesiProps) {
  const [duzenlenen, setDuzenlenen] = useState<string | null>(null);
  const [taslak, setTaslak] = useState("");
  const [arama, setArama] = useState("");
  const [acikMenu, setAcikMenu] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Açık "⋯" menüsü dışarı tık / Esc ile kapanır.
  useEffect(() => {
    if (!acikMenu) return;
    const tik = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setAcikMenu(null);
    };
    const tus = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setAcikMenu(null);
    };
    document.addEventListener("mousedown", tik);
    document.addEventListener("keydown", tus);
    return () => {
      document.removeEventListener("mousedown", tik);
      document.removeEventListener("keydown", tus);
    };
  }, [acikMenu]);

  if (daraltilmis) {
    return (
      <div className="flex flex-col items-center gap-2 py-3 h-full" data-testid="hukukbot-ray">
        {onMenu && (
          <button type="button" onClick={onMenu} aria-label="HukuDok menüsünü aç" title="HukuDok menüsü" className={RAY_DUGME}>
            <Menu className="w-4 h-4" />
          </button>
        )}
        {onDaraltAc && (
          <button
            type="button"
            onClick={onDaraltAc}
            aria-label="Sohbet geçmişini aç"
            title="Sohbet geçmişini aç"
            className={RAY_DUGME}
          >
            <PanelLeftOpen className="w-4 h-4" />
          </button>
        )}
        <button type="button" onClick={onYeni} aria-label="Yeni sohbet" title="Yeni sohbet" className={RAY_DUGME}>
          <Plus className="w-4 h-4" />
        </button>
      </div>
    );
  }

  const duzenlemeyiBaslat = (o: HukukbotOturumOzeti) => {
    setAcikMenu(null);
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

  const suzulmus = oturumlariSuz(oturumlar, arama);
  const sabitler = suzulmus.filter((o) => o.is_pinned);
  const gruplar = tariheGoreGrupla(suzulmus.filter((o) => !o.is_pinned));

  const satir = (o: HukukbotOturumOzeti) => {
    const secili = o.id === seciliId;
    const duzenleniyor = duzenlenen === o.id;
    const menuAcik = acikMenu === o.id;
    return (
      <li
        key={o.id}
        data-testid="hukukbot-oturum"
        data-oturum-id={o.id}
        data-sabit={o.is_pinned ? "1" : "0"}
        className={[
          "group relative flex items-center gap-1 min-w-0 pl-2 pr-1 py-1.5 rounded-[3px] transition-colors",
          secili ? "bg-[var(--brand-soft)]" : "hover:bg-[var(--bg-sunken)]",
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
              className="flex-1 min-w-0 h-7 px-2 bg-[var(--bg)] border border-[var(--brand)] rounded-[3px] text-[13px] text-[var(--fg)] focus:outline-none"
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
              title={o.preview ? `${o.title}\n${o.preview}` : o.title}
              className="flex-1 min-w-0 text-left flex items-center gap-1.5 cursor-pointer py-0.5"
            >
              {o.is_pinned && <Pin className="w-3 h-3 shrink-0 text-[var(--brand)]" aria-label="Sabitlenmiş" />}
              <span
                data-testid="hukukbot-oturum-baslik"
                className={[
                  "truncate text-[13px]",
                  secili ? "text-[var(--brand)] font-medium" : "text-[var(--fg)]",
                ].join(" ")}
              >
                {o.title || "Adsız sohbet"}
              </span>
            </button>
            <div ref={menuAcik ? menuRef : undefined} className="relative shrink-0">
              <button
                type="button"
                aria-label={`Sohbet eylemleri: ${o.title}`}
                aria-haspopup="menu"
                aria-expanded={menuAcik}
                onClick={() => setAcikMenu(menuAcik ? null : o.id)}
                className={`${IKON_DUGME} ${
                  menuAcik ? "opacity-100" : "opacity-100 md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100"
                }`}
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>
              {menuAcik && (
                <div
                  role="menu"
                  className="absolute right-0 top-full mt-1 z-20 w-44 py-1 rounded-[4px] border border-[var(--border-strong)] bg-[var(--bg-elevated)] shadow-[0_12px_30px_-12px_rgba(0,0,0,0.45)]"
                >
                  <button
                    type="button"
                    role="menuitem"
                    aria-label={`Başlığı düzenle: ${o.title}`}
                    className={MENU_OGE}
                    onClick={() => duzenlemeyiBaslat(o)}
                  >
                    <Pencil className="w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                    Yeniden adlandır
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    aria-label={o.is_pinned ? `Sabitlemeyi kaldır: ${o.title}` : `Sabitle: ${o.title}`}
                    className={MENU_OGE}
                    onClick={() => {
                      setAcikMenu(null);
                      onSabitle(o);
                    }}
                  >
                    {o.is_pinned ? (
                      <PinOff className="w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                    ) : (
                      <Pin className="w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                    )}
                    {o.is_pinned ? "Sabitlemeyi kaldır" : "Sabitle"}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    aria-label={`Sil: ${o.title}`}
                    className={`${MENU_OGE} !text-tone-danger`}
                    onClick={() => {
                      setAcikMenu(null);
                      onSil(o);
                    }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Sil
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </li>
    );
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="p-3 grid gap-2.5 border-b border-[var(--border)]">
        <div className="flex items-center gap-2 min-w-0">
          {onMenu && (
            <button type="button" onClick={onMenu} aria-label="HukuDok menüsünü aç" title="HukuDok menüsü" className={RAY_DUGME}>
              <Menu className="w-4 h-4" />
            </button>
          )}
          <span className="flex-1 min-w-0 truncate font-display text-[16px] font-medium text-[var(--fg)]">Hukukbot</span>
          {onDaraltAc && (
            <button
              type="button"
              onClick={onDaraltAc}
              aria-label="Sohbet geçmişini daralt"
              title="Sohbet geçmişini daralt"
              className={IKON_DUGME}
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          )}
          {onKapat && (
            <button type="button" onClick={onKapat} aria-label="Sohbet listesini kapat" className={IKON_DUGME}>
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={onYeni}
          className="w-full h-9 inline-flex items-center justify-center gap-2 rounded-[3px] border border-[var(--brand)] bg-brand-solid text-white text-[13px] font-medium tracking-[0.03em] hover:opacity-90 transition-opacity"
        >
          <Plus className="w-4 h-4" />
          Yeni sohbet
        </button>
        {oturumlar.length > 0 && (
          <div className="relative">
            <Search
              className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-subtle)] pointer-events-none"
              aria-hidden="true"
            />
            <input
              type="search"
              value={arama}
              onChange={(e) => setArama(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setArama("");
              }}
              placeholder="Sohbetlerde ara"
              aria-label="Sohbetlerde ara"
              data-testid="hukukbot-oturum-arama"
              className="w-full h-8 pl-8 pr-2 bg-[var(--bg-elevated)] border border-[var(--border)] rounded-[3px] text-[12.5px] text-[var(--fg)] placeholder:text-[var(--fg-subtle)] focus:border-[var(--brand)] focus:outline-none"
            />
          </div>
        )}
      </div>
      <nav aria-label="Sohbetler" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-2 [scrollbar-width:thin]">
        {yukleniyor && (
          <LineListSkeleton count={6} className="px-2 py-3" label="Sohbetler yükleniyor..." />
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
        {oturumlar.length > 0 && suzulmus.length === 0 && (
          <p className="px-2 py-4 text-center text-[12.5px] text-[var(--fg-muted)]" data-testid="hukukbot-arama-bos">
            Eşleşen sohbet yok.
          </p>
        )}
        {sabitler.length > 0 && (
          <>
            <h3 className={GRUP_BASLIGI}>Sabitlenenler</h3>
            <ul className={`${LISTE} mb-2`} data-testid="hukukbot-sabitler">
              {sabitler.map(satir)}
            </ul>
          </>
        )}
        {gruplar.map(({ grup, oturumlar: gruptakiler }) => (
          <section key={grup} aria-label={grup} className="mb-2">
            <h3 className={GRUP_BASLIGI}>{grup}</h3>
            <ul className={LISTE}>{gruptakiler.map(satir)}</ul>
          </section>
        ))}
      </nav>
    </div>
  );
}
