import { useMemo } from "react";
import { BookmarkPlus, Download, Loader2, MoreHorizontal, Pencil, RefreshCw, Save, Star, Trash2, Users } from "lucide-react";
import type { RaporSablonu } from "@/lib/reports";
import { sablonSahibiMi, tarihSaatBicimle } from "@/lib/reports";
import { Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";
import { DataErrorBanner } from "@/components/system/DataErrorBanner";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { ICON_BTN_CLS, LINK_BTN_CLS, SELECT_CLS } from "./ui";

/** Paylaşımlı şablon rozeti: sahibi görünür. */
function PaylasimRozeti({ sablon, sahip }: { sablon: RaporSablonu; sahip: boolean }) {
    if (!sablon.paylasimli) {
        return (
            <span className="font-mono text-[9.5px] tracking-[0.12em] uppercase px-1.5 py-0.5 border border-[var(--border)] text-[var(--fg-subtle)]">
                Özel
            </span>
        );
    }
    return (
        <span
            data-testid="paylasimli-rozeti"
            title={sahip ? "Paylaşımlı — sizin şablonunuz" : `Paylaşımlı — sahibi: ${sablon.olusturan}`}
            className="inline-flex items-center gap-1 font-mono text-[9.5px] tracking-[0.12em] uppercase px-1.5 py-0.5 border border-[var(--brand)]/40 text-[var(--brand)] bg-[var(--brand-soft)]"
        >
            <Users className="w-3 h-3" />
            {sahip ? "Paylaşımlı" : sablon.olusturan}
        </span>
    );
}

type TemplateBarProps = {
    sablonlar: RaporSablonu[];
    yukleniyor: boolean;
    /** Liste hatası — boş liste DEĞİL (satır-içi not + Yeniden dene). */
    hata: string | null;
    onRetry: () => void;
    /** Giriş yapan yöneticinin e-postası (sahiplik). */
    kullanici: string | undefined;
    seciliId: number | null;
    onSecim: (id: number | null) => void;
    onYukle: (sablon: RaporSablonu) => void;
    /** "Kaydet" — yeni ad diyaloğunu açar. */
    onKaydet: () => void;
    /** "Güncelle" — seçili şablonun tanımını taslakla değiştirir (yalnız sahibi). */
    onGuncelle: (sablon: RaporSablonu) => void;
    onSil: (sablon: RaporSablonu) => void;
    /** Taslak geçerli mi? Değilse Kaydet/Güncelle kapalı. */
    taslakGecerli: boolean;
    isleniyor: boolean;
    /**
     * G144: taslakla BİREBİR aynı tanımlı kayıtlı şablon (varsa) — "★ Kayıtlı: <ad>" gösterilir;
     * yoksa "☆ Favorilere ekle" bağlantısı (öneri kartını açar). Eski çağıranlar için isteğe bağlı.
     */
    kayitli?: RaporSablonu | null;
    onFavoriEkle?: () => void;
};

/**
 * Şablon çubuğu (G134 → G175 KOMPAKT): sayaç satırında tek satır — "Şablon" etiketi + seçim (kendi +
 * paylaşımlı; seçilinin açıklaması `title`da), paylaşım rozeti, "☆ Favorilere ekle" / "★ Kayıtlı: <ad>"
 * (G144), Yükle, Kaydet (yeni ad) ve yalnız sahibinde "…" menüsü (Güncelle / Sil — başkasınınkinde menü HİÇ yok).
 * Liste hatası satır-içi not olarak aynı satırda. Davranış G134/G144 ile aynı; yalnız görsel sıkışma.
 */
export function TemplateBar({
    sablonlar, yukleniyor, hata, onRetry, kullanici, seciliId, onSecim, onYukle, onKaydet, onGuncelle, onSil,
    taslakGecerli, isleniyor, kayitli = null, onFavoriEkle,
}: TemplateBarProps) {
    const secili = useMemo(() => sablonlar.find(s => s.id === seciliId) ?? null, [sablonlar, seciliId]);
    const sahip = secili ? sablonSahibiMi(secili, kullanici) : false;

    return (
        <div data-testid="sablon-cubugu" className="flex flex-wrap items-center gap-x-2 gap-y-1.5 min-w-0">
            <label htmlFor="rapor-sablon" className="shrink-0">
                <Eyebrow>Şablon</Eyebrow>
            </label>
            <select
                id="rapor-sablon"
                className={`${SELECT_CLS} h-7 w-auto min-w-[160px] max-w-[260px]`}
                value={seciliId ?? ""}
                onChange={e => onSecim(e.target.value ? Number(e.target.value) : null)}
                disabled={yukleniyor || isleniyor}
                title={secili?.aciklama || undefined}
            >
                <option value="">{yukleniyor ? "Şablonlar yükleniyor…" : sablonlar.length === 0 ? "Kayıtlı şablon yok" : "Şablon seçiniz"}</option>
                {sablonlar.map(s => (
                    <option key={s.id} value={s.id}>
                        {s.ad}{s.paylasimli && !sablonSahibiMi(s, kullanici) ? ` · ${s.olusturan}` : ""}
                    </option>
                ))}
            </select>
            {secili && <PaylasimRozeti sablon={secili} sahip={sahip} />}
            {yukleniyor && <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--fg-subtle)]" aria-label="Şablonlar yükleniyor" />}
            {kayitli ? (
                <span
                    data-testid="favori-kayitli"
                    className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--brand)] max-w-[240px] truncate"
                    title={`Bu format kayıtlı: ${kayitli.ad}`}
                >
                    <Star className="w-3 h-3 shrink-0 fill-current" aria-hidden="true" />
                    Kayıtlı: {kayitli.ad}
                </span>
            ) : onFavoriEkle && (
                <button
                    type="button"
                    data-testid="favori-ekle-baglantisi"
                    className={`${LINK_BTN_CLS} inline-flex items-center gap-1`}
                    onClick={onFavoriEkle}
                    disabled={!taslakGecerli || isleniyor}
                    title={taslakGecerli ? "Bu formatı favori şablon olarak ekle" : "Eklemek için geçerli bir tanım gerekir"}
                >
                    <Star className="w-3 h-3 shrink-0" aria-hidden="true" />
                    Favorilere ekle
                </button>
            )}

            <div className="flex items-center gap-1 shrink-0">
                <FlowButton
                    variant="secondary"
                    size="sm"
                    disabled={!secili || isleniyor}
                    onClick={() => secili && onYukle(secili)}
                    title="Şablonun tanımını şeride koy"
                >
                    <Download className="w-3.5 h-3.5" />
                    Yükle
                </FlowButton>
                <FlowButton
                    variant="secondary"
                    size="sm"
                    disabled={!taslakGecerli || isleniyor}
                    onClick={onKaydet}
                    title={taslakGecerli ? "Taslağı yeni şablon olarak kaydet" : "Kaydetmek için geçerli bir tanım gerekir"}
                >
                    <BookmarkPlus className="w-3.5 h-3.5" />
                    Kaydet
                </FlowButton>
                {secili && sahip && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <button
                                type="button"
                                data-testid="sablon-menu"
                                aria-label={`${secili.ad} işlemleri`}
                                title="Güncelle / Sil"
                                disabled={isleniyor}
                                className={ICON_BTN_CLS}
                            >
                                <MoreHorizontal className="w-3.5 h-3.5" />
                            </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                            align="end"
                            aria-label="Şablon işlemleri"
                            className="min-w-[160px] p-1 rounded-[3px] border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--fg)] shadow-md"
                        >
                            <DropdownMenuItem
                                data-islem="guncelle"
                                disabled={!taslakGecerli}
                                onSelect={() => onGuncelle(secili)}
                                title="Seçili şablonun tanımını taslakla değiştir"
                                className="gap-2 px-2 py-1.5 text-[12px] rounded-[2px] cursor-pointer focus:bg-[var(--bg)]"
                            >
                                <Save className="w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                                Güncelle
                            </DropdownMenuItem>
                            <DropdownMenuItem
                                data-islem="sil"
                                onSelect={() => onSil(secili)}
                                title="Şablonu sil"
                                className="gap-2 px-2 py-1.5 text-[12px] rounded-[2px] cursor-pointer focus:bg-[var(--bg)] hover:text-[var(--brand)]"
                            >
                                <Trash2 className="w-3.5 h-3.5 text-[var(--fg-subtle)]" />
                                Sil
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                )}
            </div>
            {hata && (
                // Şerit değil, satır-içi not: sayfanın tek `role=alert`i önizleme hatasına ayrılır
                // (önizleme şeridinin "Tekrar dene"si ile karışmasın); hata ≠ boş liste yine korunur.
                <span data-testid="sablon-hatasi" className="text-[11px] text-[var(--danger,#b3261e)] inline-flex items-center gap-2 min-w-0">
                    <span className="truncate">Şablonlar yüklenemedi: {hata}</span>
                    <button type="button" className={LINK_BTN_CLS} onClick={onRetry} disabled={yukleniyor}>
                        Yeniden dene
                    </button>
                </span>
            )}
        </div>
    );
}

