import { useState, useEffect, useCallback, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useSetPageTitle } from "@/hooks/usePageTitle";
import { FlowDropZone } from "@/components/flow/FlowDropZone";
import { FlowStageStrip, type FlowStage } from "@/components/flow/primitives";
import { AnalysisResults } from "@/components/AnalysisResults";
import { AnalysisPending } from "@/components/AnalysisPending";
import { QueueStatus } from "@/components/QueueStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Wand2, Loader2, AlertCircle, Link2, Search, X, TestTube2, CheckCircle2, FolderOpen, Gavel, Users, ChevronsUpDown, FileText, ExternalLink, Mail, Layers, ChevronRight, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { useCases } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { QuickCaseModal } from "@/components/QuickCaseModal";
import { getStoredOutputDir, setStoredOutputDir } from "@/lib/directoryStorage";
import { getTodayUploads, getTodayUploadItems, addTodayUpload, type TodayUploadItem } from "@/lib/todayUploads";
import { SectionHeader } from "@/components/dashboard/primitives";
import { TodayUploadsList } from "@/components/dashboard/TodayUploadsList";
import { useMsal } from "@azure/msal-react";

import { EmailModal } from "@/components/email/EmailModal";
import { BulkUploadWorkbench, type BulkUploadStartConfig } from "@/components/BulkUploadWorkbench";
import { analyzeDocument, type AnalysisData, type SuggestedCase } from "@/lib/analyzeDocument";

interface IndexCaseData {
  id: number;
  tracking_no: string;
  esas_no?: string;
  court?: string;
  responsible_lawyer_name?: string;
  status?: string;
  [key: string]: unknown;
}

// Faz 5: Pre-load buffer entry — analiz sonucu, process_id ve hangi File'a ait olduğu.
// File referansı ile eşleştirme yapıyoruz; queue mutate edildiğinde stale entry'ler
// güvenle filtrelenebilsin.
interface PreloadEntry {
  file: File;
  analysisData: AnalysisData;
  processId: string | null;
}

// Aynı anda buffer'da tutulacak en fazla pre-load sayısı (dosya başına).
const MAX_PRELOAD_DEPTH = 2;

// Global declaration for TypeScript to recognize showDirectoryPicker
declare global {
  interface Window {
    showDirectoryPicker: (options?: unknown) => Promise<FileSystemDirectoryHandle>;
  }

  interface FileSystemDirectoryHandle {
    queryPermission(descriptor?: { mode?: 'read' | 'readwrite' }): Promise<'granted' | 'denied' | 'prompt'>;
    requestPermission(descriptor?: { mode?: 'read' | 'readwrite' }): Promise<'granted' | 'denied' | 'prompt'>;
  }
}

