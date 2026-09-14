import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface ConfigItem {
    id?: number;
    code?: string;
    name: string;
    email?: string;
    description?: string;
    /** E-posta alıcısı: sorumlu avukata yazılan uygulama içi bildirimlerin kopyasını alır. */
    notify_copy?: boolean;
    parent_code?: string;
    role_type?: string;
    tc_no?: string;
    sicil_no?: string;
    gorev?: string;
    phone?: string;
    address?: string;
    city?: string;
}

/** Bir liste öğesinin adını taşıyan bağlı kayıtların dökümü (silme onayı için). */
export interface ListUsage {
    name: string;
    total: number;
    items: { label: string; count: number; clearable: boolean }[];
    clearable: boolean;   // false → bağlı alan zorunlu, boşaltılamaz; yalnızca taşınabilir
}

/** Silmede bağlı kayıtlara ne olacağı. */
export type DeleteMode = "block" | "clear" | "reassign" | "keep";

const EMPTY: ConfigItem[] = [];

/** Dava kartı zorunlu alanı (tek kaynak: backend/required_fields.py). */
export interface RequiredCaseField {
    field: string;
    label: string;
}

const EMPTY_REQUIRED: RequiredCaseField[] = [];

/**
 * G019: "hata ≠ boş liste". Bu mesajlar kullanıcıya şerit/toast olarak gösterilir;
 * boş listeyle karışmasınlar diye ayrı tutulur.
 */
export const CONFIG_LIST_ERROR = "Ayar listeleri alınamadı — sunucuya ulaşılamadı.";
export const REQUIRED_FIELDS_ERROR =
    "Zorunlu alan listesi alınamadı — sunucuya ulaşılamadı. Kaydetmeden önce tekrar deneyin.";

const CONFIG_KEYS = {
    lawyers: ["config", "lawyers"],
    statuses: ["config", "statuses"],
    doctypes: ["config", "doctypes"],
    emailRecipients: ["config", "email_recipients"],
    caseSubjects: ["config", "case_subjects"],
    fileTypes: ["config", "file_types"],
    courtTypes: ["config", "court_types"],
    partyRoles: ["config", "party_roles"],
    bureauTypes: ["config", "bureau_types"],
    cities: ["config", "cities"],
    specialties: ["config", "specialties"],
    clientCategories: ["config", "client_categories"],
    fileStatuses: ["config", "file_statuses"],
    // FAZ F'nin iki KAPALI listesi (G044 backend'de açtı, G048 karta bağladı).
    // Dava kartındaki iddia_edilen_kusur / istinaf_basvuran_taraf değerleri
    // BURADAN gelir; frontend'de sabit değer listesi tutulmaz.
    allegedFaults: ["config", "alleged_faults"],
    appealingParties: ["config", "appealing_parties"],
    // Belgeleme olayı KAPALI listeleri (G103 uçları; G105 dava kartındaki
    // olay_turu / hukumdeki_rol alanlarına ve liste filtresine bağladı).
    eventTypes: ["config", "event_types"],
    judgmentRoles: ["config", "judgment_roles"],
    // Müvekkil Tipi / Hizmet Türü KAPALI listeleri (DB-2026-002; G119 uçları,
    // G121 büro kartındaki muvekkil_tipi / hizmet_turu alanlarına ve liste
    // filtresine bağladı).
    clientTypes: ["config", "client_types"],
    serviceTypes: ["config", "service_types"],
    // G124: para birimi + teslim havuzlarından kurulan listeler (takip paneli
    // dava değeri / tıbbi tasnif / mahkeme önerileri).
    currencies: ["config", "currencies"],
    medicalProcesses: ["config", "medical_processes"],
    medicalEvents: ["config", "medical_events"],
    patientHarms: ["config", "patient_harms"],
    appliedMethods: ["config", "applied_methods"],
    cassationCourts: ["config", "cassation_courts"],
    appealCourts: ["config", "appeal_courts"],
    defendantAdministrations: ["config", "defendant_administrations"],
    // Karar sonucu RESMÎ listeleri (G060 kurdu, G061 takip paneline bağladı).
    // Takip panelindeki karar durumu dropdown'ları BURADAN okur; kayıt sırası
    // resmi havuz sırasıdır (backend sequence ile sıralı döner).
    localDecisions: ["config", "local_decisions"],
    appealDecisions: ["config", "appeal_decisions"],
    cassationDecisions: ["config", "cassation_decisions"],
    revisionDecisions: ["config", "revision_decisions"],
} as const;

