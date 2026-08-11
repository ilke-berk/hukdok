import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useCases, CASE_SEQUENCE_ERROR } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import {
  ApplyConflictError,
  CommitConflictError,
  policyKey,
  selectCommitPolicies,
  type CaseIntakeApplyRequest,
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
  buildEnrichFields,
  confirmedFieldLabels,
  enrichApplySummary,
  enrichRowGroup,
  selectEnrichParties,
} from "@/lib/intakeEnrich";
import { SESSION_EXPIRED_EVENT } from "@/lib/api";
import { debounce, saveIntakeDraft, type ReviewSnapshot } from "@/lib/intakeDraft";
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
  // Enrich modu: davada zaten kayıtlı tarafın id'si — satır salt-okunur
  // gösterilir, apply'a gönderilmez (yalnız EKLEME)
  existingId?: number | null;
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
  /** Faz 7: enrich modunda Kaydet commit yerine apply'a gider. */
  onApply?: (req: CaseIntakeApplyRequest) => Promise<unknown>;
  /** Faz 7: duplicate uyarısından "bu davayı zenginleştir" köprüsü —
      merge hedef davayla yeniden koşar, review enrich moduna geçer. */
  onEnrichExisting?: (caseId: number) => void;
  /** Faz 6.2: yarım kalan taslaktan devam — form durumu buradan init edilir. */
  initialReview?: ReviewSnapshot | null;
  /** 409 sonrası tazelenen review'da kalıcı "henüz kaydedilmedi" bandı. */
  conflictNotice?: boolean;
}

let nextPartyId = 0;
const makePartyId = () => `party-${++nextPartyId}`;

const PARTY_TYPE_LABEL: Record<ReviewParty["party_type"], string> = {
  CLIENT: "Müvekkil",
  COUNTER: "Karşı Taraf",
  THIRD: "3. Kişi",
};

// Hizmet türü bitmask etiketleri (NewCase HIZMET_TURLERI ile aynı sıra —
// index = maskedeki hane; ofis no son bloğu bu maskeden üretilir)
const SERVICE_TYPES = [
  { label: "Rapor", index: 0 },
  { label: "Danışmanlık", index: 1 },
  { label: "Dava", index: 2 },
  { label: "İcra", index: 3 },
  { label: "Yazışma", index: 4 },
];

