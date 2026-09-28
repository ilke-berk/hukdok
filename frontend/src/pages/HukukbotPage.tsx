import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Loader2, Menu, MessageSquare, Scale, X } from "lucide-react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { useConfirm } from "@/hooks/useConfirm";
import { HukukbotApiError, hukukbotApi } from "@/lib/hukukbotApi";
import type { HukukbotKaynak, HukukbotOturumOzeti } from "@/types/hukukbot";
import { OturumListesi } from "@/components/hukukbot/OturumListesi";
import { MesajBalonu } from "@/components/hukukbot/MesajBalonu";
import { SoruKutusu } from "@/components/hukukbot/SoruKutusu";
import {
  AKIS_HATA_MESAJI,
  HUKUDOK_BELGE_ACILAMADI,
  OTURUM_BULUNAMADI,
  YENI_SOHBET_BASLIGI,
  baslikUret,
  ekranMesajlari,
  gecmisUret,
  hataMetni,
  iptalMi,
  kaynakHukdokId,
  mesajAnahtari,
  oturumlariSirala,
  type EkranMesaji,
} from "@/components/hukukbot/yardimcilar";

/**
 * `/hukukbot` (G205, karar 021) — Hukukbot sohbeti HukuDok kabuğu içinde. Eski hukbot arayüzü yalnız
 * İŞLEV referansıdır; giriş/MSAL/profil kabuktan gelir, Hukukbot'a tek yol `lib/hukukbotApi.ts` (G204).
 *
 * - Sol: sohbet listesi (sabitlenenler üstte; yeni / başlık düzenle / sabitle / ONAYLI sil). 768 px altında
 *   liste çekmeceye döner (375 px'te yatay kaydırma yok).
 * - Orta: mesajlar; yanıt `/ask` NDJSON akışından parça parça yazılır, "Durdur" AbortSignal ile keser.
 *   Mesajlar ve yazı kutusu ortalanmış tek okuma sütununda (`OKUMA_SUTUNU`). Boş sohbette kutu karşılamanın
 *   hemen altında, ilk sorudan sonra dipte. Akış yalnız kullanıcı zaten dipteyse aşağı kaydırır — yukarı
 *   kaydırıp okurken sayfa onu dibe çekmez (`dipteRef`); kendi sorusunu gönderince dibe yapışır.
 * - Seçili sohbet URL'de: `/hukukbot?s=<id>` → yenilemede aynı sohbet açılır. Yeni sohbette ilk soru
 *   gönderilmeden önce oturum `POST /sessions` ile açılır (akış oturum kimliği döndürmez) ve URL'ye yazılır.
 * - Default export: rota `React.lazy` ile bağlanır (G206).
 */
/** Mesajlar ve yazı kutusunun ortak okuma sütunu — geniş ekranda satırlar uzamasın. */
const OKUMA_SUTUNU = "mx-auto w-full max-w-3xl";