/** G184: tek listeye abone olmak için anahtar (`useConfigList`). */
export type ConfigListKey = keyof typeof CONFIG_KEYS;

type AuthRequest = (url: string, method: string, body?: unknown) => Promise<Response | null>;

const CONFIG_STALE_TIME = 5 * 60 * 1000;

/**
 * G019: Hata YUTMAZ. Eski sessiz `[]` fallback'i 13 config listesinin
 * hepsini kesintide "boş liste" gibi gösteriyor, zorunlu alan ve dropdown
 * kapılarını sessizce açıyordu. Aynı dosyadaki mutasyon yolu (`request`)
 * zaten fırlatıyordu — tutarsızlık burada kapandı.
 */
const fetchConfigList = async (authRequest: AuthRequest, url: string): Promise<ConfigItem[]> => {
    const res = await authRequest(url, "GET");
    if (!res?.ok) throw new Error(CONFIG_LIST_ERROR);
    return res.json();
};

/**
 * G184: `useConfig()` ve `useConfigList()` liste sorgusunu TEK yerden kurar — aynı
 * queryKey, aynı staleTime/retry/enabled → önbellek paylaşılır, çift istek olmaz.
 * Uç yolu anahtarın ikinci parçasıdır (`["config","email_recipients"]` →
 * `/api/config/email_recipients`).
 *
 * apiClient GET'i zaten 3 denemeye kadar tekrarlıyor (Faz 4.1); react-query'nin
 * ek 3 denemesi hata şeridini saniyelerce geciktirirdi — tekrar kullanıcıya
 * bırakıldı (useClients ile aynı karar).
 */
const configListQueryOptions = (key: ConfigListKey, authRequest: AuthRequest, enabled: boolean) => ({
    queryKey: CONFIG_KEYS[key],
    queryFn: () => fetchConfigList(authRequest, `/api/config/${CONFIG_KEYS[key][1]}`),
    enabled,
    staleTime: CONFIG_STALE_TIME,
    retry: false,
});

/** Mahkeme türleri üst dava türüne (`parent_code`) göre gruplu. */
export const groupCourtTypesByParent = (items: ConfigItem[]): Record<string, ConfigItem[]> =>
    items.reduce<Record<string, ConfigItem[]>>((acc, item) => {
        const parent = item.parent_code ?? "";
        if (!acc[parent]) acc[parent] = [];
        acc[parent].push(item);
        return acc;
    }, {});

/** Taraf rolleri türüne göre ayrık: asıl taraf (MAIN) / üçüncü kişi (THIRD). */
export const splitPartyRoles = (items: ConfigItem[]): { main: ConfigItem[]; third: ConfigItem[] } => ({
    main: items.filter(r => r.role_type === "MAIN"),
    third: items.filter(r => r.role_type === "THIRD"),
});

/**
 * G184: TEK listeye abone olur (tek `useQuery`). `useConfig()` 32 sorguya birden
 * abone eder; 1-2 liste kullanan tüketici bununla yalnız ihtiyacı olan listeyi
 * izler. Önbellek `useConfig()` ile ortaktır (`configListQueryOptions`).
 *
 * `error`, `useConfig().configError` ile aynı sözleşmededir (G019: hata ≠ boş liste):
 * hata varsa kullanıcıya gösterilecek mesaj, yoksa `undefined`.
 */
export const useConfigList = (key: ConfigListKey) => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();
    const q = useQuery(configListQueryOptions(key, authRequest, accounts.length > 0));

    return {
        data: q.data ?? EMPTY,
        isLoading: q.isLoading,
        isError: q.isError,
        error: q.isError ? CONFIG_LIST_ERROR : undefined,
        isFetching: q.isFetching,
        refetch: async (): Promise<void> => { await q.refetch(); },
    };
};

