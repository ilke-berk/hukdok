import { useCallback, useMemo, useState } from "react";
import { ChevronDown, Plus, X } from "lucide-react";
import type { Katalog, KatalogIliski, KatalogKolon, KatalogVeriKaynagi, KontrolDurumu } from "@/lib/reports";
import { TANIM_LIMITLERI, bosKontrol, kolonSecilebilirMi, kontrolDoluMu } from "@/lib/reports";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { FieldPicker } from "./FieldPicker";
import { FilterChip } from "./FilterChip";
import { FilterControl } from "./FilterControl";
import {
    filtreEkle, kaynakIcinBaslangic, kolonEkle, kolonKaldir, seritFiltreleri, seritteBosOge,
    type OlusturucuDurumu, type SeritOgesi,
} from "./builderState";
import { ANA_KAYNAK_RENGI, LINK_BTN_CLS, kaynakRengi } from "./ui";

/** Prop sözleşmesi — G175 sayfaya bunu bağlar; DEĞİŞTİRME. */
export interface TanimSeridiProps {
    katalog: Katalog;
    durum: OlusturucuDurumu;
    /** Sayfanın `durumDegisti`si: `gecikmeli` yazarak girilen değer (önizleme bekletilir), yoksa hemen. */
    onChange: (durum: OlusturucuDurumu, gecikmeli?: boolean) => void;
    /** Odak çıkışı → bekleyen gecikmeli önizleme hemen istenir. */
    onHemen: () => void;
    /** Kaynak rozetinden FARKLI kaynak seçilince (onay diyaloğu ve `kaynakIcinBaslangic` sayfanın işi). */
    onKaynakSec: (anahtar: string) => void;
    /** Tarih kısayolları için bugün, `YYYY-MM-DD` (QuickFilters ile aynı amaç); yoksa gerçek bugün. */
    bugun?: string;
    /** true → düzenleme kontrolleri gizli (yalnız gösterim). */
    salt?: boolean;
}

/** cmdk bulanık skoru yerine düz alt-dize (FieldPicker/FilterControl ile aynı kural; tr-TR küçük harf). */
function altDizeFiltresi(value: string, search: string, keywords?: string[]): number {
    const q = search.trim().toLocaleLowerCase("tr-TR");
    if (!q) return 1;
    return [value, ...(keywords ?? [])].some(v => v.toLocaleLowerCase("tr-TR").includes(q)) ? 1 : 0;
}

/** `YYYY-MM-DD` → yerel gün (UTC kayması olmadan); bozuk metin → bugün. */
function gunOku(iso: string): Date {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso.trim());
    if (!m) return new Date();
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

const CIP_CLS =
    "inline-flex items-center gap-1 pl-1.5 pr-0.5 py-0.5 text-[11.5px] border rounded-[3px] max-w-full min-w-0 " +
    "border-[var(--border-strong)] bg-[var(--bg-elevated)] text-[var(--fg)]";
const CIP_ETIKET_CLS = "font-mono text-[9.5px] tracking-[0.1em] uppercase text-[var(--fg-subtle)] shrink-0";
const CIP_X_CLS =
    "w-5 h-5 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] rounded-[2px] shrink-0 " +
    "disabled:opacity-30 disabled:hover:text-[var(--fg-subtle)] disabled:cursor-not-allowed";
const GRUP_BASLIK_CLS =
    "[&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[9.5px] [&_[cmdk-group-heading]]:tracking-[0.14em] " +
    "[&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:text-[var(--fg-subtle)]";
/** Açılır paneller: tema token'ları + responsive tavan (dar ekranda %90, geniş ekranda 28rem). */
// `theme-classic`: Radix içerikleri portal ile body altına çizilir, Shell sarmalayıcısındaki tema sınıfının DIŞINDA
// kalır → `--bg-elevated` tanımsız, panel şeffaf (12.09 kullanıcı bulgusu). Modal'lar da aynı sebeple bu sınıfı taşır.
const PANEL_CLS = "theme-classic max-w-[min(90vw,28rem)] rounded-[3px] border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg)] shadow-md";

