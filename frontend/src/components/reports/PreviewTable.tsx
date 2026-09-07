import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Loader2, Table2 } from "lucide-react";
import type { OnizlemeCevabi, Siralama } from "@/lib/reports";
import { hucreBicimle } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";

type PreviewTableProps = {
    cevap: OnizlemeCevabi | null;
    yukleniyor: boolean;
    /** Sunucu/ağ hatası — boş liste DEĞİL, DataErrorBanner (G002 kuralı). */
    hata: string | null;
    onRetry: () => void;
    onSayfa: (sayfa: number) => void;
    /** Örnek boyu (10/25/50; kullanıcı kararı 07.09: önizleme küçük bir örnek + toplam sayı). */
    sayfaBoyu?: number;
    onSayfaBoyu?: (sayfaBoyu: number) => void;
    /** Taslak geçersiz (kolon yok / eksik gelişmiş filtre) — istek gitmez, boş durumda ipucu. */
    gecersiz: boolean;
    /** Etkin sıralama (en fazla 3, sıralı); başlık oku ve sıra numarası buradan. */
    siralama: Siralama[];
    /** Kolon başlığa tıkla sıralanabilir mi (`siralanabilir`)? */
    siralanabilirMi: (anahtar: string) => boolean;
    /** Başlık tıklaması: yok → artan → azalan → kaldır (builderState.siralamaDongusu). */
    onSirala: (anahtar: string) => void;
    /** Boş sonuçta "Filtreleri temizle" kısayolu — şeridi boşaltır (G139); verilmezse kısayol çıkmaz. */
    onFiltreleriTemizle?: () => void;
    /** Etkin filtre var mı — boş sonuç mesajı ve kısayol buna göre (filtresiz boş kaynakta "gevşetin" denmez). */
    filtreVar?: boolean;
};

const ORNEK_BOYU_SECENEKLERI = [10, 25, 50] as const;

const TH_CLS = "text-left px-4 py-3 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold whitespace-nowrap";
const SAGA_YASLI = new Set(["sayi", "para"]);

/**
 * Önizleme tablosu (tam genişlik, G139): başlıklar katalog etiketiyle, tarih dd.MM.yyyy, para tr-TR,
 * `null` "—"; sayfalayıcı CaseList kalıbı. G138: önizleme otomatiktir — başlıkta "güncelleniyor…"
 * durumu, "bayat" rozeti yok; `siralanabilir` başlıklar tıklanarak sıralanır (§4.1 madde 4).
 * Sayaç "N kayıt · M kolon" (§4.1 madde 7); boş sonuçta filtre gevşetme ipucu + Temizle kısayolu.
 */
