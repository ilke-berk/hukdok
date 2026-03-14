import { useState, useEffect, useCallback, useMemo } from "react";
import { Header } from "@/components/Header";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
    Search, Phone, Mail, MapPin, Loader2,
    Users, Gavel, Stethoscope, Building2, User2,
    ChevronLeft, ChevronRight, X, Filter, ChevronUp, ChevronDown, ListFilter, AlignLeft, Bold, Italic, Underline, List, FileText
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useClients } from "../hooks/useClients";
import { toast } from "sonner";
import { useDebounce } from "../hooks/useDebounce";

import { Checkbox } from "@/components/ui/checkbox";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

export interface Client {
    id: number;
    name: string;
    tc_no?: string;
    email?: string;
    phone?: string;
    mobile_phone?: string;
    address?: string;
    notes?: string;
    contact_type?: string;
    cari_kod?: string;
    category?: string;
    specialty?: string;
}

const ITEMS_PER_PAGE = 10;

const ClientList = () => {
    const navigate = useNavigate();
    const { getClients, isLoading: isHookLoading } = useClients();

    // Core data state
    const [allClients, setAllClients] = useState<Client[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    // UI states
    const [selectedClient, setSelectedClient] = useState<Client | null>(null);
    const [currentPage, setCurrentPage] = useState(1);

    // Filter states
    const [searchQuery, setSearchQuery] = useState("");
    const debouncedSearch = useDebounce(searchQuery, 300);
    const [selectedTypes, setSelectedTypes] = useState<string[]>(["Client", "Other"]);
    const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
    const [selectedCity, setSelectedCity] = useState("all");
    const [selectedSpecialty, setSelectedSpecialty] = useState("all");

    // UX Toggle states for Sidebar (Mockup style)
    const [isFilterOpen, setIsFilterOpen] = useState(true);
    const [isCatOpen, setIsCatOpen] = useState(true);

    const fetchClients = useCallback(async () => {
        try {
            setIsLoading(true);
            const data = await getClients();
            if (data) {
                setAllClients(data);
            } else {
                toast.error("Müvekkil listesi alınamadı.");
            }
        } catch (error) {
            console.error(error);
            toast.error("Bir hata oluştu.");
        } finally {
            setIsLoading(false);
        }
    }, [getClients]);

    useEffect(() => {
        fetchClients();
    }, [fetchClients]);

    const normalizeTurkish = (str: string) => str.toLocaleLowerCase('tr-TR');
    const toTitleCase = (str: string): string => {
        if (!str) return "";
        return str.split(/(\s+|[,;]+)/).map(part => {
            if (/^(\s+|[,;]+)$/.test(part)) return part;
            if (part.length === 0) return part;
            return part.charAt(0).toLocaleUpperCase('tr-TR') + part.slice(1).toLocaleLowerCase('tr-TR');
        }).join("");
    };

    const availableCities = useMemo(() => {
        const cities = new Set<string>();
        allClients.forEach(c => c.address && cities.add(toTitleCase(c.address.trim())));
        return Array.from(cities).sort((a, b) => a.localeCompare(b, "tr"));
    }, [allClients]);

    const availableSpecialties = useMemo(() => {
        const specs = new Set<string>();
        allClients.forEach(c => c.specialty && specs.add(c.specialty.trim()));
        return Array.from(specs).sort((a, b) => a.localeCompare(b, "tr"));
    }, [allClients]);

    const dashboardMetrics = useMemo(() => {
        const justClients = allClients.filter(c => c.contact_type !== "Other");
        return {
            total: justClients.length,
            doctors: justClients.filter(c => c.category === "Doktor").length,
            corporates: justClients.filter(c => c.category === "Kurum" || c.category === "Özel Hastane" || c.category === "Sigorta Şirketi").length,
            individuals: justClients.filter(c => c.category === "Bireysel").length,
            others: justClients.filter(c => !["Doktor", "Kurum", "Özel Hastane", "Sigorta Şirketi", "Bireysel"].includes(c.category || "")).length
        };
    }, [allClients]);

    const filteredClients = useMemo(() => {
        let result = allClients;
        result = result.filter(c => {
            const t = c.contact_type || "Client";
            return selectedTypes.includes(t);
        });
        if (selectedCategories.length > 0) {
            result = result.filter(c => c.category && selectedCategories.includes(c.category));
        }
        if (selectedCity && selectedCity !== "all") {
            result = result.filter(c => c.address && toTitleCase(c.address.trim()) === selectedCity);
        }
        if (selectedSpecialty && selectedSpecialty !== "all") {
            result = result.filter(c => c.specialty && c.specialty.trim() === selectedSpecialty);
        }
        if (debouncedSearch) {
            const query = normalizeTurkish(debouncedSearch);
            result = result.filter(c =>
                normalizeTurkish(c.name).includes(query) ||
                (c.tc_no && c.tc_no.includes(query)) ||
                (c.email && normalizeTurkish(c.email).includes(query)) ||
                (c.cari_kod && normalizeTurkish(c.cari_kod).includes(query)) ||
                (c.phone && c.phone.replace(/\s+/g, '').includes(query.replace(/\s+/g, ''))) ||
                (c.mobile_phone && c.mobile_phone.replace(/\s+/g, '').includes(query.replace(/\s+/g, '')))
            );
        }
        return result;
    }, [allClients, selectedTypes, selectedCategories, selectedCity, selectedSpecialty, debouncedSearch]);

    useEffect(() => {
        setCurrentPage(1);
    }, [filteredClients.length]);

    const totalPages = Math.ceil(filteredClients.length / ITEMS_PER_PAGE);
    const displayedClients = filteredClients.slice(
        (currentPage - 1) * ITEMS_PER_PAGE,
        currentPage * ITEMS_PER_PAGE
    );

    const toggleCategory = (cat: string) => {
        setSelectedCategories(prev => prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]);
    };

    const toggleType = (type: string) => {
        setSelectedTypes(prev => {
            if (prev.includes(type) && prev.length === 1) return prev;
            if (prev.includes(type)) return prev.filter(t => t !== type);
            return [...prev, type];
        });
    }

    const getCategoryIcon = (category?: string) => {
        if (!category) return <User2 className="w-[18px] h-[18px] text-muted-foreground" />;
        const low = category.toLowerCase();
        if (low.includes("doktor")) return <Stethoscope className="w-[18px] h-[18px] text-muted-foreground/80" />;
        if (low.includes("kurum") || low.includes("hastane") || low.includes("sigorta")) return <Building2 className="w-[18px] h-[18px] text-muted-foreground" />;
        return <User2 className="w-[18px] h-[18px] text-muted-foreground" />;
    };

    return (
        <div className="min-h-screen bg-background text-foreground font-sans flex flex-col transition-colors duration-300">
            <Header />

            <main className="flex-1 w-full px-4 sm:px-8 lg:px-12 py-8 flex flex-col gap-8">

                {/* TOP HEADER & METRICS */}
                <div className="flex flex-col gap-6">


                    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 lg:gap-6">
                        <MetricCard title="Toplam Müvekkil:" value={dashboardMetrics.total.toString()} />
                        <MetricCard title="Doktorlar:" value={dashboardMetrics.doctors.toString()} icon={<Stethoscope className="w-6 h-6 text-rose-500/70" />} />
                        <MetricCard title="Kurumlar:" value={dashboardMetrics.corporates.toString()} icon={<Building2 className="w-6 h-6 text-rose-500/70" />} />
                        <MetricCard title="Bireysel:" value={(dashboardMetrics.individuals + dashboardMetrics.others).toString()} icon={<User2 className="w-6 h-6 text-rose-500/70" />} />
                    </div>
                </div>

                {/* 3-COLUMN MAIN LAYOUT */}
                <div className="flex flex-col xl:flex-row gap-6 items-start flex-1 min-h-0">

                    {/* LEFT SIDEBAR (FILTRELEME) */}
                    <div className="w-full xl:w-[280px] shrink-0 flex flex-col gap-4">
                        <div className="bg-card rounded-xl border border-border flex flex-col overflow-hidden shadow-sm">
                            <div
                                className="flex justify-between items-center px-6 py-5 cursor-pointer hover:bg-accent/10 transition-colors"
                                onClick={() => setIsFilterOpen(!isFilterOpen)}
                            >
                                <span className="font-medium text-[15px]">Filtreleme</span>
                                {isFilterOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                            </div>

                            {isFilterOpen && (
                                <div className="px-6 pb-6 flex flex-col gap-6 border-t border-border pt-6">
                                    <div className="space-y-3">
                                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">HIZLI ARAMA</span>
                                        <div className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                            <Input
                                                placeholder="Müvekkil adı, TC, e-posta veya şehir..."
                                                className="pl-9 h-10 text-[13px] bg-secondary/50 border-border text-foreground placeholder:text-muted-foreground rounded-md focus-visible:ring-1 focus-visible:ring-rose-500/50 transition-all font-normal"
                                                value={searchQuery}
                                                onChange={(e) => setSearchQuery(e.target.value)}
                                            />
                                        </div>
                                    </div>

                                    {/* Tür Checkboxes */}
                                    <div className="space-y-4 pt-1">
                                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">KAYIT TÜRÜ</span>
                                        <div className="flex flex-col gap-4">
                                            <div className="flex items-center space-x-3.5">
                                                <Checkbox id="type_client" checked={selectedTypes.includes("Client")} onCheckedChange={() => toggleType("Client")} className="border-muted-foreground data-[state=checked]:bg-rose-600 data-[state=checked]:border-rose-600 w-4 h-4 rounded-sm" />
                                                <label htmlFor="type_client" className="text-[14px] text-foreground/80 cursor-pointer leading-none">Müvekkiller</label>
                                            </div>
                                            <div className="flex items-center space-x-3.5">
                                                <Checkbox id="type_other" checked={selectedTypes.includes("Other")} onCheckedChange={() => toggleType("Other")} className="border-muted-foreground data-[state=checked]:bg-rose-600 data-[state=checked]:border-rose-600 w-4 h-4 rounded-sm" />
                                                <label htmlFor="type_other" className="text-[14px] text-foreground/80 cursor-pointer leading-none">Diğer Kişiler</label>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Kategori Accordion */}
                                    <div className="space-y-4 pt-1">
                                        <div
                                            className="flex justify-between items-center cursor-pointer group"
                                            onClick={() => setIsCatOpen(!isCatOpen)}
                                        >
                                            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">KATEGORİ</span>
                                            {isCatOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" /> : <ChevronDown className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />}
                                        </div>
                                        {isCatOpen && (
                                            <div className="flex flex-col gap-4 mt-2">
                                                {["Doktor", "Kurum", "Özel Hastane", "Bireysel", "Sigorta Şirketi"].map(cat => (
                                                    <div key={cat} className="flex items-center space-x-3.5">
                                                        <Checkbox
                                                            id={`cat_${cat}`}
                                                            checked={selectedCategories.includes(cat)}
                                                            onCheckedChange={() => toggleCategory(cat)}
                                                            className="border-muted-foreground data-[state=checked]:bg-rose-600 data-[state=checked]:border-rose-600 w-4 h-4 rounded-full"
                                                        />
                                                        <label htmlFor={`cat_${cat}`} className="text-[14px] text-foreground/80 cursor-pointer leading-none font-normal">
                                                            {cat}
                                                        </label>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>

                                    {/* Şehir Dropdown */}
                                    <div className="space-y-3 pt-1">
                                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">ŞEHİR</span>
                                        <Select value={selectedCity} onValueChange={setSelectedCity}>
                                            <SelectTrigger className="h-10 text-[13px] bg-secondary/50 border-border text-foreground rounded-md font-normal">
                                                <SelectValue placeholder="Şehir" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-popover border-border text-popover-foreground text-[13px]">
                                                <SelectItem value="all">Tümü ({availableCities.length})</SelectItem>
                                                {availableCities.map(city => (
                                                    <SelectItem key={city} value={city}>{city}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Uzmanlık Dropdown */}
                                    <div className="space-y-3 pt-1">
                                        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest">TIBBİ BRANŞ</span>
                                        <Select value={selectedSpecialty} onValueChange={setSelectedSpecialty}>
                                            <SelectTrigger className="h-10 text-[13px] bg-secondary/50 border-border text-foreground rounded-md font-normal">
                                                <SelectValue placeholder="Tıbbi Branş" />
                                            </SelectTrigger>
                                            <SelectContent className="bg-popover border-border text-popover-foreground text-[13px]">
                                                <SelectItem value="all">Tüm Branşlar ({availableSpecialties.length})</SelectItem>
                                                {availableSpecialties.map(spec => (
                                                    <SelectItem key={spec} value={spec}>{spec}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        className="w-full text-xs font-medium text-muted-foreground hover:text-rose-600 mt-4 h-10 hover:bg-rose-500/10"
                                        onClick={() => {
                                            setSearchQuery("");
                                            setSelectedCategories([]);
                                            setSelectedCity("all");
                                            setSelectedSpecialty("all");
                                            setSelectedTypes(["Client", "Other"]);
                                        }}
                                    >
                                        Filtreleri Temizle
                                    </Button>

                                </div>
                            )}
                        </div>
                    </div>

                    {/* MIDDLE LIST AREA */}
                    <div className="flex-1 min-w-0 flex flex-col bg-card border border-border rounded-xl overflow-hidden shadow-sm">

                        {/* Table Header Band */}
                        <div className="grid grid-cols-12 gap-4 px-8 py-5 bg-muted/30 border-b border-border">
                            <div className="col-span-1 min-w-[40px] flex items-center justify-center">
                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Tür</span>
                            </div>
                            <div className="col-span-11 sm:col-span-5 md:col-span-5 flex items-center pr-4">
                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Ad Soyad / Ünvan</span>
                            </div>
                            <div className="hidden sm:flex sm:col-span-5 md:col-span-3 items-center pr-4">
                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">İletişim</span>
                            </div>
                            <div className="hidden md:flex md:col-span-3 items-center justify-end pr-8">
                                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">Adres / Notlar</span>
                            </div>
                        </div>

                        {/* List Content */}
                        <div className="flex-1 overflow-y-auto pb-4">
                            {isLoading ? (
                                <div className="flex justify-center items-center py-32 flex-col gap-4">
                                    <Loader2 className="w-8 h-8 animate-spin text-rose-600" />
                                    <span className="text-sm text-muted-foreground font-medium tracking-wide">Yükleniyor...</span>
                                </div>
                            ) : displayedClients.length === 0 ? (
                                <div className="flex justify-center items-center py-32 text-muted-foreground text-sm font-normal">
                                    Aradığınız kriterlere uygun müvekkil bulunamadı.
                                </div>
                            ) : (
                                <div className="flex flex-col">
                                    {displayedClients.map((client) => (
                                        <div
                                            key={client.id}
                                            onClick={() => setSelectedClient(client)}
                                            className={`grid grid-cols-12 gap-4 px-8 py-5 items-center border-b border-border cursor-pointer transition-colors hover:bg-accent/5 ${selectedClient?.id === client.id ? 'bg-accent/10 border-l-2 border-l-rose-600' : ''}`}
                                        >
                                            {/* Icon */}
                                            <div className="col-span-1 flex justify-center items-center">
                                                {getCategoryIcon(client.category)}
                                            </div>

                                            {/* Name */}
                                            <div className="col-span-11 sm:col-span-5 md:col-span-5 flex flex-col justify-center min-w-0 pr-4">
                                                <span className="font-semibold text-[15px] text-foreground truncate">{toTitleCase(client.name)}</span>
                                                {(client.category === "Doktor" && client.specialty) && (
                                                    <span className="text-xs text-muted-foreground truncate mt-1.5 font-normal">{client.specialty}</span>
                                                )}
                                                {(client.category !== "Doktor" && client.category) && (
                                                    <span className="text-xs text-muted-foreground truncate mt-1.5 font-normal">{client.category}</span>
                                                )}
                                            </div>

                                            {/* Contact */}
                                            <div className="hidden sm:flex sm:col-span-5 md:col-span-3 flex-col justify-center gap-2.5 min-w-0 pr-4">
                                                {(client.mobile_phone || client.phone) && (
                                                    <div className="flex items-center gap-2 truncate">
                                                        <span className="text-[9px] uppercase font-bold tracking-widest text-muted-foreground">CEP</span>
                                                        <span className="truncate text-sm text-foreground/80 font-sans">{client.mobile_phone || client.phone}</span>
                                                    </div>
                                                )}
                                                {client.email && (
                                                    <div className="flex items-center gap-2.5 truncate">
                                                        <Mail className="w-3.5 h-3.5 shrink-0 opacity-50 text-muted-foreground" />
                                                        <span className="truncate text-[13.5px] text-muted-foreground font-sans">{client.email}</span>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Address / Chevron */}
                                            <div className="hidden md:flex md:col-span-3 justify-end items-center gap-6 min-w-0">
                                                {client.address && (
                                                    <div className="flex items-center gap-2 truncate">
                                                        <MapPin className="w-3.5 h-3.5 shrink-0 opacity-50 text-muted-foreground" />
                                                        <span className="truncate text-sm text-muted-foreground">{toTitleCase(client.address)}</span>
                                                    </div>
                                                )}
                                                <ChevronRight className="w-4 h-4 text-muted-foreground/40 shrink-0" />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Pagination Footer */}
                        {!isLoading && filteredClients.length > 0 && (
                            <div className="px-8 py-5 flex justify-between items-center bg-muted/20 border-t border-border mt-auto">
                                <span className="text-xs text-muted-foreground font-medium">
                                    <strong className="text-foreground/80 font-semibold">{filteredClients.length}</strong> kayıttan {(currentPage - 1) * ITEMS_PER_PAGE + 1} - {Math.min(currentPage * ITEMS_PER_PAGE, filteredClients.length)} arası gösteriliyor.
                                </span>
                                <div className="flex items-center gap-1">
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 rounded-md"
                                        disabled={currentPage === 1}
                                        onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                    >
                                        <ChevronLeft className="h-4 w-4" />
                                    </Button>
                                    <div className="flex items-center justify-center min-w-[36px] px-2 h-8 bg-secondary/50 text-foreground text-xs font-semibold rounded-md border border-border">
                                        {currentPage} / {Math.max(1, totalPages)}
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 rounded-md"
                                        disabled={currentPage >= totalPages}
                                        onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                    >
                                        <ChevronRight className="h-4 w-4" />
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* RIGHT SIDEBAR (HIZLI BAKIŞ) */}
                    {selectedClient && (
                        <div
                            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm xl:hidden"
                            onClick={() => setSelectedClient(null)}
                        />
                    )}

                    <div
                        className={`fixed inset-y-0 right-0 z-50 w-full sm:w-[380px] 2xl:w-[440px] bg-card border-l border-border shadow-2xl transform transition-transform duration-300 ease-in-out flex flex-col xl:static xl:translate-x-0 xl:rounded-xl xl:shadow-sm xl:border ${selectedClient ? "translate-x-0" : "translate-x-full xl:hidden"}`}
                    >
                        {selectedClient && (
                            <>
                                {/* Quick View Header */}
                                <div className="px-6 py-5 border-b border-border flex justify-between items-center bg-muted/20 rounded-t-xl">
                                    <h2 className="text-[16px] font-semibold tracking-wide">Hızlı Bakış (Quick View)</h2>
                                    <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-rose-600 rounded-full hover:bg-rose-500/10" onClick={() => setSelectedClient(null)}>
                                        <X className="w-4 h-4" />
                                    </Button>
                                </div>

                                {/* Quick View Content */}
                                <div className="flex-1 overflow-y-auto p-6 sm:p-8 flex flex-col gap-8">

                                    {/* Action Buttons */}
                                    <div className="flex gap-4 w-full">
                                        <Button
                                            className="flex-1 bg-rose-600 hover:bg-rose-700 text-white rounded-md h-11 text-sm font-semibold shadow-sm transition-all active:scale-[0.98]"
                                            onClick={() => navigate("/new-client", { state: { client: selectedClient } })}
                                        >
                                            Düzenle
                                        </Button>
                                        <Button
                                            variant="outline"
                                            className="flex-1 h-11 text-sm font-semibold border-border text-foreground/70 hover:bg-accent/5 bg-secondary/10 rounded-md transition-all active:scale-[0.98]"
                                            onClick={() => navigate("/", { state: { searchQuery: selectedClient.name } })}
                                        >
                                            <Gavel className="w-4 h-4 mr-2.5 opacity-70" /> Davalar
                                        </Button>
                                    </div>

                                    {/* Basics */}
                                    <div className="flex flex-col gap-2">
                                        <div className="flex items-center gap-2 mb-1">
                                            {selectedClient.contact_type === "Other" && (
                                                <Badge variant="secondary" className="bg-amber-500/10 text-amber-500 border-amber-500/20 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5">DİĞER KİŞİ</Badge>
                                            )}
                                            <Badge variant="outline" className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 border-border/50 text-muted-foreground">ID: #{selectedClient.id}</Badge>
                                        </div>
                                        <h3 className="font-bold text-2xl text-foreground leading-tight tracking-tight">
                                            {toTitleCase(selectedClient.name)}
                                        </h3>
                                        <p className="text-[15px] text-muted-foreground font-medium flex items-center gap-2">
                                            {getCategoryIcon(selectedClient.category)}
                                            {selectedClient.category || "Kategori Belirtilmemiş"}
                                            {selectedClient.category === "Doktor" && selectedClient.specialty && (
                                                <span className="text-muted-foreground/40 font-light mx-1">|</span>
                                            )}
                                            {selectedClient.category === "Doktor" && selectedClient.specialty && selectedClient.specialty}
                                        </p>
                                    </div>

                                    {/* Detailed Info Grid */}
                                    <div className="flex flex-col gap-1">
                                        <div className="grid grid-cols-1 gap-1">
                                            {/* TC NO */}
                                            {selectedClient.tc_no && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">TC Kimlik Numarası</span>
                                                    <div className="flex items-center gap-3">
                                                        <User2 className="w-4 h-4 text-rose-500/60" />
                                                        <span className="font-bold text-foreground text-[15px] tracking-wider">{selectedClient.tc_no}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* CARI KOD */}
                                            {selectedClient.cari_kod && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">Cari Hesap Kodu</span>
                                                    <div className="flex items-center gap-3">
                                                        <FileText className="w-4 h-4 text-rose-500/60" />
                                                        <span className="font-bold text-foreground text-[15px] tracking-tight">{selectedClient.cari_kod}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* PHONE */}
                                            {selectedClient.phone && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">Sabit Telefon</span>
                                                    <div className="flex items-center gap-3">
                                                        <Phone className="w-4 h-4 text-rose-500/60" />
                                                        <span className="font-semibold text-foreground text-[15px]">{selectedClient.phone}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* MOBILE PHONE */}
                                            {selectedClient.mobile_phone && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">Cep Telefonu</span>
                                                        <Badge className="bg-rose-500/10 text-rose-500 border-none text-[9px] font-black h-4 px-1">CEP</Badge>
                                                    </div>
                                                    <div className="flex items-center gap-3">
                                                        <Phone className="w-4 h-4 text-rose-500/60" />
                                                        <span className="font-bold text-foreground text-[15px]">{selectedClient.mobile_phone}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* EMAIL */}
                                            {selectedClient.email && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">E-Posta Adresi</span>
                                                    <div className="flex items-center gap-3">
                                                        <Mail className="w-4 h-4 text-rose-500/60" />
                                                        <span className="font-medium text-foreground text-[14px] truncate">{selectedClient.email}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* ADDRESS */}
                                            {selectedClient.address && (
                                                <div className="flex flex-col gap-1.5 p-3 rounded-lg hover:bg-accent/5 transition-colors border-b border-border/50">
                                                    <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">İkametgah / Adres Bilgisi</span>
                                                    <div className="flex items-start gap-3">
                                                        <MapPin className="w-4 h-4 text-rose-500/60 mt-0.5" />
                                                        <span className="font-medium text-foreground text-[14px] leading-relaxed">{toTitleCase(selectedClient.address)}</span>
                                                    </div>
                                                </div>
                                            )}

                                            {/* NOTES */}
                                            {selectedClient.notes && (
                                                <div className="flex flex-col gap-2 p-4 bg-secondary/20 rounded-xl mt-4 border border-border/50">
                                                    <div className="flex items-center gap-2">
                                                        <AlignLeft className="w-3.5 h-3.5 text-muted-foreground" />
                                                        <span className="text-muted-foreground text-[10px] uppercase tracking-widest font-bold">Yöneticiden Notlar</span>
                                                    </div>
                                                    <p className="text-[13px] leading-relaxed text-foreground/80 italic font-medium">"{selectedClient.notes}"</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                </div>

                            </>
                        )}
                    </div>

                </div>
            </main>
        </div>
    );
};

const MetricCard = ({ title, value, icon }: { title: string, value: string, icon?: React.ReactNode }) => (
    <div className="bg-card border border-border rounded-xl p-6 flex items-center justify-start gap-5 shadow-sm relative overflow-hidden h-[100px] hover:shadow-md transition-shadow">
        {icon && (
            <div className="z-10 bg-secondary/30 p-3 rounded-full border border-border flex-shrink-0">
                {icon}
            </div>
        )}
        <div className="flex flex-col gap-1 z-10">
            <span className="text-[13px] text-muted-foreground font-semibold tracking-wide leading-none">{title}</span>
            <span className="text-[28px] font-bold tracking-tight leading-none mt-0.5">{value}</span>
        </div>

        {/* Subtle decorative background gradient */}
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-rose-500/[0.03] to-transparent pointer-events-none"></div>
    </div>
);

export default ClientList;
