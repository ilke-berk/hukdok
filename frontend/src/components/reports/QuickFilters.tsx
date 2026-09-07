import { useCallback, useMemo } from "react";
import type { KatalogKolon, KatalogVeriKaynagi, KontrolDurumu } from "@/lib/reports";
import { TANIM_LIMITLERI, bosKontrol, kontrolDoluMu } from "@/lib/reports";
import { FieldPicker } from "./FieldPicker";
import { FilterChip } from "./FilterChip";
import { FilterControl } from "./FilterControl";
import { SearchBox } from "./SearchBox";
import { eklenenOge, type SeritOgesi } from "./builderState";
import { ICON_BTN_CLS, LINK_BTN_CLS } from "./ui";

type QuickFiltersProps = {
    kaynak: KatalogVeriKaynagi;
    serit: SeritOgesi[];
    /** `gecikmeli`: yazarak girilen değer (sayfa 600 ms bekletir); seçim/tik anında. */
    onChange: (serit: SeritOgesi[], gecikmeli?: boolean) => void;
    /** Odak çıkışı — bekleyen gecikmeli önizleme hemen istenir. */
    onHemen: () => void;
    /** Kısayollar için bugün; test sabitler. */
    bugun?: () => Date;
};

/**
 * Filtre şeridi (§4.1 madde 2 / §5.1): `sunum=arama` yuvası en üstte tam genişlik arama kutusu (ayrı
 * satır); kaynağın diğer `hizli_filtreler`i sırayla hazır kontroller (bileşen `sunum`a göre — çip
 * satırı, var/yok, "X yok", aranabilir çoklu seçim…), "+ Başka alan" ile eklenenler aynı türde kontrol,
 * etkin filtreler çip satırında (× / "…" gelişmiş; "(boş)" → "boş"), "Filtreleri temizle" hepsini
 * (aramayı da) boşaltır. Operatör seçici YOK — op kontrolden türetilir (§4.3/§5.3, lib/reports.ts).
 */
