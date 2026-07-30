import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ExternalLink, FileText, Mail, Plus, RefreshCw, Save, Trash2, X,
} from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { FlowButton, FlowCard } from "@/components/flow/primitives";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { IntakeFieldRow } from "@/components/intake/IntakeFieldRow";
import { PartyMatchIndicator } from "@/components/PartyMatchIndicator";
import { useCases } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import {
  CommitConflictError,
  policyKey,
  selectCommitPolicies,
  type CaseIntakeCommitRequest,
  type CommitCasePartyIn,
  type MergeDraft,
  type MergePolicy,
} from "@/lib/caseIntake";
import {
  activeIntakeFields,
  buildFieldStates,
  fieldApprovalProgress,
  type IntakeFieldState,
} from "@/lib/caseIntakeFields";
import {
  bestCategoryCode,
  generateNameBlock,
  generateTrackingNumber,
  pickNameClient,
  PROCESS_MAP,
} from "@/lib/caseNumberUtils";
import { predictDocTypeFromName } from "@/lib/predictDocType";

// =====================================================================
// Adım 3 — İnceleme ("Dava Kartı Onayı"): UX'in kalbi.
// Onay semantiği: boş olmayan her AI değeri kaydetten önce tiklenmeli;
// Kaydet, tüm alanlar + en az 1 müvekkil (CLIENT) onaylanana dek pasif.
// =====================================================================

const ROL_DISPLAY: Record<string, string> = {
  DAVACI: "Davacı",
  DAVALI: "Davalı",
  MUDAHIL: "Müdahil",
  IHBAR_OLUNAN: "İhbar Olunan",
  SIGORTALI: "Davalı",        // büro hekim savunması yapar — poliçedeki sigortalı davalı adayı
  SIGORTA_SIRKETI: "İhbar Olunan",
  DIGER: "Diğer",
};

interface ReviewParty {
  id: string;
  name: string;
  role: string;
  party_type: "CLIENT" | "COUNTER" | "THIRD";
  tc_no: string;
  client_id: number | null;
  matchName: string | null;      // kayıtlı carideki kanonik ad
  matchCategory: string | null;  // ofis no isim bloğu kişi/kurum kararı için
  approved: boolean;
  fromDraft: boolean;
}

interface ReviewDocument {
  process_id: string;
  filename: string;
  newName: string;
  code: string;       // belge türü kodu
  ozet: string;
  expired: boolean;
}

interface IntakeReviewStepProps {
  draft: MergeDraft;
  isCommitting: boolean;
  onCommit: (req: CaseIntakeCommitRequest) => Promise<unknown>;
}

let nextPartyId = 0;
const makePartyId = () => `party-${++nextPartyId}`;

const PARTY_TYPE_LABEL: Record<ReviewParty["party_type"], string> = {
  CLIENT: "Müvekkil",
  COUNTER: "Karşı Taraf",
  THIRD: "3. Kişi",
};

