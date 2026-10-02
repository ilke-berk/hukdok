import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";

import {
  Command, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { foldTr } from "@/lib/aramaKatlama";

/** Liste açıkken basılan en fazla satır — Tıbbi Olay ~800 seçenek; arama/süreç daraltır. */
const GORUNUR_MAX = 100;
const TUMU = "ALL";

/** Seçenek: ad (= değer) + isteğe bağlı dava sayısı (satırın sağında basılır). */
export interface ListeFiltreSecenegi {
  name: string;
  count?: number;
}

interface Props {
  /** Seçenekler (backend sırası korunur); değer = ad. */
  options: ListeFiltreSecenegi[];
  /** Seçili ad ya da "ALL" (filtre yok). */
  value: string;
  onChange: (value: string) => void;
  /** Arama kutusu ve boş sonuç metninde geçen ad (ör. "tıbbi süreç"). */
  noun: string;
  "aria-label"?: string;
  className?: string;
}

/**
 * Uzun kapalı listeler için yazarak aranan tekli filtre seçimi (02.10: dava listesi
 * Tıbbi Süreç / Tıbbi Olay). `LawyerCombobox`'ın sade kardeşi: sekme/rozet yok, başta
 * "Tümü" satırı (değer "ALL"), Türkçe katlamalı alt-dize araması, en fazla
 * `GORUNUR_MAX` satır basılır; `count` verilen seçenekte dava sayısı sağda görünür.
 */
export function ListeFiltreCombobox({ options, value, onChange, noun, className, ...rest }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const q = foldTr(search.trim());
  const eslesenler = q ? options.filter(o => foldTr(o.name).includes(q)) : options;
  const gorunen = eslesenler.slice(0, GORUNUR_MAX);
  const secili = value !== TUMU && Boolean(value);

  const sec = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const acKapat = (o: boolean) => {
    if (o) setSearch("");
    setOpen(o);
  };

  return (
    <Popover open={open} onOpenChange={acKapat}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-label={rest["aria-label"]}
          className={cn(
            "flex w-full items-center justify-between h-9 px-3 text-[13px] text-left bg-transparent border border-[var(--border-strong)] rounded-[3px]",
            className,
          )}
        >
          <span className={cn("truncate", !secili && "text-[var(--fg-subtle)]")}>{secili ? value : "Tümü"}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[300px] p-0" align="start">
        <Command shouldFilter={false} loop>
          <CommandInput placeholder={`${noun} ara...`} aria-label={`${noun} ara`} value={search} onValueChange={setSearch} />
          <CommandList className="max-h-72">
            {eslesenler.length === 0 && (
              <div className="py-3 text-center text-[12px] text-[var(--fg-subtle)]">Sonuç yok</div>
            )}
            <CommandGroup>
              {!q && (
                <CommandItem value={TUMU} onSelect={() => sec(TUMU)} className="text-[13px]">
                  <Check className={cn("mr-2 h-4 w-4 shrink-0", !secili ? "opacity-100" : "opacity-0")} />
                  <span className="truncate flex-1">Tümü</span>
                </CommandItem>
              )}
              {gorunen.map(o => (
                <CommandItem key={o.name} value={o.name} onSelect={() => sec(o.name)} className="text-[13px]">
                  <Check className={cn("mr-2 h-4 w-4 shrink-0", value === o.name ? "opacity-100" : "opacity-0")} />
                  <span className="truncate flex-1">{o.name}</span>
                  {o.count !== undefined && (
                    <span className="ml-2 shrink-0 font-mono text-[10.5px] text-[var(--fg-subtle)]">{o.count}</span>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
            {eslesenler.length > GORUNUR_MAX && (
              <div className="px-3 py-2 text-[11px] text-[var(--fg-subtle)] border-t border-[var(--border)]">
                {eslesenler.length} sonuçtan ilk {GORUNUR_MAX} gösteriliyor — aramayı daraltın
              </div>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