const Index = () => {
  useSetPageTitle("Belge Yükleme", ["Avukat Paneli", "Belge"]);
  const { getCases, searchCases } = useCases();
  const { doctypes } = useConfig();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  // Hazırlık ekranından "Onaya Geç" sonrası 0. dosyanın analizini otomatik tetiklemek için.
  const [autoAnalyzePending, setAutoAnalyzePending] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState<string>("");
  const [openDocTypeSelect, setOpenDocTypeSelect] = useState(false);
  const [outputDirHandle, setOutputDirHandle] = useState<FileSystemDirectoryHandle | null>(null);

  // Email Modal States
  const [isEmailModalOpen, setIsEmailModalOpen] = useState(false);
  const [emailModalLoading, setEmailModalLoading] = useState(false);

  // Müvekkil bilgilendirme — metin sorumlu avukata gider. Modal açılınca davadan çekilir.
  const [clientNoticeLawyer, setClientNoticeLawyer] = useState<{ name: string; email: string } | null>(null);
  const [clientNoticeClientName, setClientNoticeClientName] = useState<string | null>(null);
  const [clientNotifyEligible, setClientNotifyEligible] = useState(false);
  const [clientWarning, setClientWarning] = useState<string | null>(null);

  // Multi-file queue states
  const [fileQueue, setFileQueue] = useState<File[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState<number>(0);
  const [processedCount, setProcessedCount] = useState<number>(0);

  // Faz 5: Pipeline pre-load buffer (FIFO). Tek slot yerine MAX_PRELOAD_DEPTH kadar
  // dosya ileriye buffer'lanır. Sıralı doldurulur (concurrent değil) — backend AI
  // API rate limit'i için aynı anda en fazla 1 preload + 1 aktif analiz çalışır.
  const [preloadBuffer, setPreloadBuffer] = useState<PreloadEntry[]>([]);
  // Eş-zamanlılık kilidi (state setter'larından önce hemen okunabilmeli).
  const preloadInProgressRef = useRef(false);
  // Preload tamamlanırken dosyanın hâlâ kuyrukta olduğunu doğrulamak için.
  const fileQueueRef = useRef<File[]>([]);

  // Faz 3: PROCESS_CACHE id (aktif dosya için)
  const [processId, setProcessId] = useState<string | null>(null);

  // Batch Mode States
  const [processedBatch, setProcessedBatch] = useState<{ path: string, name: string }[]>([]);

  // Bugün arşivlenen belgeler — drop zone sayacı + "Bugünkü yüklemelerim" listesi (localStorage, güne göre).
  const [todayCount, setTodayCount] = useState<number>(getTodayUploads());
  const [todayItems, setTodayItems] = useState<TodayUploadItem[]>(getTodayUploadItems());
  const { accounts } = useMsal();

  // Faz 3.1: Batch e-posta ayarları paylaşımı. Toggle açıkken sıradaki dosyalarda
  // EmailModal açılmaz; bu config doğrudan handleFinalProcess'e geçilir.
  const [batchEmailConfig, setBatchEmailConfig] = useState<{
    to: string[];
    cc: string[];
    perFileSend: boolean[];   // dosya bazında e-posta gönderilsin mi (fileQueue sırasıyla hizalı)
    tebligTarihi?: string;
    extraAttachments?: File[];
  } | null>(null);

  // Faz 6: Toplu yükleme hazırlık ekranı state'i. fileQueue.length > 1 olduğunda
  // dosyalar kuyruğa alınmadan önce burada belge türleri ve e-posta ayarları toplanır.
  const [showBatchPrep, setShowBatchPrep] = useState(false);
  const [pendingBatchFiles, setPendingBatchFiles] = useState<File[]>([]);
  const [batchPrep, setBatchPrep] = useState<{
    docTypes: string[];
    emailFlags: boolean[];      // dosya bazında e-posta toggle (fileQueue sırasıyla hizalı)
    emailPrefill: {
      sendEmail: boolean;
      to: { name: string; email: string }[];
      cc: { name: string; email: string }[];
      tebligTarihi: string;
      confirmPerFile: boolean;
    };
  } | null>(null);

  // Faz 3.3: Batch sonu toplu özet için sonuç biriktirme. State yerine ref kullanıyoruz —
  // ardışık handleFinalProcess çağrılarında React state güncelleme gecikmesi olmadan
  // son dosyada güncel toplamı okuyabilelim.
  const batchResultsRef = useRef<{
    successCount: number;
    emailSuccessCount: number;
    errors: { filename: string; reason: string }[];
  }>({ successCount: 0, emailSuccessCount: 0, errors: [] });

  // --- FAZ 1: Dava Bağlantısı State ---
  // Using explicit generic typing. Will define a dedicated CaseRead interface later in Faz 4
  const [allCases, setAllCases] = useState<IndexCaseData[]>([]); // Sadece son 50 davayı tutar
  const [searchResults, setSearchResults] = useState<IndexCaseData[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [caseSearch, setCaseSearch] = useState("");
  const [linkedCase, setLinkedCase] = useState<IndexCaseData | null>(null);
  const [selectedPartyId, setSelectedPartyId] = useState<number | null>(null);
  const [isTestMode, setIsTestMode] = useState(false);
  const [casesLoaded, setCasesLoaded] = useState(false);
  const [isQuickCaseModalOpen, setIsQuickCaseModalOpen] = useState(false);

  const location = useLocation();
  const navigate = useNavigate();

  // Boş ekrandaki kaynak kartları + "Dosya Seç" için gizli input'u tetikler.
  const openFilePicker = () => document.getElementById("hidden-file-input")?.click();

  // Davaları yükle (bir kere)
  useEffect(() => {
    getCases({ status: "DERDEST" }).then((data: IndexCaseData[]) => {
      setAllCases(data || []);
      setCasesLoaded(true);

      // Dacă sayfadan case yönlendirmesi var ise, seç
      if (location.state?.preselectCase) {
        setLinkedCase(location.state.preselectCase);
        toast.info(`Dava önceden seçildi: ${location.state.preselectCase.esas_no || location.state.preselectCase.tracking_no}`);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);


  // Server-side debounced search for case linking
  useEffect(() => {
    const loadOutputDir = async () => {
      const storedHandle = await getStoredOutputDir();
      if (storedHandle) {
        setOutputDirHandle(storedHandle);
      }
    };
    loadOutputDir();
  }, []);

  useEffect(() => {
    if (!caseSearch || caseSearch.trim().length < 2) {
      setSearchResults([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      setIsSearching(true);
      // Belge bağlama tüm davalarda arama yapar (sadece DERDEST değil) — kapalı/arşiv davalara da belge bağlanabilir
      const data = await searchCases(caseSearch, false, false);
      setSearchResults(data || []);
      setIsSearching(false);
    }, 400);

    return () => clearTimeout(timeoutId);
  }, [caseSearch, searchCases]);

  // Arama filtresi
  const filteredCases = caseSearch.trim().length >= 2 ? searchResults.slice(0, 8) : allCases.slice(0, 8);

  // linkedCase seçildiğinde parties ID'leriyle dolu tam dava verisini çek
  useEffect(() => {
    if (!linkedCase?.id) {
      setSelectedPartyId(null);
      return;
    }
    // Tüm CLIENT partilerin ID'si varsa tekrar çekme (sadece CLIENT partiler dropdown için gerekli)
    const parties = (linkedCase as IndexCaseData & { parties?: { id?: number; party_type?: string }[] }).parties ?? [];
    const clientParties = parties.filter(p => p.party_type === "CLIENT");
    const hasClientPartyIds = clientParties.length > 0 && clientParties.every(p => p.id != null);
    if (hasClientPartyIds) return;

    apiClient.fetch(`/api/cases/${linkedCase.id}`)
      .then(r => r.json())
      .then((fullCase: IndexCaseData) => {
        setLinkedCase(prev => prev?.id === fullCase.id ? { ...prev, ...fullCase } : prev);
      })
      .catch(() => { /* parties olmadan da devam edilebilir */ });
    setSelectedPartyId(null);
  }, [linkedCase?.id]);

  const handleFileSelect = (files: File | File[]) => {
    // Convert to array for consistent handling
    const fileArray = Array.isArray(files) ? files : [files];

    // Faz 6: Çoklu dosya seçildiğinde analiz başlamadan önce hazırlık ekranını aç.
    // Kuyruk ve diğer state'ler hazırlık ekranı onaylandığında kurulur (handleBatchPrepStart).
    if (fileArray.length > 1) {
      setPendingBatchFiles(fileArray);
      setShowBatchPrep(true);
      return;
    }

    setFileQueue(fileArray);
    setCurrentFileIndex(0);
    setProcessedCount(0);
    setProcessedBatch([]); // Reset batch
    setSelectedFile(fileArray[0]);
    setAnalysisData(null);
    setPreloadBuffer([]);
  };

  // Tezgâh "Onaya Geç" dediğinde: önceden (paralel) hesaplanmış analiz sonuçlarıyla
  // kuyruğu kur. 0. dosya doğrudan açılır, 1..N-1 preloadBuffer'a seed edilir — böylece
  // varsayılan tek-tek onay akışında her dosya analiz beklemeden anında yüklenir.
  const handleBatchPrepStart = (config: BulkUploadStartConfig) => {
    const { results, emailConfig } = config;
    setShowBatchPrep(false);
    setPendingBatchFiles([]);

    if (results.length === 0) return;

    const files = results.map((r) => r.file);
    const docTypes = results.map((r) => r.docType);
    const emailFlags = results.map((r) => r.email);

    setBatchPrep({
      docTypes,
      emailFlags,
      emailPrefill: {
        sendEmail: emailFlags.some(Boolean),
        to: emailConfig.to,
        cc: emailConfig.cc,
        tebligTarihi: emailConfig.tebligTarihi,
        confirmPerFile: emailConfig.confirmPerFile,
      },
    });

    // confirmPerFile kapalı → EmailModal hiç açılmasın; batchEmailConfig şimdiden hazır.
    // Gönderim kararı dosya bazında (perFileSend) verilir.
    if (!emailConfig.confirmPerFile) {
      const toList = emailConfig.to.map((r) => `${r.name} <${r.email}>`);
      const ccList = emailConfig.cc.map((r) => `${r.name} <${r.email}>`);
      setBatchEmailConfig({
        to: toList,
        cc: ccList,
        perFileSend: emailFlags,
        tebligTarihi: emailConfig.tebligTarihi || undefined,
        extraAttachments: undefined,
      });
    } else {
      setBatchEmailConfig(null);
    }

    setFileQueue(files);
    setCurrentFileIndex(0);
    setProcessedCount(0);
    setProcessedBatch([]);
    setSelectedFile(files[0]);
    setSelectedDocType(docTypes[0] || "");

    // Hazırlık ekranında analiz yapılmaz. Analiz burada (handoff sonrası) başlar:
    // 0. dosya otomatik analiz edilir, 1..N-1 preload effect'i ile arka planda hazırlanır.
    setAnalysisData(null);
    setProcessId(null);
    setPreloadBuffer([]);
    setAutoAnalyzePending(true);

    toast.info(`${files.length} dosya hazır — analiz başlatılıyor...`);
  };

  const handleBatchPrepCancel = () => {
    setShowBatchPrep(false);
    setPendingBatchFiles([]);
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setAnalysisData(null);
    setFileQueue([]);
    setCurrentFileIndex(0);
    setProcessedCount(0);
    setProcessedBatch([]);
    setPreloadBuffer([]);
    setProcessId(null);
    setSelectedDocType("");
    // Dava bağlantısını da sıfırla
    setLinkedCase(null);
    setCaseSearch("");
    // Faz 3: batch state sıfırla
    setBatchEmailConfig(null);
    batchResultsRef.current = { successCount: 0, emailSuccessCount: 0, errors: [] };
    // Faz 6: hazırlık state'i sıfırla
    setBatchPrep(null);
    setShowBatchPrep(false);
    setPendingBatchFiles([]);
    setAutoAnalyzePending(false);
  };

  // Faz 4.2: Bekleyen dosyaları kuyruktan çıkar. Geçmiş ve mevcut dosya korunur.
  const handleRemoveFromQueue = (index: number) => {
    if (index <= currentFileIndex) return;
    const removed = fileQueue[index];
    if (!removed) return;
    setFileQueue(prev => prev.filter((_, i) => i !== index));
    // Faz 5: Buffer'da o dosyaya ait entry varsa çıkar. File referansıyla eşleştirme
    // sayesinde diğer entry'ler korunur; effect kalan boşluğu yeniden doldurur.
    setPreloadBuffer(prev => prev.filter(e => e.file !== removed));
    toast.info(`📤 "${removed.name}" kuyruktan çıkarıldı.`);
  };

  const handleSelectDirectory = async () => {
    try {
      if (!window.showDirectoryPicker) {
        toast.error("Tarayıcınız bu özelliği desteklemiyor. (Sadece Chrome/Edge masaüstü)");
        return;
      }
      const handle = await window.showDirectoryPicker({
        id: 'hukudok-output',
        mode: 'readwrite',
      });
      setOutputDirHandle(handle);
      await setStoredOutputDir(handle); // PERSISTENT SAVE
      toast.success("Çıktı klasörü seçildi: Dosyalar buraya kaydedilecek.");
    } catch (error: unknown) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error("Klasör seçim hatası:", error);
        toast.error("Klasör seçilemedi.");
      } else if (!(error instanceof Error)) {
        console.error("Klasör seçim hatası:", error);
      }
    }
  };

  const saveFileToDisk = async (fileBlob: Blob, filename: string) => {
    if (!outputDirHandle) return false;
    try {
      // Check for permission logic if needed, but usually granted on selection
      // Verify permission
      if ((await outputDirHandle.queryPermission({ mode: 'readwrite' })) !== 'granted') {
        if ((await outputDirHandle.requestPermission({ mode: 'readwrite' })) !== 'granted') {
          throw new Error("Klasöre yazma izni verilmedi.");
        }
      }

      const fileHandle = await outputDirHandle.getFileHandle(filename, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(fileBlob);
      await writable.close();
      return true;
    } catch (error) {
      console.error("Dosya kaydedilemedi:", error);
      toast.error(`Dosya kaydedilemedi: ${filename}`);
      return false;
    }
  };

  // Otomatik dava önerisi akışı — hem ilk analizden hem de pre-load geçişinden çağrılır.
  // currentLinkedCase parametresi closure değerinin güncel olmadığı pre-load geçişinde
  // doğru "henüz bağlı değil" durumunu iletmek için açıkça verilir.
  const applyAutoSuggestionFlow = (
    suggested: SuggestedCase | null | undefined,
    currentLinkedCase: IndexCaseData | null
  ) => {
    if (!suggested || currentLinkedCase || isTestMode) return;

    if (suggested.client_parties?.length || suggested.counter_parties?.length) {
      setAnalysisData(prev => prev ? {
        ...prev,
        muvekkiller: suggested.client_parties?.length
          ? suggested.client_parties
          : prev.muvekkiller,
        muvekkil_adi: suggested.client_parties?.[0] || prev.muvekkil_adi,
        suggested_karsi_taraf: suggested.karsi_taraf || prev.suggested_karsi_taraf,
      } : prev);
    }

    if (suggested.confidence === "HIGH") {
      // Otomatik seçim yok — kullanıcı listeden onaylasın.
      toast.info(
        `🎯 Dava eşleşmesi bulundu: ${suggested.esas_no} (Skor: ${suggested.score}) — Lütfen sol panelden doğrulayıp onaylayın!`,
        { duration: 8000 }
      );
    } else if (suggested.confidence === "MEDIUM") {
      toast.info(
        `💡 Olası dava önerisi: ${suggested.esas_no} (Skor: ${suggested.score}) — Lütfen sol panelden aratıp doğrulayın veya doğru davayı seçin.`,
        { duration: 8000 }
      );
    }
    // LOW skor: hiçbir şey yapma, kullanıcı manuel seçsin
  };

  // Bir AI aday davasını bağlı dava olarak seç (öneri kartı + alternatif adaylar ortak kullanır).
  const selectSuggestedCase = (c: SuggestedCase) => {
    const fullCase = allCases.find(ac => ac.id === c.case_id);
    setLinkedCase(fullCase ?? {
      id: c.case_id,
      tracking_no: c.tracking_no,
      esas_no: c.esas_no,
      court: c.court,
      responsible_lawyer_name: c.responsible_lawyer_name,
      status: c.status,
      karsi_taraf: c.karsi_taraf || "",
      parties: c.parties || [],
    });
  };

  const handleAnalyze = async () => {
    // Web mode: File object is used directly, no file path needed
    if (!selectedFile) {
      toast.error("Lütfen önce bir dosya yükleyin");
      return;
    }

    setIsAnalyzing(true);

    // Faz 6: hazırlık ekranından gelen belge türü öncelikli; yoksa kullanıcının
    // mevcut akıştaki seçimini kullan.
    const effectiveDocType = batchPrep?.docTypes[currentFileIndex] ?? selectedDocType;

    try {
      const { analysisData: result, processId: pid } = await analyzeDocument(
        selectedFile,
        effectiveDocType || undefined,
        { onInfo: (m) => toast.info(m) },
      );
      if (pid) setProcessId(pid);
      setAnalysisData(result);
      applyAutoSuggestionFlow(result.suggested_case, linkedCase);
      toast.success("Analiz tamamlandı!");
    } catch (error) {
      console.error("Local Analysis error:", error);
      if (error instanceof Error && error.name === 'AbortError') {
        toast.error("İstek zaman aşımına uğradı. Sunucu yanıt vermiyor.");
      } else {
        toast.error(error instanceof Error ? error.message : "Analiz sırasında hata oluştu");
      }
    } finally {
      setIsAnalyzing(false);
      // Faz 5: Pre-load tetiklemesini effect üstlendi. Burada explicit çağrı yok —
      // fileQueue/currentFileIndex/preloadBuffer.length değiştikçe useEffect MAX_PRELOAD_DEPTH
      // sınırına kadar sırayla doldurur.
    }
  };

  // Hazırlık ekranından handoff sonrası: selectedFile kurulunca 0. dosyayı otomatik analiz et.
  useEffect(() => {
    if (autoAnalyzePending && selectedFile && !analysisData && !isAnalyzing) {
      setAutoAnalyzePending(false);
      handleAnalyze();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAnalyzePending, selectedFile, analysisData, isAnalyzing]);

  // Faz 5: Pre-load. Tek seferde 1 dosya işler (sıralı). Tamamlandığında dosya hâlâ
  // kuyruktaysa buffer'a push eder; bu da fill effect'i tetikleyerek sıradakini başlatır.
  const preloadNextFile = async (nextFile: File, docTypeCode?: string) => {
    if (preloadInProgressRef.current) return;
    preloadInProgressRef.current = true;
    // Faz 3.3: Preload toast'ları batch'te susturulur; özet sonda gösterilir.

    let preloadedData: AnalysisData | null = null;
    let preloadedProcessId: string | null = null;

    try {
      // Faz 6: Hazırlık ekranından gelen belge türü pre-load anında da gönderilir
      // — backend AI'a özel prompt'u kullanma şansı verilir.
      const { analysisData, processId } = await analyzeDocument(nextFile, docTypeCode);
      preloadedData = analysisData;
      preloadedProcessId = processId;
    } catch (error) {
      console.error("Preload error:", error);
      // Silent fail - just log, don't disrupt user flow
    } finally {
      // Buffer'a eklemeden önce dosyanın hâlâ kuyrukta olduğunu doğrula. Kullanıcı
      // preload sırasında dosyayı kuyruktan çıkardıysa bu race'i atlıyoruz; aksi halde
      // stale entry buffer slot'unu işgal edip sonraki preload'ı bloklardı.
      if (preloadedData && fileQueueRef.current.includes(nextFile)) {
        const finalData = preloadedData;
        const finalProcessId = preloadedProcessId;
        setPreloadBuffer(prev => {
          // Duplicate guard: aynı dosya için zaten entry varsa eklemeyiz.
          if (prev.some(e => e.file === nextFile)) return prev;
          return [...prev, { file: nextFile, analysisData: finalData, processId: finalProcessId }];
        });
      }
      preloadInProgressRef.current = false;
    }
  };

  // Faz 5: fileQueue ref'ini güncel tut — preload tamamlanma race'i için.
  useEffect(() => {
    fileQueueRef.current = fileQueue;
  }, [fileQueue]);

  // Faz 5: Buffer fill effect. Sıralı çalışır (preloadInProgressRef ile kilitli).
  // Bir preload bittiğinde preloadBuffer state'i değişir → effect tekrar tetiklenir →
  // gerekiyorsa sıradakini başlatır. Backend tarafında aynı anda en fazla 1 preload
  // + 1 aktif analiz çağrısı olur (AI API rate limit'i için bilinçli sınır).
  useEffect(() => {
    if (fileQueue.length <= 1) return;
    if (preloadInProgressRef.current) return;
    if (preloadBuffer.length >= MAX_PRELOAD_DEPTH) return;

    // Bir sonraki preload edilecek dosyanın index'i: currentFileIndex+1 baz, üstüne
    // buffer'da kaç tane varsa onun kadar ileriye gider.
    const nextIndex = currentFileIndex + 1 + preloadBuffer.length;
    if (nextIndex >= fileQueue.length) return;

    const nextFile = fileQueue[nextIndex];
    // Aynı dosya buffer'da varsa (örn. queue mutation sonrası) tetikleme.
    if (preloadBuffer.some(e => e.file === nextFile)) return;

    // Faz 6: hazırlık ekranında o dosya için belirlenmiş belge türünü pre-load'a geç.
    const nextDocType = batchPrep?.docTypes[nextIndex] || undefined;
    preloadNextFile(nextFile, nextDocType);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileQueue, currentFileIndex, preloadBuffer]);

  const [isProcessing, setIsProcessing] = useState(false);
  const [isValidated, setIsValidated] = useState(false);
  const [finalData, setFinalData] = useState<AnalysisData | null>(null);

  const handleValidationChange = useCallback((isValid: boolean, data: AnalysisData) => {
    setIsValidated(isValid);
    // Yalnızca veri değişmişse güncelleyerek sonsuz döngüyü önle
    setFinalData((prev) => JSON.stringify(prev) === JSON.stringify(data) ? prev : data);
  }, []);

  // Müvekkil bilgilendirme: EmailModal açılınca davanın sorumlu avukatını + müvekkil adını çek.
  useEffect(() => {
    if (!isEmailModalOpen) return;
    const data = finalData || analysisData;
    const belgeTuruKodu = data?.belge_turu_kodu;

    if (!linkedCase?.id) {
      // Sorumlu avukat yalnızca bağlı davadan bulunabilir.
      setClientNoticeLawyer(null);
      setClientNoticeClientName(null);
      setClientNotifyEligible(false);
      setClientWarning("Belge bir davaya bağlı değil — müvekkil bilgilendirmesi gönderilemez.");
      return;
    }

    let cancelled = false;
    setClientWarning(null);
    const qs = belgeTuruKodu ? `?belge_turu_kodu=${encodeURIComponent(belgeTuruKodu)}` : "";
    apiClient.fetch(`/api/cases/${linkedCase.id}/client-notice-target${qs}`)
      .then(res => res.ok ? res.json() : Promise.reject(res))
      .then((result: { eligible: boolean; lawyer: { name: string; email: string } | null; client_name: string | null }) => {
        if (cancelled) return;
        setClientNoticeLawyer(result.lawyer);
        setClientNoticeClientName(result.client_name);
        setClientNotifyEligible(!!result.eligible);
        if (result.eligible && !result.lawyer) {
          setClientWarning("Davanın sorumlu avukatı bulunamadı — müvekkil bilgilendirmesi gönderilemez.");
        } else if (result.eligible && result.lawyer && !result.lawyer.email) {
          setClientWarning(`Sorumlu avukatın (${result.lawyer.name}) kayıtlı e-postası yok — bilgilendirme gönderilemez.`);
        } else {
          setClientWarning(null);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setClientNoticeLawyer(null);
        setClientNoticeClientName(null);
        setClientNotifyEligible(false);
        setClientWarning("Müvekkil bilgilendirme hedefi alınamadı.");
      });

    return () => { cancelled = true; };
  }, [isEmailModalOpen, linkedCase?.id, finalData, analysisData]);




  // Step 1: User clicks "Confirm"
  const handleConfirmClick = () => {
    if (!finalData && !analysisData) return;

    // Faz 3.1: Batch modda config varsa modal atlanır; yoksa açılır.
    // Ekler kullanıcının seçtiği şekilde tekrar gönderilir (paylaşım kararı).
    // Per-recipient mesajlar dosyaya özgü kalır — backend default şablon kullanır.
    if (batchEmailConfig) {
      // Gönderim kararı dosya bazında (tezgâhtaki per-row toggle).
      const shouldSend = batchEmailConfig.perFileSend[currentFileIndex] ?? false;
      handleFinalProcess(
        batchEmailConfig.to,
        batchEmailConfig.cc,
        shouldSend,
        batchEmailConfig.tebligTarihi,
        undefined,
        batchEmailConfig.extraAttachments,
      );
      return;
    }

    setIsEmailModalOpen(true);
  };

  // Step 2: User confirms email -> Start Process
  // overrideLinkedCase: QuickCaseModal'dan yeni açılan dava, state güncel olmadan önce geçilir
  const handleFinalProcess = async (toEmails: string[], ccEmails: string[], shouldSendEmail: boolean, tebligTarihi?: string, perRecipientMessages?: Record<string, string>, extraAttachments?: File[], sendClientNotice?: boolean, clientNoticeMessage?: string, overrideLinkedCase?: IndexCaseData) => {
    const dataToUse = finalData || analysisData;
    if (!selectedFile || !dataToUse) return;

    const isBatchMode = fileQueue.length > 1;
    const isLastFile = currentFileIndex === fileQueue.length - 1;

    setEmailModalLoading(true);

    // BUG FIX: Use the approved 77-character filename from AnalysisResults
    // Add .pdf extension as we are dealing with document files
    let newFilename = dataToUse.generated_filename || "belge_bilinmiyor";
    if (!newFilename.toLowerCase().endsWith(".pdf")) {
      newFilename += ".pdf";
    }

    setIsEmailModalOpen(false);
    setEmailModalLoading(false);
    setIsProcessing(true);

    // Faz 3.3: Batch modda ara toast'lar bastırılır; sonunda toplu özet gösterilir.
    if (!isBatchMode) {
      toast.info("İşlem başlatıldı (SharePoint & E-Posta)...");
    }

    try {
      // Web Mode: FormData ile dosya ve metadata gönder
      const formData = new FormData();
      // Faz 3: send process_id so backend can use cached PDF; still attach file as fallback
      if (processId) formData.append("process_id", processId);
      formData.append("file", selectedFile);
      formData.append("new_filename", newFilename);

      // Optional fields
      // BUG FIX: The UI edits "muvekkil_kodu" for the client name. We must use it instead of the unedited "muvekkil_adi"
      const approvedMuvekkil = dataToUse.muvekkil_kodu || dataToUse.muvekkil_adi;
      if (approvedMuvekkil) formData.append("muvekkil_adi", approvedMuvekkil);
      if (dataToUse.karsi_taraf) formData.append("karsi_taraf", dataToUse.karsi_taraf);
      if (dataToUse.belge_turu_kodu) formData.append("belge_turu_kodu", dataToUse.belge_turu_kodu);
      if (dataToUse.tarih) formData.append("tarih", dataToUse.tarih);
      if (dataToUse.esas_no) formData.append("esas_no", dataToUse.esas_no);
      if (tebligTarihi) formData.append("teblig_tarihi", tebligTarihi);
      if (dataToUse.sonraki_durusma_tarihi) formData.append("sonraki_durusma_tarihi", dataToUse.sonraki_durusma_tarihi);
      if (dataToUse.sonraki_durusma_saati) formData.append("sonraki_durusma_saati", dataToUse.sonraki_durusma_saati);

      // JSON fields (arrays)
      formData.append("muvekkiller_json", JSON.stringify(dataToUse.muvekkiller || []));
      formData.append("belgede_gecen_isimler_json", JSON.stringify(dataToUse.belgede_gecen_isimler || []));
      formData.append("custom_to_json", JSON.stringify(toEmails));
      formData.append("custom_cc_json", JSON.stringify(ccEmails));
      formData.append("send_email", String(shouldSendEmail));
      formData.append("send_client_notice", String(!!sendClientNotice));
      if (clientNoticeMessage) {
        formData.append("client_notice_message", clientNoticeMessage);
      }
      if (perRecipientMessages && Object.keys(perRecipientMessages).length > 0) {
        formData.append("custom_messages_json", JSON.stringify(perRecipientMessages));
      }
      if (extraAttachments && extraAttachments.length > 0) {
        for (const file of extraAttachments) {
          formData.append("extra_attachment_files", file);
        }
      }

      // --- FAZ 1: Dava Bağlantısı ---
      const effectiveLinkedCase = overrideLinkedCase || linkedCase;
      if (effectiveLinkedCase?.id) {
        formData.append("linked_case_id", String(effectiveLinkedCase.id));
      }
      if (selectedPartyId != null) {
        formData.append("case_party_id", String(selectedPartyId));
      }
      formData.append("is_test_mode", String(isTestMode));
      if (dataToUse.ozet) {
        formData.append("ai_ozet", dataToUse.ozet);
      }

      const response = await apiClient.fetch("/confirm", {
        method: "POST",
        body: formData
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Kayıt işlemi sırasında bir hata oluştu.");
      }

      console.log("Confirmation complete:", result);

      // --- FAZ 1: Otomatik durum güncelleme bildirimi ---
      if (result.results?.auto_status_update) {
        toast.success(`🔄 Dava durumu otomatik güncellendi! (Belge türüne göre)`, { duration: 4000 });
      }

      // --- FAZ 1.5: Otomatik eksik veri tamamlama ---
      if (result.results?.auto_enrichment) {
        const enrichment = result.results.auto_enrichment;
        if (enrichment.lawyer) {
          toast.success(`👨‍⚖️ Davadaki eksik avukat tamamlandı: ${enrichment.lawyer}`);
        }
        if (enrichment.counter_party) {
          toast.success(`👥 Davaya Karşı Taraf eklendi: ${enrichment.counter_party}`);
        }
      }

      if (result.results?.hearing_date_saved) {
        const dateStr = new Date(result.results.hearing_date_saved + "T00:00:00").toLocaleDateString("tr-TR");
        const timeStr = result.results.hearing_time_saved ? ` saat ${result.results.hearing_time_saved}` : "";
        toast.success(`📅 Sonraki duruşma tarihi ajandaya eklendi: ${dateStr}${timeStr}`, { duration: 6000 });
      }

      if (result.results?.link_mode === "LINKED" && linkedCase) {
        toast.success(`📎 Belge "${linkedCase.esas_no || linkedCase.tracking_no}" davasına bağlandı.`);
      } else if (result.results?.link_mode === "TEST") {
        toast.info("🧪 TEST modunda yüklendi — dava bağlantısı yok.", { duration: 3000 });
      }

      // --- FILE SYSTEM ACCESS API SAVE ---
      if (outputDirHandle && selectedFile) {

        // 1. Try to download PROCESSED file using download_id
        const downloadId = result.results?.download_id;
        let blobToSave: Blob | File = selectedFile; // Fallback to original
        const finalSaveFilename = newFilename;

        if (downloadId) {
          try {
            const dlResponse = await apiClient.fetch(`/api/download/${downloadId}`);
            if (dlResponse.ok) {
              blobToSave = await dlResponse.blob();
              if (!isBatchMode) {
                toast.success("📄 İşlenmiş (PDF/A) dosya indirildi.");
              }
            } else {
              console.error("Download failed, falling back to original");
            }
          } catch (dlErr) {
            console.error("Download fetch error:", dlErr);
          }
        } else {
          const isNonPdf = !selectedFile.name.toLowerCase().endsWith(".pdf");
          if (isNonPdf && newFilename.toLowerCase().endsWith(".pdf")) {
            // Uyarı kritik: batch'te de görünmeli.
            toast.warning(`PDF dönüşümü sunucuda yapıldı ancak indirilemedi. Orijinal dosya (${selectedFile.name.split('.').pop()}) .pdf olarak kaydediliyor (açılmayabilir).`, { duration: 5000 });
          }
        }

        const success = await saveFileToDisk(blobToSave as File, finalSaveFilename);
        if (success && !isBatchMode) {
          toast.success(`💾 Dosya şuraya kaydedildi: ${finalSaveFilename}`);
        }
      }

      // TRACK PROCESSED FILE FOR BATCH (Web modunda dosya objesi kullanılır)
      // Fonksiyonel setter: ardışık çağrılarda stale closure'a düşmemek için.
      setProcessedBatch(prev => [...prev, { path: "", name: newFilename }]);

      // Bugünkü yükleme kaydını ekle (tekli + toplu, her başarılı arşivlemede bir).
      // Sayaç ve "Bugünkü yüklemelerim" listesi aynı localStorage kaydından beslenir.
      const ext = (selectedFile.name.split(".").pop() || "DOSYA").toUpperCase();
      const isLinked = result.results?.link_mode === "LINKED";
      const nextItems = addTodayUpload({
        filename: newFilename,
        sizeBytes: selectedFile.size,
        ext,
        clientName: approvedMuvekkil || undefined,
        caseNo: effectiveLinkedCase?.esas_no || dataToUse.esas_no || undefined,
        uploader: accounts[0]?.name || undefined,
        status: isLinked ? "BAĞLANDI" : "ARŞİVLENDİ",
      });
      setTodayItems(nextItems);
      setTodayCount(nextItems.length);

      // Faz 3.3: Batch modda per-file başarı toast'ları bastırılır; sayaçlar artırılır
      // ve sonunda toplu özet gösterilir. Kritik hata (e-posta fail) batch'te de toast atar.
      const emailFailed = shouldSendEmail && result.results?.email_warning;
      if (isBatchMode) {
        batchResultsRef.current.successCount += 1;
        if (shouldSendEmail && result.results?.email_success === true) {
          batchResultsRef.current.emailSuccessCount += 1;
        }
        if (emailFailed) {
          batchResultsRef.current.errors.push({
            filename: newFilename,
            reason: `E-posta: ${result.results.email_warning}`,
          });
          toast.error(`❌ E-posta gönderilemedi (${newFilename}): ${result.results.email_warning}`, { duration: 10000 });
        }
      } else {
        if (shouldSendEmail) {
          if (result.results?.email_success === true) {
            toast.success("✅ Belge arşivlendi ve e-posta gönderildi!");
          } else if (emailFailed) {
            toast.success("✅ Belge arşivlendi.");
            toast.error(`❌ E-posta gönderilemedi: ${result.results.email_warning}`, { duration: 10000 });
          } else {
            toast.success("✅ Belge arşivlendi.");
          }
        } else {
          toast.success("✅ Belge arşivlendi (E-posta gönderilmedi).");
        }
      }

      // Pipeline: Move to next file in queue
      if (fileQueue.length > 1 && currentFileIndex < fileQueue.length - 1) {
        const nextIndex = currentFileIndex + 1;
        setCurrentFileIndex(nextIndex);
        setProcessedCount(prev => prev + 1);
        setSelectedFile(fileQueue[nextIndex]);
        setIsValidated(false);
        setFinalData(null);
        // Faz 6: hazırlık ekranında belirlenmiş belge türü varsa otomatik doldur.
        setSelectedDocType(batchPrep?.docTypes[nextIndex] ?? "");

        // Dosya bazında reset — önceki dosyanın dava bağlantısı sıradakine sızmamalı.
        // isTestMode korunur (kullanıcı batch boyunca açık tutmak isteyebilir).
        setLinkedCase(null);
        setCaseSearch("");
        setSelectedPartyId(null);

        // Faz 5: Buffer'dan eşleşen entry'yi çek (file referansı ile). Bulunursa
        // anında yüklenir; buffer'dan çıkarılır ve effect yeni slot'u doldurur.
        const nextFile = fileQueue[nextIndex];
        const preloadedEntry = preloadBuffer.find(e => e.file === nextFile);
        if (preloadedEntry) {
          setAnalysisData(preloadedEntry.analysisData);
          setProcessId(preloadedEntry.processId);
          setPreloadBuffer(prev => prev.filter(e => e.file !== preloadedEntry.file));
          // Faz 3.3: Batch'te "anında yüklendi" toast'u susturulur — özet sonda gösterilir.
          if (!isBatchMode) {
            toast.success(`⚡ Dosya ${nextIndex + 1}/${fileQueue.length} anında yüklendi!`);
          }

          // Pre-loaded dosyada da AI önerisi akışı çalışsın.
          // linkedCase yukarıda sıfırlandı; closure eski değeri tutar, bu yüzden null geçilir.
          applyAutoSuggestionFlow(preloadedEntry.analysisData.suggested_case, null);
          // Yeni preload tetiklemesi explicit değil — effect halleder.
        } else {
          // Preload hazır değil veya başarısız oldu — kullanıcı belge türünü seçip
          // analizi manuel başlatır. Effect arka planda sıradakini doldurmaya devam eder.
          setAnalysisData(null);
          toast.info(`📁 Dosya ${nextIndex + 1}/${fileQueue.length} hazır — lütfen belge türünü seçip analizi başlatın.`);
        }
      } else {
        // All files processed!
        const totalFiles = fileQueue.length;
        // Son dosyanın da sayıma dahil edilmesi: QueueStatus tüm rozetleri yeşil gösterir.
        setProcessedCount(prev => prev + 1);

        if (isBatchMode) {
          // Faz 3.3: Batch sonu toplu özet.
          const { successCount, emailSuccessCount, errors } = batchResultsRef.current;
          const errorCount = errors.length;
          const errorList = errors.length > 0
            ? errors.map(e => e.filename).slice(0, 3).join(", ") + (errors.length > 3 ? "..." : "")
            : "";
          const summaryParts = [`🎉 ${successCount}/${totalFiles} tamamlandı`];
          if (emailSuccessCount > 0) summaryParts.push(`📧 ${emailSuccessCount} e-posta gönderildi`);
          if (errorCount > 0) summaryParts.push(`⚠️ ${errorCount} hata: ${errorList}`);
          toast.success(summaryParts.join(" · "), { duration: 8000 });
        } else {
          toast.success(`🎉 Tüm dosyalar tamamlandı! (${totalFiles}/${totalFiles})`);
        }

        // Reset'i kısa bir gecikmeyle yap: kullanıcı "N/N tamamlandı" görsel teyidini görür.
        setTimeout(() => {
          setAnalysisData(null);
          setFinalData(null);
          setSelectedFile(null);
          setFileQueue([]);
          setProcessedBatch([]); // Clear batch
          setCurrentFileIndex(0);
          setProcessedCount(0);
          setPreloadBuffer([]); // Faz 5: buffer'ı temizle
          setProcessId(null);
          setIsValidated(false);
          setLinkedCase(null);
          setCaseSearch("");
          // Faz 3.1/3.3: batch state'leri sıfırla. outputDirHandle korunur (Faz 3.2).
          setBatchEmailConfig(null);
          batchResultsRef.current = { successCount: 0, emailSuccessCount: 0, errors: [] };
          // Faz 6: hazırlık state'i de sıfırla.
          setBatchPrep(null);
        }, 1500);
      }
    } catch (error: unknown) {
      console.error("Confirmation error:", error);
      const errorMessage = error instanceof Error ? error.message : "Beklenmedik bir hata oluştu.";
      toast.error(errorMessage);
      if (isBatchMode) {
        batchResultsRef.current.errors.push({ filename: newFilename, reason: errorMessage });
      }
    } finally {
      setIsProcessing(false);
    }
  };


  const activeStage: FlowStage =
    analysisData ? "confirm" :
    isAnalyzing ? "analyze" :
    "upload";

  const stageMetaNode = (
    <div className="flex items-center gap-3">
      {fileQueue.length > 1 && (
        <span className="font-mono text-[10px] tracking-[0.14em] uppercase text-[var(--fg-subtle)]">
          {Math.min(processedCount + 1, fileQueue.length)} / {fileQueue.length} belge
        </span>
      )}
      <button
        type="button"
        onClick={handleSelectDirectory}
        title={outputDirHandle ? "Çıktı klasörünü değiştir" : "Çıktıların kaydedileceği klasörü seç"}
        className="inline-flex items-center gap-2 px-3 py-1.5 border border-[var(--border)] bg-[var(--bg)] rounded-[3px] text-[var(--fg-muted)] hover:border-[var(--brand)] hover:text-[var(--fg)] transition-colors"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${outputDirHandle ? "bg-[#2f8a5d]" : "bg-[var(--fg-subtle)]"}`} />
        <span className="text-[9px] tracking-[0.2em] uppercase text-[var(--fg-subtle)] font-semibold">Hedef</span>
        <span className="truncate max-w-[160px] normal-case text-[11px]">{outputDirHandle ? outputDirHandle.name : "Klasör seç"}</span>
      </button>
    </div>
  );

  return (
    <div className="min-h-screen">
      {/* Toplu yükleme ön hazırlık tezgâhı — 2+ dosya seçildiğinde tam sayfa açılır.
          Analiz paralel çalışır; "Onaya Geç" sonuçları varsayılan tek-tek akışa devreder. */}
      {showBatchPrep ? (
        <BulkUploadWorkbench
          files={pendingBatchFiles}
          onCancel={handleBatchPrepCancel}
          onStart={handleBatchPrepStart}
        />
      ) : (
      <main className="max-w-screen-2xl mx-auto">
        {/* Dosya seçiliyken şerit üstte kalır (analiz/onay ilerlemesini gösterir).
            Boş ekranda ise şerit + HEDEF rozeti drop zone kutusunun içine taşınır. */}
        {selectedFile && (
          <FlowStageStrip active={activeStage} meta={stageMetaNode} className="mb-7" />
        )}

        {!selectedFile && (
          <div className="grid gap-8">
            {/* 01 · Yükleme — tam genişlik hero drop zone */}
            <section>
              <SectionHeader
                eyebrow="01 · Yükleme"
                title="Belgeyi sürükleyin"
                italic="— ya da seçin"
                meta="PDF · DOCX · DOC · TXT · UDF · maks. 50 MB"
              />
              <div className="mt-3">
                <FlowDropZone
                  onFileSelect={handleFileSelect}
                  selectedFile={null}
                  onClearFile={handleClearFile}
                  todayCount={todayCount}
                  header={<FlowStageStrip active={activeStage} meta={stageMetaNode} />}
                />
              </div>
            </section>

            {/* 02 · Başka bir kaynak — 3 kaynak kartı */}
            <section>
              <SectionHeader
                eyebrow="02 · Başka bir kaynak"
                title="Doğrudan getirme yolları"
                meta="3 seçenek"
              />
              <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3.5">
                <button
                  type="button"
                  onClick={() => toast.info("UYAP entegrasyonu yakında aktif olacak.")}
                  className="group text-left p-5 bg-[var(--bg-elevated)] border border-[var(--border)] grid gap-3 transition-colors hover:border-[var(--brand)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="w-8 h-8 grid place-items-center text-[var(--brand)]">
                      <ExternalLink className="w-[18px] h-[18px]" strokeWidth={1.6} />
                    </span>
                    <span className="font-mono text-[9px] tracking-[0.18em] uppercase font-semibold px-1.5 py-1 border border-[#c47a1e]/40 text-[#c47a1e] rounded-[2px]">
                      Yakında
                    </span>
                  </div>
                  <div>
                    <div className="font-display font-medium text-[16px] tracking-[-0.01em] text-[var(--fg)]">UYAP'tan İndir</div>
                    <div className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed mt-1.5">
                      Esas no yazın; tebligat, karar ve tutanak ayrımı yapılarak indirilsin.
                    </div>
                  </div>
                  <div className="pt-2.5 border-t border-[var(--border)] font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--brand)] inline-flex items-center gap-1.5">
                    UYAP indirme <ChevronRight className="w-3 h-3" />
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => toast.info("E-posta (Outlook) entegrasyonu yakında aktif olacak.")}
                  className="group text-left p-5 bg-[var(--bg-elevated)] border border-[var(--border)] grid gap-3 transition-colors hover:border-[var(--brand)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="w-8 h-8 grid place-items-center text-[var(--brand)]">
                      <Mail className="w-[18px] h-[18px]" strokeWidth={1.6} />
                    </span>
                    <span className="font-mono text-[9px] tracking-[0.18em] uppercase font-semibold px-1.5 py-1 border border-[#c47a1e]/40 text-[#c47a1e] rounded-[2px]">
                      Yakında
                    </span>
                  </div>
                  <div>
                    <div className="font-display font-medium text-[16px] tracking-[-0.01em] text-[var(--fg)]">E-postadan Al</div>
                    <div className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed mt-1.5">
                      Outlook eklentisi ile gelen ekleri tek tıkla davaya bağlayın.
                    </div>
                  </div>
                  <div className="pt-2.5 border-t border-[var(--border)] font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--brand)] inline-flex items-center gap-1.5">
                    Outlook <ChevronRight className="w-3 h-3" />
                  </div>
                </button>

                <button
                  type="button"
                  onClick={openFilePicker}
                  className="group text-left p-5 bg-[var(--bg-elevated)] border border-[var(--border)] grid gap-3 transition-colors hover:border-[var(--brand)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="w-8 h-8 grid place-items-center text-[var(--brand)]">
                      <Layers className="w-[18px] h-[18px]" strokeWidth={1.6} />
                    </span>
                    <span className="font-mono text-[9px] tracking-[0.18em] uppercase font-semibold px-1.5 py-1 border border-[#2f8a5d]/40 text-[#2f8a5d] rounded-[2px]">
                      Aktif
                    </span>
                  </div>
                  <div>
                    <div className="font-display font-medium text-[16px] tracking-[-0.01em] text-[var(--fg)]">Toplu Yükleme</div>
                    <div className="text-[12.5px] text-[var(--fg-muted)] leading-relaxed mt-1.5">
                      Birden fazla belge seçin; sıraya alınır, arka planda işlenir.
                    </div>
                  </div>
                  <div className="pt-2.5 border-t border-[var(--border)] font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--brand)] inline-flex items-center gap-1.5">
                    Dosyaları seç <ChevronRight className="w-3 h-3" />
                  </div>
                </button>
              </div>
            </section>

            {/* 03 · Son Aktivite — bugün arşivlenen belgeler (localStorage, güne göre) */}
            <section>
              <SectionHeader
                eyebrow="03 · Son Aktivite"
                title="Bugünkü yüklemelerim"
                meta={
                  <button
                    type="button"
                    onClick={() => navigate("/activity-history")}
                    className="font-mono text-[10px] tracking-[0.16em] uppercase text-[var(--fg-subtle)] hover:text-[var(--brand)] inline-flex items-center gap-1"
                  >
                    Tümünü gör <ArrowRight className="w-3 h-3" />
                  </button>
                }
              />
              <TodayUploadsList items={todayItems} onShowAll={() => navigate("/activity-history")} />
            </section>
          </div>
        )}

        {selectedFile && (
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="space-y-6">
            <FlowDropZone
              onFileSelect={handleFileSelect}
              selectedFile={selectedFile}
              onClearFile={handleClearFile}
              isAnalyzing={isAnalyzing}
              isComplete={!!analysisData}
            />

            {/* Belge Türü Seçici — analiz başlamadan önce zorunlu */}
            {selectedFile && !analysisData && (
              <div className="bg-[var(--bg-elevated)] border border-[var(--border)] p-4 grid gap-2">
                <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                  <FileText className="w-3 h-3" />
                  Belge Türü Seçin
                  <span className="text-[var(--brand)] ml-0.5">*</span>
                </label>
                <Popover open={openDocTypeSelect} onOpenChange={setOpenDocTypeSelect}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className="w-full justify-between font-mono bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0"
                      disabled={isAnalyzing}
                    >
                      {selectedDocType
                        ? (doctypes.find(d => (d.code ?? "").replace(/_+$/, "") === selectedDocType)?.name ?? selectedDocType)
                        : "Belge türü seçin..."}
                      <ChevronsUpDown className="h-4 w-4 opacity-50 ml-2 shrink-0" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[340px] p-0 z-[100]" align="start">
                    <Command>
                      <CommandInput placeholder="Ara..." />
                      <CommandList>
                        <CommandEmpty>Sonuç bulunamadı.</CommandEmpty>
                        {doctypes.map((item) => {
                          const cleanCode = (item.code ?? "").replace(/_+$/, "");
                          return (
                            <CommandItem
                              key={item.code}
                              onSelect={() => {
                                setSelectedDocType(cleanCode);
                                setOpenDocTypeSelect(false);
                              }}
                            >
                              {item.name}
                            </CommandItem>
                          );
                        })}
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>
            )}

            {/* --- FAZ 1: DAVA BAĞLANTISI PANELİ --- */}
            <div className="bg-[var(--bg-elevated)] border border-[var(--border)] p-4 grid gap-3">
              <div className="flex items-center justify-between">
                <label className="inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase font-semibold text-[var(--fg-subtle)]">
                  <Link2 className="w-3 h-3" />
                  Dava Bağlantısı
                </label>
              </div>

              {isTestMode ? (
                <div className="flex items-center gap-2 p-3 rounded-[3px] bg-[#c47a1e]/10 border border-[#c47a1e]/30 text-xs text-[#c47a1e]">
                  <TestTube2 className="w-4 h-4 shrink-0" />
                  <span>Test modunda belge yüklenecek — dava seçimi atlanıyor. Belge <strong>TEST</strong> olarak kaydedilir.</span>
                </div>
              ) : linkedCase ? (
                <>
                <div className="flex items-start gap-3 p-3 rounded-[3px] bg-[#2f8a5d]/10 border border-[#2f8a5d]/30">
                  <CheckCircle2 className="w-5 h-5 text-[#2f8a5d] shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-[#2f8a5d] truncate max-w-[200px]" title={linkedCase.esas_no || linkedCase.tracking_no}>
                        {linkedCase.esas_no || linkedCase.tracking_no}
                      </p>
                      {/* AI eşleşme göstergesi */}
                      {analysisData?.suggested_case?.case_id === linkedCase.id && (
                        <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${analysisData.suggested_case.confidence === "HIGH"
                          ? "bg-[#2f8a5d]/20 text-[#2f8a5d]"
                          : "bg-[#c47a1e]/20 text-[#c47a1e]"
                          }`}>
                          🎯 AI {analysisData.suggested_case.confidence === "HIGH" ? "Eşleşti" : "Önerdi"} · {analysisData.suggested_case.score}p
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--fg-muted)] truncate mt-0.5">{linkedCase.court || "Mahkeme belirtilmedi"}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="outline" className="text-xs">{linkedCase.status}</Badge>
                      {analysisData?.suggested_case?.case_id === linkedCase.id && analysisData.suggested_case.match_reasons.length > 0 && (
                        <span className="text-[10px] text-[var(--fg-muted)] truncate">
                          {analysisData.suggested_case.match_reasons[0]}
                        </span>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={() => { setLinkedCase(null); setCaseSearch(""); setSelectedPartyId(null); }} className="text-[var(--fg-muted)] hover:text-[#a8323b] transition-colors" title="Davayı değiştir">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Müvekkil seçici — sadece CLIENT tipindeki taraflar gösterilir */}
                {(() => {
                  const clientParties = ((linkedCase as IndexCaseData & { parties?: { id?: number; name?: string; party_type?: string }[] })?.parties || []).filter(p => p.party_type === "CLIENT" && p.id != null);
                  if (clientParties.length === 0) return null;
                  return (
                    <div className="mt-2 space-y-1">
                      <label className="flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--fg-subtle)]">
                        <Users className="w-3 h-3" /> Belge Kime Ait?
                      </label>
                      <Select
                        value={selectedPartyId != null ? String(selectedPartyId) : "all"}
                        onValueChange={(v) => setSelectedPartyId(v === "all" ? null : Number(v))}
                      >
                        <SelectTrigger className="h-8 text-xs bg-[var(--bg)] border-[var(--border)] rounded-[3px] border-0">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Tüm Dava</SelectItem>
                          {clientParties.map(p => (
                            <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  );
                })()}
                </>
              ) : (
                <div className="space-y-2">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--fg-muted)]" />
                    <Input placeholder="Esas no veya mahkeme ile ara..." className="pl-9 h-9 text-sm bg-[var(--bg)] border-[var(--border)] rounded-[3px]" value={caseSearch} onChange={e => setCaseSearch(e.target.value)} />
                  </div>
                  {caseSearch.trim() && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {!casesLoaded ? (
                        <p className="text-xs text-[var(--fg-muted)] text-center py-2 animate-pulse">Yükleniyor...</p>
                      ) : filteredCases.length === 0 ? (
                        <p className="text-xs text-[var(--fg-muted)] text-center py-2">Sonuç bulunamadı.</p>
                      ) : filteredCases.map(c => (
                        <button key={c.id} type="button" onClick={() => { setLinkedCase(c); setCaseSearch(""); }}
                          className="w-full text-left p-2.5 rounded-[3px] border border-[var(--border)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)] transition-all duration-150">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium truncate">{c.esas_no || c.tracking_no}</span>
                            <Badge variant="outline" className="text-xs shrink-0">{c.status}</Badge>
                          </div>
                          <p className="text-xs text-[var(--fg-muted)] truncate mt-0.5">{c.court || "Mahkeme yok"}</p>
                        </button>
                      ))}
                    </div>
                  )}
                  {!caseSearch.trim() && (
                    <div className="space-y-3">
                      {/* AI önerileri: puana göre sıralı liste. Otomatik seçim YOK — kullanıcı tıklayarak bağlar. */}
                      {analysisData?.suggested_case && (() => {
                        const sc = analysisData.suggested_case!;
                        // En iyi eşleşme + diğer adaylar tek listede (backend zaten puana göre azalan döndürür).
                        const ranked = [sc, ...(sc.all_candidates || [])];
                        const docNames = Array.from(new Set([
                          analysisData.muvekkil_adi,
                          ...(analysisData.muvekkiller || []),
                          ...(analysisData.belgede_gecen_isimler || []),
                        ].filter(Boolean)));
                        return (
                          <div className="p-3 rounded-[3px] border border-[var(--brand)]/40 bg-[var(--brand-soft)] space-y-3">
                            <div className="flex items-center gap-2">
                              <Wand2 className="w-5 h-5 text-[var(--brand)]" />
                              <p className="text-sm font-semibold text-[var(--brand)]">Yapay Zeka — Olası Davalar</p>
                              <Badge variant="secondary" className="ml-auto text-[10px]">puana göre</Badge>
                            </div>

                            {/* İSİM EŞLEŞME GÖRSELLEŞTİRMESİ — belgedeki isimlerin eşleşme durumu */}
                            {docNames.length > 0 && (
                              <div className="bg-[var(--bg-sunken)] rounded-[3px] p-2.5 border border-[var(--brand)]/20 space-y-2">
                                <label className="font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-[var(--brand)]/70 block">
                                  BELGEDEKİ İSİMLER VE EŞLEŞME DURUMU
                                </label>
                                <div className="flex flex-wrap gap-1.5">
                                  {docNames.map((name, idx) => {
                                    const isMatched = sc.matched_doc_names?.includes(name as string);
                                    return (
                                      <Badge
                                        key={idx}
                                        variant={isMatched ? "default" : "outline"}
                                        className={`text-[10px] py-0.5 px-2 gap-1 transition-all duration-300 ${isMatched ? 'bg-[#2f8a5d]/20 text-[#2f8a5d] border-[#2f8a5d]/30' : 'opacity-50'}`}
                                      >
                                        {isMatched ? <CheckCircle2 className="w-3 h-3" /> : null}
                                        {name}
                                      </Badge>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Puana göre sıralı aday listesi — tıklayınca bağlanır, otomatik seçim yok */}
                            <div className="space-y-1.5">
                              {ranked.map((cand, i) => (
                                <button
                                  key={cand.case_id}
                                  type="button"
                                  onClick={() => {
                                    selectSuggestedCase(cand);
                                    toast.success(`✅ Dava bağlandı: ${cand.esas_no || cand.tracking_no}`);
                                  }}
                                  className="w-full text-left p-2.5 rounded-[3px] border border-[var(--border)] bg-[var(--bg)] hover:border-[var(--brand)] hover:bg-[var(--brand-soft)] transition-all duration-150"
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <span className="text-sm font-medium truncate">{cand.esas_no || cand.tracking_no}</span>
                                    <div className="flex items-center gap-1.5 shrink-0">
                                      {i === 0 && (
                                        <Badge className="text-[9px] px-1.5 border-0 bg-[var(--brand)]/15 text-[var(--brand)]">En yüksek</Badge>
                                      )}
                                      <Badge variant="outline" className="text-[10px] tabular-nums">{cand.score}p</Badge>
                                    </div>
                                  </div>
                                  <p className="text-xs text-[var(--fg-muted)] truncate mt-0.5">{cand.court || "Mahkeme yok"}</p>
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })()}

                      <p className="text-xs text-[var(--fg-muted)] flex items-center gap-1.5 px-1 mt-2">
                        <FolderOpen className="w-4 h-4 opacity-70" />
                        Farklı bir davaya bağlamak için yukarıdan arama yapın.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
            {/* --- END DAVA BAĞLANTISI --- */}

            {selectedFile && (
              <>
                <QueueStatus totalFiles={fileQueue.length} currentIndex={currentFileIndex} processedCount={processedCount} onRemoveFile={handleRemoveFromQueue} />

                <Button data-analyze-btn onClick={handleAnalyze} disabled={isAnalyzing || isProcessing || (!analysisData && !selectedDocType)}
                  className="w-full h-14 text-lg font-semibold rounded-[3px] bg-[var(--brand)] hover:bg-[var(--brand-hover)] text-[var(--brand-fg)] transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed" size="lg">
                  {isAnalyzing ? (<><Loader2 className="w-5 h-5 mr-2 animate-spin" />Analiz Ediliyor...</>) : (<><Wand2 className="w-5 h-5 mr-2" />Analizi Başlat</>)}
                </Button>
                {analysisData?.ozet && (
                  <div className="bg-[var(--bg-elevated)] border border-[var(--border)] rounded-none p-6">
                    <label className="text-sm font-semibold flex items-center gap-2 mb-3 text-[var(--fg)]">
                      <AlertCircle className="w-4 h-4 text-[var(--brand)]" />
                      Belge Özeti
                    </label>
                    <p className="text-sm text-[var(--fg-muted)] leading-relaxed italic">"{analysisData.ozet}"</p>
                  </div>
                )}
              </>
            )}
          </div>
          <div className="flex flex-col gap-4 sticky top-8 self-start">
            {analysisData ? (
              <>
                <AnalysisResults data={analysisData} onValidationChange={handleValidationChange} linkedCase={linkedCase} />
                <Button
                  onClick={() => {
                    if (!linkedCase && !isTestMode) {
                      setIsQuickCaseModalOpen(true);
                    } else {
                      handleConfirmClick();
                    }
                  }}
                  disabled={isProcessing || !isValidated || !outputDirHandle}
                  className={`w-full h-16 text-xl font-bold rounded-[3px] transition-all duration-200 ${(isValidated && outputDirHandle)
                    ? "bg-[#2f8a5d] hover:bg-[#2f8a5d]/90 text-white"
                    : "bg-[var(--bg-sunken)] text-[var(--fg-subtle)] cursor-not-allowed opacity-70"
                    }`}
                >
                  {isProcessing ? (
                    <><Loader2 className="w-6 h-6 mr-2 animate-spin" />İşleniyor (SharePoint & Kayıt)...</>
                  ) : (
                    !outputDirHandle
                      ? "⚠️ Çıktı Klasörü Seçiniz (Masaüstü)"
                      : (isValidated ? "✅ Onayla ve İşlemi Tamamla" : "⚠️ Lütfen Tüm Alanları Onaylayın")
                  )}
                </Button>
              </>
            ) : (
              <AnalysisPending isAnalyzing={isAnalyzing} />
            )}
          </div>
        </div>
        )}
      </main>
      )}

      {/* Email Modal */}
      <EmailModal
        isOpen={isEmailModalOpen}
        onClose={() => setIsEmailModalOpen(false)}
        onConfirm={(to, cc, shouldSend, tebligTarihi, perRecipientMessages, extraAttachments, sendClientNotice, clientNoticeMessage) => {
          handleFinalProcess(to, cc, shouldSend, tebligTarihi, perRecipientMessages, extraAttachments, sendClientNotice, clientNoticeMessage);
        }}
        clientNoticeLawyer={clientNoticeLawyer}
        clientNoticeClientName={clientNoticeClientName}
        clientNotifyEligible={clientNotifyEligible}
        clientWarning={clientWarning}
        isLoading={emailModalLoading}
        // Faz 6: confirmPerFile açıkken hazırlık ekranındaki ayarlar prefill olur.
        defaultTo={batchPrep?.emailPrefill.to ?? []}
        defaultCc={batchPrep?.emailPrefill.cc ?? []}
        defaultSendEmail={batchPrep?.emailFlags[currentFileIndex] ?? batchPrep?.emailPrefill.sendEmail}
        defaultTebligTarihi={batchPrep?.emailPrefill.tebligTarihi}
        batchCount={fileQueue.length > 1 ? processedBatch.length + 1 : 0}
        totalFiles={fileQueue.length}
        analysisContext={{
          muvekkil_adi: (finalData || analysisData)?.muvekkil_kodu || (finalData || analysisData)?.muvekkil_adi,
          muvekkiller: (finalData || analysisData)?.muvekkiller,
          belge_turu_kodu: (finalData || analysisData)?.belge_turu_kodu,
          tarih: (finalData || analysisData)?.tarih,
          ozet: (finalData || analysisData)?.ozet,
          karsi_taraf: (finalData || analysisData)?.karsi_taraf,
          sonraki_durusma_tarihi: (finalData || analysisData)?.sonraki_durusma_tarihi,
          sonraki_durusma_saati: (finalData || analysisData)?.sonraki_durusma_saati,
        }}
      />

      {/* Hızlı Dava Oluştur Modal — dava bulunmadığında açılır */}
      <QuickCaseModal
        open={isQuickCaseModalOpen}
        onClose={() => setIsQuickCaseModalOpen(false)}
        prefill={{
          // Öncelik: kullanıcı formu → eşleşen DB davası → AI önerisi
          esas_no: finalData?.esas_no || analysisData?.esas_no,
          muvekkiller: finalData?.muvekkiller?.length ? finalData.muvekkiller : analysisData?.muvekkiller,
          muvekkil_adi: finalData?.muvekkil_kodu || finalData?.muvekkil_adi || analysisData?.muvekkil_adi,
          karsi_taraf:
            finalData?.karsi_taraf ||           // 1. Kullanıcının formda yazdığı
            (linkedCase as { karsi_taraf?: string })?.karsi_taraf ||  // 2. Eşleşen DB kaydından (case_matcher)
            analysisData?.suggested_karsi_taraf, // 3. AI önerisi (fallback)
          court: finalData?.court || analysisData?.court,
          tarih: finalData?.tarih || analysisData?.tarih,
        }}
        onCaseCreated={async (newCase) => {
          setLinkedCase(newCase);
          setIsQuickCaseModalOpen(false);
          setAllCases(prev => [newCase, ...prev]);

          // Dava açıldıktan hemen sonra belgeyi otomatik kaydet (e-posta modalsiz)
          // overrideLinkedCase ile state güncellenmesini beklemeden yeni davayı geç
          const dataToProcess = finalData || analysisData;
          if (dataToProcess && selectedFile) {
            toast.info("📎 Dava açıldı — belge SharePoint'e otomatik kaydediliyor...", { duration: 4000 });
            await handleFinalProcess([], [], false, undefined, undefined, undefined, undefined, undefined, newCase);
          }
        }}
      />
    </div>
  );
};

export default Index;
