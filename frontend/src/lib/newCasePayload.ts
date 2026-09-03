import type { CaseData } from "@/hooks/useCases";
import { DEFAULT_SERVICE_TYPE, type NewCaseFormValues } from "@/lib/newCaseDraft";

/**
 * NewCase sayfasının saf (React'sız) yardımcıları: düzenleme modunda form
 * değerleri ve POST/PUT gövdesi. Sayfa dosyasından ayrı durur ki `NewCase.tsx`
 * yalnız bileşen export etsin (react-refresh/only-export-components) ve
 * `NewCase.payload.test.ts` bileşeni içe almadan doğrudan test edebilsin.
 */

export interface EditModeParty {
    party_type: string;
    name: string;
    role: string;
    birth_year?: number;
    gender?: string;
    client_id?: number | null;
    tc_no?: string | null;
}

export interface EditModeCaseData {
    id?: number;
    tracking_no: string;
    status: string;
    history?: { date: string; action: string; user?: string; old?: string; new?: string; field?: string }[];
    file_type?: string;
    sub_type?: string;
    subject?: string;
    court?: string;
    responsible_lawyer_name?: string;
    uyap_lawyer_name?: string;
    esas_no?: string;
    opening_date?: string;
    service_type?: string;
    maddi_tazminat?: number | string;
    manevi_tazminat?: number | string;
    acceptance_date?: string;
    bureau_type?: string;
    sub_type_extra?: string;
    judicial_unit?: string;
    atama_tarihi?: string;
    hasar_dosya_no?: string;
    hukuk_no?: string;
    klasor_no_2?: string;
    notes?: string;
    parties?: EditModeParty[];
    lawyers?: { name: string; lawyer_id?: number | null }[];
}

export const toUpperTR = (str: string) => str.toLocaleUpperCase('tr-TR').trim();

// "Ad1;Ad2" biçiminde tek satıra yazılan çoklu isimleri ayrı kişilere böler
export const splitPartyNames = (value: string): string[] =>
    value.split(";").map(s => s.trim()).filter(Boolean);

/**
 * Düzenleme modunda forma yüklenecek değerler — TEK kaynak: hem ilk state hem de
 * `editModeCase` değişince koşan effect bunu çağırır. G020 öncesi iki ayrı kopya
 * vardı ve ilk state `serviceType`'ı kayıttaki değere bakmadan "00000" açıyordu.
 */
export function editModeFormValues(source?: EditModeCaseData): NewCaseFormValues {
    return {
        fileType: source?.file_type || "",
        subType: source?.sub_type || "",
        subject: source?.subject || "",
        court: source?.court || "",
        category: "",
        lawyer: source?.responsible_lawyer_name || "",
        uyapLawyer: source?.uyap_lawyer_name || "",
        esasNo: source?.esas_no || "",
        fileOpeningDate: source?.opening_date || "",
        serviceType: source?.service_type || DEFAULT_SERVICE_TYPE,
        maddiTazminat: source?.maddi_tazminat?.toString() || "",
        maneviTazminat: source?.manevi_tazminat?.toString() || "",
        acceptanceDate: source?.acceptance_date || "",
        bureauType: source?.bureau_type || "",
        subTypeExtra: source?.sub_type_extra || "",
        judicialUnit: source?.judicial_unit || "",
        atamaTarihi: source?.atama_tarihi || "",
        hasarDosyaNo: source?.hasar_dosya_no || "",
        hukukNo: source?.hukuk_no || "",
        klasorNo2: source?.klasor_no_2 || "",
        notes: source?.notes || "",
    };
}

export interface CasePayloadInput {
    trackingNo: string;
    status: string;
    formData: NewCaseFormValues;
    clients: Array<{ name: string; role: string }>;
    counterParties: Array<{ name: string; role: string; tc_no?: string }>;
    thirdParties: Array<{ name: string; role: string; tc_no?: string }>;
    /** Kayıtlı müvekkiller — isim eşleşen taraf `client_id` ile bağlanır */
    dbClients: Array<{ id?: number; name: string }>;
    lawyers: Array<{ name: string; lawyer_id?: number | null }>;
}

/**
 * POST/PUT gövdesini üretir. Saf fonksiyon (testten doğrudan çağrılır) ve dönüş
 * tipi `CaseData` — yüke girmeyen bir alan artık derleme hatasıdır. G020: eskiden
 * gövde `as CaseData` ile cast'leniyordu ve `service_type` hiç gönderilmiyordu.
 */
export function buildCasePayload(input: CasePayloadInput): CaseData {
    const { formData } = input;
    return {
        tracking_no: input.trackingNo,
        esas_no: formData.esasNo,
        status: input.status,
        service_type: formData.serviceType,
        file_type: formData.fileType,
        sub_type: formData.subType,
        subject: formData.subject,
        court: formData.court,
        opening_date: formData.fileOpeningDate,
        responsible_lawyer_name: formData.lawyer,
        uyap_lawyer_name: formData.uyapLawyer,
        maddi_tazminat: formData.maddiTazminat ? Number(formData.maddiTazminat) : 0,
        manevi_tazminat: formData.maneviTazminat ? Number(formData.maneviTazminat) : 0,
        acceptance_date: formData.acceptanceDate || undefined,
        bureau_type: formData.bureauType || undefined,
        sub_type_extra: formData.subTypeExtra || undefined,
        judicial_unit: formData.judicialUnit || undefined,
        atama_tarihi: formData.atamaTarihi || undefined,
        hasar_dosya_no: formData.hasarDosyaNo || undefined,
        hukuk_no: formData.hukukNo || undefined,
        klasor_no_2: formData.klasorNo2 || undefined,
        notes: formData.notes || undefined,
        parties: [
            // splitPartyNames: blur tetiklenmeden kalan ";"li girişler kayda ayrı kişiler olarak gitsin
            ...input.clients.filter(c => c.name).flatMap(c => splitPartyNames(c.name).map(name => ({
                client_id: input.dbClients.find(db => toUpperTR(db.name) === toUpperTR(name))?.id,
                name,
                role: c.role,
                party_type: "CLIENT" as const
            }))),
            ...input.counterParties.filter(c => c.name).flatMap(c => {
                const names = splitPartyNames(c.name);
                return names.map(name => ({
                    name,
                    role: c.role,
                    party_type: "COUNTER" as const,
                    // TC tek isimli satırda anlamlı; çoklu isimde kime ait belirsiz
                    tc_no: names.length === 1 ? (c.tc_no || undefined) : undefined
                }));
            }),
            ...input.thirdParties.filter(t => t.name).flatMap(t => {
                const names = splitPartyNames(t.name);
                return names.map(name => ({
                    name,
                    role: t.role,
                    party_type: "THIRD" as const,
                    tc_no: names.length === 1 ? (t.tc_no || undefined) : undefined
                }));
            })
        ],
        lawyers: input.lawyers,
    };
}
