// Belge tezgâhı sağ bölgesi (G270): dört işlem — birleştir (işaretli dosyalar, liste sırasıyla), böl (aralık metni ya da
// her sayfa ayrı), sıkıştır (üç seviye), damga (metin/konum/sayfalar/punto/renk). Karart, not ve sayfa düzenle yuvaları
// `disabled` + "sonraki sürüm" (G271/G272 açar). Çıktı adı sunucudan gelen `ad`dır; indirme seçili dosyayı indirir.
import { useId, useState, type ReactNode } from "react";
import { Combine, Download, Eraser, Layers, Loader2, MessageSquareText, Scissors, Shrink, Stamp } from "lucide-react";
import { FlowButton } from "@/components/flow/primitives";
import { bolAraliklariniAyristir, damgaSayfalariniAyristir } from "@/lib/pdfAraclariApi";
import {
  DAMGA_KONUMLARI,
  SIKISTIRMA_SEVIYELERI,
  type DamgaKonumu,
  type Dosya,
  type Islem,
  type IslemIstegi,
  type SikistirmaSeviyesi,
} from "@/types/pdfAraclari";

type Props = {
  secili: Dosya | null;
  isaretliler: Dosya[];
  surenIslem: Islem | null;
  indiriliyor: boolean;
  onIslem: (istek: IslemIstegi) => void;
  onIndir: () => void;
};

const KONUM_ADLARI: Record<DamgaKonumu, string> = {
  "sag-ust": "Sağ üst",
  "sol-ust": "Sol üst",
  "sag-alt": "Sağ alt",
  "sol-alt": "Sol alt",
  orta: "Orta",
};

const SEVIYE_ADLARI: Record<SikistirmaSeviyesi, string> = {
  ekran: "Ekran (en küçük)",
  ebook: "E-kitap (dengeli)",
  yazici: "Yazıcı (en kaliteli)",
};

const SONRAKI_SURUM = "Sonraki sürümde";

const GIRDI_SINIFI =
  "w-full rounded-[3px] border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[13px] text-[var(--fg)] focus:outline-none focus:border-[var(--brand)]";
const ETIKET_SINIFI = "block font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)] mb-1";

function Bolum({ baslik, ikon, children }: { baslik: string; ikon: ReactNode; children: ReactNode }) {
  return (
    <section className="border-b border-[var(--border)] pb-4 last:border-b-0">
      <h3 className="flex items-center gap-2 font-display text-[14px] font-medium text-[var(--fg)] mb-2">
        <span className="text-[var(--brand)]">{ikon}</span>
        {baslik}
      </h3>
      {children}
    </section>
  );
}

