import { useState } from "react";
import { Check, ChevronDown, ChevronsUpDown, Scale, ShieldCheck } from "lucide-react";

import { AiPill } from "@/components/flow/primitives";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command, CommandEmpty, CommandGroup, CommandInput, CommandItem,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Popover, PopoverAnchor, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import type { ClientPrior, MergeField } from "@/lib/caseIntake";
import type { IntakeFieldDef, IntakeFieldState } from "@/lib/caseIntakeFields";

interface IntakeFieldRowProps {
  def: IntakeFieldDef;
  state: IntakeFieldState;
  /** Merge taslağı meta verisi (kaynak rozeti, adaylar, güven) — draftKey'siz alanlarda yok. */
  field?: MergeField;
  /** select widget seçenekleri (yargı türü, avukatlar…) */
  options?: string[];
  /** Müvekkilin geçmiş davalarından öneri (düşük güvenli — tıklanınca uygulanır) */
  prior?: ClientPrior;
  /** Değer değişimi — düzenlemek alanı OTOMATİK tikler (onay semantiği). */
  onChange: (value: string) => void;
  onApprove: (approved: boolean) => void;
}

/**
 * Review satırı: onay Checkbox'ı + değer editörü (AI ön-dolu) + kaynak rozeti
 * ("3/4 belge · dilekce.pdf") + adaylar popover'ı (anlaşmazlıkta tıkla-seç).
 * Onay semantiği: boş olmayan her AI değeri kaydetten önce tiklenmeli;
 * düzenleme otomatik tikler. Zorunlu alan boşken de tik ister — boş tik
 * "bu bilgi şu anda elimde yok" onay diyaloğundan geçer; zorunlu olmayan
 * boş alanın tiki pasiftir.
 */
