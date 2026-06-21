import { useState, useEffect, useMemo } from "react";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { usePageSearch } from "@/components/system/PageSearch";
import {
  Phone, Mail, MapPin, Loader2,
  Users, Gavel, Stethoscope, Building2, User2, UserPlus,
  ChevronLeft, ChevronRight, X, FileText, AlignLeft,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useClients } from "../hooks/useClients";
import { useDebounce } from "../hooks/useDebounce";
import { YetkiBelgesiModal } from "@/components/YetkiBelgesiModal";

import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { MetricCard, SectionHeader, HairlineCard, Eyebrow } from "@/components/dashboard/primitives";
import { FlowButton } from "@/components/flow/primitives";

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
  client_type?: string;
  il?: string;
  sektor?: string;
  yevmiye_no?: string;
  noterlik?: string;
  vekaletname_tarihi?: string;
  vekil_avukatlar?: string;
  gecerlilik_tarihi?: string;
  vekalet_no?: string;
  buro_vekalet_no?: string;
}

const ITEMS_PER_PAGE = 12;
const CATEGORIES = ["Doktor", "Kurum", "Özel Hastane", "Bireysel", "Sigorta Şirketi"];

function normalizeTurkish(str: string) {
  return str.toLocaleLowerCase("tr-TR");
}

function toTitleCase(str: string): string {
  if (!str) return "";
  return str.split(/(\s+|[,;]+)/).map(part => {
    if (/^(\s+|[,;]+)$/.test(part)) return part;
    if (part.length === 0) return part;
    return part.charAt(0).toLocaleUpperCase("tr-TR") + part.slice(1).toLocaleLowerCase("tr-TR");
  }).join("");
}

function CategoryIcon({ category, className = "w-4 h-4" }: { category?: string; className?: string }) {
  if (!category) return <User2 className={className} />;
  const low = category.toLowerCase();
  if (low.includes("doktor")) return <Stethoscope className={className} />;
  if (low.includes("kurum") || low.includes("hastane") || low.includes("sigorta")) return <Building2 className={className} />;
  return <User2 className={className} />;
}

function DetailRow({ label, value, icon: Icon }: { label: string; value: React.ReactNode; icon?: typeof User2 }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-3 py-2.5 border-b border-[var(--border)] last:border-b-0">
      <span className="font-mono text-[9.5px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] self-center">
        {label}
      </span>
      <div className="flex items-center gap-2 text-[13px] text-[var(--fg)] min-w-0">
        {Icon && <Icon className="w-3.5 h-3.5 text-[var(--fg-subtle)] shrink-0" />}
        <span className="truncate">{value}</span>
      </div>
    </div>
  );
}