export default function HukukbotPage() {
  useSetPageTitle("Hukukbot", ["Araçlar", "Hukukbot"]);
  const confirm = useConfirm();
  const [params, setParams] = useSearchParams();
  const seciliId = params.get("s") || null;

  const [oturumlar, setOturumlar] = useState<HukukbotOturumOzeti[]>([]);
  const [listeYukleniyor, setListeYukleniyor] = useState(true);
  const [listeHatasi, setListeHatasi] = useState<string | null>(null);
  const [mesajlar, setMesajlar] = useState<EkranMesaji[]>([]);
  const [oturumYukleniyor, setOturumYukleniyor] = useState(false);
  const [oturumHatasi, setOturumHatasi] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [inen, setInen] = useState<string | null>(null);
  const [cekmece, setCekmece] = useState(false);

  /** Süren `/ask` akışının iptali ("Durdur", sohbet değişimi, sayfadan çıkış). */
  const akisRef = useRef<AbortController | null>(null);
  /** Ekrandaki mesajların ait olduğu oturum — kendi açtığımız oturum URL'ye yazılınca yeniden çekilmez. */
  const yuklenenIdRef = useRef<string | null>(null);
  const kaydirmaRef = useRef<HTMLDivElement | null>(null);
  /** Kullanıcı mesaj listesinin dibinde mi (son ~80 px) — otomatik kaydırma yalnız bu true iken. */
  const dipteRef = useRef(true);

  // Sohbet listesi — açılışta bir kez.
  useEffect(() => {
    const ac = new AbortController();
    hukukbotApi
      .oturumlariListele(ac.signal)
      .then((liste) => {
        setOturumlar(oturumlariSirala(liste));
        setListeHatasi(null);
      })
      .catch((e: unknown) => {
        if (!iptalMi(e)) setListeHatasi(hataMetni(e));
      })
      .finally(() => {
        if (!ac.signal.aborted) setListeYukleniyor(false);
      });
    return () => ac.abort();
  }, []);

  // Seçili sohbetin mesajları — URL'deki `s` değişince.
  useEffect(() => {
    if (!seciliId) {
      setOturumHatasi(null);
      setOturumYukleniyor(false);
      if (yuklenenIdRef.current !== null) {
        yuklenenIdRef.current = null;
        setMesajlar([]);
      }
      return;
    }
    if (yuklenenIdRef.current === seciliId) return;
    dipteRef.current = true;
    const ac = new AbortController();
    setOturumYukleniyor(true);
    setOturumHatasi(null);
    setMesajlar([]);
    hukukbotApi
      .oturumGetir(seciliId, ac.signal)
      .then((oturum) => {
        yuklenenIdRef.current = seciliId;
        setMesajlar(ekranMesajlari(oturum.messages ?? []));
      })
      .catch((e: unknown) => {
        if (iptalMi(e)) return;
        yuklenenIdRef.current = seciliId;
        setOturumHatasi(e instanceof HukukbotApiError && e.status === 404 ? OTURUM_BULUNAMADI : hataMetni(e));
      })
      .finally(() => {
        if (!ac.signal.aborted) setOturumYukleniyor(false);
      });
    return () => ac.abort();
  }, [seciliId]);

  // Sayfadan çıkışta süren akışı bırak.
  useEffect(() => {
    return () => {
      akisRef.current?.abort();
    };
  }, []);

  // Yeni parça / mesaj → kullanıcı dipteyse en alta kaydır.
  useEffect(() => {
    const el = kaydirmaRef.current;
    if (el && dipteRef.current) el.scrollTop = el.scrollHeight;
  }, [mesajlar]);

  const kaydirildi = () => {
    const el = kaydirmaRef.current;
    if (el) dipteRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  // Çekmece açıkken Esc kapatır.
  useEffect(() => {
    if (!cekmece) return;
    const tus = (e: KeyboardEvent) => {
      if (e.key === "Escape") setCekmece(false);
    };
    document.addEventListener("keydown", tus);
    return () => document.removeEventListener("keydown", tus);
  }, [cekmece]);

  const akisiKes = () => {
    akisRef.current?.abort();
    akisRef.current = null;
  };

  const sec = (id: string) => {
    setCekmece(false);
    if (id === seciliId) return;
    akisiKes();
    setParams({ s: id });
  };

  const yeniSohbet = () => {
    setCekmece(false);
    akisiKes();
    yuklenenIdRef.current = null;
    setMesajlar([]);
    setOturumHatasi(null);
    if (seciliId) setParams({});
  };

  const gonder = async (soru: string) => {
    const metin = soru.trim();
    if (!metin || gonderiliyor) return;

    const gecmis = gecmisUret(mesajlar);
    dipteRef.current = true;
    const yanitAnahtari = mesajAnahtari("model");
    setMesajlar((onceki) => [
      ...onceki,
      { anahtar: mesajAnahtari("kullanici"), role: "user", content: metin },
      { anahtar: yanitAnahtari, role: "model", content: "", akiyor: true },
    ]);
    setOturumHatasi(null);
    setGonderiliyor(true);
    const ac = new AbortController();
    akisRef.current = ac;
    const yanitiGuncelle = (f: (m: EkranMesaji) => EkranMesaji) =>
      setMesajlar((onceki) => onceki.map((m) => (m.anahtar === yanitAnahtari ? f(m) : m)));

    let oturumId = seciliId;
    try {
      if (!oturumId) {
        const yeni = await hukukbotApi.oturumOlustur(baslikUret(metin));
        oturumId = yeni.id;
        const ozet: HukukbotOturumOzeti = {
          id: yeni.id,
          title: yeni.title,
          created_at: yeni.created_at,
          is_pinned: yeni.is_pinned,
          preview: null,
        };
        setOturumlar((onceki) => oturumlariSirala([ozet, ...onceki.filter((o) => o.id !== ozet.id)]));
        if (ac.signal.aborted) throw new DOMException("İstek iptal edildi.", "AbortError");
        yuklenenIdRef.current = yeni.id;
        setParams({ s: yeni.id });
      }
      for await (const olay of hukukbotApi.ask(
        { question: metin, history: gecmis.length > 0 ? gecmis : null },
        { sessionId: oturumId, signal: ac.signal },
      )) {
        if (olay.type === "content") {
          const parca = olay.data;
          yanitiGuncelle((m) => ({ ...m, content: m.content + parca }));
        } else if (olay.type === "sources") {
          const kaynaklar = olay.data;
          yanitiGuncelle((m) => ({ ...m, sources: kaynaklar }));
        } else {
          console.warn("Hukukbot akışı hata olayıyla bitti", olay.data);
          yanitiGuncelle((m) => ({ ...m, hata: AKIS_HATA_MESAJI }));
        }
      }
    } catch (e) {
      if (iptalMi(e)) {
        yanitiGuncelle((m) => ({ ...m, durduruldu: true }));
      } else {
        const mesaj = hataMetni(e);
        yanitiGuncelle((m) => ({ ...m, hata: mesaj }));
      }
    } finally {
      yanitiGuncelle((m) => ({ ...m, akiyor: false }));
      if (akisRef.current === ac) akisRef.current = null;
      setGonderiliyor(false);
      if (oturumId) {
        const id = oturumId;
        setOturumlar((onceki) => onceki.map((o) => (o.id === id ? { ...o, preview: metin.slice(0, 100) } : o)));
      }
    }
  };

  const yenidenAdlandir = async (id: string, baslik: string) => {
    const eski = oturumlar.find((o) => o.id === id)?.title;
    setOturumlar((onceki) => onceki.map((o) => (o.id === id ? { ...o, title: baslik } : o)));
    try {
      await hukukbotApi.oturumGuncelle(id, { title: baslik });
    } catch (e) {
      if (eski !== undefined) {
        setOturumlar((onceki) => onceki.map((o) => (o.id === id ? { ...o, title: eski } : o)));
      }
      toast.error(`Başlık kaydedilemedi. ${hataMetni(e)}`);
    }
  };

  const sabitle = async (oturum: HukukbotOturumOzeti) => {
    const yeniDurum = !oturum.is_pinned;
    const uygula = (durum: boolean) =>
      setOturumlar((onceki) =>
        oturumlariSirala(onceki.map((o) => (o.id === oturum.id ? { ...o, is_pinned: durum } : o))),
      );
    uygula(yeniDurum);
    try {
      await hukukbotApi.oturumGuncelle(oturum.id, { is_pinned: yeniDurum });
    } catch (e) {
      uygula(!yeniDurum);
      toast.error(`Sabitleme kaydedilemedi. ${hataMetni(e)}`);
    }
  };

  const sil = async (oturum: HukukbotOturumOzeti) => {
    const onay = await confirm({
      tone: "destructive",
      title: "Sohbet silinsin mi?",
      context: "Hukukbot",
      body: `"${oturum.title || "Adsız sohbet"}" sohbeti ve tüm mesajları kalıcı olarak silinir.`,
      irreversible: true,
      confirmLabel: "Sil",
    });
    if (!onay) return;
    try {
      await hukukbotApi.oturumSil(oturum.id);
      setOturumlar((onceki) => onceki.filter((o) => o.id !== oturum.id));
      if (oturum.id === seciliId) yeniSohbet();
      toast.success("Sohbet silindi.");
    } catch (e) {
      toast.error(`Sohbet silinemedi. ${hataMetni(e)}`);
    }
  };

  const indir = async (kaynak: HukukbotKaynak) => {
    // HukuDok'tan aktarılmış belge → HukuDok'un kendi ucundan (SharePoint arşivi), yeni sekmede okunur.
    // Sekme ilk await'ten ÖNCE açılır; sonradan açılanı pop-up engelleyicisi keser.
    const belgeId = kaynakHukdokId(kaynak);
    if (belgeId !== null) {
      const sekme = window.open("", "_blank");
      setInen(kaynak.filename);
      try {
        await hukukbotApi.hukudokBelgesiniAc(belgeId, sekme);
      } catch (e) {
        sekme?.close();
        const ek = e instanceof HukukbotApiError && e.status === 404 ? " Belge silinmiş ya da erişiminiz yok." : "";
        toast.error(`${HUKUDOK_BELGE_ACILAMADI}${ek}`);
      } finally {
        setInen(null);
      }
      return;
    }
    // İlk kurulumdan kalan belge (HukuDok kaydı yok) → Hukukbot'un yerel PDF klasörü.
    setInen(kaynak.filename);
    try {
      await hukukbotApi.indir(kaynak.filename);
    } catch (e) {
      toast.error(`Dosya açılamadı. ${hataMetni(e)}`);
    } finally {
      setInen(null);
    }
  };

  const bosSohbet = !oturumYukleniyor && !oturumHatasi && mesajlar.length === 0;

  const aktifBaslik = seciliId
    ? (oturumlar.find((o) => o.id === seciliId)?.title ?? "Sohbet")
    : YENI_SOHBET_BASLIGI;

  const liste = (
    <OturumListesi
      oturumlar={oturumlar}
      seciliId={seciliId}
      yukleniyor={listeYukleniyor}
      hata={listeHatasi}
      onSec={sec}
      onYeni={yeniSohbet}
      onYenidenAdlandir={yenidenAdlandir}
      onSabitle={sabitle}
      onSil={sil}
    />
  );

  return (
    <div
      data-testid="hukukbot-sayfasi"
      className="flex w-full min-w-0 h-[calc(100dvh-7.25rem)] min-h-[420px] border border-[var(--border)] bg-[var(--bg-elevated)] rounded-[3px] overflow-hidden"
    >
      <aside
        aria-label="Sohbet listesi"
        className="hidden md:flex w-72 lg:w-80 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--bg)]"
      >
        {liste}
      </aside>

      {cekmece && (
        <div
          className="md:hidden fixed inset-0 z-40 flex"
          role="dialog"
          aria-modal="true"
          aria-label="Sohbetler"
          data-testid="hukukbot-cekmece"
        >
          <div className="w-[85vw] max-w-xs h-full flex flex-col bg-[var(--bg)] border-r border-[var(--border)] shadow-xl">
            <div className="h-12 shrink-0 flex items-center justify-between px-3 border-b border-[var(--border)]">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                Sohbetler
              </span>
              <button
                type="button"
                aria-label="Sohbet listesini kapat"
                onClick={() => setCekmece(false)}
                className="w-8 h-8 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)]"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 min-h-0">{liste}</div>
          </div>
          <button
            type="button"
            aria-label="Kapat"
            tabIndex={-1}
            className="flex-1 bg-black/40"
            onClick={() => setCekmece(false)}
          />
        </div>
      )}

      <section aria-label="Sohbet" className="flex-1 min-w-0 flex flex-col">
        <header className="h-12 shrink-0 flex items-center gap-2 px-3 md:px-5 border-b border-[var(--border)]">
          <button
            type="button"
            onClick={() => setCekmece(true)}
            aria-label="Sohbet listesini aç"
            className="md:hidden w-8 h-8 grid place-items-center rounded-[3px] border border-[var(--border)] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:border-[var(--brand)] shrink-0"
          >
            <Menu className="w-4 h-4" />
          </button>
          <MessageSquare className="hidden md:block w-4 h-4 text-[var(--brand)] shrink-0" aria-hidden="true" />
          <h2 className="truncate text-[14px] font-medium text-[var(--fg)]" data-testid="hukukbot-aktif-baslik">
            {aktifBaslik}
          </h2>
        </header>

        <div
          ref={kaydirmaRef}
          onScroll={kaydirildi}
          className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-3 md:px-6"
        >
          <div className={`${OKUMA_SUTUNU} pt-5 pb-8 min-h-full flex flex-col`}>
            {oturumYukleniyor && (
              <div role="status" className="flex items-center gap-2 text-[13px] text-[var(--fg-muted)]">
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                Sohbet yükleniyor...
              </div>
            )}
            {!oturumYukleniyor && oturumHatasi && (
              <p role="alert" data-testid="hukukbot-oturum-hatasi" className="text-[13px] text-tone-danger">
                {oturumHatasi}
              </p>
            )}
            {bosSohbet && (
              <div className="flex-1 grid place-items-center pb-[8vh]">
                <div className="w-full grid justify-items-center gap-3 text-center">
                  <div className="w-12 h-12 grid place-items-center rounded-full bg-[var(--brand-soft)] text-[var(--brand)]">
                    <Scale className="w-5 h-5" strokeWidth={1.8} aria-hidden="true" />
                  </div>
                  <h3 className="font-display text-[24px] font-medium text-[var(--fg)]">Hukukbot'a sorun</h3>
                  <p className="max-w-md text-[13px] leading-[1.6] text-[var(--fg-muted)]">
                    Mevzuat ve içtihat sorularınızı yazın; yanıtın dayandığı kaynaklar cevabın altında listelenir.
                  </p>
                  <div className="w-full mt-4 text-left">
                    <SoruKutusu gonderiliyor={gonderiliyor} onGonder={gonder} onDurdur={akisiKes} autoFocus />
                  </div>
                </div>
              </div>
            )}
            {mesajlar.length > 0 && (
              <div className="grid gap-6" data-testid="hukukbot-mesajlar">
                {mesajlar.map((m) => (
                  <MesajBalonu key={m.anahtar} mesaj={m} onIndir={indir} inen={inen} />
                ))}
              </div>
            )}
          </div>
        </div>

        {!bosSohbet && (
          <div className="shrink-0 px-3 md:px-6 pb-3 pt-2 bg-gradient-to-t from-[var(--bg-elevated)] from-60% to-transparent -mt-6 relative">
            <div className={OKUMA_SUTUNU}>
              <SoruKutusu gonderiliyor={gonderiliyor} onGonder={gonder} onDurdur={akisiKes} />
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