export const useConfig = () => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();
    const queryClient = useQueryClient();
    const enabled = accounts.length > 0;

    // Backend'in mesajını (örn. 409 "… zaten listede mevcut") çağırana taşıyarak yanıtı döner
    const request = async <T,>(url: string, method: string, body?: unknown, fallback = "İşlem başarısız"): Promise<T> => {
        const res = await authRequest(url, method, body);
        if (!res?.ok) {
            let detail = fallback;
            try {
                const data = await res?.json();
                if (typeof data?.detail === "string") detail = data.detail;
            } catch { /* gövde JSON değilse generic mesaj kalır */ }
            throw new Error(detail);
        }
        return res.json().catch(() => ({} as T));
    };

    const mutate = async (url: string, method: string, body?: unknown): Promise<boolean> => {
        await request(url, method, body);
        return true;
    };

    const invalidate = (...keys: (typeof CONFIG_KEYS)[keyof typeof CONFIG_KEYS][]) =>
        Promise.all(keys.map((k) => queryClient.invalidateQueries({ queryKey: k })));

    // Zorunlu alan ucu liste sorgularıyla aynı seçenekleri taşır (bkz. configListQueryOptions).
    const queryOpts = { enabled, staleTime: CONFIG_STALE_TIME, retry: false } as const;
    // G184: liste sorguları useConfigList ile TEK kurucudan — önbellek ortak.
    const listOpts = (key: ConfigListKey) => configListQueryOptions(key, authRequest, enabled);

    // --- QUERIES ---
    const lawyersQ = useQuery(listOpts("lawyers"));
    const statusesQ = useQuery(listOpts("statuses"));
    const doctypesQ = useQuery(listOpts("doctypes"));
    const emailRecipientsQ = useQuery(listOpts("emailRecipients"));
    const caseSubjectsQ = useQuery(listOpts("caseSubjects"));
    const fileTypesQ = useQuery(listOpts("fileTypes"));
    const courtTypesQ = useQuery(listOpts("courtTypes"));
    const partyRolesQ = useQuery(listOpts("partyRoles"));
    const bureauTypesQ = useQuery(listOpts("bureauTypes"));
    const citiesQ = useQuery(listOpts("cities"));
    const specialtiesQ = useQuery(listOpts("specialties"));
    const clientCategoriesQ = useQuery(listOpts("clientCategories"));
    const fileStatusesQ = useQuery(listOpts("fileStatuses"));
    const allegedFaultsQ = useQuery(listOpts("allegedFaults"));
    const appealingPartiesQ = useQuery(listOpts("appealingParties"));
    const eventTypesQ = useQuery(listOpts("eventTypes"));
    const judgmentRolesQ = useQuery(listOpts("judgmentRoles"));
    const clientTypesQ = useQuery(listOpts("clientTypes"));
    const serviceTypesQ = useQuery(listOpts("serviceTypes"));
    const currenciesQ = useQuery(listOpts("currencies"));
    const medicalProcessesQ = useQuery(listOpts("medicalProcesses"));
    const medicalEventsQ = useQuery(listOpts("medicalEvents"));
    const patientHarmsQ = useQuery(listOpts("patientHarms"));
    const appliedMethodsQ = useQuery(listOpts("appliedMethods"));
    const cassationCourtsQ = useQuery(listOpts("cassationCourts"));
    const appealCourtsQ = useQuery(listOpts("appealCourts"));
    const defendantAdministrationsQ = useQuery(listOpts("defendantAdministrations"));
    const localDecisionsQ = useQuery(listOpts("localDecisions"));
    const appealDecisionsQ = useQuery(listOpts("appealDecisions"));
    const cassationDecisionsQ = useQuery(listOpts("cassationDecisions"));
    const revisionDecisionsQ = useQuery(listOpts("revisionDecisions"));
    const requiredCaseFieldsQ = useQuery({
        queryKey: ["config", "required_case_fields"],
        queryFn: async (): Promise<{ fields: RequiredCaseField[]; party_rule: RequiredCaseField | null }> => {
            const res = await authRequest("/api/config/required_case_fields", "GET");
            // G019: boş zorunlu alan listesi = "hiçbir alan zorunlu değil" demek;
            // kesintide kapı sessizce açılıyordu. Artık hata state'ine düşer.
            if (!res?.ok) throw new Error(REQUIRED_FIELDS_ERROR);
            return res.json();
        },
        ...queryOpts,
    });

    // G019: hata boş listeden ayrışsın diye açıkça dışa verilir (useClients deseni).
    const listQueries = [
        lawyersQ, statusesQ, doctypesQ, emailRecipientsQ, caseSubjectsQ, fileTypesQ,
        courtTypesQ, partyRolesQ, bureauTypesQ, citiesQ, specialtiesQ,
        clientCategoriesQ, fileStatusesQ, allegedFaultsQ, appealingPartiesQ,
        eventTypesQ, judgmentRolesQ, clientTypesQ, serviceTypesQ,
        localDecisionsQ, appealDecisionsQ, cassationDecisionsQ, revisionDecisionsQ,
        currenciesQ, medicalProcessesQ, medicalEventsQ, patientHarmsQ, appliedMethodsQ,
        cassationCourtsQ, appealCourtsQ, defendantAdministrationsQ,
    ];
    const isConfigError = listQueries.some(q => q.isError);
    const isRequiredFieldsError = requiredCaseFieldsQ.isError;
    const isRefetchingConfig = listQueries.some(q => q.isFetching) || requiredCaseFieldsQ.isFetching;
    const refetchConfig = async (): Promise<void> => {
        await Promise.all([
            ...listQueries.map(q => q.refetch()),
            requiredCaseFieldsQ.refetch(),
        ]);
    };

    const isLoading =
        lawyersQ.isLoading || statusesQ.isLoading || doctypesQ.isLoading ||
        emailRecipientsQ.isLoading || caseSubjectsQ.isLoading ||
        fileTypesQ.isLoading || courtTypesQ.isLoading || partyRolesQ.isLoading ||
        bureauTypesQ.isLoading || citiesQ.isLoading || specialtiesQ.isLoading ||
        clientCategoriesQ.isLoading || fileStatusesQ.isLoading ||
        allegedFaultsQ.isLoading || appealingPartiesQ.isLoading ||
        eventTypesQ.isLoading || judgmentRolesQ.isLoading ||
        clientTypesQ.isLoading || serviceTypesQ.isLoading ||
        localDecisionsQ.isLoading || appealDecisionsQ.isLoading ||
        cassationDecisionsQ.isLoading || revisionDecisionsQ.isLoading ||
        currenciesQ.isLoading || medicalProcessesQ.isLoading || medicalEventsQ.isLoading ||
        patientHarmsQ.isLoading || appliedMethodsQ.isLoading || cassationCourtsQ.isLoading ||
        appealCourtsQ.isLoading || defendantAdministrationsQ.isLoading;

    const typeToKey: Record<string, (typeof CONFIG_KEYS)[keyof typeof CONFIG_KEYS]> = {
        lawyers: CONFIG_KEYS.lawyers,
        statuses: CONFIG_KEYS.statuses,
        doctypes: CONFIG_KEYS.doctypes,
        email_recipients: CONFIG_KEYS.emailRecipients,
        case_subjects: CONFIG_KEYS.caseSubjects,
        file_types: CONFIG_KEYS.fileTypes,
        court_types: CONFIG_KEYS.courtTypes,
        party_roles: CONFIG_KEYS.partyRoles,
        bureau_types: CONFIG_KEYS.bureauTypes,
        cities: CONFIG_KEYS.cities,
        specialties: CONFIG_KEYS.specialties,
        client_categories: CONFIG_KEYS.clientCategories,
        file_statuses: CONFIG_KEYS.fileStatuses,
    };

    const invalidateType = (type: string) => {
        const key = typeToKey[type];
        // Dava türü adı mahkeme türlerinin parent_code'unda da geçer
        const extra = type === "file_types" ? [CONFIG_KEYS.courtTypes] : [];
        return key ? invalidate(key, ...extra) : undefined;
    };

    // --- MUTATIONS ---
    const addLawyerM = useMutation({ mutationFn: ({ code, name, tc_no, sicil_no, gorev, email, phone, address, city }: { code: string; name: string; tc_no?: string; sicil_no?: string; gorev?: string; email?: string; phone?: string; address?: string; city?: string }) => mutate("/api/config/lawyers", "POST", { code, name, tc_no, sicil_no, gorev, email, phone, address, city }), onSuccess: () => invalidate(CONFIG_KEYS.lawyers) });
    const addStatusM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/statuses", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.statuses) });
    const addDoctypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/doctypes", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.doctypes) });
    const addEmailM = useMutation({ mutationFn: ({ name, email, description }: { name: string; email: string; description: string }) => mutate("/api/config/email_recipients", "POST", { name, email, description }), onSuccess: () => invalidate(CONFIG_KEYS.emailRecipients) });

    const addCaseSubjectM = useMutation({
        mutationFn: (name: string) => {
            const code = name.replace(/\s+/g, "").substring(0, 4).toUpperCase() + Math.random().toString(36).substring(2, 6).toUpperCase();
            return mutate("/api/config/case_subjects", "POST", { code, name });
        },
        onSuccess: () => invalidate(CONFIG_KEYS.caseSubjects),
    });

    const addFileTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/file_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.fileTypes) });
    const addCourtTypeM = useMutation({ mutationFn: ({ code, name, parent_code }: { code: string; name: string; parent_code: string }) => mutate("/api/config/court_types", "POST", { code, name, parent_code }), onSuccess: () => invalidate(CONFIG_KEYS.courtTypes) });
    const addPartyRoleM = useMutation({ mutationFn: ({ code, name, role_type }: { code: string; name: string; role_type: string }) => mutate("/api/config/party_roles", "POST", { code, name, role_type }), onSuccess: () => invalidate(CONFIG_KEYS.partyRoles) });
    const addBureauTypeM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/bureau_types", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.bureauTypes) });
    const addCityM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/cities", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.cities) });
    const addSpecialtyM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/specialties", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.specialties) });
    const addClientCategoryM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/client_categories", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.clientCategories) });
    const addFileStatusM = useMutation({ mutationFn: ({ code, name }: { code: string; name: string }) => mutate("/api/config/file_statuses", "POST", { code, name }), onSuccess: () => invalidate(CONFIG_KEYS.fileStatuses) });

    // Ortak düzenleme — ad değiştiyse backend eski adı taşıyan dava/müvekkil/belge
    // kayıtlarına yayar; dönen sayı kaç kaydın yansıdığıdır.
    const updateItemM = useMutation({
        mutationFn: ({ type, code, fields }: { type: string; code: string; fields: Record<string, string | undefined> }) =>
            request<{ updated?: number }>("/api/config/update", "POST", { type, code, fields }, "Güncelleme başarısız")
                .then(d => d.updated ?? 0),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    // Ortak silme — mode bağlı kayıtlara ne olacağını belirler (boşalt / taşı / dokunma)
    const deleteItemM = useMutation({
        mutationFn: ({ type, code, mode, targetCode }: { type: string; code: string; mode: DeleteMode; targetCode?: string }) =>
            request<{ affected?: number }>("/api/config/delete", "POST", { type, code, mode, target_code: targetCode }, "Silme başarısız")
                .then(d => d.affected ?? 0),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    const reorderListM = useMutation({
        mutationFn: ({ type, orderedIds }: { type: string; orderedIds: string[] }) =>
            mutate("/api/config/reorder", "POST", { type, ordered_ids: orderedIds }),
        onSuccess: (_data, { type }) => invalidateType(type),
    });

    // Derived: court types grouped by parent + party roles split by type
    // (G184: useConfigList tüketicisi aynı fonksiyonlarla türetir).
    const courtTypesByParent = groupCourtTypesByParent(courtTypesQ.data ?? EMPTY);
    const { main: mainPartyRoles, third: thirdPartyRoles } = splitPartyRoles(partyRolesQ.data ?? EMPTY);

    return {
        lawyers: lawyersQ.data ?? EMPTY,
        statuses: statusesQ.data ?? EMPTY,
        doctypes: doctypesQ.data ?? EMPTY,
        emailRecipients: emailRecipientsQ.data ?? EMPTY,
        caseSubjects: caseSubjectsQ.data ?? EMPTY,
        fileTypes: fileTypesQ.data ?? EMPTY,
        courtTypes: courtTypesQ.data ?? EMPTY,
        courtTypesByParent,
        partyRoles: partyRolesQ.data ?? EMPTY,
        mainPartyRoles,
        thirdPartyRoles,
        bureauTypes: bureauTypesQ.data ?? EMPTY,
        cities: citiesQ.data ?? EMPTY,
        specialties: specialtiesQ.data ?? EMPTY,
        clientCategories: clientCategoriesQ.data ?? EMPTY,
        fileStatuses: fileStatusesQ.data ?? EMPTY,
        allegedFaults: allegedFaultsQ.data ?? EMPTY,
        appealingParties: appealingPartiesQ.data ?? EMPTY,
        eventTypes: eventTypesQ.data ?? EMPTY,
        judgmentRoles: judgmentRolesQ.data ?? EMPTY,
        clientTypes: clientTypesQ.data ?? EMPTY,
        serviceTypes: serviceTypesQ.data ?? EMPTY,
        // G124 listeleri
        currencies: currenciesQ.data ?? EMPTY,
        medicalProcesses: medicalProcessesQ.data ?? EMPTY,
        medicalEvents: medicalEventsQ.data ?? EMPTY,
        patientHarms: patientHarmsQ.data ?? EMPTY,
        appliedMethods: appliedMethodsQ.data ?? EMPTY,
        cassationCourts: cassationCourtsQ.data ?? EMPTY,
        appealCourts: appealCourtsQ.data ?? EMPTY,
        defendantAdministrations: defendantAdministrationsQ.data ?? EMPTY,
        localDecisions: localDecisionsQ.data ?? EMPTY,
        appealDecisions: appealDecisionsQ.data ?? EMPTY,
        cassationDecisions: cassationDecisionsQ.data ?? EMPTY,
        revisionDecisions: revisionDecisionsQ.data ?? EMPTY,
        requiredCaseFields: requiredCaseFieldsQ.data?.fields ?? EMPTY_REQUIRED,
        requiredPartyRule: requiredCaseFieldsQ.data?.party_rule ?? null,
        isLoading,

        // G019: "hata ≠ boş liste" — çağıran kesintiyi boş listeyle karıştırmasın.
        isConfigError,
        configError: isConfigError ? CONFIG_LIST_ERROR : undefined,
        isRequiredFieldsError,
        requiredFieldsError: isRequiredFieldsError ? REQUIRED_FIELDS_ERROR : undefined,
        refetchConfig,
        isRefetchingConfig,

        addLawyer: (code: string, name: string, tc_no?: string, sicil_no?: string, gorev?: string, email?: string, phone?: string, address?: string, city?: string) => addLawyerM.mutateAsync({ code, name, tc_no, sicil_no, gorev, email, phone, address, city }),
        addStatus: (code: string, name: string) => addStatusM.mutateAsync({ code, name }),
        addDoctype: (code: string, name: string) => addDoctypeM.mutateAsync({ code, name }),
        addEmail: (name: string, email: string, description: string) => addEmailM.mutateAsync({ name, email, description }),
        addCaseSubject: (name: string) => addCaseSubjectM.mutateAsync(name),
        addFileType: (code: string, name: string) => addFileTypeM.mutateAsync({ code, name }),
        addCourtType: (code: string, name: string, parent_code: string) => addCourtTypeM.mutateAsync({ code, name, parent_code }),
        addPartyRole: (code: string, name: string, role_type: string) => addPartyRoleM.mutateAsync({ code, name, role_type }),
        addBureauType: (code: string, name: string) => addBureauTypeM.mutateAsync({ code, name }),
        addCity: (code: string, name: string) => addCityM.mutateAsync({ code, name }),
        addSpecialty: (code: string, name: string) => addSpecialtyM.mutateAsync({ code, name }),
        addClientCategory: (code: string, name: string) => addClientCategoryM.mutateAsync({ code, name }),
        addFileStatus: (code: string, name: string) => addFileStatusM.mutateAsync({ code, name }),

        reorderList: (type: string, orderedIds: string[]) => reorderListM.mutateAsync({ type, orderedIds }),

        /** Liste öğesini düzenler; yansıyan bağlı kayıt sayısını döner. */
        updateItem: (type: string, code: string, fields: Record<string, string | undefined>) => updateItemM.mutateAsync({ type, code, fields }),
        /** Öğenin adını taşıyan bağlı kayıtların dökümü — silme onayı öncesi. */
        fetchUsage: (type: string, code: string) =>
            request<ListUsage>(`/api/config/usage?type=${encodeURIComponent(type)}&code=${encodeURIComponent(code)}`, "GET", undefined, "Kullanım bilgisi alınamadı"),
        /** Liste öğesini siler; etkilenen bağlı kayıt sayısını döner. */
        deleteItem: (type: string, code: string, mode: DeleteMode, targetCode?: string) => deleteItemM.mutateAsync({ type, code, mode, targetCode }),
    };
};