export function IslemPaneli({ secili, isaretliler, surenIslem, indiriliyor, onIslem, onIndir }: Props) {
  const kimlik = useId();
  const mesgul = surenIslem !== null;
  const toplamSayfa = secili?.sayfa ?? 0;

  const [birlestirAdi, setBirlestirAdi] = useState("birlestirilmis.pdf");
  const [bolKipi, setBolKipi] = useState<"aralik" | "her_sayfa">("aralik");
  const [bolMetni, setBolMetni] = useState("");
  const [seviye, setSeviye] = useState<SikistirmaSeviyesi>("ebook");
  const [damgaMetni, setDamgaMetni] = useState("ASLI GİBİDİR");
  const [damgaKonumu, setDamgaKonumu] = useState<DamgaKonumu>("sag-ust");
  const [damgaSayfalari, setDamgaSayfalari] = useState("");
  const [damgaPunto, setDamgaPunto] = useState(12);
  const [damgaRengi, setDamgaRengi] = useState("#b00020");

  const bolAraliklari = bolKipi === "aralik" ? bolAraliklariniAyristir(bolMetni, toplamSayfa) : null;
  const bolGecerli = !!secili && (bolKipi === "her_sayfa" ? toplamSayfa >= 1 : bolAraliklari !== null);
  const damgaSayfaListesi = damgaSayfalariniAyristir(damgaSayfalari, toplamSayfa);
  const damgaGecerli =
    !!secili && damgaMetni.trim().length > 0 && damgaMetni.length <= 120 && damgaSayfaListesi !== null && damgaPunto >= 4 && damgaPunto <= 144;

  const suruyor = (islem: Islem) => surenIslem === islem;
  const ikon = (islem: Islem, Ikon: typeof Combine) =>
    suruyor(islem) ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Ikon className="w-3.5 h-3.5" />;

  return (
    <div className="flex flex-col gap-4" data-testid="islem-paneli">
      <div className="text-[12px] text-[var(--fg-muted)]">
        {secili ? (
          <>
            Seçili: <span className="text-[var(--fg)] font-medium break-all">{secili.ad}</span> · {secili.sayfa} sayfa
          </>
        ) : (
          "İşlem için soldan bir dosya seçin."
        )}
      </div>

      <Bolum baslik="Birleştir" ikon={<Combine className="w-4 h-4" />}>
        <p className="text-[12px] text-[var(--fg-muted)] mb-2">
          Soldaki listede işaretli dosyalar liste sırasıyla tek PDF olur ({isaretliler.length} işaretli; ↑/↓ ile sıralayın).
        </p>
        <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-birlestir-ad`}>Çıktı adı</label>
        <input id={`${kimlik}-birlestir-ad`} className={GIRDI_SINIFI} value={birlestirAdi} onChange={(e) => setBirlestirAdi(e.target.value)} maxLength={200} />
        <FlowButton
          size="sm"
          className="mt-2"
          disabled={mesgul || isaretliler.length < 2}
          title={isaretliler.length < 2 ? "En az iki dosya işaretleyin" : undefined}
          onClick={() =>
            onIslem({
              islem: "birlestir",
              girdiler: isaretliler.map((d) => d.id),
              parametreler: {},
              cikti_adi: birlestirAdi.trim() || undefined,
            })
          }
        >
          {ikon("birlestir", Combine)}
          Birleştir
        </FlowButton>
      </Bolum>

      <Bolum baslik="Böl" ikon={<Scissors className="w-4 h-4" />}>
        <div className="flex flex-col gap-1.5 text-[13px] text-[var(--fg)]">
          <label className="flex items-center gap-2">
            <input type="radio" name={`${kimlik}-bol`} checked={bolKipi === "aralik"} onChange={() => setBolKipi("aralik")} className="accent-[var(--brand)]" />
            Aralıklar
          </label>
          <input
            aria-label="Böl aralıkları"
            className={GIRDI_SINIFI}
            placeholder="1-3,4-7"
            value={bolMetni}
            disabled={bolKipi !== "aralik"}
            onChange={(e) => setBolMetni(e.target.value)}
          />
          {bolKipi === "aralik" && bolMetni.trim() && bolAraliklari === null && (
            <p role="alert" className="text-[11px] text-[rgb(var(--tone-danger-rgb))]">
              Aralık biçimi: 1-3,4-7 — 1'den {toplamSayfa || "?"}'e kadar, çakışmasız.
            </p>
          )}
          <label className="flex items-center gap-2">
            <input type="radio" name={`${kimlik}-bol`} checked={bolKipi === "her_sayfa"} onChange={() => setBolKipi("her_sayfa")} className="accent-[var(--brand)]" />
            Her sayfa ayrı dosya
          </label>
        </div>
        <FlowButton
          size="sm"
          className="mt-2"
          disabled={mesgul || !bolGecerli}
          onClick={() =>
            secili &&
            onIslem({
              islem: "bol",
              girdiler: [secili.id],
              parametreler: bolKipi === "her_sayfa" ? { her_n: 1 } : { araliklar: bolAraliklari ?? [] },
            })
          }
        >
          {ikon("bol", Scissors)}
          Böl
        </FlowButton>
      </Bolum>

      <Bolum baslik="Sıkıştır" ikon={<Shrink className="w-4 h-4" />}>
        <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-seviye`}>Seviye</label>
        <select id={`${kimlik}-seviye`} className={GIRDI_SINIFI} value={seviye} onChange={(e) => setSeviye(e.target.value as SikistirmaSeviyesi)}>
          {SIKISTIRMA_SEVIYELERI.map((s) => (
            <option key={s} value={s}>
              {SEVIYE_ADLARI[s]}
            </option>
          ))}
        </select>
        <FlowButton
          size="sm"
          className="mt-2"
          disabled={mesgul || !secili}
          onClick={() => secili && onIslem({ islem: "sikistir", girdiler: [secili.id], parametreler: { seviye } })}
        >
          {ikon("sikistir", Shrink)}
          Sıkıştır
        </FlowButton>
      </Bolum>

      <Bolum baslik="Damga" ikon={<Stamp className="w-4 h-4" />}>
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">
            <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-damga-metin`}>Metin</label>
            <input id={`${kimlik}-damga-metin`} className={GIRDI_SINIFI} value={damgaMetni} maxLength={120} onChange={(e) => setDamgaMetni(e.target.value)} />
          </div>
          <div>
            <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-damga-konum`}>Konum</label>
            <select id={`${kimlik}-damga-konum`} className={GIRDI_SINIFI} value={damgaKonumu} onChange={(e) => setDamgaKonumu(e.target.value as DamgaKonumu)}>
              {DAMGA_KONUMLARI.map((k) => (
                <option key={k} value={k}>
                  {KONUM_ADLARI[k]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-damga-sayfalar`}>Sayfalar</label>
            <input id={`${kimlik}-damga-sayfalar`} className={GIRDI_SINIFI} placeholder="hepsi" value={damgaSayfalari} onChange={(e) => setDamgaSayfalari(e.target.value)} />
          </div>
          <div>
            <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-damga-punto`}>Punto</label>
            <input
              id={`${kimlik}-damga-punto`}
              type="number"
              min={4}
              max={144}
              className={GIRDI_SINIFI}
              value={damgaPunto}
              onChange={(e) => setDamgaPunto(Number(e.target.value))}
            />
          </div>
          <div>
            <label className={ETIKET_SINIFI} htmlFor={`${kimlik}-damga-renk`}>Renk</label>
            <input id={`${kimlik}-damga-renk`} type="color" className="h-8 w-full cursor-pointer bg-transparent" value={damgaRengi} onChange={(e) => setDamgaRengi(e.target.value)} />
          </div>
        </div>
        <FlowButton
          size="sm"
          className="mt-2"
          disabled={mesgul || !damgaGecerli}
          onClick={() =>
            secili &&
            damgaSayfaListesi !== null &&
            onIslem({
              islem: "damga",
              girdiler: [secili.id],
              parametreler: { metin: damgaMetni.trim(), konum: damgaKonumu, sayfalar: damgaSayfaListesi, punto: damgaPunto, renk: damgaRengi },
            })
          }
        >
          {ikon("damga", Stamp)}
          Damgala
        </FlowButton>
      </Bolum>

      <Bolum baslik="Sayfa işlemleri" ikon={<Layers className="w-4 h-4" />}>
        <div className="flex flex-wrap gap-2">
          <FlowButton size="sm" variant="secondary" disabled title={SONRAKI_SURUM}>
            <Layers className="w-3.5 h-3.5" />
            Sayfa düzenle
          </FlowButton>
          <FlowButton size="sm" variant="secondary" disabled title={SONRAKI_SURUM}>
            <Eraser className="w-3.5 h-3.5" />
            Karart
          </FlowButton>
          <FlowButton size="sm" variant="secondary" disabled title={SONRAKI_SURUM}>
            <MessageSquareText className="w-3.5 h-3.5" />
            Not
          </FlowButton>
        </div>
        <p className="mt-1.5 text-[11px] text-[var(--fg-subtle)]">Sayfa ızgarası, karartma ve not sonraki sürümde açılır.</p>
      </Bolum>

      <FlowButton disabled={!secili || indiriliyor || mesgul} onClick={onIndir} className="w-full">
        {indiriliyor ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
        {secili ? `İndir: ${secili.ad}` : "İndir"}
      </FlowButton>
    </div>
  );
}
