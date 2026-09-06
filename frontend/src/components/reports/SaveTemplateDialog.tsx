import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { FlowButton } from "@/components/flow/primitives";
import { Eyebrow } from "@/components/dashboard/primitives";
import { INPUT_CLS } from "./ui";

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
            <DialogContent className="max-w-md rounded-none border-[var(--border)] bg-[var(--bg-elevated)]">
                <DialogHeader>
                    <DialogTitle className="font-display text-[18px] font-medium text-[var(--fg)]">
                        {mod === "yeni" ? "Şablonu kaydet" : "Şablonu düzenle"}
                    </DialogTitle>
                    <DialogDescription className="text-[12px] text-[var(--fg-muted)]">
                        {mod === "yeni"
                            ? "Oluşturucudaki veri kaynağı, kolonlar, filtreler ve sıralama bu adla saklanır."
                            : "Ad, açıklama ve paylaşım güncellenir; rapor tanımı olduğu gibi kalır."}
                    </DialogDescription>
                </DialogHeader>

                <form
                    className="flex flex-col gap-4"
                    onSubmit={e => { e.preventDefault(); void gonder(); }}
                >
                    <div className="flex flex-col gap-1.5">
                        <label htmlFor="sablon-ad"><Eyebrow>Ad</Eyebrow></label>
                        <input
                            id="sablon-ad"
                            className={INPUT_CLS}
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
                            className={`${INPUT_CLS} h-auto min-h-[64px] py-2 resize-y`}
                            value={aciklama}
                            maxLength={ACIKLAMA_MAX}
                            placeholder="İsteğe bağlı"
                            onChange={e => setAciklama(e.target.value)}
                        />
                    </div>
                    <div className="flex items-center justify-between gap-3 border border-[var(--border)] bg-[var(--bg)] px-3 py-2.5">
                        <div className="flex flex-col gap-0.5">
                            <label htmlFor="sablon-paylasimli" className="text-[12.5px] text-[var(--fg)] cursor-pointer">Paylaşımlı</label>
                            <span className="text-[11px] text-[var(--fg-subtle)]">Diğer yöneticiler de listede görür ve yükler; yalnız siz güncelleyip silersiniz.</span>
                        </div>
                        <Switch
                            id="sablon-paylasimli"
                            checked={paylasimli}
                            onCheckedChange={setPaylasimli}
                            className="data-[state=checked]:bg-[var(--brand)]"
                        />
                    </div>

                    <DialogFooter className="gap-2">
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
