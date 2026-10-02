import { useState } from "react";
import { Check, ChevronsUpDown, X } from "lucide-react";

import {
  Command, CommandGroup, CommandInput, CommandItem, CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { foldTr } from "@/lib/aramaKatlama";

/** Seçenek: config `lawyers` satırının bileşenin okuduğu alt kümesi (`ConfigItem` uyumlu). */
export interface LawyerOption {
  name: string;
  /** `lawyers.gorev`: AVUKAT | DIŞ AVUKAT | DİĞER | boş (`models.py`). */
  gorev?: string | null;
  /** Seçimde yayılan değer; yoksa `name`. (Dava listesi filtresi avukat KODUNU gönderir.) */
  value?: string;
}

interface CommonProps {
  lawyers: LawyerOption[];
  /** Tekli modda listenin başına "tümü" satırı (ör. filtrede "Tüm Avukatlar"); seçilince `value` yayılır. */
  allOption?: { label: string; value: string };
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

/** Katlanmış alt-dize eşleşmesi (bulanık skor değil). */
function eslesir(name: string, search: string): boolean {
  const q = foldTr(search.trim());
  return !q || foldTr(name).includes(q);
}

/** Satır rozeti: AVUKAT → "İç", DIŞ AVUKAT → "Dış", DİĞER/boş → yok. */
function gorevRozeti(gorev?: string | null): "İç" | "Dış" | null {
  const g = foldTr((gorev ?? "").trim()).replace(/\s+/g, " ");
  if (g === "avukat") return "İç";
  if (g === "dis avukat") return "Dış";
  return null;
}

type Sekme = "ofis" | "dis";
/** DIŞ AVUKAT → "dis" sekmesi; AVUKAT, DİĞER ve boş → "ofis". */
const sekmesi = (l: LawyerOption): Sekme => (gorevRozeti(l.gorev) === "Dış" ? "dis" : "ofis");
const SEKME_ADI: Record<Sekme, string> = { ofis: "Ofis Avukatları", dis: "Dış Avukatlar" };

/**
 * Yazarak aranan avukat seçimi (G213): düz `Select` yerine `ui/popover` + `ui/command`
 * (cmdk) combobox'ı. Değer sözleşmesi avukat ADI string'idir (tekli: string, çoklu:
 * string[]) — payload şekli çağıranda değişmez. Arama Türkçe katlamalı ve büyük/küçük
 * harf duyarsız; her satırda `gorev` rozeti (İç/Dış). Çoklu modda seçilenler tetikleyicinin
 * üstünde çip olarak durur (× ile çıkar) ve listede işaretlidir; seçim listeyi açık tutar.
 * Klavye cmdk + Radix'ten: yazma, ↑↓, Enter seçer, Esc kapatır.
 * 27.09 (kullanıcı isteği): dış avukatlar ayrı sekmede ("Ofis Avukatları" | "Dış Avukatlar";
 * DİĞER/boş ofiste), sekme başlığında eşleşme sayısı; süzme bileşende (cmdk `shouldFilter=false`).
 * İsteğe bağlı `value` (yayılan değer ≠ ad, ör. filtrede avukat kodu) ve `allOption` ("Tüm Avukatlar").
 */
export function LawyerCombobox(props: LawyerComboboxProps) {
  const { lawyers, placeholder, disabled = false, id, className } = props;
  const allOption = props.mode === "single" ? props.allOption : undefined;
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [sekme, setSekme] = useState<Sekme>("ofis");
  const selected: string[] = props.mode === "multi" ? props.value : (props.value ? [props.value] : []);
  const degeri = (l: LawyerOption) => l.value ?? l.name;

  const pick = (value: string) => {
    if (props.mode === "multi") {
      props.onChange(
        props.value.includes(value) ? props.value.filter(n => n !== value) : [...props.value, value],
      );
    } else {
      props.onChange(value);
      setOpen(false);
    }
  };

  const remove = (value: string) => {
    if (props.mode === "multi") props.onChange(props.value.filter(n => n !== value));
  };

  // Listede olmayan (eski/AI) seçili değer de görünür ve seçili kalmalı ("tümü" değeri hariç).
  const options: LawyerOption[] = [
    ...selected
      .filter(v => v !== allOption?.value && !lawyers.some(l => degeri(l) === v))
      .map(v => ({ name: v })),
    ...lawyers,
  ];
  const adi = (value: string) =>
    value === allOption?.value ? allOption.label : (options.find(l => degeri(l) === value)?.name ?? value);

  // Dış avukatlar ayrı sekmede; sekmeler yalnız iki grup da varsa görünür. Arama aktif
  // sekmede süzer, sekme başlıkları her sekmedeki eşleşme sayısını gösterir.
  const sekmeli = options.some(l => sekmesi(l) === "dis") && options.some(l => sekmesi(l) === "ofis");
  const eslesenler = options.filter(l => eslesir(l.name, search));
  const sayi = (s: Sekme) => eslesenler.filter(l => sekmesi(l) === s).length;
  const gorunen = sekmeli ? eslesenler.filter(l => sekmesi(l) === sekme) : eslesenler;
  const tumuGorunur = Boolean(allOption) && eslesir(allOption!.label, search);

  const acKapat = (o: boolean) => {
    if (disabled) return;
    if (o) {
      // Açılışta seçili avukatın sekmesi (yoksa ofis) gelir; arama temizlenir.
      const secili = props.mode === "single" ? options.find(l => degeri(l) === props.value) : undefined;
      setSekme(secili ? sekmesi(secili) : "ofis");
      setSearch("");
    }
    setOpen(o);
  };

  const triggerText = props.mode === "single" && props.value
    ? adi(props.value)
    : placeholder ?? (props.mode === "multi" ? "Avukat Ekle..." : "Seçiniz...");
  const showingValue = props.mode === "single" && Boolean(props.value) && props.value !== allOption?.value;

  return (
    <div className="min-w-0" data-testid="lawyer-combobox">
      {props.mode === "multi" && props.value.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {props.value.map(value => (
            <span
              key={value}
              data-testid="lawyer-chip"
              className="inline-flex items-center gap-1 bg-[var(--brand-soft)] text-[var(--brand)] px-2 py-1 text-[11px] font-medium border border-brand/20"
            >
              {adi(value)}
              <button
                type="button"
                disabled={disabled}
                onClick={e => { e.preventDefault(); remove(value); }}
                className="hover:opacity-70 transition-opacity"
                aria-label={`${adi(value)} avukatını çıkar`}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <Popover open={open} onOpenChange={acKapat}>
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
          <Command shouldFilter={false} loop>
            <CommandInput placeholder="Avukat ara..." aria-label="Avukat ara" value={search} onValueChange={setSearch} />
            {sekmeli && (
              <div role="tablist" aria-label="Avukat grubu" className="flex border-b border-[var(--border)]">
                {(["ofis", "dis"] as const).map(s => (
                  <button
                    key={s}
                    type="button"
                    role="tab"
                    aria-selected={sekme === s}
                    data-testid={`lawyer-sekme-${s}`}
                    onClick={() => setSekme(s)}
                    className={cn(
                      "flex-1 px-3 py-2 text-[12px] border-b-2 -mb-px transition-colors",
                      sekme === s
                        ? "border-[var(--brand)] text-[var(--fg)] font-medium"
                        : "border-transparent text-[var(--fg-muted)] hover:text-[var(--fg)]",
                    )}
                  >
                    {SEKME_ADI[s]} <span className="font-mono text-[10.5px] opacity-70">({sayi(s)})</span>
                  </button>
                ))}
              </div>
            )}
            <CommandList className="max-h-64">
              {!tumuGorunur && gorunen.length === 0 && (
                <div className="py-3 text-center text-[12px] text-[var(--fg-subtle)]">
                  {sekmeli && eslesenler.length > 0
                    ? `Bu sekmede yok — ${SEKME_ADI[sekme === "ofis" ? "dis" : "ofis"]} sekmesinde ${eslesenler.length} sonuç`
                    : "Avukat bulunamadı"}
                </div>
              )}
              <CommandGroup>
                {tumuGorunur && allOption && (
                  <CommandItem
                    key={`__tumu__${allOption.value}`}
                    value={allOption.value}
                    onSelect={() => pick(allOption.value)}
                    data-lawyer={allOption.label}
                    data-checked={props.value === allOption.value ? "true" : "false"}
                    className="text-[13px]"
                  >
                    <Check className={cn("mr-2 h-4 w-4 shrink-0", props.value === allOption.value ? "opacity-100" : "opacity-0")} />
                    <span className="truncate flex-1">{allOption.label}</span>
                  </CommandItem>
                )}
                {gorunen.map(l => {
                  const isSelected = selected.includes(degeri(l));
                  const rozet = gorevRozeti(l.gorev);
                  return (
                    <CommandItem
                      key={degeri(l)}
                      value={degeri(l)}
                      onSelect={() => pick(degeri(l))}
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
