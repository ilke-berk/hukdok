/**
 * PartyMatchIndicator.tsx
 *
 * Tanıdık Sorgu göstergesi: taraf isim alanının yanında küçük yuvarlak durum
 * noktası. Gri = eşleşme yok, sarı = tanıdık isim (olası), kırmızı = çıkar
 * çatışması riski veya TC ile kesin eşleşme. Tıklayınca eşleşme detayları
 * popover'da listelenir. Kayıt hiçbir durumda engellenmez.
 */
import { useEffect, useRef } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
    useInlinePartyCheck,
    PartyMatch,
    PartyCheckResult,
    PartyType,
    MIN_CHECK_LENGTH,
    splitCheckNames,
} from "@/hooks/usePartyCheck";

const nameKey = (name: string) => name.trim().toLocaleUpperCase("tr-TR");

const MATCH_BASIS_LABEL: Record<PartyMatch["matched_on"], string> = {
    tc_no: "TC ile kesin eşleşme",
    name_exact: "İsim eşleşmesi",
    name_fuzzy: "Benzer isim — yazım hatası olabilir",
};

const sourceLabel = (m: PartyMatch): string => {
    if (m.source === "client") {
        return m.contact_type === "Client" ? "Müvekkil / Cari Kaydı" : "Cari Kaydı";
    }
    return "Geçmiş Dosya Tarafı";
};

const MatchLine = ({ m }: { m: PartyMatch }) => (
    <div className="border border-[var(--border)] bg-[var(--bg)] px-2.5 py-2 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
            <span
                className={cn(
                    "text-[9px] font-mono font-bold uppercase tracking-wider px-1 py-0.5",
                    m.source === "client"
                        ? "bg-red-500/10 text-red-600"
                        : "bg-amber-500/10 text-amber-600"
                )}
            >
                {sourceLabel(m)}
            </span>
            <span className="text-[12px] font-semibold text-[var(--fg)]">{m.name}</span>
            {m.cari_kod && (
                <span className="text-[9px] bg-primary/10 text-primary px-1 font-bold">{m.cari_kod}</span>
            )}
            {m.tc_no && (
                <span className="text-[10px] font-mono text-[var(--fg-muted)]">TC {m.tc_no}</span>
            )}
        </div>
        {m.source === "case_party" && (
            <div className="text-[11px] text-[var(--fg-muted)] font-mono">
                {[m.tracking_no, m.role, m.case_status].filter(Boolean).join(" · ")}
                {m.case_subject ? <span className="block truncate font-sans">{m.case_subject}</span> : null}
            </div>
        )}
        <div className="text-[10px] text-[var(--fg-subtle)]">
            {MATCH_BASIS_LABEL[m.matched_on]}
        </div>
    </div>
);

export interface PartyMatchIndicatorProps {
    /** Alan değeri — ";" veya "," ile çoklu isim içerebilir */
    value: string;
    partyType: PartyType;
    excludeCaseId?: number;
    /** İsim (TR-upper) → TC eşlemesi; verilirse sorgular TC ile kesinleşir */
    tcByName?: Record<string, string>;
    /** Verilirse popover içinde eşleşen her isim için TC girişi gösterilir */
    onTcChange?: (name: string, tc: string) => void;
    /** Eşleşme durumu değişince üst bileşene bildirir (satır altı özet + TC alanı için) */
    onStateChange?: (state: {
        hasMatch: boolean;
        conflict: boolean;
        /** Eşleşen kayıtların kısa özeti: isim + varsa TC (ekranda gösterim için) */
        matched: Array<{ name: string; tc_no?: string | null }>;
    }) => void;
    className?: string;
}