const ClientList = () => {
  useSetPageTitle("Müvekkiller", ["Avukat Paneli"]);
  const navigate = useNavigate();
  const { clients: allClients, isLoading: isClientsLoading } = useClients();
  const [initialLoaded, setInitialLoaded] = useState(false);
  const isLoading = !initialLoaded && isClientsLoading;

  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  // Arama tek mutlak üst bardan sürülür (usePageSearch)
  const { query: searchQuery, setQuery: setSearchQuery } = usePageSearch({
    placeholder: "Ad, TC, e-posta, telefon veya cari kod ile ara…",
  });
  const debouncedSearch = useDebounce(searchQuery, 300);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(["Client", "Other"]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>([]);
  const [selectedCity, setSelectedCity] = useState("all");
  const [selectedSpecialty, setSelectedSpecialty] = useState("all");

  const [yetkiBelgesiOpen, setYetkiBelgesiOpen] = useState(false);

  useEffect(() => {
    if (!isClientsLoading && !initialLoaded) setInitialLoaded(true);
  }, [isClientsLoading, initialLoaded]);

  const availableCities = useMemo(() => {
    const cities = new Set<string>();
    allClients.forEach(c => c.il && cities.add(toTitleCase(c.il.trim())));
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
      others: justClients.filter(c => !["Doktor", "Kurum", "Özel Hastane", "Sigorta Şirketi", "Bireysel"].includes(c.category || "")).length,
    };
  }, [allClients]);

  const filteredClients = useMemo(() => {
    let result = allClients;
    result = result.filter(c => selectedTypes.includes(c.contact_type || "Client"));
    if (selectedCategories.length > 0) {
      result = result.filter(c => c.category && selectedCategories.includes(c.category));
    }
    if (selectedCity !== "all") {
      result = result.filter(c => c.il && toTitleCase(c.il.trim()) === selectedCity);
    }
    if (selectedSpecialty !== "all") {
      result = result.filter(c => c.specialty && c.specialty.trim() === selectedSpecialty);
    }
    if (debouncedSearch) {
      const q = normalizeTurkish(debouncedSearch);
      result = result.filter(c =>
        normalizeTurkish(c.name).includes(q) ||
        (c.tc_no && c.tc_no.includes(q)) ||
        (c.email && normalizeTurkish(c.email).includes(q)) ||
        (c.cari_kod && normalizeTurkish(c.cari_kod).includes(q)) ||
        (c.phone && c.phone.replace(/\s+/g, "").includes(q.replace(/\s+/g, ""))) ||
        (c.mobile_phone && c.mobile_phone.replace(/\s+/g, "").includes(q.replace(/\s+/g, "")))
      );
    }
    return result;
  }, [allClients, selectedTypes, selectedCategories, selectedCity, selectedSpecialty, debouncedSearch]);

  useEffect(() => { setCurrentPage(1); }, [filteredClients.length]);

  const totalPages = Math.ceil(filteredClients.length / ITEMS_PER_PAGE);
  const displayedClients = filteredClients.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE,
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
  };

  const clearFilters = () => {
    setSearchQuery("");
    setSelectedCategories([]);
    setSelectedCity("all");
    setSelectedSpecialty("all");
    setSelectedTypes(["Client", "Other"]);
  };

  const activeFilterCount =
    (debouncedSearch ? 1 : 0) +
    selectedCategories.length +
    (selectedCity !== "all" ? 1 : 0) +
    (selectedSpecialty !== "all" ? 1 : 0) +
    (selectedTypes.length !== 2 ? 1 : 0);

  return (
    <div className="grid gap-7 max-w-[1600px]">

      {/* Üst başlık */}
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <Eyebrow>01 · Liste</Eyebrow>
          <h1 className="mt-1 font-display text-[26px] tracking-[-0.01em] text-[var(--fg)] font-medium">
            Müvekkiller
          </h1>
        </div>
        <FlowButton variant="primary" onClick={() => navigate("/new-client")}>
          <UserPlus className="w-3.5 h-3.5" />
          Yeni Müvekkil
        </FlowButton>
      </div>

      {/* Metrikler */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Toplam Müvekkil"
          value={dashboardMetrics.total}
          icon={<Users className="w-4 h-4" />}
          tone="brand"
          hint="Aktif kayıtlar"
        />
        <MetricCard
          label="Doktorlar"
          value={dashboardMetrics.doctors}
          icon={<Stethoscope className="w-4 h-4" />}
          tone="success"
          hint="Sağlık profesyonelleri"
        />
        <MetricCard
          label="Kurumlar"
          value={dashboardMetrics.corporates}
          icon={<Building2 className="w-4 h-4" />}
          tone="warning"
          hint="Hastane · Sigorta"
        />
        <MetricCard
          label="Bireysel"
          value={dashboardMetrics.individuals + dashboardMetrics.others}
          icon={<User2 className="w-4 h-4" />}
          tone="neutral"
          hint="Şahıs müvekkiller"
        />
      </section>

      {/* Üçlü grid: rail + tablo + quick view */}
      <section
        className="grid gap-5 items-start"
        style={{ gridTemplateColumns: selectedClient ? "260px 1fr 380px" : "260px 1fr" }}
      >
        {/* Filtre rail */}
        <HairlineCard className="flex flex-col gap-6 sticky top-2">
          {activeFilterCount > 0 && (
            <div className="flex items-center justify-between gap-2 -mb-2">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                {activeFilterCount} filtre aktif
              </span>
              <FlowButton variant="ghost" size="sm" onClick={clearFilters}>
                <X className="w-3 h-3" />
                Temizle
              </FlowButton>
            </div>
          )}
          <div>
            <Eyebrow>Kayıt Türü</Eyebrow>
            <div className="mt-2 flex flex-col gap-2">
              <label className="flex items-center gap-2.5 cursor-pointer">
                <Checkbox
                  checked={selectedTypes.includes("Client")}
                  onCheckedChange={() => toggleType("Client")}
                  className="w-4 h-4 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
                />
                <span className="text-[13px] text-[var(--fg)]">Müvekkiller</span>
              </label>
              <label className="flex items-center gap-2.5 cursor-pointer">
                <Checkbox
                  checked={selectedTypes.includes("Other")}
                  onCheckedChange={() => toggleType("Other")}
                  className="w-4 h-4 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
                />
                <span className="text-[13px] text-[var(--fg)]">Diğer Kişiler</span>
              </label>
            </div>
          </div>

          <div>
            <Eyebrow>Kategori</Eyebrow>
            <div className="mt-2 flex flex-col gap-2">
              {CATEGORIES.map(cat => (
                <label key={cat} className="flex items-center gap-2.5 cursor-pointer">
                  <Checkbox
                    checked={selectedCategories.includes(cat)}
                    onCheckedChange={() => toggleCategory(cat)}
                    className="w-4 h-4 rounded-[2px] data-[state=checked]:bg-[var(--brand)] data-[state=checked]:border-[var(--brand)]"
                  />
                  <span className="text-[13px] text-[var(--fg)]">{cat}</span>
                </label>
              ))}
            </div>
          </div>

          <div>
            <Eyebrow>Şehir</Eyebrow>
            <Select value={selectedCity} onValueChange={setSelectedCity}>
              <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                <SelectValue placeholder="Şehir" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tümü ({availableCities.length})</SelectItem>
                {availableCities.map(city => (
                  <SelectItem key={city} value={city}>{city}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {availableSpecialties.length > 0 && (
            <div>
              <Eyebrow>Tıbbi Branş</Eyebrow>
              <Select value={selectedSpecialty} onValueChange={setSelectedSpecialty}>
                <SelectTrigger className="mt-2 h-10 bg-[var(--bg)] border-[var(--border)] text-[13px] rounded-[3px]">
                  <SelectValue placeholder="Branş" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tümü ({availableSpecialties.length})</SelectItem>
                  {availableSpecialties.map(spec => (
                    <SelectItem key={spec} value={spec}>{spec}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </HairlineCard>

        {/* Tablo */}
        <HairlineCard padded={false}>
          <div className="flex items-baseline justify-between px-5 py-4 border-b border-[var(--border)]">
            <SectionHeader
              title={debouncedSearch ? "Arama Sonuçları" : "Müvekkil Listesi"}
              italic={debouncedSearch ? `— "${debouncedSearch}"` : undefined}
              className="flex-1"
              meta={
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  {isLoading ? "Yükleniyor…" : `${filteredClients.length} kayıt`}
                </span>
              }
            />
          </div>

          {isLoading ? (
            <div className="grid place-items-center gap-3 py-20 text-[var(--fg-subtle)]">
              <Loader2 className="w-7 h-7 animate-spin" />
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase">Yükleniyor</span>
            </div>
          ) : displayedClients.length === 0 ? (
            <div className="grid place-items-center gap-3 py-20 text-center text-[var(--fg-subtle)]">
              <Users className="w-9 h-9 opacity-30" />
              <p className="text-[13px]">Bu kriterlere uygun müvekkil bulunamadı.</p>
              {activeFilterCount > 0 && (
                <FlowButton variant="secondary" size="sm" onClick={clearFilters}>
                  Filtreleri temizle
                </FlowButton>
              )}
            </div>
          ) : (
            <div className="flex flex-col">
              {displayedClients.map(c => {
                const isSelected = selectedClient?.id === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setSelectedClient(c)}
                    className={[
                      "grid grid-cols-[auto_1fr_auto] gap-4 items-center px-5 py-3.5 text-left transition-colors border-b border-[var(--border)] last:border-b-0",
                      isSelected
                        ? "bg-[var(--brand-soft)] border-l-2 border-l-[var(--brand)]"
                        : "hover:bg-[var(--bg)]",
                    ].join(" ")}
                  >
                    <div className="w-8 h-8 rounded-full grid place-items-center bg-[var(--bg-sunken)] text-[var(--brand)] shrink-0">
                      <CategoryIcon category={c.category} className="w-4 h-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-display text-[14px] font-medium text-[var(--fg)] truncate">
                          {toTitleCase(c.name)}
                        </span>
                        {c.contact_type === "Other" && (
                          <span className="inline-flex items-center px-1.5 py-0.5 font-mono text-[9px] tracking-[0.14em] uppercase border border-[#c47a1e]/30 bg-[#c47a1e]/10 text-[#c47a1e]">
                            Diğer
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-[11px] text-[var(--fg-subtle)] mt-1">
                        {c.category && (
                          <span className="truncate">{c.category}{c.specialty ? ` · ${c.specialty}` : ""}</span>
                        )}
                        {c.mobile_phone || c.phone ? (
                          <span className="font-mono tracking-[0.04em] truncate">
                            {c.mobile_phone || c.phone}
                          </span>
                        ) : null}
                        {c.il && <span className="truncate">{toTitleCase(c.il)}</span>}
                      </div>
                    </div>
                    <ChevronRight className="w-3.5 h-3.5 text-[var(--fg-subtle)] shrink-0" />
                  </button>
                );
              })}
            </div>
          )}

          {filteredClients.length > 0 && (
            <div className="flex items-center justify-between px-5 py-3 border-t border-[var(--border)] bg-[var(--bg)]">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                {(currentPage - 1) * ITEMS_PER_PAGE + 1}–{Math.min(currentPage * ITEMS_PER_PAGE, filteredClients.length)} / {filteredClients.length}
              </span>
              <div className="flex items-center gap-2">
                <FlowButton
                  variant="ghost"
                  size="sm"
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                >
                  <ChevronLeft className="w-3.5 h-3.5" />
                  Geri
                </FlowButton>
                <span className="font-mono text-[11px] tabular-nums px-2.5 py-1 border border-[var(--border)] bg-[var(--bg-elevated)]">
                  {currentPage} / {Math.max(1, totalPages)}
                </span>
                <FlowButton
                  variant="ghost"
                  size="sm"
                  disabled={currentPage >= totalPages}
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                >
                  İleri
                  <ChevronRight className="w-3.5 h-3.5" />
                </FlowButton>
              </div>
            </div>
          )}
        </HairlineCard>

        {/* Quick View paneli */}
        {selectedClient && (
          <HairlineCard padded={false} className="sticky top-2 max-h-[calc(100vh-3rem)] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)] bg-[var(--bg)]">
              <Eyebrow tone="brand">Hızlı Bakış</Eyebrow>
              <button
                type="button"
                onClick={() => setSelectedClient(null)}
                aria-label="Paneli kapat"
                className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 grid gap-5">
              {/* Headline */}
              <div>
                <div className="flex items-center gap-2 font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  <CategoryIcon category={selectedClient.category} className="w-3.5 h-3.5" />
                  {selectedClient.category || "Kategori belirtilmemiş"}
                  {selectedClient.specialty && <span>· {selectedClient.specialty}</span>}
                </div>
                <h2 className="mt-1.5 font-display text-[20px] tracking-[-0.005em] text-[var(--fg)] font-medium leading-tight">
                  {toTitleCase(selectedClient.name)}
                </h2>
                <div className="mt-2 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                  ID · #{selectedClient.id}
                </div>
              </div>

              {/* Eylemler */}
              <div className="grid gap-2">
                <div className="grid grid-cols-2 gap-2">
                  <FlowButton variant="primary" size="sm" onClick={() => navigate("/new-client", { state: { client: selectedClient } })}>
                    Düzenle
                  </FlowButton>
                  <FlowButton variant="secondary" size="sm" onClick={() => navigate("/cases", { state: { clientName: selectedClient.name } })}>
                    <Gavel className="w-3.5 h-3.5" />
                    Davalar
                  </FlowButton>
                </div>
                <FlowButton variant="secondary" size="sm" onClick={() => setYetkiBelgesiOpen(true)}>
                  <FileText className="w-3.5 h-3.5" />
                  Yetki Belgesi
                </FlowButton>
              </div>

              {/* Detaylar */}
              <div className="border-t border-[var(--border)] pt-2">
                {selectedClient.tc_no && <DetailRow label="TC" value={selectedClient.tc_no} icon={User2} />}
                {selectedClient.cari_kod && <DetailRow label="Cari" value={selectedClient.cari_kod} icon={FileText} />}
                {selectedClient.mobile_phone && <DetailRow label="Cep" value={selectedClient.mobile_phone} icon={Phone} />}
                {selectedClient.phone && !selectedClient.mobile_phone && <DetailRow label="Tel" value={selectedClient.phone} icon={Phone} />}
                {selectedClient.email && <DetailRow label="E-posta" value={selectedClient.email} icon={Mail} />}
                {selectedClient.address && <DetailRow label="Adres" value={toTitleCase(selectedClient.address)} icon={MapPin} />}
                {selectedClient.il && !selectedClient.address && <DetailRow label="İl" value={toTitleCase(selectedClient.il)} icon={MapPin} />}
                {selectedClient.sektor && <DetailRow label="Sektör" value={selectedClient.sektor} icon={Building2} />}
              </div>

              {/* Vekalet bilgileri */}
              {(selectedClient.noterlik || selectedClient.vekaletname_tarihi || selectedClient.buro_vekalet_no || selectedClient.vekil_avukatlar) && (
                <div className="bg-[var(--bg-sunken)] border border-[var(--border)] p-4">
                  <div className="font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] mb-2 pb-2 border-b border-[var(--border)]">
                    Vekalet Bilgileri
                  </div>
                  <div className="grid gap-2 text-[12px]">
                    {selectedClient.buro_vekalet_no && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Büro Vekalet No</span>
                        <span className="font-mono text-[var(--fg)] text-right">{selectedClient.buro_vekalet_no}</span>
                      </div>
                    )}
                    {selectedClient.yevmiye_no && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Yevmiye No</span>
                        <span className="font-mono text-[var(--fg)] text-right">{selectedClient.yevmiye_no}</span>
                      </div>
                    )}
                    {selectedClient.noterlik && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Noterlik</span>
                        <span className="text-[var(--fg)] text-right truncate max-w-[180px]">{selectedClient.noterlik}</span>
                      </div>
                    )}
                    {selectedClient.vekaletname_tarihi && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Veriliş</span>
                        <span className="font-mono text-[var(--fg)]">{selectedClient.vekaletname_tarihi}</span>
                      </div>
                    )}
                    {selectedClient.gecerlilik_tarihi && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Geçerlilik</span>
                        <span className="font-mono text-[var(--fg)]">{selectedClient.gecerlilik_tarihi}</span>
                      </div>
                    )}
                    {selectedClient.vekalet_no && (
                      <div className="flex justify-between gap-3">
                        <span className="text-[var(--fg-muted)]">Vekalet No</span>
                        <span className="font-mono text-[var(--fg)]">{selectedClient.vekalet_no}</span>
                      </div>
                    )}
                    {selectedClient.vekil_avukatlar && (
                      <div className="mt-1.5 pt-2 border-t border-[var(--border)]">
                        <div className="text-[var(--fg-muted)] mb-1.5">Vekil Avukatlar</div>
                        <div className="flex flex-col gap-1">
                          {selectedClient.vekil_avukatlar.split(";").map((av, idx) => (
                            <span key={idx} className="text-[12px] text-[var(--fg)] pl-2 border-l-2 border-[var(--brand)]/40">
                              {toTitleCase(av.trim())}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Notlar */}
              {selectedClient.notes && (
                <div className="bg-[var(--bg-sunken)] border border-[var(--border)] p-4">
                  <div className="flex items-center gap-1.5 font-mono text-[9.5px] tracking-[0.18em] uppercase text-[var(--fg-subtle)] mb-2">
                    <AlignLeft className="w-3 h-3" />
                    Notlar
                  </div>
                  <p className="text-[13px] leading-relaxed text-[var(--fg-muted)] italic">
                    "{selectedClient.notes}"
                  </p>
                </div>
              )}
            </div>
          </HairlineCard>
        )}
      </section>

      {selectedClient && yetkiBelgesiOpen && (
        <YetkiBelgesiModal
          open={yetkiBelgesiOpen}
          onClose={() => setYetkiBelgesiOpen(false)}
          client={selectedClient}
        />
      )}
    </div>
  );
};

export default ClientList;