const HAZIR_SETLER_BASLIGI = "Hazır setler";

/** Bağlı kolonun (G166) ilişki öneki ile adı: katalog etiketi zaten `"<İlişki> · <Ad>"` ise ikilenmez. */
function kolonAdi(kolon: KatalogKolon, iliski: KatalogIliski | undefined): { onek: string | null; ad: string } {
    if (!kolon.bag) return { onek: null, ad: kolon.etiket };
    const onek = iliski?.etiket ?? kolon.bag;
    const ayrac = `${onek} · `;
    return { onek, ad: kolon.etiket.startsWith(ayrac) ? kolon.etiket.slice(ayrac.length) : kolon.etiket };
}

/** "+ Kolon" grup başlığı: ana kaynakta `grup`; bağlı kolonda `"<İlişki> · <grup>"` (katalog önek vermişse aynen). */
function grupBasligi(kolon: KatalogKolon, iliski: KatalogIliski | undefined): string {
    const grup = kolon.grup || "Diğer";
    if (!kolon.bag) return grup;
    const onek = iliski?.etiket ?? kolon.bag;
    return grup.startsWith(`${onek} · `) ? grup : `${onek} · ${grup}`;
}

const ayniDizi = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

/**
 * Tanım şeridi (G173): sohbetin ALTINDA, uygulanan `OlusturucuDurumu`'nu tek satırlık (saran) çip şeridi
 * olarak çizer ve yerinde düzenletir — kaynak rozeti (menü) · kolon çipleri (× / "+ Kolon" gruplu combobox,
 * hazır setler) · filtre çipleri (gövdeye tık → popover'da mevcut `FilterControl`; "+ Filtre" → `FieldPicker`)
 * · sıralama çipleri (× — ekleme tablo başlığından) · Temizle. Kontrollü bileşen: iç kopya yok, her değişiklik
 * `onChange` ile sayfaya gider; yalnız "hangi popover açık" yerel durumdur. Boş kontrol (değer girilmemiş)
 * çip olarak görünmez ama durumda kalır (QuickFilters kuralı); "+ Filtre" ile eklenen alanın düzenleyicisi
 * açık gelir, doldurulmadan kapatılırsa çip yok. Bağlı kaynak kolonu (G166 `bag`) ilişki öneki + ayrık renk
 * çubuğuyla (`ui.ts::kaynakRengi`). Sayfaya bağlama G175'te.
 */
