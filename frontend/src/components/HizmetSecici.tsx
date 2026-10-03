import { useState } from "react";
import { Check, ChevronsUpDown, Lock } from "lucide-react";

import {
  Command, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useConfigList } from "@/hooks/useConfig";
import { foldTr } from "@/lib/aramaKatlama";
import { cn } from "@/lib/utils";

export interface HizmetSeciciProps {
  /** Seçili hizmet adları (`service_types` listesinin ADLARI). Kilitli adlar buraya GİRMEZ. */
  value: string[];
  onChange: (value: string[]) => void;
  /** İşaretli + değiştirilemez gösterilecek adlar (föy/paket kaynaklı hizmetler). */
  kilitli?: string[];
  disabled?: boolean;
  id?: string;
  /** Erişilebilir etiket (ör. "Ali Veli için hizmetler"). */
  "aria-label"?: string;
  placeholder?: string;
  /** İlk çizimde liste açık gelsin (kartta "Hizmet ekle" tıklanınca). */
  defaultOpen?: boolean;
  /** Tetikleyici düğmenin ek sınıfları. */
  className?: string;
}

/** Katlanmış alt-dize eşleşmesi (bulanık skor değil) — `LawyerCombobox` ile aynı kural. */
function eslesir(ad: string, arama: string): boolean {
  const q = foldTr(arama.trim());
  return !q || foldTr(ad).includes(q);
}

/**
 * Hizmet türü çoklu seçicisi (G252; G253 yeni dava ekranlarında da kullanır).
 *
 * Seçenekler `useConfigList("serviceTypes")` — liste sırası (`sequence`) korunur; yayılan
 * değer de liste sırasındadır. Gövde `ui/popover` + `ui/command` (cmdk): onay kutulu liste,
 * Türkçe katlamalı arama, klavye (yazma, ↑↓, Enter işaretler, Esc kapatır). Seçim listeyi
 * açık tutar (çoklu). Kapalıyken seçili adlar tetikleyicide çip, hiç seçim yoksa yer tutucu.
 *
 * `kilitli` adlar işaretli + devre dışı görünür ve `onChange` değerine ASLA girmez (çağıran
 * yalnız kendi kümesini — elle seçimleri — alır).
 *
 * Listede olmayan (eski adlı) seçili değer kaybolmaz: çipte amber "liste dışı" damgasıyla
 * durur ve listenin sonunda yalnız KALDIRILABİLİR satır olarak görünür; yeniden seçenek
 * olarak sunulmaz.
 */