export function QuickFilters({ kaynak, serit, onChange, onHemen, bugun }: QuickFiltersProps) {
    const kolonHaritasi = useMemo(() => new Map(kaynak.kolonlar.map(k => [k.anahtar, k])), [kaynak]);
    const kolonOf = useCallback((anahtar: string) => kolonHaritasi.get(anahtar), [kolonHaritasi]);

    const serittekiAlanlar = useMemo(() => {
        const s = new Set<string>();
        for (const o of serit) {
            s.add(o.durum.alan);
            for (const a of o.alanSecenekleri) s.add(a);
        }
        return s;
    }, [serit]);

    const eklenebilir = useMemo(
        () => kaynak.kolonlar.filter(k => k.filtrelenebilir && !serittekiAlanlar.has(k.anahtar)),
        [kaynak, serittekiAlanlar],
    );

    const etkin = serit.filter(o => kontrolDoluMu(o.durum));
    const etkinSayisi = etkin.length;
    const tavanDolu = etkinSayisi >= TANIM_LIMITLERI.filtre_max;

    const ogeDegistir = (id: string, durum: KontrolDurumu, gecikmeli?: boolean) =>
        onChange(serit.map(o => (o.id === id ? { ...o, durum } : o)), gecikmeli);

    /** Yuvanın kendi kolonu (alan değiştirici alternatife çekilmişse ilk seçenek). */
    const yuvaKolonu = (o: SeritOgesi): KatalogKolon | undefined =>
        o.alanSecenekleri.length > 0 ? kolonOf(o.alanSecenekleri[0]) ?? kolonOf(o.durum.alan) : kolonOf(o.durum.alan);

    /** Çipin × düğmesi: yuva boşa döner, eklenen alan şeritten kalkar. */
    const ogeKaldir = (o: SeritOgesi) => {
        const kolon = yuvaKolonu(o);
        if (o.hizli && kolon) {
            onChange(serit.map(x => (x.id === o.id ? { ...x, durum: bosKontrol(kolon, o.sunum) } : x)));
        } else {
            onChange(serit.filter(x => x.id !== o.id));
        }
    };

    /** Eklenen alanın (yuva değil) şeritten kaldırılması — dolu olsun olmasın. */
    const alaniKaldir = (id: string) => onChange(serit.filter(x => x.id !== id));

    const alanEkle = (anahtar: string) => {
        const kolon = kolonOf(anahtar);
        if (!kolon || !kolon.filtrelenebilir) return;
        onChange([...serit, eklenenOge(bosKontrol(kolon))]);
    };

    const temizle = () => {
        const yeni: SeritOgesi[] = [];
        for (const o of serit) {
            if (!o.hizli) continue;
            const kolon = yuvaKolonu(o);
            if (kolon) yeni.push({ ...o, durum: bosKontrol(kolon, o.sunum) });
        }
        onChange(yeni);
    };

    // Arama yuvaları ayrı satırda (şeridin üstü), kalan kontroller ızgarada.
    const aramaYuvalari = serit.filter(o => o.sunum === "arama" && o.durum.kontrol === "metin_icerir");
    const digerOgeler = serit.filter(o => !aramaYuvalari.includes(o));

    return (
        <div data-testid="filtre-seridi" className="flex flex-col gap-4 px-5 py-4 border-b border-[var(--border)]">
            {/* Minimal (07.09): "Filtreler" etiketi ve sayaç kalktı; yalnız eylemler sağda. */}
            <div className="flex items-center justify-end gap-2">
                <div className="flex items-center gap-3">
                    <FieldPicker kolonlar={eklenebilir} onSec={alanEkle} disabled={tavanDolu} />
                    <button
                        type="button"
                        className={LINK_BTN_CLS}
                        onClick={temizle}
                        disabled={etkinSayisi === 0 && serit.every(o => o.hizli)}
                    >
                        Filtreleri temizle
                    </button>
                </div>
            </div>

            {aramaYuvalari.map(o => {
                const kolon = kolonOf(o.durum.alan);
                if (!kolon || o.durum.kontrol !== "metin_icerir") return null;
                const d = o.durum;
                return (
                    <div key={o.id} data-testid="filtre-kontrolu" data-alan={d.alan} data-kontrol={d.kontrol} data-sunum="arama">
                        <SearchBox
                            etiket={kolon.etiket}
                            placeholder={kolon.aciklama}
                            metin={d.metin}
                            onYaz={metin => ogeDegistir(o.id, { ...d, metin, tam: false }, true)}
                            onTemizle={() => ogeDegistir(o.id, { ...d, metin: "", tam: false })}
                            onHemen={onHemen}
                        />
                    </div>
                );
            })}

            {digerOgeler.length > 0 && (
                <div className="grid gap-x-6 gap-y-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                    {digerOgeler.map(o => {
                        const kolon: KatalogKolon | undefined = kolonOf(o.durum.alan);
                        if (!kolon) return null;
                        // Çip satırı geniş: ızgarada tam satır kaplar.
                        const genis = o.sunum === "cipler" && o.durum.kontrol === "coklu_secim";
                        return (
                            <div key={o.id} className={"relative flex items-start gap-1 min-w-0" + (genis ? " col-span-full" : "")}>
                                <div className="flex-1 min-w-0">
                                    <FilterControl
                                        oge={o}
                                        kolon={kolon}
                                        kolonOf={kolonOf}
                                        onChange={(durum, gecikmeli) => ogeDegistir(o.id, durum, gecikmeli)}
                                        onHemen={onHemen}
                                        bugun={bugun}
                                    />
                                </div>
                                {!o.hizli && (
                                    <button
                                        type="button"
                                        className={ICON_BTN_CLS + " mt-4 shrink-0"}
                                        aria-label={`${kolon.etiket} alanını şeritten kaldır`}
                                        onClick={() => alaniKaldir(o.id)}
                                        title="Alanı şeritten kaldır"
                                    >
                                        ×
                                    </button>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {etkin.length > 0 && (
                <div data-testid="etkin-filtreler" className="flex flex-wrap items-center gap-2 pt-1">
                    {etkin.map(o => {
                        const kolon = kolonOf(o.durum.alan);
                        if (!kolon) return null;
                        return (
                            <FilterChip
                                key={o.id}
                                oge={o}
                                kolon={kolon}
                                onDegistir={durum => ogeDegistir(o.id, durum)}
                                onKaldir={() => ogeKaldir(o)}
                            />
                        );
                    })}
                </div>
            )}
        </div>
    );
}
