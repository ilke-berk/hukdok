import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { FlowButton } from "@/components/flow/primitives";
import { Eyebrow } from "@/components/dashboard/primitives";

/** Şablonun künyesi — `tanim` dışarıda kalır (yeni kayıtta taslak, düzenlemede şablonun kendisi). */
export interface SablonKunyesi {
    ad: string;
    aciklama: string | null;
    paylasimli: boolean;
}

export type SablonDiyalogModu = "yeni" | "duzenle";

type SaveTemplateDialogProps = {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    mod: SablonDiyalogModu;
    /** Düzenleme modunda mevcut künye; yeni kayıtta boş. */
    baslangic?: SablonKunyesi | null;
    onSubmit: (kunye: SablonKunyesi) => Promise<void>;
    kaydediliyor: boolean;
};

const AD_MAX = 120;
const ACIKLAMA_MAX = 500;

/**
 * Diyaloğa yerel alan sınıfı (G212): yeniden tasarlanmış modallarla aynı ölçü — h-9 / 13px,
 * köşesiz, odakta `--brand` kenarı. `ui.ts::INPUT_CLS` rapor şeridinde de kullanıldığı için
 * orada değiştirilmez.
 */
const ALAN_CLS =
    "w-full h-9 px-3 text-[13px] rounded-none border border-[var(--border)] bg-[var(--bg)] text-[var(--fg)] " +
    "placeholder:text-[var(--fg-subtle)] focus:outline-none focus:border-[var(--brand)] disabled:opacity-50";

/**
 * Şablon kaydet/düzenle diyaloğu (G134): ad (zorunlu, ≤120), açıklama (≤500), paylaşımlı
 * `Switch`. Sınırlar plan §2.5 kolon genişlikleriyle aynı (sunucu 422 ile yine doğrular).
 */
export function SaveTemplateDialog({ open, onOpenChange, mod, baslangic, onSubmit, kaydediliyor }: SaveTemplateDialogProps) {
    const [ad, setAd] = useState("");
    const [aciklama, setAciklama] = useState("");
    const [paylasimli, setPaylasimli] = useState(false);

    // Başlangıç künyesi ref'te: yalnız AÇILIŞTA forma yazılır (yeni → boş, düzenle → şablon);
    // üst bileşenin her render'da yeni nesne üretmesi yazılmakta olan formu sıfırlamaz.
    const baslangicRef = useRef(baslangic);
    baslangicRef.current = baslangic;
    useEffect(() => {
        if (!open) return;
        const b = baslangicRef.current;
        setAd(b?.ad ?? "");
        setAciklama(b?.aciklama ?? "");
        setPaylasimli(b?.paylasimli ?? false);
    }, [open]);

    const adTemiz = ad.trim();
    const gecerli = adTemiz.length > 0 && adTemiz.length <= AD_MAX && aciklama.length <= ACIKLAMA_MAX;

    const gonder = async () => {
        if (!gecerli || kaydediliyor) return;
        const aciklamaTemiz = aciklama.trim();
        await onSubmit({ ad: adTemiz, aciklama: aciklamaTemiz ? aciklamaTemiz : null, paylasimli });
    };

    return (
        <Dialog open={open} onOpenChange={o => { if (!kaydediliyor) onOpenChange(o); }}>
            <DialogContent
                data-testid="sablon-diyalogu"
                className="theme-classic max-w-md max-h-[88vh] overflow-y-auto bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-0 gap-0"
            >
                {/* Üst brand accent şeridi — diğer yeniden tasarlanmış modallarla aynı */}
                <div className="h-[3px] bg-brand-solid" aria-hidden="true" />

                <DialogHeader
                    data-testid="sablon-diyalogu-baslik"
                    className="px-6 pt-5 pb-4 pr-12 border-b border-[var(--border)] space-y-0 text-left"
                >
                    <div className="grid gap-1 min-w-0">
                        <Eyebrow tone="brand">Rapor şablonu</Eyebrow>
                        <DialogTitle className="font-display text-[20px] font-medium tracking-[-0.005em] text-[var(--fg)] leading-tight">
                            {mod === "yeni" ? "Şablonu kaydet" : "Şablonu düzenle"}
                        </DialogTitle>
                        <DialogDescription className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed">
                            {mod === "yeni"
                                ? "Oluşturucudaki veri kaynağı, kolonlar, filtreler ve sıralama bu adla saklanır."
                                : "Ad, açıklama ve paylaşım güncellenir; rapor tanımı olduğu gibi kalır."}
                        </DialogDescription>
                    </div>
                </DialogHeader>

                <form
                    className="flex flex-col"
                    onSubmit={e => { e.preventDefault(); void gonder(); }}
                >
                    <div data-testid="sablon-diyalogu-govde" className="flex flex-col gap-4 px-6 py-5">
                        <div className="flex flex-col gap-1.5">
                            <label htmlFor="sablon-ad"><Eyebrow>Ad</Eyebrow></label>
                            <input
                                id="sablon-ad"
                                className={ALAN_CLS}
                                value={ad}
                                maxLength={AD_MAX}
                                placeholder="örn. Derdest davalar — aylık"
                                onChange={e => setAd(e.target.value)}
                                autoFocus
                            />
                        </div>
                        <div className="flex flex-col gap-1.5">
                            <label htmlFor="sablon-aciklama"><Eyebrow>Açıklama</Eyebrow></label>
                            <textarea
                                id="sablon-aciklama"
                                className={`${ALAN_CLS} h-auto min-h-[72px] py-2 leading-relaxed resize-y`}
                                value={aciklama}
                                maxLength={ACIKLAMA_MAX}
                                placeholder="İsteğe bağlı"
                                onChange={e => setAciklama(e.target.value)}
                            />
                        </div>
                        <div className="flex items-center justify-between gap-3 border border-[var(--border)] bg-[var(--bg-sunken)] px-4 py-3">
                            <div className="flex flex-col gap-1 min-w-0">
                                <label htmlFor="sablon-paylasimli" className="text-[13px] font-medium text-[var(--fg)] cursor-pointer">Paylaşımlı</label>
                                <span className="text-[12px] leading-relaxed text-[var(--fg-muted)]">Diğer kullanıcılar da listede görür ve yükler; yalnız siz güncelleyip silersiniz.</span>
                            </div>
                            <Switch
                                id="sablon-paylasimli"
                                checked={paylasimli}
                                onCheckedChange={setPaylasimli}
                                className="data-[state=checked]:bg-brand-solid shrink-0"
                            />
                        </div>
                    </div>

                    <DialogFooter
                        data-testid="sablon-diyalogu-alt"
                        className="px-6 py-4 gap-2 border-t border-[var(--border)] bg-[var(--bg)] sm:justify-end"
                    >
                        <FlowButton variant="secondary" size="sm" onClick={() => onOpenChange(false)} disabled={kaydediliyor}>
                            Vazgeç
                        </FlowButton>
                        <FlowButton type="submit" variant="primary" size="sm" disabled={!gecerli || kaydediliyor}>
                            {kaydediliyor && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                            {mod === "yeni" ? "Kaydet" : "Güncelle"}
                        </FlowButton>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
