import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMsal } from "@azure/msal-react";
import { useAuthRequest } from "@/hooks/useAuthRequest";

export interface ClientData {
    id?: number;
    name: string;
    tc_no?: string;
    vergi_no?: string;
    email?: string;
    phone?: string;
    mobile_phone?: string;
    address?: string;
    notes?: string;
    client_type?: string;
    category?: string;
    birth_year?: number;
    gender?: string;
    specialty?: string;
    cari_kod?: string;
    il?: string;
    contact_type?: string;
    sektor?: string;
    yevmiye_no?: string;
    noterlik?: string;
    vekaletname_tarihi?: string;
    vekil_avukatlar?: string;
    gecerlilik_tarihi?: string;
    vekalet_no?: string;
    buro_vekalet_no?: string;
}

export interface ClientCaseSummary {
    active_cases: number;
    total_cases: number;
}

/** G002: liste hatası kullanıcıya bu mesajla gösterilir (boş liste ile karışmasın). */
export const CLIENT_LIST_ERROR = "Müvekkil listesi alınamadı — sunucuya ulaşılamadı.";

export const useClients = () => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();
    const queryClient = useQueryClient();
    const enabled = accounts.length > 0;

    const clientsQ = useQuery({
        queryKey: ["clients"],
        queryFn: async () => {
            const res = await authRequest("/api/clients", "GET");
            // G002: eskiden hata da `[]` dönüyordu — müvekkil listesi boş görünüp
            // kullanıcı kayıtların silindiğini sanıyordu. Artık hata state'ine düşer.
            if (!res?.ok) throw new Error(CLIENT_LIST_ERROR);
            return res.json() as Promise<ClientData[]>;
        },
        enabled,
        staleTime: 5 * 60 * 1000,
        // apiClient GET'i zaten 3 denemeye kadar tekrarlıyor (Faz 4.1); react-query'nin
        // ek 3 denemesi hata şeridini ~7 sn geciktirirdi. Tekrar kullanıcıya bırakıldı.
        retry: false,
    });

    const invalidate = () => queryClient.invalidateQueries({ queryKey: ["clients"] });

    const saveClientM = useMutation({
        mutationFn: async (data: ClientData) => {
            const res = await authRequest("/api/clients", "POST", data);
            return res ? res.ok : false;
        },
        onSuccess: invalidate,
    });

    const updateClientM = useMutation({
        mutationFn: async ({ id, data }: { id: number; data: ClientData }) => {
            const res = await authRequest(`/api/clients/${id}`, "PUT", data);
            return res ? res.ok : false;
        },
        onSuccess: invalidate,
    });

    const deleteClientM = useMutation({
        // Soft-delete: gerekçe zorunlu; kayıt arşive taşınır, admin geri alabilir.
        mutationFn: async ({ id, reason }: { id: number; reason: string }) => {
            const res = await authRequest(
                `/api/clients/${id}?reason=${encodeURIComponent(reason)}`, "DELETE"
            );
            return res ? res.ok : false;
        },
        onSuccess: invalidate,
    });

    // Silme dialogu bilgilendirmesi: aktif (DERDEST/DANIŞ) + toplam dava sayısı.
    // Hata durumunda null döner — uyarı gösterilmez, silme engellenmez.
    const getClientCaseSummary = async (id: number): Promise<ClientCaseSummary | null> => {
        const res = await authRequest(`/api/clients/${id}/case-summary`, "GET");
        if (res?.ok) return res.json() as Promise<ClientCaseSummary>;
        return null;
    };

    const isLoading =
        clientsQ.isLoading ||
        saveClientM.isPending ||
        updateClientM.isPending ||
        deleteClientM.isPending;

    return {
        clients: clientsQ.data ?? [],
        isLoading,
        // G002: hata boş listeden ayrışsın diye açıkça dışa verilir.
        isClientsError: clientsQ.isError,
        clientsError: clientsQ.isError ? CLIENT_LIST_ERROR : undefined,
        refetchClients: () => clientsQ.refetch(),
        isRefetchingClients: clientsQ.isFetching,
        saveClient: (data: ClientData) => saveClientM.mutateAsync(data),
        updateClient: (id: number, data: ClientData) => updateClientM.mutateAsync({ id, data }),
        deleteClient: (id: number, reason: string) => deleteClientM.mutateAsync({ id, reason }),
        getClientCaseSummary,
    };
};
