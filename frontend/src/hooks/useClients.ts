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
}

export const useClients = () => {
    const { accounts } = useMsal();
    const { authRequest } = useAuthRequest();
    const queryClient = useQueryClient();
    const enabled = accounts.length > 0;

    const clientsQ = useQuery({
        queryKey: ["clients"],
        queryFn: async () => {
            const res = await authRequest("/api/clients", "GET");
            if (res?.ok) return res.json() as Promise<ClientData[]>;
            return [] as ClientData[];
        },
        enabled,
        staleTime: 5 * 60 * 1000,
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
        mutationFn: async (id: number) => {
            const res = await authRequest(`/api/clients/${id}`, "DELETE");
            return res ? res.ok : false;
        },
        onSuccess: invalidate,
    });

    const isLoading =
        clientsQ.isLoading ||
        saveClientM.isPending ||
        updateClientM.isPending ||
        deleteClientM.isPending;

    return {
        clients: clientsQ.data ?? [],
        isLoading,
        saveClient: (data: ClientData) => saveClientM.mutateAsync(data),
        updateClient: (id: number, data: ClientData) => updateClientM.mutateAsync({ id, data }),
        deleteClient: (id: number) => deleteClientM.mutateAsync(id),
    };
};
