import { useState } from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";

import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** Seçenek: config `lawyers` satırının bileşenin okuduğu alt kümesi (`ConfigItem` uyumlu). */
export interface LawyerOption {
  name: string;
  /** `lawyers.gorev`: AVUKAT | DIŞ AVUKAT | DİĞER | boş (`models.py`). */
  gorev?: string | null;
}

interface CommonProps {
  lawyers: LawyerOption[];
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
  /** Tetikleyici düğmenin ek sınıfları (çağıranın yükseklik/kenar düzeni). */
  className?: string;
}

interface SingleProps extends CommonProps {
  mode: "single";
  value: string;
  onChange: (value: string) => void;
}

interface MultiProps extends CommonProps {
  mode: "multi";
  value: string[];
  onChange: (value: string[]) => void;
}

export type LawyerComboboxProps = SingleProps | MultiProps;

/**
 * Türkçe katlama: tr-TR küçük harf + ç/ğ/ı/ş/ö/ü → c/g/i/s/o/u + birleşik
 * işaretlerin atılması ("İ".toLowerCase() kalıntısı dahil). "ŞAHİN" ≡ "sahin".
 * (Repodaki `predictDocType.foldTr` modül-içi ve alfanümerik dışını da sildiği
 * için arama alt-dizesine uygun değil — burada boşluk/nokta korunur.)
 */
function foldTr(s: string): string {
  return s
    .toLocaleLowerCase("tr-TR")
    .replace(/ç/g, "c")
    .replace(/ğ/g, "g")
    .replace(/ı/g, "i")
    .replace(/ş/g, "s")
    .replace(/ö/g, "o")
    .replace(/ü/g, "u")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** cmdk süzgeci: katlanmış alt-dize (bulanık skor değil). */
function lawyerFilter(value: string, search: string): number {
  const q = foldTr(search.trim());
  if (!q) return 1;
  return foldTr(value).includes(q) ? 1 : 0;
}

/** Satır rozeti: AVUKAT → "İç", DIŞ AVUKAT → "Dış", DİĞER/boş → yok. */
function gorevRozeti(gorev?: string | null): "İç" | "Dış" | null {
  const g = foldTr((gorev ?? "").trim()).replace(/\s+/g, " ");
  if (g === "avukat") return "İç";
  if (g === "dis avukat") return "Dış";
  return null;
}

/**
 * Yazarak aranan avukat seçimi (G213): düz `Select` yerine `ui/popover` + `ui/command`
 * (cmdk) combobox'ı. Değer sözleşmesi avukat ADI string'idir (tekli: string, çoklu:
 * string[]) — payload şekli çağıranda değişmez. Arama Türkçe katlamalı ve büyük/küçük
 * harf duyarsız; her satırda `gorev` rozeti (İç/Dış). Çoklu modda seçilenler tetikleyicinin
 * üstünde çip olarak durur (× ile çıkar) ve listede işaretlidir; seçim listeyi açık tutar.
 * Klavye cmdk + Radix'ten: yazma, ↑↓, Enter seçer, Esc kapatır.
 */
export function LawyerCombobox(props: LawyerComboboxProps) {
  const { lawyers, placeholder, disabled = false, id, className } = props;
  const [open, setOpen] = useState(false);
  const selected: string[] = props.mode === "multi" ? props.value : (props.value ? [props.value] : []);

  const pick = (name: string) => {
    if (props.mode === "multi") {
      props.onChange(
        props.value.includes(name) ? props.value.filter(n => n !== name) : [...props.value, name],
      );
    } else {
      props.onChange(name);
      setOpen(false);
    }
  };

  const remove = (name: string) => {
    if (props.mode === "multi") props.onChange(props.value.filter(n => n !== name));
  };

  // Tekli modda listede olmayan (eski/AI) değer de görünür ve seçili kalmalı.
  const options: LawyerOption[] = [
    ...selected.filter(n => !lawyers.some(l => l.name === n)).map(n => ({ name: n })),
    ...lawyers,
  ];

  const triggerText = props.mode === "single" && props.value
    ? props.value
    : placeholder ?? (props.mode === "multi" ? "Avukat Ekle..." : "Seçiniz...");
  const showingValue = props.mode === "single" && Boolean(props.value);

  return (
    <div className="min-w-0" data-testid="lawyer-combobox">
      {props.mode === "multi" && props.value.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {props.value.map(name => (
            <span
              key={name}
              data-testid="lawyer-chip"
              className="inline-flex items-center gap-1 bg-[var(--brand-soft)] text-[var(--brand)] px-2 py-1 text-[11px] font-medium border border-brand/20"
            >
              {name}
              <button
                type="button"
                disabled={disabled}
                onClick={e => { e.preventDefault(); remove(name); }}
                className="hover:opacity-70 transition-opacity"
                aria-label={`${name} avukatını çıkar`}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <Popover open={open} onOpenChange={o => { if (!disabled) setOpen(o); }}>
        <PopoverTrigger asChild>
          <button
            type="button"
            id={id}
            role="combobox"
            aria-expanded={open}
            aria-label={props["aria-label"]}
            disabled={disabled}
            className={cn(
              "flex w-full items-center justify-between h-9 px-3 text-[13px] text-left bg-transparent border border-[var(--border-strong)] rounded-[3px] disabled:cursor-not-allowed disabled:opacity-50",
              className,
            )}
          >
            <span className={cn("truncate", !showingValue && "text-[var(--fg-subtle)]")}>{triggerText}</span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[280px] p-0" align="start">
          <Command filter={lawyerFilter} loop>
            <CommandInput placeholder="Avukat ara..." aria-label="Avukat ara" />
            <CommandList className="max-h-64">
              <CommandEmpty className="py-3 text-center text-[12px] text-[var(--fg-subtle)]">
                Avukat bulunamadı
              </CommandEmpty>
              <CommandGroup>
                {options.map(l => {
                  const isSelected = selected.includes(l.name);
                  const rozet = gorevRozeti(l.gorev);
                  return (
                    <CommandItem
                      key={l.name}
                      value={l.name}
                      onSelect={() => pick(l.name)}
                      data-lawyer={l.name}
                      data-checked={isSelected ? "true" : "false"}
                      className="text-[13px]"
                    >
                      <Check className={cn("mr-2 h-4 w-4 shrink-0", isSelected ? "opacity-100" : "opacity-0")} />
                      <span className="truncate flex-1">{l.name}</span>
                      {rozet && (
                        <span
                          data-testid="lawyer-gorev-rozeti"
                          className={cn(
                            "ml-2 shrink-0 font-mono text-[9.5px] tracking-[0.1em] uppercase px-1.5 py-0.5 border",
                            rozet === "İç"
                              ? "border-[var(--brand)]/30 text-[var(--brand)]"
                              : "border-[var(--border-strong)] text-[var(--fg-muted)]",
                          )}
                        >
                          {rozet}
                        </span>
                      )}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