export function IntakeFieldRow({ def, state, field, options, prior, onChange, onApprove }: IntakeFieldRowProps) {
  const [comboboxOpen, setComboboxOpen] = useState(false);
  const [emptyConfirmOpen, setEmptyConfirmOpen] = useState(false);
  const isEmpty = state.value === "";
  const needsApproval = !isEmpty || Boolean(def.required);
  const candidates = field?.candidates ?? [];
  const showCandidates = candidates.length > 1;
  const confidence = field?.confidence != null ? Math.round(field.confidence * 100) : undefined;
  const sourceLabel = field && field.sources.length > 0
    ? `${field.sources.length} belge · ${field.sources[0]}${field.sources.length > 1 ? " +" : ""}`
    : null;

  const inputId = `intake-field-${def.key}`;

  const editor = (() => {
    switch (def.widget) {
      case "textarea":
        return (
          <Textarea
            id={inputId}
            value={state.value}
            onChange={e => onChange(e.target.value)}
            rows={2}
            className="text-[13px] border-[var(--border-strong)] bg-transparent"
          />
        );
      case "select":
        return (
          <Select value={state.value || undefined} onValueChange={onChange}>
            <SelectTrigger id={inputId} className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent">
              <SelectValue placeholder="Seçiniz..." />
            </SelectTrigger>
            <SelectContent>
              {/* AI değeri seçenek listesinde yoksa da seçilebilir kalmalı */}
              {state.value && !(options || []).includes(state.value) && (
                <SelectItem value={state.value}>{state.value}</SelectItem>
              )}
              {(options || []).map(o => (
                <SelectItem key={o} value={o}>{o}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      case "combobox":
        // Kanonik liste alanları (dava konusu, uzmanlık): aranabilir seçim —
        // NewCase'teki desenle aynı; değer YA listeden YA boş, serbest metin yok.
        return (
          <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
            <PopoverTrigger asChild>
              <Button
                id={inputId}
                variant="outline"
                role="combobox"
                aria-expanded={comboboxOpen}
                className="w-full h-9 justify-between font-normal text-[13px] bg-transparent border-[var(--border-strong)]"
              >
                <span className="truncate">{state.value || "Seçiniz..."}</span>
                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[300px] p-0" align="start">
              <Command>
                <CommandInput placeholder={`${def.label} ara...`} />
                <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                <CommandGroup className="max-h-64 overflow-auto">
                  {(options || []).map(o => (
                    <CommandItem
                      key={o}
                      value={o}
                      onSelect={() => {
                        onChange(o === state.value ? "" : o);
                        setComboboxOpen(false);
                      }}
                    >
                      <Check className={`mr-2 h-4 w-4 ${state.value === o ? "opacity-100" : "opacity-0"}`} />
                      {o}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </Command>
            </PopoverContent>
          </Popover>
        );
      case "date":
        return (
          <Input
            id={inputId}
            type="date"
            value={state.value}
            onChange={e => onChange(e.target.value)}
            className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent"
          />
        );
      case "money":
        return (
          <Input
            id={inputId}
            type="number"
            min={0}
            step="0.01"
            value={state.value}
            onChange={e => onChange(e.target.value)}
            className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent"
          />
        );
      default: // text | court
        return (
          <Input
            id={inputId}
            value={state.value}
            onChange={e => onChange(e.target.value)}
            className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent"
          />
        );
    }
  })();

  return (
    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 py-2.5">
      <div className="pt-6">
        <Popover open={emptyConfirmOpen} onOpenChange={setEmptyConfirmOpen}>
          {/* Anchor yalnız konum verir (Trigger DEĞİL — trigger her tıkta
              toggle yapar, dolu alanda da panel açardı); açma kararı yalnız
              onCheckedChange'teki boş+zorunlu koşulunda */}
          <PopoverAnchor asChild>
            <span>
              <Checkbox
                checked={state.approved}
                disabled={!needsApproval}
                onCheckedChange={v => {
                  // Boş zorunlu alanı tiklemek onay ister; tik kaldırmak serbest
                  if (v === true && isEmpty && def.required) {
                    setEmptyConfirmOpen(true);
                    return;
                  }
                  onApprove(v === true);
                }}
                aria-label={`${def.label} alanını onayla`}
              />
            </span>
          </PopoverAnchor>
          <PopoverContent align="start" side="right" className="w-80 p-4">
            <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              Zorunlu Alan Boş
            </p>
            <p className="text-[13px] text-[var(--fg)] mt-1.5 leading-relaxed">
              <strong>{def.label}</strong> alanı boş onaylanacak. "Bu bilgi şu anda
              elimde yok — bilgiye sahip olduğumda dava kartına kaydedeceğim."
            </p>
            <div className="flex gap-2 justify-end mt-3">
              <button
                type="button"
                onClick={() => setEmptyConfirmOpen(false)}
                className="px-3 py-1.5 text-[12px] text-[var(--fg-muted)] hover:text-[var(--fg)] border border-[var(--border-strong)] transition-colors"
              >
                Vazgeç
              </button>
              <button
                type="button"
                onClick={() => {
                  onApprove(true);
                  setEmptyConfirmOpen(false);
                }}
                className="px-3 py-1.5 text-[12px] font-medium bg-[var(--brand)] text-[var(--brand-fg)] hover:opacity-90 transition-opacity"
              >
                Onaylıyorum
              </button>
            </div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <label
            htmlFor={inputId}
            className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]"
          >
            {def.label}
            {def.required && <span className="text-[var(--brand)] ml-1">*</span>}
          </label>
          <div className="flex items-center gap-1.5">
            {field?.verified === true && (
              <span title="Değer belgede kanıtla doğrulandı" className="inline-flex items-center gap-1 font-mono text-[9.5px] tracking-[0.1em] uppercase text-emerald-600">
                <ShieldCheck className="w-3 h-3" /> Kanıtlı
              </span>
            )}
            {field?.arbiter && (
              <span
                title={`Hakem kararı: ${field.arbiter.gerekce || field.arbiter.secilen_deger}`}
                className="inline-flex items-center gap-1 font-mono text-[9.5px] tracking-[0.1em] uppercase text-[var(--fg-muted)]"
              >
                <Scale className="w-3 h-3" /> Hakem
              </span>
            )}
            {state.aiValue !== "" && <AiPill confidence={confidence} />}
          </div>
        </div>

        {editor}

        <div className="flex items-center gap-3 mt-1 min-h-[18px]">
          {sourceLabel && (
            <span className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)]">
              {sourceLabel}
            </span>
          )}
          {prior && prior.value !== state.value && (
            <button
              type="button"
              onClick={() => onChange(prior.value)}
              className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:underline"
              title={`Bu müvekkilin son ${prior.total} davasının ${prior.count}'inde kullanılmış — tıklayınca uygulanır`}
            >
              Geçmiş: {prior.value} ({prior.count}/{prior.total})
            </button>
          )}
          {field?.known_court_suggestion && field.known_court_suggestion !== state.value && (
            <button
              type="button"
              onClick={() => onChange(field.known_court_suggestion!)}
              className="font-mono text-[10px] tracking-[0.04em] text-[var(--brand)] hover:underline"
              title="Mevcut davalardaki bilinen yazımı kullan"
            >
              Bilinen yazım: {field.known_court_suggestion}
            </button>
          )}
          {showCandidates && (
            <Popover>
              <PopoverTrigger asChild>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 font-mono text-[10px] tracking-[0.04em] text-[var(--brand)] hover:underline"
                >
                  {candidates.length} aday <ChevronDown className="w-3 h-3" />
                </button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-80 p-2">
                <p className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)] px-2 pb-2">
                  Belgeler anlaşamadı — doğru değeri seçin
                </p>
                <ul className="grid gap-1">
                  {candidates.map((c, i) => (
                    <li key={i}>
                      <button
                        type="button"
                        onClick={() => onChange(String(c.value ?? ""))}
                        className={[
                          "w-full text-left px-2 py-1.5 text-[13px] hover:bg-[var(--brand-soft)] transition-colors",
                          String(c.value ?? "") === state.value ? "bg-[var(--bg-sunken)] text-[var(--fg)]" : "text-[var(--fg-muted)]",
                        ].join(" ")}
                      >
                        <span className="break-all">{String(c.value ?? "")}</span>
                        <span className="block font-mono text-[10px] text-[var(--fg-subtle)] mt-0.5">
                          {c.count} belge · {c.sources.slice(0, 2).join(", ")}{c.sources.length > 2 ? "…" : ""}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </PopoverContent>
            </Popover>
          )}
        </div>
      </div>
    </div>
  );
}
