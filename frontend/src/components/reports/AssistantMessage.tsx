import { AlertTriangle, Check, Sparkles, Undo2, Wand2 } from "lucide-react";
import type { Katalog } from "@/lib/reports";
import { EYLEM_ETIKETLERI, errorKodIpucu, tanimOzeti, type SohbetKaydi } from "@/lib/reportsChat";
import { FlowButton } from "@/components/flow/primitives";

type AssistantMessageProps = {
    kayit: SohbetKaydi;
    /** Tanım özetinde veri kaynağı etiketi için (anahtar → etiket). */
    katalog: Katalog | null;
    /** "Oluşturucuya uygula" — yalnız tanım dolu ve (otomatik uygulama reddedildiği için) uygulanmamışken görünür. */
    onUygula?: (kayit: SohbetKaydi) => void;
    /** "Geri al" (G143) — yalnız bu kaydın uygulaması geri alınabilirken verilir (tek adım). */
    onGeriAl?: () => void;
};

/**
 * Tek sohbet balonu (G135 → G143): kullanıcı sağda; asistan solda — `warning` olayları sarı şerit,
 * `failed` kırmızı kutu + `error_kod` ipucu; `tanim` varsa özet kartı (kaynak, kolon/filtre sayısı).
 * G143: tanım OTOMATİK uygulanır — kart "uygulandı" rozeti + "Geri al" bağlantısı (tek adım) taşır;
 * "Oluşturucuya uygula" yalnız otomatik uygulama reddedilmişse (kaynak katalogda yok) görünür.
 */
export function AssistantMessage({ kayit, katalog, onUygula, onGeriAl }: AssistantMessageProps) {
    if (kayit.rol === "user") {
        return (
            <div className="flex justify-end" data-testid="sohbet-kullanici">
                <div className="max-w-[88%] px-3 py-2 rounded-[6px] rounded-br-[2px] bg-[var(--brand)] text-white text-[13px] whitespace-pre-wrap break-words">
                    {kayit.icerik}
                </div>
            </div>
        );
    }

    if (kayit.hata) {
        return (
            <div className="flex justify-start" data-testid="sohbet-hata">
                <div
                    role="alert"
                    className="max-w-[92%] px-3 py-2 rounded-[6px] rounded-bl-[2px] border border-red-300 bg-red-50 text-[13px] text-red-950"
                >
                    <div className="flex items-start gap-2">
                        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-red-700" />
                        <div className="min-w-0">
                            <p className="font-medium">{kayit.hata.ozet}</p>
                            <p className="mt-1 text-[12px] text-red-900/80">{errorKodIpucu(kayit.hata.kod)}</p>
                            <p className="mt-1 font-mono text-[10px] tracking-[0.08em] uppercase text-red-900/60">
                                {kayit.hata.kod}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    const tanim = kayit.tanim ?? null;
    const ozet = tanim ? tanimOzeti(tanim) : null;
    const kaynakEtiketi = ozet
        ? katalog?.veri_kaynaklari.find(v => v.anahtar === ozet.kaynak)?.etiket ?? ozet.kaynak
        : null;

    return (
        <div className="flex justify-start" data-testid="sohbet-asistan">
            <div className="max-w-[92%] min-w-0 grid gap-2">
                <div className="px-3 py-2 rounded-[6px] rounded-bl-[2px] bg-[var(--bg)] border border-[var(--border)] text-[13px] text-[var(--fg)] whitespace-pre-wrap break-words">
                    <div className="flex items-center gap-1.5 mb-1 font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                        <Sparkles className="w-3 h-3" /> Asistan
                    </div>
                    {kayit.icerik || <span className="text-[var(--fg-subtle)] italic">(metin yok)</span>}
                </div>

                {(kayit.uyarilar ?? []).map((u, i) => (
                    <div
                        key={i}
                        data-testid="sohbet-uyari"
                        className="flex items-start gap-2 px-3 py-1.5 rounded-[4px] border border-amber-300 bg-amber-50 text-[12px] text-amber-900"
                    >
                        <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <span>{u}</span>
                    </div>
                ))}

                {tanim && ozet && (
                    <div data-testid="tanim-ozeti" className="px-3 py-2 rounded-[4px] border border-[var(--border)] bg-[var(--bg-elevated)] grid gap-2">
                        <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">Rapor tanımı</div>
                        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[12px]">
                            <dt className="text-[var(--fg-muted)]">Kaynak</dt>
                            <dd className="text-[var(--fg)]">{kaynakEtiketi}</dd>
                            <dt className="text-[var(--fg-muted)]">Kolon</dt>
                            <dd className="text-[var(--fg)]">{ozet.kolon}</dd>
                            <dt className="text-[var(--fg-muted)]">Filtre</dt>
                            <dd className="text-[var(--fg)]">{ozet.filtre}</dd>
                            {ozet.siralama > 0 && (
                                <>
                                    <dt className="text-[var(--fg-muted)]">Sıralama</dt>
                                    <dd className="text-[var(--fg)]">{ozet.siralama}</dd>
                                </>
                            )}
                        </dl>
                        <div className="flex items-center gap-2 flex-wrap">
                            {kayit.uygulandi ? (
                                <span
                                    data-testid="tanim-uygulandi"
                                    className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--brand)]"
                                >
                                    <Check className="w-3 h-3" /> Oluşturucuya uygulandı
                                </span>
                            ) : (
                                <FlowButton variant="secondary" size="sm" onClick={() => onUygula?.(kayit)} title="Tanımı sol sütundaki oluşturucuya koy">
                                    <Wand2 className="w-3.5 h-3.5" /> Oluşturucuya uygula
                                </FlowButton>
                            )}
                            {kayit.eylem && (
                                <span className="font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--fg-subtle)]">
                                    · {EYLEM_ETIKETLERI[kayit.eylem]}
                                </span>
                            )}
                            {kayit.uygulandi && onGeriAl && (
                                <button
                                    type="button"
                                    onClick={onGeriAl}
                                    data-testid="tanim-geri-al"
                                    title="Asistan uygulamadan önceki taslağa dön (tek adım)"
                                    className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--fg-muted)] underline underline-offset-2 hover:text-[var(--fg)] transition-colors"
                                >
                                    <Undo2 className="w-3.5 h-3.5" /> Geri al
                                </button>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
