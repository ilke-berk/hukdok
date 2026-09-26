/**
 * Dava kartının tarihli not paneli (G215; 26.09 toplantısı "not alma").
 *
 * Kim, ne zaman, ne yazdı: en yeni üstte. Yeni not eklenir; `can_delete=true` gelen not silinir
 * (yetki kararı sunucunundur — yazan ya da yönetici). Eski tek serbest metin (`cases.notes`) bu
 * panelden AYRIDIR; kartta "Genel not" başlığıyla yerinde kalır.
 *
 * Bilinçli seçimler:
 * - İyimser güncelleme YOK: ekleme/silme başarılı olunca liste sunucudan yeniden çekilir
 *   (sıra ve `can_delete` sunucunun kararıdır; iki sekmede eşzamanlı yazımda da doğru kalır).
 * - Not metni düz metin olarak basılır (React kaçışı; `dangerouslySetInnerHTML` YOK), satır sonları
 *   `whitespace-pre-wrap` ile korunur.
 */
import { useCallback, useEffect, useState } from "react";
import { MessageSquareText, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
    type CaseNote,
    NOT_AZAMI_UZUNLUK,
    NOT_SAYAC_ESIGI,
    ekle,
    listele,
    notGecerliMi,
    notTarihi,
    sil,
    yazanEtiketi,
} from "@/lib/caseNotes";

const hataMesaji = (err: unknown, varsayilan: string): string =>
    err instanceof Error && err.message ? err.message : varsayilan;

interface Props {
    caseId: number;
}

export default function CaseNotesPanel({ caseId }: Props) {
    const [notlar, setNotlar] = useState<CaseNote[]>([]);
    const [yukleniyor, setYukleniyor] = useState(true);
    const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
    const [taslak, setTaslak] = useState("");
    const [gonderiliyor, setGonderiliyor] = useState(false);
    const [silinenId, setSilinenId] = useState<number | null>(null);

    const yenile = useCallback(async () => {
        try {
            const liste = await listele(caseId);
            setNotlar(liste);
            setYuklemeHatasi(null);
        } catch (err) {
            setYuklemeHatasi(hataMesaji(err, "Notlar yüklenemedi."));
        } finally {
            setYukleniyor(false);
        }
    }, [caseId]);

    useEffect(() => {
        setYukleniyor(true);
        void yenile();
    }, [yenile]);

    const uzunluk = taslak.trim().length;
    const ekleEtkin = notGecerliMi(taslak) && !gonderiliyor;

    const handleEkle = async () => {
        if (!notGecerliMi(taslak) || gonderiliyor) return;
        setGonderiliyor(true);
        try {
            await ekle(caseId, taslak.trim());
            setTaslak("");
            await yenile();
        } catch (err) {
            toast.error(hataMesaji(err, "Not eklenemedi."));
        } finally {
            setGonderiliyor(false);
        }
    };

    const handleSil = async (note: CaseNote) => {
        if (!window.confirm("Bu not silinsin mi?")) return;
        setSilinenId(note.id);
        try {
            await sil(caseId, note.id);
            await yenile();
        } catch (err) {
            toast.error(hataMesaji(err, "Not silinemedi."));
        } finally {
            setSilinenId(null);
        }
    };

    return (
        <Card className="bg-[var(--bg-elevated)] border-[var(--border)] rounded-none" data-testid="case-notes-panel">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <MessageSquareText className="w-4 h-4 text-brand" />
                    Notlar
                    {notlar.length > 0 && (
                        <span className="text-xs font-normal text-muted-foreground">({notlar.length})</span>
                    )}
                </CardTitle>
                <CardDescription>Davaya tarihli notlar — kim, ne zaman, ne yazdı</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <Textarea
                        value={taslak}
                        onChange={e => setTaslak(e.target.value)}
                        placeholder="Yeni not yazın…"
                        aria-label="Yeni not"
                        disabled={gonderiliyor}
                        className="bg-[var(--bg)] border-[var(--border)] rounded-none"
                        data-testid="case-note-input"
                    />
                    <div className="flex items-center justify-end gap-3">
                        {uzunluk > NOT_SAYAC_ESIGI && (
                            <span
                                className={
                                    uzunluk > NOT_AZAMI_UZUNLUK
                                        ? "text-xs text-tone-danger"
                                        : "text-xs text-[var(--fg-muted)]"
                                }
                                data-testid="case-note-counter"
                            >
                                {uzunluk > NOT_AZAMI_UZUNLUK
                                    ? `${uzunluk - NOT_AZAMI_UZUNLUK} karakter fazla`
                                    : `${NOT_AZAMI_UZUNLUK - uzunluk} karakter kaldı`}
                            </span>
                        )}
                        <Button
                            size="sm"
                            onClick={() => void handleEkle()}
                            disabled={!ekleEtkin}
                            data-testid="case-note-add"
                        >
                            {gonderiliyor ? "Ekleniyor…" : "Ekle"}
                        </Button>
                    </div>
                </div>

                {yukleniyor ? (
                    <p className="text-sm text-[var(--fg-muted)]">Notlar yükleniyor…</p>
                ) : yuklemeHatasi ? (
                    <p className="text-sm text-tone-danger" data-testid="case-notes-error">{yuklemeHatasi}</p>
                ) : notlar.length === 0 ? (
                    <p className="text-sm text-[var(--fg-muted)]" data-testid="case-notes-empty">Henüz not yok</p>
                ) : (
                    <ul className="space-y-2" data-testid="case-notes-list">
                        {notlar.map(n => (
                            <li
                                key={n.id}
                                className="p-3 border border-[var(--border)] bg-[var(--bg)]"
                                data-testid="case-note-item"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="text-xs text-[var(--fg-muted)] min-w-0">
                                        <span className="font-medium text-[var(--fg)]" title={n.author_email}>
                                            {yazanEtiketi(n)}
                                        </span>
                                        <span className="mx-1.5">·</span>
                                        <time dateTime={n.created_at}>{notTarihi(n.created_at)}</time>
                                    </div>
                                    {n.can_delete && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-7 px-2 text-[var(--fg-muted)] hover:text-tone-danger"
                                            onClick={() => void handleSil(n)}
                                            disabled={silinenId === n.id}
                                            aria-label="Notu sil"
                                            data-testid="case-note-delete"
                                        >
                                            <Trash2 className="w-3.5 h-3.5" />
                                        </Button>
                                    )}
                                </div>
                                <p className="mt-1.5 text-sm whitespace-pre-wrap break-words" data-testid="case-note-body">
                                    {n.body}
                                </p>
                            </li>
                        ))}
                    </ul>
                )}
            </CardContent>
        </Card>
    );
}
