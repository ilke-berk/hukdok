/**
 * usePartyCheck.ts
 *
 * Tanıdık Sorgu / Çıkar Çatışması Kontrolü.
 * Dosya açarken girilen taraf isimlerini (davacı/davalı/başvuran) backend'de
 * cari kayıtları ve geçmiş dosya taraflarıyla karşılaştırır.
 * Kayıt hiçbir durumda engellenmez — yalnızca uyarı gösterilir.
 */
import { useQuery } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import { useAuthRequest } from "@/hooks/useAuthRequest";
import { useDebounce } from "@/hooks/useDebounce";
import { MIN_CHECK_LENGTH, splitCheckNames, partyNameKey } from "@/lib/partyCheck";

export { MIN_CHECK_LENGTH, splitCheckNames };

export type PartyType = "CLIENT" | "COUNTER" | "THIRD";

export interface PartyCheckQuery {
    name: string;
    tc_no?: string;
    party_type?: PartyType;
}

export interface PartyMatch {
    source: "client" | "case_party";
    strength: "certain" | "probable" | "possible";
    matched_on: "tc_no" | "name_exact" | "name_fuzzy";
    name: string;
    client_id?: number | null;
    cari_kod?: string | null;
    category?: string | null;
    contact_type?: string | null;
    case_id?: number | null;
    tracking_no?: string | null;
    case_subject?: string | null;
    case_status?: string | null;
    role?: string | null;
    party_type?: string | null;
    /** Eşleşen kaydın TC'si — ekranda karşılaştırma için gösterilir */
    tc_no?: string | null;
}

export interface PartyCheckResult {
    query: PartyCheckQuery;
    conflict: boolean;
    matches: PartyMatch[];
}

const nameKey = partyNameKey;

/** Kayıt öncesi toplu kontrol için imperatif çağrı. */
export const usePartyCheck = () => {
    const { authRequest } = useAuthRequest();

    const checkParties = async (
        parties: PartyCheckQuery[],
        excludeCaseId?: number
    ): Promise<PartyCheckResult[]> => {
        const filtered = parties.filter(p => p.name.trim().length >= MIN_CHECK_LENGTH);
        if (filtered.length === 0) return [];
        const res = await authRequest("/api/parties/check", "POST", {
            parties: filtered.slice(0, 20),
            exclude_case_id: excludeCaseId,
        });
        if (res?.ok) {
            const data = await res.json();
            return (data.results ?? []) as PartyCheckResult[];
        }
        return [];
    };

    return { checkParties };
};

export interface InlinePartyCheckState {
    results: PartyCheckResult[];
    matches: PartyMatch[];
    /** Çıkar çatışması riski veya TC ile kesin eşleşme → kırmızı gösterge */
    conflict: boolean;
    isChecking: boolean;
    /** En az bir isim sorgulandı ve yanıt geldi */
    checked: boolean;
}

/**
 * Alan değerine bağlı debounce'lu canlı kontrol.
 * `rawValue` ";" / "," ile çoklu isim içerebilir; her isim ayrı sorgulanır.
 * `tcByName`: isim (TR-upper) → TC eşlemesi; TC girilince kontrol kesinleşir.
 */
export const useInlinePartyCheck = (
    rawValue: string,
    partyType: PartyType,
    options?: { tcByName?: Record<string, string>; excludeCaseId?: number }
): InlinePartyCheckState => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();

    const debouncedValue = useDebounce(rawValue, 600);
    const tcSignature = JSON.stringify(options?.tcByName ?? {});
    const debouncedTcSignature = useDebounce(tcSignature, 600);

    const names = splitCheckNames(debouncedValue).filter(n => n.length >= MIN_CHECK_LENGTH);
    const tcByName: Record<string, string> = JSON.parse(debouncedTcSignature);

    const parties: PartyCheckQuery[] = names.map(name => ({
        name,
        tc_no: tcByName[nameKey(name)] || undefined,
        party_type: partyType,
    }));

    const q = useQuery({
        queryKey: [
            "party-check",
            partyType,
            names.map(nameKey).join("|"),
            debouncedTcSignature,
            options?.excludeCaseId ?? null,
        ],
        queryFn: async () => {
            const res = await authRequest("/api/parties/check", "POST", {
                parties: parties.slice(0, 20),
                exclude_case_id: options?.excludeCaseId,
            });
            if (res?.ok) {
                const data = await res.json();
                return (data.results ?? []) as PartyCheckResult[];
            }
            return [] as PartyCheckResult[];
        },
        enabled: accounts.length > 0 && names.length > 0,
        staleTime: 60_000,
        gcTime: 5 * 60_000,
    });

    const results = q.data ?? [];
    const matches = results.flatMap(r => r.matches);
    const conflict =
        results.some(r => r.conflict) ||
        matches.some(m => m.matched_on === "tc_no");

    return {
        results,
        matches,
        conflict,
        isChecking: q.isFetching,
        checked: names.length > 0 && q.isSuccess,
    };
};