// Sağa sabit işlem kolonu (AdminPage.tsx STICKY_ACTIONS kalıbı): arka plan kart rengi.
const STICKY_ACTIONS = "text-right sticky right-0 bg-[var(--bg-elevated)] shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.15)]";
const TH_CLS = "text-left px-4 py-2.5 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] font-semibold whitespace-nowrap";
const TD_CLS = "px-4 py-2 text-[12px] align-middle whitespace-nowrap text-[var(--fg)]";

type TemplatesTableProps = {
    sablonlar: RaporSablonu[];
    yukleniyor: boolean;
    hata: string | null;
    onRetry: () => void;
    kullanici: string | undefined;
    onYukle: (sablon: RaporSablonu) => void;
    /** Künye düzenleme (ad/açıklama/paylaşım) — yalnız sahibi. */
    onDuzenle: (sablon: RaporSablonu) => void;
    onSil: (sablon: RaporSablonu) => void;
    isleniyor: boolean;
};

/** "Şablonlar" sekmesi: aynı listenin tablosu — ad, sahibi, paylaşım, güncellenme, işlemler. */
export function TemplatesTable({ sablonlar, yukleniyor, hata, onRetry, kullanici, onYukle, onDuzenle, onSil, isleniyor }: TemplatesTableProps) {
    return (
        <div className="flex flex-col">
            <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-[var(--border)]">
                <span className="inline-flex items-center gap-2 font-mono text-[11px] tracking-[0.14em] uppercase text-[var(--fg)] font-semibold">
                    Şablonlar
                    <span className="font-mono text-[10px] tracking-[0.12em] px-1.5 py-0.5 border border-[var(--border)] bg-[var(--bg)] text-[var(--fg-muted)] tabular-nums">
                        {sablonlar.length}
                    </span>
                </span>
                <button type="button" className={ICON_BTN_CLS} onClick={onRetry} disabled={yukleniyor} aria-label="Şablonları yenile" title="Yenile">
                    <RefreshCw className={`w-3.5 h-3.5 ${yukleniyor ? "animate-spin" : ""}`} />
                </button>
            </div>
            {hata ? (
                <div className="p-4">
                    <DataErrorBanner description={hata} onRetry={onRetry} isRetrying={yukleniyor} />
                </div>
            ) : sablonlar.length === 0 ? (
                <p className="px-4 py-12 text-center text-[13px] text-[var(--fg-subtle)]">
                    {yukleniyor ? "Şablonlar yükleniyor…" : "Henüz kayıtlı şablon yok. Rapor sekmesinde tanımı hazırlayıp Kaydet'e basın."}
                </p>
            ) : (
                <div className="overflow-x-auto">
                    <table className="w-full border-collapse">
                        <thead>
                            <tr className="bg-[var(--bg)] border-b border-[var(--border)]">
                                <th className={TH_CLS}>Ad</th>
                                <th className={TH_CLS}>Sahibi</th>
                                <th className={TH_CLS}>Paylaşım</th>
                                <th className={TH_CLS}>Veri kaynağı</th>
                                <th className={TH_CLS}>Güncellenme</th>
                                <th className={`${TH_CLS} ${STICKY_ACTIONS}`}>İşlemler</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sablonlar.map(s => {
                                const sahip = sablonSahibiMi(s, kullanici);
                                return (
                                    <tr key={s.id} data-testid="sablon-satiri" data-sablon-id={s.id} className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--bg)] transition-colors">
                                        <td className={`${TD_CLS} max-w-[360px]`}>
                                            <div className="truncate font-medium" title={s.ad}>{s.ad}</div>
                                            {s.aciklama && <div className="truncate text-[11px] text-[var(--fg-subtle)]" title={s.aciklama}>{s.aciklama}</div>}
                                        </td>
                                        <td className={`${TD_CLS} text-[var(--fg-muted)]`}>{sahip ? "Siz" : s.olusturan}</td>
                                        <td className={TD_CLS}><PaylasimRozeti sablon={s} sahip={sahip} /></td>
                                        <td className={`${TD_CLS} font-mono text-[11px]`}>{s.tanim.veri_kaynagi}</td>
                                        <td className={`${TD_CLS} font-mono text-[11px] tabular-nums text-[var(--fg-muted)]`}>{tarihSaatBicimle(s.updated_at)}</td>
                                        <td className={`${TD_CLS} ${STICKY_ACTIONS}`}>
                                            <div className="inline-flex items-center gap-1">
                                                <button type="button" className={ICON_BTN_CLS} onClick={() => onYukle(s)} disabled={isleniyor} aria-label={`${s.ad} yükle`} title="Oluşturucuya yükle">
                                                    <Download className="w-3.5 h-3.5" />
                                                </button>
                                                {sahip && (
                                                    <>
                                                        <button type="button" className={ICON_BTN_CLS} onClick={() => onDuzenle(s)} disabled={isleniyor} aria-label={`${s.ad} düzenle`} title="Ad / açıklama / paylaşım">
                                                            <Pencil className="w-3.5 h-3.5" />
                                                        </button>
                                                        <button type="button" className={`${ICON_BTN_CLS} hover:text-[var(--brand)]`} onClick={() => onSil(s)} disabled={isleniyor} aria-label={`${s.ad} sil`} title="Sil">
                                                            <Trash2 className="w-3.5 h-3.5" />
                                                        </button>
                                                    </>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
