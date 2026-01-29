
import { useState, useEffect } from "react";
import { getApiUrl } from "@/lib/api";

type Option = {
    code: string;
    name: string;
    description?: string;
};

export const useConfig = () => {
    const [lawyers, setLawyers] = useState<Option[]>([]);
    const [statuses, setStatuses] = useState<Option[]>([]);
    const [doctypes, setDoctypes] = useState<Option[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const baseUrl = await getApiUrl();

                const [resLawyers, resStatuses, resDoctypes] = await Promise.all([
                    fetch(`${baseUrl}/api/config/lawyers`),
                    fetch(`${baseUrl}/api/config/statuses`),
                    fetch(`${baseUrl}/api/config/doctypes`),
                ]);

                if (resLawyers.ok) setLawyers(await resLawyers.json());
                if (resStatuses.ok) setStatuses(await resStatuses.json());
                if (resDoctypes.ok) setDoctypes(await resDoctypes.json());

            } catch (error) {
                console.error("Failed to load config:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchConfig();
    }, []);

    return { lawyers, statuses, doctypes, isLoading };
};
