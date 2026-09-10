import { AlertTriangle, Check, Download, Sparkles, Undo2 } from "lucide-react";
import type { Katalog } from "@/lib/reports";
import { errorKodIpucu, tanimAyrintisi, type SohbetKaydi } from "@/lib/reportsChat";
import { FlowButton } from "@/components/flow/primitives";

export type IndirmeFormati = "xlsx" | "csv";

type AssistantMessageProps = {
    kayit: SohbetKaydi;
    /** Tanım ayrıntısı için (anahtar → etiket; bağlı kolon etiketleri dahil). */
    katalog: Katalog | null;
    /** "Onayla ve uygula" — tanım oluşturucuya konur, önizleme gelir (G167 teyit adımı). */
    onOnayla?: (kayit: SohbetKaydi) => void;
    /** "Excel indir" / "CSV indir" — kartın tanımıyla doğrudan indirme (uygulanmış olsun olmasın). */
    onIndir?: (kayit: SohbetKaydi, format: IndirmeFormati) => void;
    /** "Geri al" — yalnız bu kaydın uygulaması geri alınabilirken verilir (tek adım). */
    onGeriAl?: () => void;
};

/**
 * Tek sohbet balonu (G135 → G143 → G167): kullanıcı sağda; asistan solda — `warning` sarı şerit,
 * `failed` kırmızı kutu + `error_kod` ipucu; `tanim` varsa TEYİT KARTI: kaynak, kolonlar, filtreler ve
 * sıralama OKUNUR (`tanimAyrintisi`: etiket · operatör · değer), altında "Onayla ve uygula" + "Excel indir" +
 * "CSV indir". G167: tanım OTOMATİK UYGULANMAZ — kullanıcı önce okur, yanlışsa yazarak düzeltir (bir
 * sonraki cevap bu tanımı günceller), doğruysa onaylar. Asistan indirme önerdiyse (`eylem: indir_*`) ilgili
 * indirme düğmesi birincil olur ama yine tık bekler. Uygulanınca rozet + "Geri al"; indirme düğmeleri kalır.
 */
export function AssistantMessage({ kayit, katalog, onOnayla, onIndir, onGeriAl }: AssistantMessageProps) {
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
    const ayrinti = tanim ? tanimAyrintisi(tanim, katalog) : null;
    const onerilenIndirme: IndirmeFormati | null =
        kayit.eylem === "indir_xlsx" ? "xlsx" : kayit.eylem === "indir_csv" ? "csv" : null;

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

                {tanim && ayrinti && (
                    <div data-testid="tanim-ozeti" className="px-3 py-2 rounded-[4px] border border-[var(--border)] bg-[var(--bg-elevated)] grid gap-2">
                        <div className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">Rapor tanımı</div>
                        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[12px]">
                            <dt className="text-[var(--fg-muted)]">Kaynak</dt>
                            <dd className="text-[var(--fg)]" data-testid="tanim-kaynak">{ayrinti.kaynak}</dd>
                            <dt className="text-[var(--fg-muted)]">Kolonlar</dt>
                            <dd className="text-[var(--fg)] flex flex-wrap gap-1" data-testid="tanim-kolonlar">
                                {ayrinti.kolonlar.map((k, i) => (
                                    <span key={i} className="px-1.5 py-0.5 rounded-[3px] bg-[var(--bg)] border border-[var(--border)]">{k}</span>
                                ))}
                            </dd>
                            <dt className="text-[var(--fg-muted)]">Filtreler</dt>
                            <dd className="text-[var(--fg)]" data-testid="tanim-filtreler">
                                {ayrinti.filtreler.length === 0
                                    ? <span className="text-[var(--fg-subtle)]">yok (tüm kayıtlar)</span>
                                    : <ul className="grid gap-0.5">{ayrinti.filtreler.map((f, i) => <li key={i}>{f}</li>)}</ul>}
                            </dd>
                            <dt className="text-[var(--fg-muted)]">Sıralama</dt>
                            <dd className="text-[var(--fg)]" data-testid="tanim-siralama">
                                {ayrinti.siralama.length === 0
                                    ? <span className="text-[var(--fg-subtle)]">varsayılan</span>
                                    : ayrinti.siralama.join(", ")}
                            </dd>
                        </dl>

                        {!kayit.uygulandi && (
                            <p className="text-[11px] text-[var(--fg-subtle)]" data-testid="tanim-teyit-notu">
                                {onerilenIndirme
                                    ? "Asistan indirme önerdi. Doğruysa indirin; yanlışsa düzeltmeyi yazın."
                                    : "Doğruysa onaylayın; yanlışsa düzeltmeyi yazın, asistan bu tanımı günceller."}
                            </p>
                        )}

                        <div className="flex items-center gap-2 flex-wrap">
                            {kayit.uygulandi ? (
                                <span
                                    data-testid="tanim-uygulandi"
                                    className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.12em] uppercase text-[var(--brand)]"
                                >
                                    <Check className="w-3 h-3" /> Oluşturucuya uygulandı
                                </span>
                            ) : (
                                <FlowButton
                                    variant={onerilenIndirme ? "secondary" : "primary"}
                                    size="sm"
                                    onClick={() => onOnayla?.(kayit)}
                                        title="Tanımı onayla: oluşturucuya konur, önizleme gelir"
                                >
                                    <Check className="w-3.5 h-3.5" /> Onayla ve uygula
                                </FlowButton>
                            )}
                            <FlowButton
                                variant={onerilenIndirme === "xlsx" ? "primary" : "secondary"}
                                size="sm"
                                onClick={() => onIndir?.(kayit, "xlsx")}
                                title="Bu tanımla Excel indir (indirme geçmişine yazılır)"
                            >
                                <Download className="w-3.5 h-3.5" /> Excel indir
                            </FlowButton>
                            <FlowButton
                                variant={onerilenIndirme === "csv" ? "primary" : "secondary"}
                                size="sm"
                                onClick={() => onIndir?.(kayit, "csv")}
                                title="Bu tanımla CSV indir (indirme geçmişine yazılır)"
                            >
                                <Download className="w-3.5 h-3.5" /> CSV indir
                            </FlowButton>
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