export function PreviewTable({
    cevap, yukleniyor, hata, onRetry, onSayfa, sayfaBoyu, onSayfaBoyu, gecersiz, siralama, siralanabilirMi, onSirala,
    onFiltreleriTemizle, filtreVar = false,
}: PreviewTableProps) {
    const toplamSayfa = cevap ? Math.ceil(cevap.toplam / cevap.sayfa_boyu) || 1 : 1;
    const siraOf = (anahtar: string) => siralama.findIndex(s => s.alan === anahtar);

    return (
        <div className="flex flex-col">
            {/* Tablo başlığı */}
            <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-[var(--border)]">
                <div className="flex items-center gap-3 min-w-0">
                    {/* Minimal (07.09): "Örnek" etiketi ve "ilk N satır" notu kalktı; toplam rozeti yeter. */}
                    {cevap && !hata && (
                        <span
                            data-testid="toplam-rozeti"
                            title="Raporun tamamındaki kayıt sayısı; tablo yalnız bir örnek gösterir, tam liste Excel/CSV'de"
                            className="font-mono text-[10px] tracking-[0.12em] uppercase px-1.5 py-0.5 border border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] tabular-nums"
                        >
                            {cevap.toplam.toLocaleString("tr-TR")} kayıt · {cevap.kolonlar.length} kolon
                        </span>
                    )}
                    {gecersiz && !yukleniyor && (
                        <span
                            data-testid="taslak-eksik"
                            role="status"
                            title="Önizleme için en az bir kolon seçin ve filtreleri tamamlayın"
                            className="font-mono text-[9.5px] tracking-[0.12em] uppercase text-[var(--brand)]"
                        >
                            taslak eksik — en az bir kolon seçin ve filtreleri tamamlayın
                        </span>
                    )}
                    {yukleniyor && (
                        <span
                            data-testid="guncelleniyor"
                            role="status"
                            className="inline-flex items-center gap-1 font-mono text-[9.5px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]"
                        >
                            <Loader2 className="w-3 h-3 animate-spin" />
                            güncelleniyor…
                        </span>
                    )}
                </div>
            </div>

            {hata ? (
                <div className="p-4">
                    <DataErrorBanner description={hata} onRetry={onRetry} isRetrying={yukleniyor} />
                </div>
            ) : !cevap ? (
                <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
                    <Table2 className="w-9 h-9 opacity-30" />
                    <p className="text-[13px]">
                        {yukleniyor
                            ? "Önizleme alınıyor…"
                            : gecersiz
                                ? "Önizleme için en az bir kolon seçin ve filtreleri tamamlayın."
                                : "Önizleme hazırlanıyor…"}
                    </p>
                </div>
            ) : cevap.satirlar.length === 0 ? (
                <div data-testid="bos-sonuc" className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
                    <Table2 className="w-9 h-9 opacity-30" />
                    <p className="text-[13px]">
                        {filtreVar ? "Bu filtrelerle kayıt yok — filtreleri gevşetin." : "Bu kaynakta kayıt yok."}
                    </p>
                    {filtreVar && onFiltreleriTemizle && (
                        <FlowButton variant="secondary" size="sm" onClick={onFiltreleriTemizle}>
                            Filtreleri temizle
                        </FlowButton>
                    )}
                </div>
            ) : (
                <div className={`overflow-x-auto ${yukleniyor ? "opacity-60" : ""}`}>
                    <table className="w-full border-collapse">
                        <thead>
                            <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                                {cevap.kolonlar.map(k => {
                                    const sira = siraOf(k.anahtar);
                                    const yon = sira >= 0 ? siralama[sira].yon : null;
                                    const sagda = SAGA_YASLI.has(k.tip);
                                    const tiklanabilir = siralanabilirMi(k.anahtar);
                                    return (
                                        <th
                                            key={k.anahtar}
                                            aria-sort={yon === "asc" ? "ascending" : yon === "desc" ? "descending" : "none"}
                                            className={`${TH_CLS} ${sagda ? "text-right" : ""}`}
                                        >
                                            {tiklanabilir ? (
                                                <button
                                                    type="button"
                                                    aria-label={`${k.etiket} sırala`}
                                                    title={yon === null ? "Artan sırala" : yon === "asc" ? "Azalan sırala" : "Sıralamayı kaldır"}
                                                    onClick={() => onSirala(k.anahtar)}
                                                    className={[
                                                        "inline-flex items-center gap-1 uppercase tracking-[0.18em] hover:text-[var(--fg)] transition-colors",
                                                        sagda ? "flex-row-reverse" : "",
                                                        yon ? "text-[var(--brand)]" : "",
                                                    ].join(" ")}
                                                >
                                                    {k.etiket}
                                                    {yon === "asc" && <ArrowUp className="w-3 h-3" aria-hidden />}
                                                    {yon === "desc" && <ArrowDown className="w-3 h-3" aria-hidden />}
                                                    {yon === null && <ArrowUpDown className="w-3 h-3 opacity-30" aria-hidden />}
                                                    {yon && siralama.length > 1 && (
                                                        <span className="text-[8px] tabular-nums opacity-70">{sira + 1}</span>
                                                    )}
                                                </button>
                                            ) : (
                                                k.etiket
                                            )}
                                        </th>
                                    );
                                })}
                            </tr>
                        </thead>
                        <tbody>
                            {cevap.satirlar.map((satir, i) => (
                                <tr key={i} className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] transition-colors">
                                    {cevap.kolonlar.map(k => {
                                        const metin = hucreBicimle(satir[k.anahtar], k.tip);
                                        const bos = metin === "—";
                                        return (
                                            <td
                                                key={k.anahtar}
                                                className={[
                                                    "px-4 py-2.5 text-[12px] align-top whitespace-nowrap max-w-[320px] truncate",
                                                    SAGA_YASLI.has(k.tip) ? "text-right tabular-nums" : "",
                                                    k.tip === "tarih" ? "font-mono text-[11px] tabular-nums" : "",
                                                    bos ? "text-[var(--fg-subtle)]" : "text-[var(--fg)]",
                                                ].join(" ")}
                                                title={bos ? undefined : metin}
                                            >
                                                {metin}
                                            </td>
                                        );
                                    })}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {cevap && !hata && cevap.toplam > 0 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
                    <label className="inline-flex items-center gap-2">
                        <Eyebrow>Örnek boyu</Eyebrow>
                        <select
                            aria-label="Örnek boyu"
                            data-testid="ornek-boyu"
                            value={sayfaBoyu ?? cevap.sayfa_boyu}
                            disabled={!onSayfaBoyu || yukleniyor}
                            onChange={e => onSayfaBoyu?.(Number(e.target.value))}
                            className="h-7 px-2 font-mono text-[11px] tabular-nums border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg)]"
                        >
                            {ORNEK_BOYU_SECENEKLERI.map(n => (
                                <option key={n} value={n}>{n} satır</option>
                            ))}
                        </select>
                    </label>
                    <div className="flex items-center gap-2">
                        <FlowButton
                            variant="ghost"
                            size="sm"
                            disabled={cevap.sayfa <= 1 || yukleniyor}
                            onClick={() => onSayfa(cevap.sayfa - 1)}
                        >
                            <ChevronLeft className="w-3.5 h-3.5" />
                            Geri
                        </FlowButton>
                        <span className="font-mono text-[11px] tabular-nums px-2.5 py-1 border border-[var(--border)] bg-[var(--bg-elevated)]">
                            {cevap.sayfa} / {toplamSayfa}
                        </span>
                        <FlowButton
                            variant="ghost"
                            size="sm"
                            disabled={cevap.sayfa >= toplamSayfa || yukleniyor}
                            onClick={() => onSayfa(cevap.sayfa + 1)}
                        >
                            İleri
                            <ChevronRight className="w-3.5 h-3.5" />
                        </FlowButton>
                    </div>
                </div>
            )}
        </div>
    );
}