export function IntakeReviewStep({ draft, isCommitting, onCommit }: IntakeReviewStepProps) {
  const { getClientCaseSequence } = useCases();
  const { lawyers, doctypes, emailRecipients, courtTypesByParent } = useConfig();

  // --- Alanlar ---------------------------------------------------------
  const [fieldStates, setFieldStates] = useState<Record<string, IntakeFieldState>>(
    () => buildFieldStates(draft),
  );

  const setFieldValue = (key: string, value: string) => {
    // Düzenlemek otomatik tikler; kullanıcının boşalttığı alan boş kaydedilir
    setFieldStates(prev => ({
      ...prev,
      [key]: { ...prev[key], value, touched: true, approved: value !== "" ? true : prev[key].approved },
    }));
  };

  const setFieldApproved = (key: string, approved: boolean) => {
    setFieldStates(prev => ({ ...prev, [key]: { ...prev[key], approved } }));
  };

  // --- Taraflar --------------------------------------------------------
  const [parties, setParties] = useState<ReviewParty[]>(() =>
    draft.parties.map(p => ({
      id: makePartyId(),
      name: p.match?.name || p.name, // kayıtlı carinin kanonik yazımı tercih edilir
      role: ROL_DISPLAY[p.rol] || p.rol,
      party_type: p.party_type,
      tc_no: p.tc_no || "",
      client_id: p.match?.client_id ?? null,
      matchName: p.match?.name ?? null,
      matchCategory: p.match?.category ?? null,
      approved: false,
      fromDraft: true,
    })),
  );

  const patchParty = (id: string, patch: Partial<ReviewParty>) => {
    setParties(prev => prev.map(p => (p.id === id ? { ...p, ...patch } : p)));
  };

  const addParty = (party_type: ReviewParty["party_type"]) => {
    setParties(prev => [...prev, {
      id: makePartyId(),
      name: "",
      role: party_type === "CLIENT" ? "Davacı" : party_type === "COUNTER" ? "Davalı" : "Diğer",
      party_type,
      tc_no: "",
      client_id: null,
      matchName: null,
      matchCategory: null,
      approved: true, // elle eklenen satır kullanıcının kendi girdisi — tik istemez
      fromDraft: false,
    }]);
  };

  const approvedClients = useMemo(
    () => parties.filter(p => p.party_type === "CLIENT" && p.approved && p.name.trim()),
    [parties],
  );
  const partiesApproved = parties.every(p => p.approved || !p.name.trim());

  // --- Ofis No ---------------------------------------------------------
  const [trackingNo, setTrackingNo] = useState("");
  const [isGeneratingNo, setIsGeneratingNo] = useState(false);

  const regenerateTracking = useCallback(async () => {
    if (approvedClients.length === 0) {
      setTrackingNo("");
      return;
    }
    setIsGeneratingNo(true);
    try {
      const source = approvedClients.map(p => ({
        name: p.name,
        category: p.matchCategory || "",
      }));
      const named = pickNameClient(source);
      const catCode = bestCategoryCode(source);
      const seq = named.name
        ? await getClientCaseSequence(named.name, generateNameBlock(named.name, named.category))
        : 1;
      setTrackingNo(generateTrackingNumber({
        category: catCode,
        clientName: named.name,
        clientCategory: named.category,
        sequence: seq,
        processType: fieldStates.file_type?.value || "Hukuk",
        serviceType: "00000",
      }));
    } finally {
      setIsGeneratingNo(false);
    }
  }, [approvedClients, fieldStates.file_type?.value, getClientCaseSequence]);

  // İlk müvekkil onaylanınca (ve müvekkil seti / yargı türü değiştikçe) üretilir
  const approvedClientsKey = approvedClients.map(p => p.name).join("|");
  const fileTypeValue = fieldStates.file_type?.value;
  useEffect(() => {
    regenerateTracking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvedClientsKey, fileTypeValue]);

  // --- Poliçeler -------------------------------------------------------
  // Varsayılan seçim: kayıtlı olmayan + müvekkil eşleşmeli poliçeler
  const [selectedPolicies, setSelectedPolicies] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const p of draft.policies) {
      initial[policyKey(p)] = !p.saved && p.client_id != null;
    }
    return initial;
  });

  // --- Belge şeridi ----------------------------------------------------
  const [documents, setDocuments] = useState<ReviewDocument[]>([]);
  useEffect(() => {
    // doctypes yüklenince tahminsiz belgelere ad-bazlı fallback uygulanır
    setDocuments(prev => {
      if (prev.length > 0) return prev.map(d => ({
        ...d,
        code: d.code || predictDocTypeFromName(d.filename, doctypes),
      }));
      return draft.documents.map(d => ({
        process_id: d.process_id,
        filename: d.filename,
        newName: d.filename,
        code: d.belge_turu_kodu || predictDocTypeFromName(d.filename, doctypes),
        ozet: d.ozet || "",
        expired: d.status === "expired",
      }));
    });
  }, [draft.documents, doctypes]);

  const patchDocument = (process_id: string, patch: Partial<ReviewDocument>) => {
    setDocuments(prev => prev.map(d => (d.process_id === process_id ? { ...d, ...patch } : d)));
  };

  // --- E-posta bildirimi (karar 2: varsayılan KAPALI) ------------------
  const [sendEmail, setSendEmail] = useState(false);
  const [emailTo, setEmailTo] = useState<string[]>([]);
  const [customEmail, setCustomEmail] = useState("");

  const addEmailRecipient = (addr: string) => {
    const v = addr.trim().toLowerCase();
    if (!/^\S+@\S+\.\S+$/.test(v)) {
      toast.error("Geçerli bir e-posta adresi girin.");
      return;
    }
    setEmailTo(prev => (prev.includes(v) ? prev : [...prev, v]));
    setCustomEmail("");
  };

  // --- Kaydet kapısı ---------------------------------------------------
  const progress = fieldApprovalProgress(fieldStates);
  const canSave =
    progress.complete &&
    partiesApproved &&
    approvedClients.length > 0 &&
    trackingNo !== "" &&
    (!sendEmail || emailTo.length > 0) &&
    !isCommitting &&
    !isGeneratingNo;

  const gateHint = !progress.complete
    ? `${progress.approved}/${progress.required} alan onaylandı`
    : approvedClients.length === 0
      ? "En az 1 müvekkil onaylanmalı"
      : !partiesApproved
        ? "Tüm taraf satırları onaylanmalı (ya da boş bırakılmalı)"
        : trackingNo === ""
          ? "Ofis numarası üretilemedi"
          : sendEmail && emailTo.length === 0
            ? "E-posta için en az bir alıcı ekleyin (ya da bildirimi kapatın)"
            : null;

  // --- Commit ----------------------------------------------------------
  const buildRequest = (tracking: string): CaseIntakeCommitRequest => {
    const v = (key: string) => fieldStates[key]?.value?.trim() || "";
    const num = (key: string) => {
      const raw = v(key);
      return raw ? Number(raw) : 0;
    };
    const lawyerName = v("responsible_lawyer_name");
    const lawyerObj = lawyers.find(l => l.name === lawyerName);

    const commitParties: CommitCasePartyIn[] = parties
      .filter(p => p.approved && p.name.trim())
      .map(p => ({
        client_id: p.client_id ?? undefined,
        name: p.name.trim(),
        role: p.role || (p.party_type === "CLIENT" ? "Davacı" : "Davalı"),
        party_type: p.party_type,
        tc_no: p.tc_no || undefined,
      }));

    const muvekkilAdi = approvedClients[0]?.name || null;

    return {
      case: {
        tracking_no: tracking,
        esas_no: v("esas_no") || null,
        status: "DERDEST", // sunucu zaten zorlar (karar 1)
        service_type: "00000",
        file_type: v("file_type") || null,
        sub_type: v("sub_type") || null,
        sub_type_extra: v("sub_type_extra") || null,
        subject: v("subject") || null,
        court: v("court") || null,
        opening_date: v("opening_date") || null,
        responsible_lawyer_name: lawyerName || null,
        uyap_lawyer_name: v("uyap_lawyer_name") || null,
        maddi_tazminat: num("maddi_tazminat"),
        manevi_tazminat: num("manevi_tazminat"),
        notes: v("notes") || null,
        parties: commitParties,
        lawyers: lawyerName ? [{ name: lawyerName, lawyer_id: lawyerObj?.id ?? null }] : [],
      },
      documents: documents
        .filter(d => !d.expired)
        .map(d => ({
          process_id: d.process_id,
          new_filename: d.newName.trim() || d.filename,
          original_filename: d.filename,
          belge_turu_kodu: d.code || null,
          ai_ozet: d.ozet || null,
          esas_no: v("esas_no") || null,
          muvekkil_adi: muvekkilAdi,
        })),
      policies: selectCommitPolicies(
        draft.policies.filter(p => selectedPolicies[policyKey(p)]),
      ),
      options: { send_email: sendEmail, email_to: sendEmail ? emailTo : [] },
    };
  };

  const handleSave = async () => {
    try {
      await onCommit(buildRequest(trackingNo));
    } catch (e) {
      if (e instanceof CommitConflictError) {
        // 409: hiçbir belge tüketilmedi (Faz 4 garantisi) — sequence yenile,
        // ofis numarasını yeniden üret, BİR kez otomatik tekrar dene (karar 3).
        try {
          await regenerateTracking();
          const source = approvedClients.map(p => ({ name: p.name, category: p.matchCategory || "" }));
          const named = pickNameClient(source);
          const seq = named.name
            ? await getClientCaseSequence(named.name, generateNameBlock(named.name, named.category))
            : 1;
          const fresh = generateTrackingNumber({
            category: bestCategoryCode(source),
            clientName: named.name,
            clientCategory: named.category,
            sequence: seq,
            processType: fieldStates.file_type?.value || "Hukuk",
            serviceType: "00000",
          });
          setTrackingNo(fresh);
          await onCommit(buildRequest(fresh));
        } catch (retryErr) {
          toast.error("Kayıt başarısız", {
            description: retryErr instanceof Error ? retryErr.message : "Ofis numarası çakışması çözülemedi.",
          });
        }
      } else {
        toast.error("Kayıt başarısız", {
          description: e instanceof Error ? e.message : "Sunucu hatası oluştu.",
        });
      }
    }
  };

  // --- Render ----------------------------------------------------------
  const fieldDefs = activeIntakeFields();
  const lawyerNames = lawyers.map(l => l.name);

  // Priors: ilk cari-eşleşmeli müvekkilin geçmiş dava alışkanlıkları — düşük
  // güvenli ön-dolgu ÖNERİSİ olarak rozet gösterilir, otomatik uygulanmaz.
  const priorClientId = parties.find(p => p.party_type === "CLIENT" && p.client_id != null)?.client_id;
  const clientPriors = priorClientId != null ? draft.priors?.[String(priorClientId)] : undefined;

  // Alt tür seçenekleri yargı türüne bağlıdır (NewCase'teki ALT_TURLER ile aynı kaynak)
  const subTypeOptions = (courtTypesByParent?.[fieldStates.file_type?.value || ""] || [])
    .map(i => i.name ?? "")
    .filter(Boolean);
  const expiredCount = documents.filter(d => d.expired).length;
  const relevantPolicies = draft.policies;

  return (
    <div className="grid gap-5">
      {/* Uyarı bantları */}
      {draft.duplicate_case && (
        <div className="border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-[13px] text-[var(--fg)] min-w-0">
            Bu dava zaten kayıtlı olabilir:{" "}
            <Link
              to={`/cases/${draft.duplicate_case.id}`}
              target="_blank"
              className="font-mono text-[12px] text-[var(--brand)] hover:underline inline-flex items-center gap-1"
            >
              {draft.duplicate_case.tracking_no} <ExternalLink className="w-3 h-3" />
            </Link>{" "}
            — inceleyin ya da yine de devam edin.
          </span>
        </div>
      )}
      {draft.warnings.map((w, i) => (
        <div key={i} className="border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-[13px] text-[var(--fg)]">{w.message}</span>
        </div>
      ))}

      <div className="grid lg:grid-cols-2 gap-5 items-start">
        {/* Sol: dava kartı alanları */}
        <FlowCard padded={false}>
          <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
              Dava Kartı Alanları
            </span>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              <span className="text-[var(--fg)] font-semibold">{progress.approved}</span>/{progress.required} alan onaylandı
            </span>
          </div>
          <div className="px-5">
            {fieldDefs.map(def => (
              <IntakeFieldRow
                key={def.key}
                def={def}
                state={fieldStates[def.key]}
                field={def.draftKey ? draft.fields[def.draftKey] : undefined}
                options={
                  def.key === "file_type" ? Object.keys(PROCESS_MAP)
                    : def.key === "sub_type" ? subTypeOptions
                      : def.key === "responsible_lawyer_name" || def.key === "uyap_lawyer_name" ? lawyerNames
                        : undefined
                }
                prior={def.priorsKey ? clientPriors?.[def.priorsKey] : undefined}
                onChange={value => setFieldValue(def.key, value)}
                onApprove={approved => setFieldApproved(def.key, approved)}
              />
            ))}
          </div>

          {/* Ofis No */}
          <div className="px-5 py-4 border-t border-[var(--border)]">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                Ofis No (Takip Numarası)
              </span>
              <button
                type="button"
                onClick={regenerateTracking}
                disabled={isGeneratingNo || approvedClients.length === 0}
                title="Sıra numarasını yeniden sorgula"
                className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors disabled:opacity-30"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isGeneratingNo ? "animate-spin" : ""}`} />
              </button>
            </div>
            <Input
              value={trackingNo}
              readOnly
              placeholder="İlk müvekkil onaylanınca üretilir"
              className="h-9 font-mono text-[13px] border-[var(--border-strong)] bg-[var(--bg-sunken)]"
            />
          </div>
        </FlowCard>

        {/* Sağ kolon: taraflar + poliçeler + belgeler */}
        <div className="grid gap-5">
          {/* Taraflar */}
          <FlowCard padded={false}>
            <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                Taraflar
              </span>
              <div className="flex gap-1.5">
                {(["CLIENT", "COUNTER", "THIRD"] as const).map(t => (
                  <FlowButton key={t} variant="ghost" size="sm" onClick={() => addParty(t)}>
                    <Plus className="w-3 h-3" /> {PARTY_TYPE_LABEL[t]}
                  </FlowButton>
                ))}
              </div>
            </div>
            <ul className="divide-y divide-[var(--border)]">
              {parties.map(p => (
                <li key={p.id} className="px-5 py-3 grid grid-cols-[auto_1fr] gap-x-3">
                  <div className="pt-2">
                    <Checkbox
                      checked={p.approved}
                      onCheckedChange={v => patchParty(p.id, { approved: v === true })}
                      aria-label={`${p.name || "taraf"} satırını onayla`}
                    />
                  </div>
                  <div className="grid gap-2 min-w-0">
                    <div className="flex items-center gap-2">
                      <Input
                        value={p.name}
                        onChange={e => patchParty(p.id, {
                          name: e.target.value,
                          approved: true,
                          // ad değişti — eski cari eşleşmesi artık güvenilmez
                          client_id: null, matchName: null,
                        })}
                        placeholder="Ad Soyad / Kurum"
                        className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent flex-1"
                      />
                      {p.name.trim() && (
                        <PartyMatchIndicator value={p.name} partyType={p.party_type} />
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Select
                        value={p.party_type}
                        onValueChange={v => patchParty(p.id, { party_type: v as ReviewParty["party_type"], approved: true })}
                      >
                        <SelectTrigger className="h-8 w-[130px] text-[12px] border-[var(--border-strong)] bg-transparent">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(["CLIENT", "COUNTER", "THIRD"] as const).map(t => (
                            <SelectItem key={t} value={t}>{PARTY_TYPE_LABEL[t]}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Input
                        value={p.role}
                        onChange={e => patchParty(p.id, { role: e.target.value, approved: true })}
                        placeholder="Rol"
                        className="h-8 w-[120px] text-[12px] border-[var(--border-strong)] bg-transparent"
                      />
                      <Input
                        value={p.tc_no}
                        onChange={e => patchParty(p.id, { tc_no: e.target.value, approved: true })}
                        placeholder="TC No"
                        className="h-8 w-[130px] font-mono text-[12px] border-[var(--border-strong)] bg-transparent"
                      />
                      <button
                        type="button"
                        onClick={() => setParties(prev => prev.filter(x => x.id !== p.id))}
                        aria-label="Tarafı sil"
                        className="w-7 h-7 grid place-items-center text-[var(--fg-subtle)] hover:text-[var(--brand)] hover:bg-[var(--brand-soft)] transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {p.matchName && p.client_id != null && (
                      <p className="font-mono text-[10px] tracking-[0.04em] text-emerald-600">
                        Kayıtlı cari: {p.matchName} (#{p.client_id})
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </FlowCard>

          {/* Poliçeler */}
          {relevantPolicies.length > 0 && (
            <FlowCard padded={false}>
              <div className="px-5 py-3 border-b border-[var(--border)]">
                <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                  Poliçeler — seçilenler müvekkil kartına kaydedilir
                </span>
              </div>
              <ul className="divide-y divide-[var(--border)]">
                {relevantPolicies.map((p: MergePolicy) => {
                  const key = policyKey(p);
                  const disabled = p.saved || p.client_id == null;
                  return (
                    <li key={key} className="px-5 py-3 flex items-start gap-3">
                      <Checkbox
                        checked={p.saved ? true : (selectedPolicies[key] ?? false)}
                        disabled={disabled}
                        onCheckedChange={v =>
                          setSelectedPolicies(prev => ({ ...prev, [key]: v === true }))
                        }
                        aria-label={`${p.police_no || "poliçe"} kaydını seç`}
                        className="mt-0.5"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[13px] text-[var(--fg)] font-medium">
                            {p.police_no || "Poliçe no yok"}
                          </span>
                          {p.police_turu && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 border border-[var(--border-strong)] text-[var(--fg-muted)]">
                              {p.police_turu}
                            </span>
                          )}
                          {p.relevant && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 border border-emerald-600/40 bg-emerald-500/10 text-emerald-600">
                              İlgili dönem
                            </span>
                          )}
                          {p.saved && (
                            <span className="font-mono text-[10px] px-1.5 py-0.5 border border-[var(--border)] text-[var(--fg-subtle)]">
                              Zaten kayıtlı
                            </span>
                          )}
                        </div>
                        <p className="text-[12px] text-[var(--fg-muted)] mt-1">
                          {p.sigorta_sirketi || "?"} · {p.baslangic || "?"} – {p.bitis || "?"}
                          {p.retroaktif && ` · retroaktif ${p.retroaktif}`}
                          {p.sigortali && ` · ${p.sigortali}`}
                        </p>
                        {p.client_id == null && !p.saved && (
                          <p className="font-mono text-[10px] text-amber-600 mt-1">
                            Müvekkil eşleşmesi yok — kaydedilemez (poliçe bilgisi notlara yazılabilir)
                          </p>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </FlowCard>
          )}

          {/* Belge şeridi */}
          <FlowCard padded={false}>
            <div className="px-5 py-3 border-b border-[var(--border)]">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
                Belgeler · {documents.length}
                {expiredCount > 0 && <span className="text-[var(--brand)]"> · {expiredCount} süresi dolmuş</span>}
              </span>
            </div>
            <ul className="divide-y divide-[var(--border)]">
              {documents.map(d => (
                <li key={d.process_id} className={`px-5 py-3 grid gap-2 ${d.expired ? "opacity-50" : ""}`}>
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-[var(--fg-subtle)] shrink-0" strokeWidth={1.5} />
                    <span className="font-mono text-[10px] text-[var(--fg-subtle)] break-all min-w-0">
                      {d.filename}
                    </span>
                    {d.expired && (
                      <span className="font-mono text-[10px] px-1.5 py-0.5 border border-[var(--brand)]/40 bg-[var(--brand-soft)] text-[var(--brand)] shrink-0">
                        Süresi doldu — arşivlenmeyecek
                      </span>
                    )}
                  </div>
                  {!d.expired && (
                    <>
                      <div className="flex flex-wrap gap-2">
                        <Input
                          value={d.newName}
                          onChange={e => patchDocument(d.process_id, { newName: e.target.value })}
                          placeholder="Arşiv dosya adı"
                          className="h-8 text-[12px] border-[var(--border-strong)] bg-transparent flex-1 min-w-[200px]"
                        />
                        <Select
                          value={d.code || undefined}
                          onValueChange={v => patchDocument(d.process_id, { code: v })}
                        >
                          <SelectTrigger className="h-8 w-[220px] text-[12px] border-[var(--border-strong)] bg-transparent">
                            <SelectValue placeholder="Belge türü..." />
                          </SelectTrigger>
                          <SelectContent>
                            {d.code && !doctypes.some(t => t.code === d.code) && (
                              <SelectItem value={d.code}>{d.code}</SelectItem>
                            )}
                            {doctypes.map(t => (
                              <SelectItem key={t.code || t.name} value={t.code || t.name}>
                                {t.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      {d.ozet && (
                        <Textarea
                          value={d.ozet}
                          onChange={e => patchDocument(d.process_id, { ozet: e.target.value })}
                          rows={2}
                          className="text-[12px] border-[var(--border-strong)] bg-transparent"
                        />
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          </FlowCard>
        </div>
      </div>

      {/* E-posta bildirimi (karar 2: varsayılan KAPALI; Faz 4 devir notu b) */}
      <FlowCard>
        <label className="flex items-center gap-2.5 cursor-pointer select-none">
          <Checkbox
            checked={sendEmail}
            onCheckedChange={v => setSendEmail(v === true)}
            aria-label="E-posta bildirimi gönder"
          />
          <span className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
            <Mail className="w-3 h-3" /> Belgeler arşivlenince e-posta bildirimi gönder
          </span>
        </label>

        {sendEmail && (
          <div className="mt-3 grid gap-2">
            {emailTo.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {emailTo.map(addr => (
                  <span
                    key={addr}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-[var(--bg-sunken)] border border-[var(--border)] font-mono text-[11px] text-[var(--fg)]"
                  >
                    {addr}
                    <button
                      type="button"
                      onClick={() => setEmailTo(prev => prev.filter(a => a !== addr))}
                      aria-label={`${addr} alıcısını kaldır`}
                      className="text-[var(--fg-subtle)] hover:text-[var(--brand)]"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {emailRecipients.filter(r => r.email && !emailTo.includes(r.email.toLowerCase())).length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                  Kayıtlı alıcılar:
                </span>
                {emailRecipients
                  .filter(r => r.email && !emailTo.includes(r.email.toLowerCase()))
                  .map(r => (
                    <button
                      key={r.email}
                      type="button"
                      onClick={() => addEmailRecipient(r.email!)}
                      className="inline-flex items-center gap-1 px-2 py-1 border border-dashed border-[var(--border-strong)] font-mono text-[11px] text-[var(--fg-muted)] hover:text-[var(--brand)] hover:border-[var(--brand)] transition-colors"
                      title={r.email!}
                    >
                      <Plus className="w-3 h-3" /> {r.name || r.email}
                    </button>
                  ))}
              </div>
            )}

            <div className="flex items-center gap-2">
              <Input
                value={customEmail}
                onChange={e => setCustomEmail(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addEmailRecipient(customEmail);
                  }
                }}
                placeholder="alici@ornek.com"
                type="email"
                className="h-8 max-w-xs text-[13px] border-[var(--border-strong)] bg-transparent"
              />
              <FlowButton variant="ghost" onClick={() => addEmailRecipient(customEmail)} disabled={!customEmail.trim()}>
                <Plus className="w-3.5 h-3.5" /> Ekle
              </FlowButton>
            </div>
          </div>
        )}
      </FlowCard>

      {/* Kaydet çubuğu */}
      <FlowCard className="flex items-center justify-between gap-4 sticky bottom-4 shadow-lg">
        <span className="text-[13px] text-[var(--fg-muted)]">
          {gateHint || "Taslak hazır — tek tıkla dava açılır, belgeler arşive kuyruklanır."}
        </span>
        <FlowButton variant="primary" onClick={handleSave} disabled={!canSave}>
          <Save className="w-3.5 h-3.5" />
          {isCommitting ? "Kaydediliyor…" : "Kaydet ve Arşivle"}
        </FlowButton>
      </FlowCard>
    </div>
  );
}