export function HizmetSecici({
  value, onChange, kilitli = [], disabled = false, id, placeholder = "Hizmet seçin…", defaultOpen = false, className,
  ...rest
}: HizmetSeciciProps) {
  const { data: serviceTypes, error } = useConfigList("serviceTypes");
  const [open, setOpen] = useState(defaultOpen && !disabled);
  const [search, setSearch] = useState("");

  const secenekler = serviceTypes.map(s => s.name).filter(Boolean);
  const kilitliKume = new Set(kilitli);
  const seciliKume = new Set(value.filter(ad => !kilitliKume.has(ad)));
  // Liste henüz gelmediyse/boşsa hiçbir değer "liste dışı" sayılmaz (caseCardFields kuralı).
  const listeDisi = (ad: string) => secenekler.length > 0 && !secenekler.includes(ad);
  const listeDisiSecililer = Array.from(seciliKume).filter(ad => !secenekler.includes(ad));

  /** Yayılan değer: liste sırası, ardından listede olmayan seçililer; kilitli adlar hariç. */
  const yay = (kume: Set<string>) => {
    onChange([
      ...secenekler.filter(ad => kume.has(ad)),
      ...Array.from(kume).filter(ad => !secenekler.includes(ad)),
    ]);
  };

  const degistir = (ad: string) => {
    if (disabled || kilitliKume.has(ad)) return;
    const yeni = new Set(seciliKume);
    if (yeni.has(ad)) yeni.delete(ad);
    else yeni.add(ad);
    yay(yeni);
  };

  const acKapat = (o: boolean) => {
    if (disabled) return;
    if (o) setSearch("");
    setOpen(o);
  };

  // Tetikleyicideki çipler: önce kilitli (paket), sonra seçili — ikisi de liste sırasında.
  const sirala = (adlar: string[]) => [
    ...secenekler.filter(ad => adlar.includes(ad)),
    ...adlar.filter(ad => !secenekler.includes(ad)),
  ];
  const kilitliCipler = sirala(Array.from(kilitliKume));
  const seciliCipler = sirala(Array.from(seciliKume));
  const bos = kilitliCipler.length === 0 && seciliCipler.length === 0;

  const gorunenSecenekler = secenekler.filter(ad => eslesir(ad, search));
  const gorunenListeDisi = listeDisiSecililer.filter(ad => eslesir(ad, search));

  return (
    <div className="min-w-0" data-testid="hizmet-secici">
      <Popover open={open} onOpenChange={acKapat}>
        <PopoverTrigger asChild>
          <button
            type="button"
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-label={rest["aria-label"]}
            disabled={disabled}
            className={cn(
              "flex w-full items-center justify-between gap-2 min-h-9 px-3 py-1.5 text-[13px] text-left bg-transparent border border-[var(--border-strong)] rounded-[3px] disabled:cursor-not-allowed disabled:opacity-50",
              className,
            )}
          >
            {bos ? (
              <span className="truncate text-[var(--fg-subtle)]" data-testid="hizmet-secici-yer-tutucu">{placeholder}</span>
            ) : (
              <span className="flex flex-wrap gap-1.5 min-w-0">
                {kilitliCipler.map(ad => (
                  <span
                    key={`k:${ad}`}
                    data-testid="hizmet-secici-cip"
                    data-kilitli="true"
                    title="Kayıtlı hizmet — buradan değiştirilemez"
                    className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium border border-[var(--border-strong)] text-[var(--fg-muted)] bg-[var(--bg-sunken)]"
                  >
                    <Lock className="w-3 h-3 shrink-0" aria-hidden="true" />
                    {ad}
                  </span>
                ))}
                {seciliCipler.map(ad => (
                  <span
                    key={`s:${ad}`}
                    data-testid="hizmet-secici-cip"
                    data-kilitli="false"
                    data-liste-disi={listeDisi(ad) ? "true" : "false"}
                    title={listeDisi(ad) ? "Bu değer hizmet türü listesinde yok" : undefined}
                    className={cn(
                      "inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium border",
                      listeDisi(ad)
                        ? "border-amber-500/40 text-amber-700 dark:text-amber-400"
                        // Yazı normal metin rengi: koyu temada bordo yazı bordo zeminde okunmuyordu (03.10).
                        : "bg-[var(--brand-soft)] text-[var(--fg)] border-brand/50",
                    )}
                  >
                    {ad}
                  </span>
                ))}
              </span>
            )}
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" aria-hidden="true" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[280px] p-0" align="start">
          <Command shouldFilter={false} loop>
            <CommandInput placeholder="Hizmet ara..." aria-label="Hizmet ara" value={search} onValueChange={setSearch} />
            <CommandList className="max-h-64" aria-multiselectable="true">
              {gorunenSecenekler.length === 0 && gorunenListeDisi.length === 0 && (
                <div className="py-3 px-3 text-center text-[12px] text-[var(--fg-subtle)]" data-testid="hizmet-secici-bos">
                  {error ?? (secenekler.length === 0 ? "Hizmet türü listesi boş" : "Hizmet bulunamadı")}
                </div>
              )}
              <CommandGroup>
                {gorunenSecenekler.map(ad => {
                  const kilit = kilitliKume.has(ad);
                  const isaretli = kilit || seciliKume.has(ad);
                  return (
                    <CommandItem
                      key={ad}
                      value={ad}
                      disabled={kilit}
                      onSelect={() => degistir(ad)}
                      data-hizmet={ad}
                      data-checked={isaretli ? "true" : "false"}
                      data-kilitli={kilit ? "true" : "false"}
                      aria-checked={isaretli}
                      // Odaktaki satır: ortak CommandItem yazıyı `accent-foreground` (koyu temada bordo)
                      // yapıyor, bordo zeminde okunmuyor — burada normal metin rengi kalır (03.10).
                      className="text-[13px] data-[selected=true]:text-foreground"
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "mr-2 flex h-4 w-4 shrink-0 items-center justify-center border",
                          isaretli ? "border-[var(--brand)] bg-[var(--brand)] text-white" : "border-[var(--border-strong)]",
                        )}
                      >
                        {isaretli && <Check className="h-3 w-3" />}
                      </span>
                      <span className="truncate flex-1">{ad}</span>
                      {/* Yalnız kilit simgesi: "paket" yazısı kullanıcının kafasını karıştırıyordu (03.10). */}
                      {kilit && <Lock className="ml-2 w-3 h-3 shrink-0 text-[var(--fg-muted)]" aria-hidden="true" data-testid="hizmet-secici-kilit" />}
                    </CommandItem>
                  );
                })}
                {gorunenListeDisi.map(ad => (
                  <CommandItem
                    key={`ld:${ad}`}
                    value={`liste-disi:${ad}`}
                    onSelect={() => degistir(ad)}
                    data-hizmet={ad}
                    data-checked="true"
                    data-liste-disi="true"
                    aria-checked={true}
                    className="text-[13px] data-[selected=true]:text-foreground"
                  >
                    <span
                      aria-hidden="true"
                      className="mr-2 flex h-4 w-4 shrink-0 items-center justify-center border border-amber-500/60 bg-amber-500/20 text-amber-700 dark:text-amber-400"
                    >
                      <Check className="h-3 w-3" />
                    </span>
                    <span className="truncate flex-1">{ad}</span>
                    <span className="ml-2 shrink-0 font-mono text-[9.5px] tracking-[0.1em] uppercase px-1.5 py-0.5 border border-amber-500/40 text-amber-700 dark:text-amber-400">
                      liste dışı
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