export function TanimSeridi({ katalog, durum, onChange, onHemen, onKaynakSec, bugun, salt = false }: TanimSeridiProps) {
    const kaynak: KatalogVeriKaynagi | undefined = katalog.veri_kaynaklari.find(k => k.anahtar === durum.veri_kaynagi);
    const kolonHaritasi = useMemo(() => new Map((kaynak?.kolonlar ?? []).map(k => [k.anahtar, k])), [kaynak]);
    const kolonOf = useCallback((anahtar: string) => kolonHaritasi.get(anahtar), [kolonHaritasi]);
    const iliskiler = useMemo(() => kaynak?.iliskiler ?? [], [kaynak]);
    const iliskiAnahtarlari = useMemo(() => iliskiler.map(i => i.anahtar), [iliskiler]);
    const iliskiOf = useCallback(
        (bag: string | null | undefined) => (bag ? iliskiler.find(i => i.anahtar === bag) : undefined),
        [iliskiler],
    );
    const bugunFn = useMemo(() => (bugun ? () => gunOku(bugun) : undefined), [bugun]);

    /** Açık düzenleyici: `serit` öğesi id'si. Tek seferde en çok bir popover. */
    const [acikId, setAcikId] = useState<string | null>(null);
    const [kolonSeciciAcik, setKolonSeciciAcik] = useState(false);

    // ---- kolonlar ----
    const seciliKume = useMemo(() => new Set(durum.kolonlar), [durum.kolonlar]);
    const kolonTavan = durum.kolonlar.length >= TANIM_LIMITLERI.kolon_max;
    const tekKolon = durum.kolonlar.length <= 1;

    /** "+ Kolon" listesi: seçilebilir ve henüz seçilmemiş kolonlar, katalog sırasında grup başlıklarıyla. */
    const kolonGruplari = useMemo(() => {
        const sira: string[] = [];
        const uyeler = new Map<string, KatalogKolon[]>();
        for (const k of kaynak?.kolonlar ?? []) {
            if (!kolonSecilebilirMi(k) || seciliKume.has(k.anahtar)) continue;
            const baslik = grupBasligi(k, iliskiOf(k.bag));
            if (!uyeler.has(baslik)) {
                sira.push(baslik);
                uyeler.set(baslik, []);
            }
            uyeler.get(baslik)!.push(k);
        }
        return sira.map(baslik => ({ baslik, kolonlar: uyeler.get(baslik)! }));
    }, [kaynak, seciliKume, iliskiOf]);

    /** Hazır setler: katalogda olmayan / seçilemeyen anahtarlar düşer, boş set listelenmez. */
    const hazirSetler = useMemo(
        () => (kaynak?.kolon_setleri ?? [])
            .map(s => ({ ad: s.ad, kolonlar: s.kolonlar.filter(k => kolonSecilebilirMi(kolonOf(k))) }))
            .filter(s => s.kolonlar.length > 0),
        [kaynak, kolonOf],
    );

    const kolonlariEkle = (anahtarlar: readonly string[]) => {
        const yeni = kolonEkle(durum, anahtarlar);
        if (yeni !== durum) onChange(yeni);
        setKolonSeciciAcik(false);
    };

    // ---- filtreler ----
    const doluAlanlar = useMemo(() => {
        const s = new Set<string>();
        for (const o of durum.serit) if (kontrolDoluMu(o.durum)) s.add(o.durum.alan);
        return s;
    }, [durum.serit]);
    const filtreTavan = seritFiltreleri(durum.serit).length >= TANIM_LIMITLERI.filtre_max;
    /** "+ Filtre" listesi: filtrelenebilir, dolu filtresi olmayan alanlar; bağlı kolon "+ Kolon" ile aynı önekli grupta. */
    const filtreEklenebilir = useMemo(
        () => (kaynak?.kolonlar ?? [])
            .filter(k => k.filtrelenebilir && !doluAlanlar.has(k.anahtar))
            .map(k => (k.bag ? { ...k, grup: grupBasligi(k, iliskiOf(k.bag)) } : k)),
        [kaynak, doluAlanlar, iliskiOf],
    );

    const ogeDegistir = (id: string, yeniDurum: KontrolDurumu, gecikmeli?: boolean) =>
        onChange({ ...durum, serit: durum.serit.map(o => (o.id === id ? { ...o, durum: yeniDurum } : o)) }, gecikmeli);

    /** Yuvanın kendi kolonu (alan değiştirici alternatife çekilmişse ilk seçenek) — QuickFilters kuralı. */
    const yuvaKolonu = (o: SeritOgesi): KatalogKolon | undefined =>
        o.alanSecenekleri.length > 0 ? kolonOf(o.alanSecenekleri[0]) ?? kolonOf(o.durum.alan) : kolonOf(o.durum.alan);

    /** Çipin ×: hızlı yuva boş kontrole döner (durumda kalır, çip düşer); eklenen alan şeritten kalkar. */
    const ogeKaldir = (o: SeritOgesi) => {
        if (acikId === o.id) setAcikId(null);
        const kolon = yuvaKolonu(o);
        if (o.hizli && kolon) {
            onChange({ ...durum, serit: durum.serit.map(x => (x.id === o.id ? { ...x, durum: bosKontrol(kolon, o.sunum) } : x)) });
        } else {
            onChange({ ...durum, serit: durum.serit.filter(x => x.id !== o.id) });
        }
    };

    /** "+ Filtre": boş kontrol eklenir (ya da alanın boş öğesi yeniden kullanılır) ve düzenleyicisi açılır. */
    const filtreAlaniSec = (anahtar: string) => {
        const kolon = kolonOf(anahtar);
        if (!kolon || !kolon.filtrelenebilir) return;
        const yeni = filtreEkle(durum, kolon);
        if (yeni !== durum) onChange(yeni);
        setAcikId(seritteBosOge(yeni.serit, anahtar)?.id ?? null);
    };

    // ---- temizle ----
    const varsayilan = useMemo(() => (kaynak ? kaynakIcinBaslangic(kaynak).kolonlar : []), [kaynak]);
    const zatenTemiz = !kaynak || (
        seritFiltreleri(durum.serit).length === 0 && durum.siralama.length === 0 && ayniDizi(durum.kolonlar, varsayilan)
    );
    const temizle = () => {
        if (!kaynak) return;
        setAcikId(null);
        onChange(kaynakIcinBaslangic(kaynak));
    };

    const kaynakEtiketi = kaynak?.etiket ?? durum.veri_kaynagi;

    return (
        <div role="group" aria-label="Rapor tanımı" data-testid="tanim-seridi" className="flex flex-wrap items-center gap-2 w-full min-w-0">
            {/* 1. Kaynak rozeti */}
            {salt ? (
                <span data-testid="serit-kaynak" className={CIP_CLS + " pr-2 font-medium"}>
                    <span aria-hidden className="w-0.5 h-3.5 rounded-sm shrink-0" style={{ background: ANA_KAYNAK_RENGI }} />
                    {kaynakEtiketi}
                </span>
            ) : (
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <button
                            type="button"
                            data-testid="serit-kaynak"
                            aria-label={`Veri kaynağı: ${kaynakEtiketi}`}
                            className={CIP_CLS + " pr-1.5 font-medium hover:border-[var(--brand)] transition-colors"}
                        >
                            <span aria-hidden className="w-0.5 h-3.5 rounded-sm shrink-0" style={{ background: ANA_KAYNAK_RENGI }} />
                            {kaynakEtiketi}
                            <ChevronDown className="w-3 h-3 text-[var(--fg-subtle)]" />
                        </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" aria-label="Veri kaynağı seç" className={PANEL_CLS + " min-w-[220px] p-1"}>
                        {katalog.veri_kaynaklari.map(k => {
                            const secili = k.anahtar === durum.veri_kaynagi;
                            return (
                                <DropdownMenuItem
                                    key={k.anahtar}
                                    data-kaynak={k.anahtar}
                                    data-secili={secili ? "true" : undefined}
                                    onSelect={() => { if (!secili) onKaynakSec(k.anahtar); }}
                                    className={"flex flex-col items-start gap-0 px-2 py-1.5 rounded-[2px] cursor-pointer focus:bg-[var(--bg)] " + (secili ? "text-[var(--brand)]" : "text-[var(--fg)]")}
                                >
                                    <span className="text-[12px] font-medium">{k.etiket}</span>
                                    {k.aciklama && <span className="text-[11px] text-[var(--fg-muted)]">{k.aciklama}</span>}
                                </DropdownMenuItem>
                            );
                        })}
                    </DropdownMenuContent>
                </DropdownMenu>
            )}

            {/* 2. Kolon çipleri */}
            {durum.kolonlar.map(anahtar => {
                const kolon = kolonOf(anahtar);
                const { onek, ad } = kolon ? kolonAdi(kolon, iliskiOf(kolon.bag)) : { onek: null, ad: anahtar };
                const tamAd = kolon?.etiket ?? anahtar;
                return (
                    <span key={anahtar} data-testid={`serit-kolon-${anahtar}`} data-bag={kolon?.bag ?? undefined} className={CIP_CLS + (salt ? " pr-2" : "")}>
                        <span aria-hidden data-testid="kaynak-cubugu" className="w-0.5 h-3.5 rounded-sm shrink-0" style={{ background: kaynakRengi(kolon?.bag, iliskiAnahtarlari) }} />
                        {/* Metin düğümleri: textContent/kopyalama "Müvekkil · Telefon" okusun (flex boşluğu vermez). */}
                        {onek && <><span className={CIP_ETIKET_CLS}>{onek} ·</span>{" "}</>}
                        <span className="truncate" title={tamAd}>{ad}</span>
                        {!salt && (
                            <button
                                type="button"
                                aria-label={`${tamAd} kolonunu kaldır`}
                                disabled={tekKolon}
                                title={tekKolon ? "En az bir kolon gerekli" : "Kolonu kaldır"}
                                onClick={() => onChange(kolonKaldir(durum, anahtar))}
                                className={CIP_X_CLS}
                            >
                                <X className="w-3 h-3" />
                            </button>
                        )}
                    </span>
                );
            })}

            {/* 3. + Kolon */}
            {!salt && kaynak && (
                <Popover open={kolonSeciciAcik} onOpenChange={setKolonSeciciAcik}>
                    <PopoverTrigger asChild>
                        <button
                            type="button"
                            data-testid="serit-kolon-ekle"
                            className={LINK_BTN_CLS + " inline-flex items-center gap-0.5 shrink-0"}
                            disabled={kolonTavan}
                            title={kolonTavan ? `En çok ${TANIM_LIMITLERI.kolon_max} kolon` : "Kolon ekle"}
                            aria-haspopup="dialog"
                        >
                            <Plus className="w-3 h-3" />
                            Kolon
                        </button>
                    </PopoverTrigger>
                    <PopoverContent align="start" data-testid="kolon-secici" className={PANEL_CLS + " w-[300px] p-0"}>
                        <Command loop filter={altDizeFiltresi} className="bg-transparent text-[var(--fg)]">
                            <CommandInput aria-label="Kolon ara" placeholder="Kolon ara…" autoFocus className="h-9 text-[12px]" />
                            <CommandList className="max-h-72">
                                <CommandEmpty className="py-3 text-[11px] text-[var(--fg-subtle)]">Kolon bulunamadı.</CommandEmpty>
                                {hazirSetler.length > 0 && (
                                    <CommandGroup heading={HAZIR_SETLER_BASLIGI} className={GRUP_BASLIK_CLS}>
                                        {hazirSetler.map(s => (
                                            <CommandItem
                                                key={s.ad}
                                                value={`set ${s.ad}`}
                                                data-set={s.ad}
                                                onSelect={() => kolonlariEkle(s.kolonlar)}
                                                className="text-[12px] py-1 justify-between gap-2"
                                            >
                                                <span>{s.ad}</span>
                                                <span className="text-[10.5px] text-[var(--fg-subtle)]">{s.kolonlar.length} kolon</span>
                                            </CommandItem>
                                        ))}
                                    </CommandGroup>
                                )}
                                {kolonGruplari.map(g => (
                                    <CommandGroup key={g.baslik} heading={g.baslik} className={GRUP_BASLIK_CLS}>
                                        {g.kolonlar.map(k => (
                                            <CommandItem
                                                key={k.anahtar}
                                                value={k.etiket}
                                                keywords={[k.anahtar]}
                                                data-kolon={k.anahtar}
                                                onSelect={() => kolonlariEkle([k.anahtar])}
                                                className="text-[12px] py-1"
                                            >
                                                {kolonAdi(k, iliskiOf(k.bag)).ad}
                                            </CommandItem>
                                        ))}
                                    </CommandGroup>
                                ))}
                            </CommandList>
                        </Command>
                    </PopoverContent>
                </Popover>
            )}

            {/* 4. Filtre çipleri — dolu olanlar; açık düzenleyicinin boş öğesi taslak çapa olarak */}
            {kaynak && durum.serit.map(o => {
                const kolon = kolonOf(o.durum.alan);
                if (!kolon) return null;
                const dolu = kontrolDoluMu(o.durum);
                const acik = acikId === o.id;
                if (!dolu && !acik) return null;
                return (
                    <Popover key={o.id} open={acik} onOpenChange={a => setAcikId(a ? o.id : null)}>
                        <PopoverAnchor asChild>
                            <span data-serit-capa={o.id} className="inline-flex max-w-full min-w-0">
                                {dolu ? (
                                    <FilterChip
                                        oge={o}
                                        kolon={kolon}
                                        onDegistir={d => ogeDegistir(o.id, d)}
                                        onKaldir={() => ogeKaldir(o)}
                                        onAc={salt ? undefined : () => setAcikId(id => (id === o.id ? null : o.id))}
                                        acik={acik}
                                    />
                                ) : (
                                    <span data-testid="serit-filtre-taslak" data-alan={o.durum.alan} className={CIP_CLS + " pr-2 border-dashed text-[var(--fg-muted)]"}>
                                        <span className={CIP_ETIKET_CLS}>{kolon.etiket}</span>
                                        <span>…</span>
                                    </span>
                                )}
                            </span>
                        </PopoverAnchor>
                        {!salt && (
                            <PopoverContent
                                align="start"
                                data-testid="filtre-duzenleyici"
                                data-alan={o.durum.alan}
                                className={PANEL_CLS + " w-auto min-w-[260px] p-3"}
                                // Çapanın kendisine (çip gövdesi/×/…) tıklamak dışarı sayılmaz — gövde düğmesi kendi toggle'ını yapar.
                                onInteractOutside={e => {
                                    const hedef = e.target as Element | null;
                                    if (hedef?.closest?.(`[data-serit-capa="${o.id}"]`)) e.preventDefault();
                                }}
                            >
                                <FilterControl
                                    oge={o}
                                    kolon={kolon}
                                    kolonOf={kolonOf}
                                    onChange={(d, gecikmeli) => ogeDegistir(o.id, d, gecikmeli)}
                                    onHemen={onHemen}
                                    bugun={bugunFn}
                                />
                            </PopoverContent>
                        )}
                    </Popover>
                );
            })}

            {/* 5. + Filtre */}
            {!salt && kaynak && (
                <span data-testid="serit-filtre-ekle" className="shrink-0">
                    <FieldPicker
                        kolonlar={filtreEklenebilir}
                        etiket="Filtre"
                        disabled={filtreTavan}
                        title={filtreTavan ? `En çok ${TANIM_LIMITLERI.filtre_max} filtre` : "Filtre ekle"}
                        onSec={filtreAlaniSec}
                    />
                </span>
            )}

            {/* 6. Sıralama çipleri (ekleme tablo başlığından) */}
            {durum.siralama.map(s => {
                const etiket = kolonOf(s.alan)?.etiket ?? s.alan;
                const artan = s.yon === "asc";
                return (
                    <span key={s.alan} data-testid={`serit-siralama-${s.alan}`} data-yon={s.yon} className={CIP_CLS + (salt ? " pr-2" : "")}>
                        <span aria-label={artan ? "artan" : "azalan"} title={artan ? "Artan" : "Azalan"} className="text-[var(--fg-subtle)]">{artan ? "↑" : "↓"}</span>
                        {" "}
                        <span className="truncate">{etiket}</span>
                        {!salt && (
                            <button
                                type="button"
                                aria-label={`${etiket} sıralamasını kaldır`}
                                title="Sıralamayı kaldır"
                                onClick={() => onChange({ ...durum, siralama: durum.siralama.filter(x => x.alan !== s.alan) })}
                                className={CIP_X_CLS}
                            >
                                <X className="w-3 h-3" />
                            </button>
                        )}
                    </span>
                );
            })}

            {/* 7. Temizle */}
            {!salt && kaynak && (
                <button
                    type="button"
                    data-testid="serit-temizle"
                    className={LINK_BTN_CLS + " ml-auto shrink-0"}
                    disabled={zatenTemiz}
                    title="Filtreleri boşalt, kolonları varsayılana döndür"
                    onClick={temizle}
                >
                    Temizle
                </button>
            )}
        </div>
    );
}