export const PartyMatchIndicator = ({
    value,
    partyType,
    excludeCaseId,
    tcByName,
    onTcChange,
    onStateChange,
    className,
}: PartyMatchIndicatorProps) => {
    const { results, matches, conflict, isChecking, checked } = useInlinePartyCheck(
        value,
        partyType,
        { tcByName, excludeCaseId }
    );

    const hasMatch = matches.length > 0;
    // Aynı kişi birden çok dosyada eşleşebilir — isim+TC bazında teke indir
    const matchedSummary: Array<{ name: string; tc_no?: string | null }> = [];
    const summarySeen = new Set<string>();
    for (const m of matches) {
        const key = `${nameKey(m.name)}|${m.tc_no || ""}`;
        if (summarySeen.has(key)) continue;
        summarySeen.add(key);
        matchedSummary.push({ name: m.name, tc_no: m.tc_no });
    }
    const summarySignature = JSON.stringify(matchedSummary);

    // onStateChange kimliği her render'da değişebilir — ref üzerinden çağır
    const stateCbRef = useRef(onStateChange);
    stateCbRef.current = onStateChange;
    useEffect(() => {
        stateCbRef.current?.({ hasMatch, conflict, matched: JSON.parse(summarySignature) });
    }, [hasMatch, conflict, summarySignature]);

    const queryable = splitCheckNames(value).some(n => n.length >= MIN_CHECK_LENGTH);

    // Nokta rengi
    let dotClass = "bg-transparent border border-[var(--border-strong)]"; // henüz kontrol yok
    let title = "Tanıdık sorgusu için isim yetersiz";
    if (queryable) {
        if (isChecking) {
            dotClass = "bg-[var(--fg-subtle)]/40 animate-pulse";
            title = "Kayıtlar kontrol ediliyor…";
        } else if (conflict) {
            dotClass = "bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.6)]";
            title = "Çıkar çatışması riski / kesin eşleşme — detay için tıklayın";
        } else if (hasMatch) {
            dotClass = "bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.5)]";
            title = "Bu isim kayıtlarda mevcut — detay için tıklayın";
        } else if (checked) {
            dotClass = "bg-[var(--fg-subtle)]/35";
            title = "Kayıtlarda eşleşme yok";
        }
    }

    const dot = (
        <button
            type="button"
            title={title}
            aria-label={title}
            className={cn(
                "shrink-0 w-2.5 h-2.5 rounded-full transition-colors self-center",
                hasMatch && "cursor-pointer",
                dotClass,
                className
            )}
        />
    );

    if (!hasMatch) return dot;

    // Eşleşen isim başına gruplu popover içeriği
    const withMatches = results.filter((r: PartyCheckResult) => r.matches.length > 0);

    return (
        <Popover>
            <PopoverTrigger asChild>{dot}</PopoverTrigger>
            <PopoverContent className="w-[340px] p-3 space-y-3" align="start">
                <div
                    className={cn(
                        "text-[11px] font-mono font-bold uppercase tracking-[0.14em]",
                        conflict ? "text-red-600" : "text-amber-600"
                    )}
                >
                    {conflict ? "Çıkar Çatışması Riski" : "Tanıdık Kayıt Bulundu"}
                </div>
                {withMatches.map((r, i) => (
                    <div key={i} className="space-y-1.5">
                        {withMatches.length > 1 && (
                            <div className="text-[11px] font-semibold text-[var(--fg)]">{r.query.name}</div>
                        )}
                        <div className="space-y-1.5">
                            {r.matches.map((m, j) => (
                                <MatchLine key={j} m={m} />
                            ))}
                        </div>
                        {onTcChange && (
                            <div className="pt-0.5">
                                <Input
                                    inputMode="numeric"
                                    maxLength={11}
                                    placeholder="TC ile kesinleştir (opsiyonel)"
                                    value={tcByName?.[nameKey(r.query.name)] || ""}
                                    onChange={e =>
                                        onTcChange(r.query.name, e.target.value.replace(/\D/g, ""))
                                    }
                                    className="h-7 text-[12px] font-mono bg-[var(--bg)] border-[var(--border)]"
                                />
                            </div>
                        )}
                    </div>
                ))}
                <p className="text-[10px] text-[var(--fg-subtle)] leading-relaxed border-t border-[var(--border)] pt-2">
                    Bu bir uyarıdır; kayıt engellenmez. TC girilirse eşleşme kesinleşir
                    veya "aynı isim, farklı kişi" olarak temizlenir.
                </p>
            </PopoverContent>
        </Popover>
    );
};