export function IntakeReviewStep({ draft, isCommitting, onCommit, onApply, onEnrichExisting, initialReview, conflictNotice }: IntakeReviewStepProps) {
  const { getClientCaseSequence } = useCases();
  const { lawyers, doctypes, emailRecipients, courtTypesByParent, caseSubjects, specialties, bureauTypes, requiredCaseFields } = useConfig();

  // Faz 7 — enrich modu: mevcut davayı belgeden doldur/teyit. Yalnız fark
  // listesi gösterilir; tik semantiği "onay" değil "UYGULA"dır (tik'lenmeyen
  // alan davada dokunulmaz), ofis no / hizmet türü / avukat blokları gizlenir.
  const enrichMode = draft.mode === "enrich" && draft.case != null;
  const enrichCase = draft.case;

  // Zorunlu alan seti (required_fields.py tek kaynak, /api/config/required_case_fields).
  // Zorunlu alanlar boşken de tik ister — boş tik "bilgi elimde yok" onayı gerektirir.
  // Enrich modunda uygulanmaz: dava zaten açık, eksikler panel uyarısının işi.
  const requiredFieldKeys = useMemo(
    () => (enrichMode ? new Set<string>() : new Set(requiredCaseFields.map(f => f.field))),
    [requiredCaseFields, enrichMode],
  );

  // --- Alanlar ---------------------------------------------------------
  const [fieldStates, setFieldStates] = useState<Record<string, IntakeFieldState>>(
    () => initialReview?.fieldStates ?? buildFieldStates(draft),
  );

  const setFieldValue = (key: string, value: string) => {
    // Düzenlemek otomatik tikler; boşaltmak tiki DÜŞÜRÜR — zorunlu alan
    // boş bırakılacaksa "bilgi elimde yok" onayıyla yeniden tiklenmeli
    setFieldStates(prev => ({
      ...prev,
      [key]: { ...prev[key], value, touched: true, approved: value !== "" },
    }));
  };

  const setFieldApproved = (key: string, approved: boolean) => {
    setFieldStates(prev => ({ ...prev, [key]: { ...prev[key], approved } }));
  };

  // --- Taraflar --------------------------------------------------------
  // Restore'da id'ler taze üretilir (sayaç oturuma özgü, saklanan id çakışır)
  const [parties, setParties] = useState<ReviewParty[]>(() =>
    initialReview
      ? initialReview.parties.map(p => ({ ...p, id: makePartyId() }))
      : draft.parties.map(p => ({
          id: makePartyId(),
          // Kayıtlı taraf davadaki yazımıyla, kalanlar kanonik cari yazımıyla
          name: p.existing?.name || p.match?.name || p.name,
          role: p.existing?.role || ROL_DISPLAY[p.rol] || p.rol,
          party_type: p.party_type,
          tc_no: p.tc_no || "",
          client_id: p.match?.client_id ?? null,
          matchName: p.match?.name ?? null,
          matchCategory: p.match?.category ?? null,
          approved: false,
          fromDraft: true,
          existingId: p.existing?.case_party_id ?? null,
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

  // --- Hizmet Türü (bitmask, NewCase deseni) ---------------------------
  // Seçilen her hizmet ofis numarasının son bloğuna (11000 gibi) yansır.
  const [serviceMask, setServiceMask] = useState(initialReview?.serviceMask ?? "00000");
  const toggleService = (index: number, checked: boolean) => {
    setServiceMask(prev => {
      const mask = prev.split("");
      mask[index] = checked ? "1" : "0";
      return mask.join("");
    });
  };

  // --- Dava Avukatları (çoklu, NewCase deseni) -------------------------
  const [selectedLawyers, setSelectedLawyers] = useState<Array<{ name: string; lawyer_id?: number | null }>>(
    initialReview?.selectedLawyers ?? [],
  );

  // --- Ofis No ---------------------------------------------------------
  const [trackingNo, setTrackingNo] = useState(initialReview?.trackingNo ?? "");
  const [isGeneratingNo, setIsGeneratingNo] = useState(false);
  // G002: ofis no sırası alınamadıysa kayıt bloke (null = hata yok)
  const [sequenceError, setSequenceError] = useState<string | null>(null);

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
        serviceType: serviceMask,
      }));
      setSequenceError(null);
    } finally {
      setIsGeneratingNo(false);
    }
  }, [approvedClients, fieldStates.file_type?.value, serviceMask, getClientCaseSequence]);

  /**
   * G002: effect'ten çağrılan sarmalayıcı — sıra numarası hatası artık
   * yutulmuyor; yakalanmazsa unhandled rejection olurdu. Hata bayrağı
   * kaydetmeyi bloke eder (uydurma ofis numarasıyla kayıt YOK).
   */
  const regenerateTrackingSafely = useCallback(async () => {
    try {
      await regenerateTracking();
    } catch (error) {
      console.error(error);
      setSequenceError(error instanceof Error ? error.message : CASE_SEQUENCE_ERROR);
    }
  }, [regenerateTracking]);

  // İlk müvekkil onaylanınca (ve müvekkil seti / yargı türü / hizmet maskesi değiştikçe) üretilir.
  // Enrich modunda dava zaten numaralı — üretim tamamen atlanır.
  const approvedClientsKey = approvedClients.map(p => p.name).join("|");
  const fileTypeValue = fieldStates.file_type?.value;
  useEffect(() => {
    if (enrichMode) return;
    regenerateTrackingSafely();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [approvedClientsKey, fileTypeValue, serviceMask]);

  // --- Poliçeler -------------------------------------------------------
  // Varsayılan seçim: kayıtlı olmayan + müvekkil eşleşmeli poliçeler
  const [selectedPolicies, setSelectedPolicies] = useState<Record<string, boolean>>(() => {
    if (initialReview) return initialReview.selectedPolicies;
    const initial: Record<string, boolean> = {};
    for (const p of draft.policies) {
      initial[policyKey(p)] = !p.saved && p.client_id != null;
    }
    return initial;
  });

  // --- Belge şeridi ----------------------------------------------------
  const [documents, setDocuments] = useState<ReviewDocument[]>(
    () => initialReview?.documents ?? [],
  );
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
  const [sendEmail, setSendEmail] = useState(initialReview?.sendEmail ?? false);
  const [emailTo, setEmailTo] = useState<string[]>(initialReview?.emailTo ?? []);
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

  // --- Taslak dayanıklılığı (Faz 6.2 katman 2) -------------------------
  // Form durumu sessionStorage'a debounce'lu yazılır; oturum düşmesi
  // (SESSION_EXPIRED_EVENT) ve pagehide'da bekletmeden flush edilir.
  const snapshotRef = useRef<() => ReviewSnapshot>(() => ({} as ReviewSnapshot));
  snapshotRef.current = () => ({
    fieldStates,
    parties: parties.map(({ id: _id, ...rest }) => rest),
    serviceMask,
    selectedLawyers,
    trackingNo,
    selectedPolicies,
    documents,
    sendEmail,
    emailTo,
  });
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const saveDraftRef = useRef<ReturnType<typeof debounce> | null>(null);
  if (saveDraftRef.current === null) {
    saveDraftRef.current = debounce(
      () => saveIntakeDraft(draftRef.current, snapshotRef.current()),
      1000,
    );
  }
  useEffect(() => {
    saveDraftRef.current!();
  }, [fieldStates, parties, serviceMask, selectedLawyers, trackingNo,
      selectedPolicies, documents, sendEmail, emailTo]);
  useEffect(() => {
    const save = saveDraftRef.current!;
    const flush = () => save.flush();
    window.addEventListener(SESSION_EXPIRED_EVENT, flush);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener(SESSION_EXPIRED_EVENT, flush);
      window.removeEventListener("pagehide", flush);
      // Unmount: commit başarısında taslak zaten temizlendi — bekleyen yazım
      // bayat taslağı geri getirmesin diye iptal edilir.
      save.cancel();
    };
  }, []);

  // --- Enrich uygulama yükü (Faz 7) ------------------------------------
  // Tik = UYGULA: yalnız tik'li ve kayıtlı değerden farklı alanlar + kayıtlı
  // olmayan tik'li taraflar gider; tik'lenmeyen her şey davada dokunulmaz.
  const enrichFieldsPayload = enrichMode ? buildEnrichFields(fieldStates, draft) : {};
  const enrichParties = enrichMode ? selectEnrichParties(parties) : [];
  const activeDocuments = documents.filter(d => !d.expired);
  const enrichCounts = {
    fields: Object.keys(enrichFieldsPayload).length,
    parties: enrichParties.length,
    documents: activeDocuments.length,
    policies: draft.policies.filter(
      p => selectedPolicies[policyKey(p)] && !p.saved && p.client_id != null,
    ).length,
  };
  const enrichHasWork =
    enrichCounts.fields + enrichCounts.parties + enrichCounts.documents + enrichCounts.policies > 0;

  // --- Kaydet kapısı ---------------------------------------------------
  const progress = fieldApprovalProgress(fieldStates, requiredFieldKeys);
  const canSave = enrichMode
    ? enrichHasWork && (!sendEmail || emailTo.length > 0) && !isCommitting
    : progress.complete &&
      partiesApproved &&
      approvedClients.length > 0 &&
      trackingNo !== "" &&
      (!sendEmail || emailTo.length > 0) &&
      !isCommitting &&
      !isGeneratingNo &&
      // G002: sıra numarası doğrulanamadıysa kaydet düğmesi de kapalı kalır
      !sequenceError;

  const gateHint = enrichMode
    ? sendEmail && emailTo.length === 0
      ? "E-posta için en az bir alıcı ekleyin (ya da bildirimi kapatın)"
      : enrichApplySummary(enrichCounts)
    : !progress.complete
      ? `${progress.approved}/${progress.required} alan onaylandı`
      : approvedClients.length === 0
        ? "En az 1 müvekkil onaylanmalı"
        : !partiesApproved
          ? "Tüm taraf satırları onaylanmalı (ya da boş bırakılmalı)"
          : sequenceError
            ? "Ofis numarası doğrulanamadı — bağlantıyı kontrol edip yenileyin"
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
        service_type: serviceMask,
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
        judicial_unit: v("judicial_unit") || null,
        hasar_dosya_no: v("hasar_dosya_no") || null,
        hukuk_no: v("hukuk_no") || null,
        klasor_no_2: v("klasor_no_2") || null,
        acceptance_date: v("acceptance_date") || null,
        bureau_type: v("bureau_type") || null,
        atama_tarihi: v("atama_tarihi") || null,
        notes: v("notes") || null,
        parties: commitParties,
        // Sorumlu avukat + eklenen dava avukatları (ad bazında tekilleştirilir)
        lawyers: [
          ...(lawyerName ? [{ name: lawyerName, lawyer_id: lawyerObj?.id ?? null }] : []),
          ...selectedLawyers.filter(sl => sl.name !== lawyerName),
        ],
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

  // --- Apply (Faz 7 — enrich modu) -------------------------------------
  const buildApplyRequest = (): CaseIntakeApplyRequest => {
    const esasNo = fieldStates.esas_no?.value?.trim() || enrichCase?.esas_no || null;
    const muvekkilAdi =
      parties.find(p => p.party_type === "CLIENT" && p.name.trim())?.name ?? null;
    return {
      case_id: enrichCase!.id,
      // Eşzamanlılık imzası: dava bu ekran açıldıktan sonra değiştiyse backend
      // 409 döner (eski taslaklarda alan yok → null → kontrol atlanır).
      expected_updated_at: enrichCase?.updated_at ?? null,
      fields: enrichFieldsPayload,
      parties: enrichParties.map(p => ({
        client_id: p.client_id ?? undefined,
        name: p.name.trim(),
        role: p.role || (p.party_type === "CLIENT" ? "Davacı" : "Davalı"),
        party_type: p.party_type,
        tc_no: p.tc_no || undefined,
      })),
      documents: activeDocuments.map(d => ({
        process_id: d.process_id,
        new_filename: d.newName.trim() || d.filename,
        original_filename: d.filename,
        belge_turu_kodu: d.code || null,
        ai_ozet: d.ozet || null,
        esas_no: esasNo,
        muvekkil_adi: muvekkilAdi,
      })),
      policies: selectCommitPolicies(
        draft.policies.filter(p => selectedPolicies[policyKey(p)]),
      ),
      options: { send_email: sendEmail, email_to: sendEmail ? emailTo : [] },
    };
  };

  const handleSave = async () => {
    if (enrichMode) {
      if (!onApply) return;
      try {
        await onApply(buildApplyRequest());
      } catch (e) {
        // 409 stale_case: hook toast'lar ve merge'i otomatik tazeler — review
        // yeni draft'la remount olur, burada ikinci bir hata göstermeyiz.
        if (e instanceof ApplyConflictError) return;
        toast.error("Güncelleme başarısız", {
          description: e instanceof Error ? e.message : "Sunucu hatası oluştu.",
        });
      }
      return;
    }
    // G002: ofis numarası sunucudan doğrulanamadıysa kayıt BLOKE — sessiz `1`
    // sırasıyla üretilmiş numara dolu çıkıp commit'i 409'a düşürüyordu.
    if (sequenceError) {
      toast.error("Kaydedilemez: ofis numarası doğrulanamadı", {
        description: `${sequenceError} Bağlantı düzelince "Ofis No" alanını yenileyin.`,
      });
      return;
    }
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
            serviceType: serviceMask,
          });
          setTrackingNo(fresh);
          await onCommit(buildRequest(fresh));
        } catch (retryErr) {
          // G002: tekrar sırasında sıra numarası da alınamadıysa (sunucu hâlâ
          // erişilemez) bayrağı kaldır — sonraki kaydet denemesi de bloke olsun.
          if (retryErr instanceof Error && retryErr.message === CASE_SEQUENCE_ERROR) {
            setSequenceError(retryErr.message);
          }
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
  // Enrich modunda yalnız FARK listesi satır olur (fill/conflict); teyit
  // edilenler özet çipine katlanır, kalan alanlar gizlenir (plan İK 5.4).
  const allFieldDefs = activeIntakeFields();
  const fieldDefs = enrichMode
    ? allFieldDefs.filter(def => enrichRowGroup(def, draft) === "action")
    : allFieldDefs;
  const confirmedLabels = enrichMode ? confirmedFieldLabels(draft) : [];

  // Alanlar bölüm başlıklarıyla gruplanır (ardışık aynı section tek grup);
  // her grup içte 2 sütunlu ızgara — wide alanlar tam satır kaplar.
  const fieldSections = useMemo(() => {
    const sections: { title: string; defs: typeof fieldDefs }[] = [];
    for (const def of fieldDefs) {
      const title = def.section || "";
      const last = sections[sections.length - 1];
      if (last && last.title === title) last.defs.push(def);
      else sections.push({ title, defs: [def] });
    }
    return sections;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const lawyerNames = lawyers.map(l => l.name);

  // Priors: ilk cari-eşleşmeli müvekkilin geçmiş dava alışkanlıkları — düşük
  // güvenli ön-dolgu ÖNERİSİ olarak rozet gösterilir, otomatik uygulanmaz.
  const priorClientId = parties.find(p => p.party_type === "CLIENT" && p.client_id != null)?.client_id;
  const clientPriors = priorClientId != null ? draft.priors?.[String(priorClientId)] : undefined;

  // Yargı Birimi seçenekleri yargı türüne bağlıdır (NewCase'teki ALT_TURLER ile aynı kaynak)
  const judicialUnitOptions = (courtTypesByParent?.[fieldStates.file_type?.value || ""] || [])
    .map(i => i.name ?? "")
    .filter(Boolean);
  const bureauTypeOptions = bureauTypes.map(b => b.name ?? "").filter(Boolean);

  // Dava konusu: NewCase ile aynı sıralama — tıbbi kötü uygulama konuları en üstte
  const subjectOptions = useMemo(() => {
    const pinned = ["Rücuen Alacak (Tıbbi Kötü Uygulama)", "Tazminat (Tıbbi Kötü Uygulama)"];
    return [...caseSubjects]
      .sort((a, b) => {
        const ia = pinned.indexOf(a.name);
        const ib = pinned.indexOf(b.name);
        if (ia !== -1 && ib !== -1) return ia - ib;
        if (ia !== -1) return -1;
        if (ib !== -1) return 1;
        return 0;
      })
      .map(s => s.name);
  }, [caseSubjects]);
  const specialtyOptions = useMemo(() => specialties.map(s => s.name), [specialties]);
  const expiredCount = documents.filter(d => d.expired).length;
  const relevantPolicies = draft.policies;

  return (
    <div className="grid gap-5">
      {/* 409 sonrası kalıcı uyarı: toast kaçırılsa bile "kaydedildi" sanılmasın.
          Bant bir sonraki Kaydet denemesine kadar durur (hook temizler). */}
      {conflictNotice && (
        <div className="border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-[13px] text-[var(--fg)]">
            <span className="font-semibold">Değişiklikler henüz kaydedilmedi.</span>{" "}
            Dava bu ekran açıkken güncellendiği için öneriler güncel değerlerle
            tazelendi — farkları yeniden işaretleyip Kaydet'e basın.
          </span>
        </div>
      )}

      {/* Enrich modu başlığı: hedef dava */}
      {enrichMode && enrichCase && (
        <div className="border border-[var(--brand)]/40 bg-[var(--brand-soft)] px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <span className="text-[13px] text-[var(--fg)]">
            <span className="font-semibold">Mevcut dava zenginleştiriliyor:</span>{" "}
            <Link
              to={`/cases/${enrichCase.id}`}
              target="_blank"
              className="font-mono text-[12px] text-[var(--brand)] hover:underline inline-flex items-center gap-1"
            >
              {enrichCase.tracking_no} <ExternalLink className="w-3 h-3" />
            </Link>
            {enrichCase.esas_no && <span className="font-mono text-[12px]"> · {enrichCase.esas_no}</span>}
            {enrichCase.court && <span className="text-[12px] text-[var(--fg-muted)]"> · {enrichCase.court}</span>}
          </span>
          <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
            Tik'lenen öneriler davaya işlenir — tik'lenmeyen alanlara dokunulmaz
          </span>
        </div>
      )}

      {/* Uyarı bantları */}
      {draft.duplicate_case && (
        <div className="border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex items-center gap-3 flex-wrap">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-[13px] text-[var(--fg)] min-w-0 flex-1">
            Bu dava zaten kayıtlı olabilir:{" "}
            <Link
              to={`/cases/${draft.duplicate_case.id}`}
              target="_blank"
              className="font-mono text-[12px] text-[var(--brand)] hover:underline inline-flex items-center gap-1"
            >
              {draft.duplicate_case.tracking_no} <ExternalLink className="w-3 h-3" />
            </Link>{" "}
            — inceleyin, bu davayı zenginleştirin ya da yine de devam edin.
          </span>
          {onEnrichExisting && (
            <FlowButton
              size="sm"
              variant="secondary"
              onClick={() => onEnrichExisting(draft.duplicate_case!.id)}
              disabled={isCommitting}
            >
              Bu davayı zenginleştir →
            </FlowButton>
          )}
        </div>
      )}
      {draft.warnings.map((w, i) => (
        <div key={i} className="border border-amber-500/40 bg-amber-500/10 px-4 py-3 flex items-center gap-3">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="text-[13px] text-[var(--fg)]">{w.message}</span>
        </div>
      ))}

      {/* Sol (alanlar) içte 2 sütunlu olduğundan biraz daha geniş tutulur */}
      <div className="grid lg:grid-cols-[3fr_2fr] gap-5 items-start">
        {/* Sol: dava kartı alanları */}
        <FlowCard padded={false}>
          <div className="px-5 py-3 border-b border-[var(--border)] flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.18em] uppercase text-[var(--fg-subtle)]">
              {enrichMode ? "Belgeden Öneriler — Fark Listesi" : "Dava Kartı Alanları"}
            </span>
            <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
              {enrichMode ? (
                <><span className="text-[var(--fg)] font-semibold">{enrichCounts.fields}</span> alan uygulanacak</>
              ) : (
                <><span className="text-[var(--fg)] font-semibold">{progress.approved}</span>/{progress.required} alan onaylandı</>
              )}
            </span>
          </div>
          {enrichMode && confirmedLabels.length > 0 && (
            <div className="px-5 py-3 border-b border-[var(--border)] flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
                Belgeyle teyit edildi:
              </span>
              {confirmedLabels.map(label => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1 font-mono text-[10px] px-1.5 py-0.5 border border-emerald-600/40 bg-emerald-500/10 text-emerald-600"
                >
                  ✓ {label}
                </span>
              ))}
            </div>
          )}
          {enrichMode && fieldDefs.length === 0 && (
            <div className="px-5 py-4 text-[13px] text-[var(--fg-muted)]">
              Belgelerden dava kartına uygulanacak yeni alan önerisi çıkmadı —
              belgeler yine de arşivlenebilir, yeni taraf/poliçe eklenebilir.
            </div>
          )}
          <div className="px-5 pb-4">
            {fieldSections.map(sec => (
              <div key={sec.title} className="pt-4 first:pt-3">
                {sec.title && (
                  <div className="font-mono text-[9.5px] tracking-[0.22em] uppercase font-semibold text-[var(--brand)] border-b border-[var(--border)] pb-1.5">
                    {sec.title}
                  </div>
                )}
                <div className="grid sm:grid-cols-2 gap-x-8">
                  {sec.defs.map(def => (
                    <div key={def.key} className={def.wide ? "sm:col-span-2" : "min-w-0"}>
                      <IntakeFieldRow
                        def={requiredFieldKeys.has(def.key) ? { ...def, required: true } : def}
                        state={fieldStates[def.key]}
                        field={def.draftKey ? draft.fields[def.draftKey] : undefined}
                        options={
                          def.key === "file_type" ? Object.keys(PROCESS_MAP)
                            : def.key === "judicial_unit" ? judicialUnitOptions
                              : def.key === "sub_type" || def.key === "sub_type_extra" ? specialtyOptions
                                : def.key === "subject" ? subjectOptions
                                  : def.key === "bureau_type" ? bureauTypeOptions
                                    : def.key === "responsible_lawyer_name" || def.key === "uyap_lawyer_name" ? lawyerNames
                                      : undefined
                        }
                        prior={def.priorsKey ? clientPriors?.[def.priorsKey] : undefined}
                        onChange={value => setFieldValue(def.key, value)}
                        onApprove={approved => setFieldApproved(def.key, approved)}
                        enrichMode={enrichMode}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Dava Avukatları + Hizmet Türü — yan yana (enrich modunda gizli:
              sorumlu avukat/hizmet maskesi açılışın işi, kartta düzenlenir) */}
          {!enrichMode && (
          <div className="grid sm:grid-cols-2 border-t border-[var(--border)]">
            <div className="px-5 py-4">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] block mb-1.5">
                Dava Avukatları (Sorumluya Ek)
              </span>
              {selectedLawyers.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-2">
                  {selectedLawyers.map((sl, idx) => (
                    <span key={idx} className="inline-flex items-center gap-1 bg-[var(--brand-soft)] text-[var(--brand)] px-2 py-1 text-[11px] font-medium border border-[var(--brand)]/20">
                      {sl.name}
                      <button
                        type="button"
                        onClick={() => setSelectedLawyers(prev => prev.filter((_, i) => i !== idx))}
                        className="hover:opacity-70 transition-opacity"
                        aria-label={`${sl.name} avukatını çıkar`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <Select
                value=""
                onValueChange={v => {
                  if (v && !selectedLawyers.find(l => l.name === v)) {
                    const obj = lawyers.find(l => l.name === v);
                    setSelectedLawyers(prev => [...prev, { name: v, lawyer_id: obj?.id ?? null }]);
                  }
                }}
              >
                <SelectTrigger className="h-9 text-[13px] border-[var(--border-strong)] bg-transparent">
                  <SelectValue placeholder="Avukat Ekle..." />
                </SelectTrigger>
                <SelectContent className="max-h-64">
                  {lawyerNames.map(n => <SelectItem key={n} value={n}>{n}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            {/* Hizmet Türü — seçimler ofis numarasının son bloğunu şekillendirir */}
            <div className="px-5 py-4 border-t sm:border-t-0 sm:border-l border-[var(--border)]">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)] block mb-2">
                Hizmet Türü (Çoklu Seçim)
              </span>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2">
                {SERVICE_TYPES.map(t => (
                  <label key={t.index} className="flex items-center gap-2 text-[13px] text-[var(--fg)] cursor-pointer">
                    <Checkbox
                      checked={serviceMask[t.index] === "1"}
                      onCheckedChange={checked => toggleService(t.index, checked === true)}
                    />
                    {t.label}
                  </label>
                ))}
              </div>
              <p className="font-mono text-[10px] text-[var(--fg-subtle)] mt-2">
                Seçimler ofis numarasının son bloğuna (11000) yansır.
              </p>
            </div>
          </div>
          )}

          {/* Ofis No (enrich modunda gizli — dava zaten numaralı) */}
          {!enrichMode && (
          <div className="px-5 py-4 border-t border-[var(--border)]">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                Ofis No (Takip Numarası)
              </span>
              <button
                type="button"
                onClick={regenerateTrackingSafely}
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
            {/* G002: sıra numarası alınamadı — gösterilen numara güvenilmez, kayıt bloke */}
            {sequenceError && (
              <p role="alert" className="mt-1.5 text-[12px] text-[var(--danger,#b3261e)]">
                {sequenceError} Numara doğrulanana kadar kayıt yapılamaz.
              </p>
            )}
          </div>
          )}
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
                enrichMode && p.existingId != null ? (
                  // Davada zaten kayıtlı taraf: salt-okunur, apply'a gitmez
                  // (yalnız EKLEME — mevcut taraf silinmez/değiştirilmez)
                  <li key={p.id} className="px-5 py-2.5 flex items-center gap-2 flex-wrap">
                    <span className="text-[13px] text-[var(--fg)]">{p.name}</span>
                    {p.role && (
                      <span className="text-[12px] text-[var(--fg-muted)]">· {p.role}</span>
                    )}
                    <span className="font-mono text-[10px] px-1.5 py-0.5 border border-[var(--border)] text-[var(--fg-subtle)]">
                      Davada kayıtlı
                    </span>
                  </li>
                ) : (
                <li key={p.id} className="px-5 py-3 grid grid-cols-[auto_1fr] gap-x-3">
                  <div className="pt-2">
                    <Checkbox
                      checked={p.approved}
                      onCheckedChange={v => patchParty(p.id, { approved: v === true })}
                      aria-label={
                        enrichMode
                          ? `${p.name || "taraf"} satırını davaya ekle`
                          : `${p.name || "taraf"} satırını onayla`
                      }
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
                    {enrichMode && p.fromDraft && (
                      <p className="font-mono text-[10px] tracking-[0.04em] text-[var(--fg-subtle)]">
                        Belgeden yeni taraf önerisi — tik'lenirse davaya eklenir
                      </p>
                    )}
                  </div>
                </li>
                )
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
          {isCommitting
            ? "Kaydediliyor…"
            : enrichMode
              ? "Davayı Güncelle ve Arşivle"
              : "Kaydet ve Arşivle"}
        </FlowButton>
      </FlowCard>
    </div>
  );
}
