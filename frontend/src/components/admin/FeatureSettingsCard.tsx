// Yönetim paneli "Özellikler" sekmesi — uygulama düzeyi aç/kapa anahtarları.
// Kaynak: GET /api/admin/settings (backend registry'si; frontend'de sabit liste
// tutulmaz), yazım: PUT /api/admin/settings/{key}. Anahtar kapalıyken backend
// ilgili özelliği kullanıcı isteğinden bağımsız uygulamaz (asıl kapı sunucuda);
// buradaki toggle o kapının yönetici yüzüdür.
import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { apiClient } from "@/lib/api";

export interface FeatureSetting {
    key: string;
    value: boolean;
    default: boolean;
    label: string;
    description: string;
    updated_by: string | null;
    updated_at: string | null;
}

const formatUpdatedAt = (iso: string | null): string | null => {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" });
};

export function FeatureSettingsCard() {
    const [settings, setSettings] = useState<FeatureSetting[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [savingKey, setSavingKey] = useState<string | null>(null);

    const load = useCallback(async () => {
        setIsLoading(true);
        setLoadError(null);
        try {
            const res = await apiClient.fetch("/api/admin/settings");
            if (!res.ok) throw new Error("Ayarlar alınamadı");
            const data = await res.json();
            setSettings(data.settings ?? []);
        } catch (e) {
            setLoadError(e instanceof Error ? e.message : "Ayarlar alınamadı");
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    const handleToggle = async (key: string, next: boolean) => {
        const previous = settings;
        // Optimistic: anahtar anında döner, hata olursa geri alınır.
        setSettings(prev => prev.map(s => (s.key === key ? { ...s, value: next } : s)));
        setSavingKey(key);
        try {
            const res = await apiClient.fetch(`/api/admin/settings/${key}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ value: next }),
            });
            if (!res.ok) throw new Error("Ayar kaydedilemedi");
            toast.success(next ? "Özellik açıldı" : "Özellik kapatıldı");
            // updated_by/updated_at sunucuda yazılır — taze hâli çek.
            void load();
        } catch (e) {
            setSettings(previous);
            toast.error(e instanceof Error ? e.message : "Ayar kaydedilemedi");
        } finally {
            setSavingKey(null);
        }
    };

    return (
        <Card className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none">
            <CardHeader>
                <CardTitle>Özellik Anahtarları</CardTitle>
                <CardDescription>
                    Kapalı bir özellik, kullanıcılar istese bile sistem tarafından uygulanmaz.
                </CardDescription>
            </CardHeader>
            <CardContent>
                {isLoading ? (
                    <div className="flex justify-center py-6">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                    </div>
                ) : loadError ? (
                    <p className="text-sm text-destructive py-2">{loadError}</p>
                ) : settings.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-2">Tanımlı özellik anahtarı yok.</p>
                ) : (
                    <ul className="divide-y divide-[var(--border)]">
                        {settings.map(s => {
                            const updatedAt = formatUpdatedAt(s.updated_at);
                            return (
                                <li key={s.key} className="flex items-start justify-between gap-6 py-4">
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium text-[var(--fg)]">{s.label}</p>
                                        <p className="text-[12px] text-[var(--fg-muted)] leading-relaxed mt-1 max-w-[70ch]">
                                            {s.description}
                                        </p>
                                        {s.updated_by && (
                                            <p className="text-[11px] text-[var(--fg-muted)] opacity-70 mt-1.5">
                                                Son değişiklik: {s.updated_by}{updatedAt ? ` · ${updatedAt}` : ""}
                                            </p>
                                        )}
                                    </div>
                                    <div className="flex items-center gap-2 shrink-0 pt-0.5">
                                        <span className={`text-[11px] font-mono uppercase tracking-[0.06em] ${s.value ? "text-[var(--brand)]" : "text-[var(--fg-muted)]"}`}>
                                            {s.value ? "Açık" : "Kapalı"}
                                        </span>
                                        <Switch
                                            checked={s.value}
                                            disabled={savingKey === s.key}
                                            onCheckedChange={(next: boolean) => void handleToggle(s.key, next)}
                                            aria-label={s.label}
                                        />
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </CardContent>
        </Card>
    );
}
