/**
 * Kartın föyleri (`case_foys`) — G123.
 *
 * Teslim paketi föy başına gelir (SistemNo), kart ise davadır; bir kartın
 * altında birden çok föy olabilir. Föy düzeyinde gelen Müvekkil Tipi /
 * Hizmet Türü / Durum kart tek slotunda kardeş föyler çelişince YAZILMAZ
 * (04.09 paketi: 973 kart) — bilgi föyün kendisinde durur ve BURADA görünür.
 * SistemNo ve TKU da yalnız buradadır (kart kolonları boş, arama föyden).
 *
 * SALT OKUNUR: föy satırlarının tek yazıcısı aktarımdır (scripts/hukdok_aktarim).
 * Föy yoksa panel hiç basılmaz (boş kart gürültüdür — caseCardFields kuralı).
 */
import { Layers } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { foyDurumEtiketi, foyKapsamEtiketi } from "@/lib/foyLabels";

export interface CaseFoyEntry {
    id: number;
    sistem_no: string;
    tku_no?: string | null;
    hasar_no?: string | null;
    mko_id?: string | null;
    muvekkil_no?: string | null;
    muvekkil_tipi?: string | null;
    hizmet_turu?: string | null;
    /** Kart status havuzu: DERDEST | MAHZEN (eşlenemeyen teslim yazımı ham gelir). */
    durum?: string | null;
    source?: string | null;
    /** TKU kart birleştirmesinde sönen kartın ofis dosya numarası; NULL = föy başka karttan taşınmadı. */
    onceki_tracking_no?: string | null;
    /** G125: teslimdeki ham satır (orijinal başlık → değer); NULL = ham satırsız eski kayıt. */
    ham_veri?: Record<string, unknown> | null;
    /** NULL = kapsamda; SILINDI | KAPSAM_DISI = veri ekibi kapsamdan çıkardı (silinmedi). */
    kapsam_durumu?: string | null;
    kapsam_gerekcesi?: string | null;
    kapsam_tarihi?: string | null;
}

const fmtDate = (iso?: string | null): string => {
    if (!iso) return "";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("tr-TR");
};

interface Props {
    foyler?: CaseFoyEntry[] | null;
}

export default function CaseFoyPanel({ foyler }: Props) {
    if (!foyler || foyler.length === 0) return null;
    return (
        <Card className="bg-[var(--bg-elevated)] border-[var(--border)] rounded-none" data-testid="case-foy-panel">
            <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                    <Layers className="w-4 h-4 text-primary" />
                    Föyler
                    <span className="text-xs font-normal text-muted-foreground">({foyler.length})</span>
                </CardTitle>
                <CardDescription>
                    Eski sistem föyleri (SistemNo / TKU) ve föy düzeyindeki müvekkil tipi, hizmet türü, durum
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground text-left">
                                <th className="py-1.5 pr-3">SistemNo</th>
                                <th className="py-1.5 pr-3">TKU</th>
                                <th className="py-1.5 pr-3">Hasar No</th>
                                <th className="py-1.5 pr-3">Müvekkil Tipi</th>
                                <th className="py-1.5 pr-3">Hizmet Türü</th>
                                <th className="py-1.5 pr-3">Durum</th>
                                <th className="py-1.5 pr-3">MKO Föy / Cari</th>
                            </tr>
                        </thead>
                        <tbody>
                            {foyler.map(f => {
                                const kapsam = foyKapsamEtiketi(f.kapsam_durumu);
                                return (
                                    <tr key={f.id} className="border-t border-[var(--border)] align-top">
                                        <td className="py-2 pr-3 font-mono whitespace-nowrap">
                                            {f.sistem_no}
                                            {kapsam && (
                                                <span
                                                    className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-700 dark:text-amber-400"
                                                    title={[kapsam, f.kapsam_gerekcesi, fmtDate(f.kapsam_tarihi)].filter(Boolean).join(" · ")}
                                                >
                                                    {kapsam}
                                                </span>
                                            )}
                                            {f.onceki_tracking_no && (
                                                <span
                                                    className="block text-[10px] text-muted-foreground whitespace-nowrap"
                                                    title="TKU kart birleştirmesinde sönen kartın ofis dosya numarası"
                                                    data-testid="foy-onceki-ofis-no"
                                                >
                                                    eski ofis no: {f.onceki_tracking_no}
                                                </span>
                                            )}
                                        </td>
                                        <td className="py-2 pr-3 font-mono whitespace-nowrap">{f.tku_no || "—"}</td>
                                        <td className="py-2 pr-3 font-mono whitespace-nowrap">{f.hasar_no || "—"}</td>
                                        <td className="py-2 pr-3">{f.muvekkil_tipi || "—"}</td>
                                        <td className="py-2 pr-3">{f.hizmet_turu || "—"}</td>
                                        <td className="py-2 pr-3 whitespace-nowrap">{foyDurumEtiketi(f.durum)}</td>
                                        <td className="py-2 pr-3 font-mono whitespace-nowrap text-muted-foreground">
                                            {[f.mko_id, f.muvekkil_no].filter(Boolean).join(" / ") || "—"}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
                {/* G125: ham satır — kart alanına yazılamayan (çelişki/mükerrer) değer
                    burada bulunur; paket dosyasına dönmek gerekmez. Açılır blok. */}
                {foyler.some(f => f.ham_veri && Object.keys(f.ham_veri).length > 0) && (
                    <details className="mt-3" data-testid="foy-ham-veri">
                        <summary className="text-xs text-muted-foreground cursor-pointer select-none">
                            Teslimdeki ham satırlar (tüm sütunlar)
                        </summary>
                        <div className="mt-2 space-y-3">
                            {foyler.filter(f => f.ham_veri && Object.keys(f.ham_veri).length > 0).map(f => (
                                <div key={f.id}>
                                    <p className="font-mono text-[11px] font-semibold mb-1">{f.sistem_no}</p>
                                    <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5 text-[11px]">
                                        {Object.entries(f.ham_veri as Record<string, unknown>).map(([k, v]) => (
                                            <div key={k} className="flex gap-2 min-w-0">
                                                <dt className="text-muted-foreground shrink-0">{k}:</dt>
                                                <dd className="truncate" title={String(v)}>{String(v)}</dd>
                                            </div>
                                        ))}
                                    </dl>
                                </div>
                            ))}
                        </div>
                    </details>
                )}
            </CardContent>
        </Card>
    );
}
