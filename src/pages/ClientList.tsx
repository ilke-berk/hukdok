import { useState, useEffect } from "react";
import { Header } from "@/components/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { UserPlus, Search, User, Phone, Mail, MapPin, Loader2, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useClients } from "@/hooks/useClients";
import { toast } from "sonner";

interface Client {
    id: number;
    name: string;
    tc_no?: string;
    email?: string;
    phone?: string;
    address?: string;
    notes?: string;
}

const ClientList = () => {
    const navigate = useNavigate();
    const { getClients, isLoading: isHookLoading } = useClients();
    const [clients, setClients] = useState<Client[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");

    useEffect(() => {
        fetchClients();
    }, []);

    const fetchClients = async () => {
        try {
            setIsLoading(true);
            const data = await getClients();
            if (data) {
                setClients(data);
            } else {
                toast.error("Müvekkil listesi alınamadı.");
            }
        } catch (error) {
            console.error(error);
            toast.error("Bir hata oluştu.");
        } finally {
            setIsLoading(false);
        }
    };

    const filteredClients = clients.filter(client =>
        client.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (client.tc_no && client.tc_no.includes(searchQuery)) ||
        (client.email && client.email.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    return (
        <div className="min-h-screen bg-background">
            <Header />

            <main className="container mx-auto px-6 py-8">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight text-primary">Müvekkiller</h1>
                        <p className="text-muted-foreground mt-1">
                            Sistemde kayıtlı müvekkilleri görüntüleyin ve yönetin.
                        </p>
                    </div>
                    <Button onClick={() => navigate("/new-client")} size="lg" className="shadow-lg gap-2">
                        <UserPlus className="w-5 h-5" />
                        Yeni Müvekkil
                    </Button>
                </div>

                <Card className="glass-card shadow-lg border-muted/40">
                    <CardHeader className="pb-4">
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                            <Input
                                placeholder="İsim, TC No veya E-posta ile ara..."
                                className="pl-10 text-lg py-6"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                    </CardHeader>
                    <CardContent>
                        {isLoading ? (
                            <div className="flex justify-center py-12">
                                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                            </div>
                        ) : filteredClients.length === 0 ? (
                            <div className="text-center py-12 text-muted-foreground">
                                <p className="text-lg">Müvekkil bulunamadı.</p>
                                {searchQuery && <p className="text-sm">Arama kriterlerini değiştirip tekrar deneyin.</p>}
                            </div>
                        ) : (
                            <div className="rounded-md border">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            <TableHead>Ad Soyad / Ünvan</TableHead>
                                            <TableHead>İletişim</TableHead>
                                            <TableHead>Adres / Notlar</TableHead>
                                            <TableHead className="text-right">Detay</TableHead>
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {filteredClients.map((client) => (
                                            <TableRow key={client.id} className="group cursor-pointer hover:bg-muted/50">
                                                <TableCell className="font-medium text-lg">
                                                    <div className="flex flex-col">
                                                        <span>{client.name}</span>
                                                        {client.tc_no && (
                                                            <span className="text-sm text-muted-foreground font-mono">{client.tc_no}</span>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex flex-col gap-1 text-sm">
                                                        {client.phone && (
                                                            <div className="flex items-center gap-2 text-muted-foreground">
                                                                <Phone className="w-3 h-3" /> {client.phone}
                                                            </div>
                                                        )}
                                                        {client.email && (
                                                            <div className="flex items-center gap-2 text-muted-foreground">
                                                                <Mail className="w-3 h-3" /> {client.email}
                                                            </div>
                                                        )}
                                                    </div>
                                                </TableCell>
                                                <TableCell className="max-w-xs truncate text-muted-foreground text-sm">
                                                    {client.address && (
                                                        <div className="flex items-center gap-1 truncate mb-1" title={client.address}>
                                                            <MapPin className="w-3 h-3 shrink-0" /> {client.address}
                                                        </div>
                                                    )}
                                                    {client.notes && (
                                                        <div className="flex items-center gap-1 truncate text-xs italic opacity-70" title={client.notes}>
                                                            <FileText className="w-3 h-3 shrink-0" /> {client.notes}
                                                        </div>
                                                    )}
                                                </TableCell>
                                                <TableCell className="text-right">
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="hover:bg-primary/10 hover:text-primary"
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            navigate("/new-client", { state: { client } });
                                                        }}
                                                    >
                                                        Düzenle
                                                    </Button>
                                                </TableCell>
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        )}
                        <div className="mt-4 text-xs text-muted-foreground text-center">
                            Toplam {filteredClients.length} kayıt listelendi.
                        </div>
                    </CardContent>
                </Card>
            </main>
        </div>
    );
};

export default ClientList;
