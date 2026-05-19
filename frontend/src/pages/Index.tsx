import { useState, useEffect, useCallback, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { FileUpload } from "@/components/FileUpload";
import { AnalysisResults } from "@/components/AnalysisResults";
import { AnalysisPending } from "@/components/AnalysisPending";
import { QueueStatus } from "@/components/QueueStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Wand2, Loader2, AlertCircle, Link2, Search, X, TestTube2, CheckCircle2, FolderOpen, Gavel, Users, ChevronsUpDown, FileText } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { useCases } from "@/hooks/useCases";
import { useConfig } from "@/hooks/useConfig";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { QuickCaseModal } from "@/components/QuickCaseModal";
import { getStoredOutputDir, setStoredOutputDir } from "@/lib/directoryStorage";

import { EmailModal } from "@/components/email/EmailModal";
import { BatchPrepScreen, type BatchPrepConfig } from "@/components/BatchPrepScreen";

interface SuggestedCase {
  case_id: number;
  tracking_no: string;
  esas_no: string;
  court: string;
  responsible_lawyer_name: string;
  status: string;
  score: number;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  match_reasons: string[];
  all_candidates: SuggestedCase[];
  karsi_taraf?: string;
  counter_parties?: string[];
  client_parties?: string[];
  parties?: { id?: number; name?: string; role?: string; party_type?: string; client_id?: number; birth_year?: number; gender?: string }[];
  matched_doc_names?: string[];
}

interface AnalysisData {
  tarih: string;
  belge_turu_kodu: string;
  muvekkil_kodu: string;
  muvekkil_adi?: string;
  muvekkiller?: string[];
  karsi_taraf?: string;
  suggested_karsi_taraf?: string;       // AI'ın bulduğu karşı taraf (QuickCaseModal için)
  belgede_gecen_isimler: string[];
  esas_no: string;
  durum: string;
  ofis_dosya_no: string;
  yedek1: string;
  yedek2: string;
  ozet: string;
  generated_filename: string;
  hash: string;
  court?: string;                          // Mahkeme adı (QuickCaseModal için)
  suggested_case?: SuggestedCase | null;
  sonraki_durusma_tarihi?: string;
  sonraki_durusma_saati?: string;
}

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
  const { getCases, searchCases } = useCases();
  const { doctypes } = useConfig();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState<string>("");
  const [openDocTypeSelect, setOpenDocTypeSelect] = useState(false);
  const [outputDirHandle, setOutputDirHandle] = useState<FileSystemDirectoryHandle | null>(null);

  // Email Modal States
  const [isEmailModalOpen, setIsEmailModalOpen] = useState(false);
  const [emailModalLoading, setEmailModalLoading] = useState(false);

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

  // Faz 3.1: Batch e-posta ayarları paylaşımı. Toggle açıkken sıradaki dosyalarda
  // EmailModal açılmaz; bu config doğrudan handleFinalProcess'e geçilir.
  const [batchEmailConfig, setBatchEmailConfig] = useState<{
    to: string[];
    cc: string[];
    shouldSend: boolean;
    tebligTarihi?: string;
    extraAttachments?: File[];
  } | null>(null);

  // Faz 6: Toplu yükleme hazırlık ekranı state'i. fileQueue.length > 1 olduğunda
  // dosyalar kuyruğa alınmadan önce burada belge türleri ve e-posta ayarları toplanır.
  const [showBatchPrep, setShowBatchPrep] = useState(false);
  const [pendingBatchFiles, setPendingBatchFiles] = useState<File[]>([]);
  const [batchPrep, setBatchPrep] = useState<{
    docTypes: string[];
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
      const data = await searchCases(caseSearch, false, true);
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

  // Faz 6: Hazırlık ekranı onaylandığında: kuyruğu kur, batchPrep'i kaydet,
  // confirmPerFile kapalıysa batchEmailConfig'i şimdiden doldur (modal atlanır).
  const handleBatchPrepStart = (config: BatchPrepConfig) => {
    const files = pendingBatchFiles;
    setShowBatchPrep(false);
    setPendingBatchFiles([]);

    setBatchPrep({
      docTypes: config.docTypes,
      emailPrefill: {
        sendEmail: config.emailConfig.sendEmail,
        to: config.emailConfig.to,
        cc: config.emailConfig.cc,
        tebligTarihi: config.emailConfig.tebligTarihi,
        confirmPerFile: config.emailConfig.confirmPerFile,
      },
    });

    // confirmPerFile kapalı → EmailModal hiç açılmasın; batchEmailConfig şimdiden hazır.
    // sendEmail kapalı da aynı yola gider (modal atlanır, e-posta gönderilmez).
    if (!config.emailConfig.confirmPerFile) {
      const toList = config.emailConfig.to.map((r) => `${r.name} <${r.email}>`);
      const ccList = config.emailConfig.cc.map((r) => `${r.name} <${r.email}>`);
      setBatchEmailConfig({
        to: toList,
        cc: ccList,
        shouldSend: config.emailConfig.sendEmail,
        tebligTarihi: config.emailConfig.tebligTarihi || undefined,
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
    setSelectedDocType(config.docTypes[0] || "");
    setAnalysisData(null);
    setPreloadBuffer([]);

    toast.info(`${files.length} dosya kuyruğa alındı. Pipeline başlatılıyor...`);
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

  const handleAnalyze = async () => {
    // Web mode: File object is used directly, no file path needed
    if (!selectedFile) {
      toast.error("Lütfen önce bir dosya yükleyin");
      return;
    }

    setIsAnalyzing(true);

    // --- VIRTUAL BLANK PDF (Boş Belge) ---
    // Web modunda bu özellik şimdilik devre dışı
    // TODO: Gerekirse web için yeniden tasarlanabilir

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 300000); // 300 saniye (5dk) zaman aşımı

    try {
      // Web Mode: FormData ile dosya gönder
      const formData = new FormData();
      formData.append("file", selectedFile);
      // Faz 6: hazırlık ekranından gelen belge türü öncelikli; yoksa kullanıcının
      // mevcut akıştaki seçimini kullan.
      const effectiveDocType = batchPrep?.docTypes[currentFileIndex] ?? selectedDocType;
      if (effectiveDocType) formData.append("belge_turu_kodu", effectiveDocType);

      const response = await apiClient.fetch("/process", {
        method: "POST",
        body: formData,  // Content-Type otomatik ayarlanır (multipart/form-data)
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error("Sunucu hatası: " + response.statusText);
      }

      if (!response.body) throw new Error("ReadableStream not supported");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();

        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // Keep incomplete line in buffer

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const msg = JSON.parse(line);

              if (msg.status === "info") {
                toast.info(msg.message);
              } else if (msg.status === "error") {
                throw new Error(msg.message);
              } else if (msg.status === "complete") {
                const resultData = msg.data;
                if (msg.process_id) setProcessId(msg.process_id);
                console.log("Stream Complete Data:", resultData);

                const analysisResult: AnalysisData = {
                  tarih: resultData.tarih || "",
                  belge_turu_kodu: effectiveDocType || resultData.belge_turu_kodu || "",
                  muvekkil_kodu: resultData.muvekkil_adi || "",
                  muvekkil_adi: resultData.muvekkil_adi || "",          // QuickCaseModal için
                  muvekkiller: resultData.muvekkiller || [],
                  karsi_taraf: resultData.karsi_taraf || "",
                  suggested_karsi_taraf: resultData.suggested_karsi_taraf || "",
                  belgede_gecen_isimler: resultData.belgede_gecen_isimler || [],
                  esas_no: resultData.esas_no || "",
                  durum: resultData.durum || "G",
                  ofis_dosya_no: resultData.ofis_dosya_no || "000000000",
                  yedek1: "X",
                  yedek2: "XX",
                  ozet: resultData.ozet || "",
                  generated_filename: "",
                  hash: resultData.hash || "",
                  court: resultData.court || undefined,
                  suggested_case: resultData.suggested_case || null,
                  sonraki_durusma_tarihi: resultData.sonraki_durusma_tarihi || undefined,
                  sonraki_durusma_saati: resultData.sonraki_durusma_saati || undefined,
                };
                setAnalysisData(analysisResult);

                applyAutoSuggestionFlow(resultData.suggested_case, linkedCase);

                toast.success("Analiz tamamlandı!");
              }
            } catch (e) {
              console.error("JSON Parse Error on Stream chunk", e);
            }
          }
        }

        if (done) break;
      }
    } catch (error) {
      console.error("Local Analysis error:", error);
      if (error instanceof Error && error.name === 'AbortError') {
        toast.error("İstek zaman aşımına uğradı. Sunucu yanıt vermiyor (30sn).");
      } else {
        toast.error(error instanceof Error ? error.message : "Analiz sırasında hata oluştu");
      }
    } finally {
      clearTimeout(timeoutId);
      setIsAnalyzing(false);
      // Faz 5: Pre-load tetiklemesini effect üstlendi. Burada explicit çağrı yok —
      // fileQueue/currentFileIndex/preloadBuffer.length değiştikçe useEffect MAX_PRELOAD_DEPTH
      // sınırına kadar sırayla doldurur.
    }
  };

  // Faz 5: Pre-load. Tek seferde 1 dosya işler (sıralı). Tamamlandığında dosya hâlâ
  // kuyruktaysa buffer'a push eder; bu da fill effect'i tetikleyerek sıradakini başlatır.
  const preloadNextFile = async (nextFile: File, docTypeCode?: string) => {
    if (preloadInProgressRef.current) return;
    preloadInProgressRef.current = true;
    // Faz 3.3: Preload toast'ları batch'te susturulur; özet sonda gösterilir.

    let preloadedData: AnalysisData | null = null;
    let preloadedProcessId: string | null = null;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000);

      // Web Mode: FormData ile dosya gönder
      const formData = new FormData();
      formData.append("file", nextFile);
      // Faz 6: Hazırlık ekranından gelen belge türü pre-load anında da gönderilir
      // — backend AI'a özel prompt'u kullanma şansı verilir (Bug #3 çözümü).
      if (docTypeCode) formData.append("belge_turu_kodu", docTypeCode);

      const response = await apiClient.fetch("/process", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error("Preload failed: " + response.statusText);
      }

      if (!response.body) throw new Error("ReadableStream not supported");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();

        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const msg = JSON.parse(line);

              if (msg.status === "error") {
                console.error("Preload error:", msg.message);
              } else if (msg.status === "complete") {
                const resultData = msg.data;
                if (msg.process_id) preloadedProcessId = msg.process_id;

                // handleAnalyze ile birebir aynı alan kümesi. Faz 6: hazırlık
                // ekranından gelen docTypeCode varsa onu kullan; yoksa AI'ın bulduğu
                // değere düş (kullanıcı dosyaya geçince yine düzeltebilir).
                preloadedData = {
                  tarih: resultData.tarih || "",
                  belge_turu_kodu: docTypeCode || resultData.belge_turu_kodu || "",
                  muvekkil_kodu: resultData.muvekkil_adi || "",
                  muvekkil_adi: resultData.muvekkil_adi || "",
                  muvekkiller: resultData.muvekkiller || [],
                  karsi_taraf: resultData.karsi_taraf || "",
                  suggested_karsi_taraf: resultData.suggested_karsi_taraf || "",
                  belgede_gecen_isimler: resultData.belgede_gecen_isimler || [],
                  esas_no: resultData.esas_no || "",
                  durum: resultData.durum || "G",
                  ofis_dosya_no: resultData.ofis_dosya_no || "000000000",
                  yedek1: "X",
                  yedek2: "XX",
                  ozet: resultData.ozet || "",
                  generated_filename: "",
                  hash: resultData.hash || "",
                  court: resultData.court || undefined,
                  suggested_case: resultData.suggested_case || null,
                  sonraki_durusma_tarihi: resultData.sonraki_durusma_tarihi || undefined,
                  sonraki_durusma_saati: resultData.sonraki_durusma_saati || undefined,
                };
              }
            } catch (e) {
              console.error("Preload JSON parse error:", e);
            }
          }
        }

        if (done) break;
      }
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




  // Step 1: User clicks "Confirm"
  const handleConfirmClick = () => {
    if (!finalData && !analysisData) return;

    // Faz 3.1: Batch modda config varsa modal atlanır; yoksa açılır.
    // Ekler kullanıcının seçtiği şekilde tekrar gönderilir (paylaşım kararı).
    // Per-recipient mesajlar dosyaya özgü kalır — backend default şablon kullanır.
    if (batchEmailConfig) {
      handleFinalProcess(
        batchEmailConfig.to,
        batchEmailConfig.cc,
        batchEmailConfig.shouldSend,
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
  const handleFinalProcess = async (toEmails: string[], ccEmails: string[], shouldSendEmail: boolean, tebligTarihi?: string, perRecipientMessages?: Record<string, string>, extraAttachments?: File[], overrideLinkedCase?: IndexCaseData) => {
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


  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container max-w-screen-2xl mx-auto px-6 py-8">
        <div className="flex justify-end mb-4">
          <Button
            variant={outputDirHandle ? "outline" : "secondary"}
            onClick={handleSelectDirectory}
            className="gap-2"
            title={outputDirHandle ? "Klasör Seçili (Değiştirmek için tıkla)" : "Çıktıların otomatik kaydedileceği klasörü seç"}
          >
            {outputDirHandle ? `📂 Klasör: ${outputDirHandle.name}` : "📂 Çıktı Klasörü Seç (Masaüstü)"}
            {outputDirHandle && <span className="text-green-500">●</span>}
          </Button>
        </div>
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="space-y-6">
            <FileUpload
              onFileSelect={handleFileSelect}
              selectedFile={selectedFile}
              onClearFile={handleClearFile}
              isAnalyzing={isAnalyzing}
              isComplete={!!analysisData}
            />

            {/* Belge Türü Seçici — analiz başlamadan önce zorunlu */}
            {selectedFile && !analysisData && (
              <div className="rounded-xl border border-border/60 bg-card/70 p-4 space-y-2">
                <label className="text-sm font-semibold flex items-center gap-2">
                  <FileText className="w-4 h-4 text-primary" />
                  Belge Türü Seçin
                  <span className="text-destructive text-xs">*</span>
                </label>
                <Popover open={openDocTypeSelect} onOpenChange={setOpenDocTypeSelect}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className="w-full justify-between font-mono glass-input border-0"
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
            <div className="rounded-xl border border-border/60 bg-card/70 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold flex items-center gap-2">
                  <Link2 className="w-4 h-4 text-primary" />
                  Dava Bağlantısı
                </label>
              </div>

              {isTestMode ? (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-400">
                  <TestTube2 className="w-4 h-4 shrink-0" />
                  <span>Test modunda belge yüklenecek — dava seçimi atlanıyor. Belge <strong>TEST</strong> olarak kaydedilir.</span>
                </div>
              ) : linkedCase ? (
                <>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-semibold text-emerald-400 truncate max-w-[200px]" title={linkedCase.esas_no || linkedCase.tracking_no}>
                        {linkedCase.esas_no || linkedCase.tracking_no}
                      </p>
                      {/* AI eşleşme göstergesi */}
                      {analysisData?.suggested_case?.case_id === linkedCase.id && (
                        <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${analysisData.suggested_case.confidence === "HIGH"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : "bg-blue-500/20 text-blue-300"
                          }`}>
                          🎯 AI {analysisData.suggested_case.confidence === "HIGH" ? "Eşleşti" : "Önerdi"} · {analysisData.suggested_case.score}p
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{linkedCase.court || "Mahkeme belirtilmedi"}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <Badge variant="outline" className="text-xs">{linkedCase.status}</Badge>
                      {analysisData?.suggested_case?.case_id === linkedCase.id && analysisData.suggested_case.match_reasons.length > 0 && (
                        <span className="text-[10px] text-muted-foreground truncate">
                          {analysisData.suggested_case.match_reasons[0]}
                        </span>
                      )}
                    </div>
                  </div>
                  <button type="button" onClick={() => { setLinkedCase(null); setCaseSearch(""); setSelectedPartyId(null); }} className="text-muted-foreground hover:text-destructive transition-colors" title="Davayı değiştir">
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Müvekkil seçici — sadece CLIENT tipindeki taraflar gösterilir */}
                {(() => {
                  const clientParties = ((linkedCase as IndexCaseData & { parties?: { id?: number; name?: string; party_type?: string }[] })?.parties || []).filter(p => p.party_type === "CLIENT" && p.id != null);
                  if (clientParties.length === 0) return null;
                  return (
                    <div className="mt-2 space-y-1">
                      <label className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                        <Users className="w-3 h-3" /> Belge Kime Ait?
                      </label>
                      <Select
                        value={selectedPartyId != null ? String(selectedPartyId) : "all"}
                        onValueChange={(v) => setSelectedPartyId(v === "all" ? null : Number(v))}
                      >
                        <SelectTrigger className="h-8 text-xs glass-input border-0">
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
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                    <Input placeholder="Esas no veya mahkeme ile ara..." className="pl-9 h-9 text-sm glass-input" value={caseSearch} onChange={e => setCaseSearch(e.target.value)} />
                  </div>
                  {caseSearch.trim() && (
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {!casesLoaded ? (
                        <p className="text-xs text-muted-foreground text-center py-2 animate-pulse">Yükleniyor...</p>
                      ) : filteredCases.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-2">Sonuç bulunamadı.</p>
                      ) : filteredCases.map(c => (
                        <button key={c.id} type="button" onClick={() => { setLinkedCase(c); setCaseSearch(""); }}
                          className="w-full text-left p-2.5 rounded-lg border border-border/50 hover:border-primary/50 hover:bg-primary/5 transition-all duration-150">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium truncate">{c.esas_no || c.tracking_no}</span>
                            <Badge variant="outline" className="text-xs shrink-0">{c.status}</Badge>
                          </div>
                          <p className="text-xs text-muted-foreground truncate mt-0.5">{c.court || "Mahkeme yok"}</p>
                        </button>
                      ))}
                    </div>
                  )}
                  {!caseSearch.trim() && (
                    <div className="space-y-3">
                      {/* EĞER BİR ÖNERİ VARSA VE HENÜZ SEÇİLMEDİYSE KULLANICIYA KUTU İÇİNDE SOR */}
                      {analysisData?.suggested_case && (
                        <div className="p-3 rounded-xl border border-primary/40 bg-primary/10 space-y-3 shadow-sm">
                          <div className="flex items-center gap-2">
                            <Wand2 className="w-5 h-5 text-primary" />
                            <p className="text-sm font-semibold text-primary">Yapay Zeka Tespiti</p>
                            <Badge variant={analysisData.suggested_case.confidence === "HIGH" ? "default" : "secondary"} className="ml-auto text-[10px]">
                              Skor: {analysisData.suggested_case.score}
                            </Badge>
                          </div>

                          {/* İSİM EŞLEŞME GÖRSELLEŞTİRMESİ */}
                          <div className="bg-background/40 rounded-lg p-2.5 border border-primary/20 space-y-2">
                            <label className="text-[9px] font-bold uppercase tracking-wider text-primary/70 block">
                              BELGEDEKİ İSİMLER VE EŞLEŞME DURUMU
                            </label>
                            <div className="flex flex-wrap gap-1.5">
                              {Array.from(new Set([
                                analysisData.muvekkil_adi,
                                ...(analysisData.muvekkiller || []),
                                ...(analysisData.belgede_gecen_isimler || [])
                              ].filter(Boolean))).map((name, idx) => {
                                const isMatched = analysisData.suggested_case?.matched_doc_names?.includes(name);
                                return (
                                  <Badge
                                    key={idx}
                                    variant={isMatched ? "default" : "outline"}
                                    className={`text-[10px] py-0.5 px-2 gap-1 transition-all duration-300 ${isMatched ? 'bg-emerald-500/20 text-emerald-600 border-emerald-500/30' : 'opacity-50'}`}
                                  >
                                    {isMatched ? <CheckCircle2 className="w-3 h-3" /> : null}
                                    {name}
                                  </Badge>
                                );
                              })}
                            </div>
                          </div>

                          <p className="text-xs text-muted-foreground leading-relaxed">
                            Bu belgenin <strong>{analysisData.suggested_case.esas_no}</strong> numaralı dava dosyasına ait olduğu tespit edildi. Doğruluyor musunuz?
                          </p>
                          <Button
                            onClick={() => {
                              // Tüm db verisini çekmek için allCases içinden bulalım.
                              const fullCase = allCases.find((c) => c.id === analysisData.suggested_case?.case_id);
                              if (fullCase) {
                                setLinkedCase(fullCase);
                              } else {
                                // Fallback (eğer allCases henüz dolmadıysa)
                                setLinkedCase({
                                  id: analysisData.suggested_case.case_id,
                                  tracking_no: analysisData.suggested_case.tracking_no,
                                  esas_no: analysisData.suggested_case.esas_no,
                                  court: analysisData.suggested_case.court,
                                  responsible_lawyer_name: analysisData.suggested_case.responsible_lawyer_name,
                                  status: analysisData.suggested_case.status,
                                  karsi_taraf: analysisData.suggested_case.karsi_taraf || "",
                                  parties: analysisData.suggested_case.parties || []
                                });
                              }
                              toast.success("✅ Dava onaylandı ve bağlandı.");
                            }}
                            className="w-full h-10 gap-2 bg-primary/90 hover:bg-primary shadow-sm"
                          >
                            <CheckCircle2 className="w-4 h-4" /> Evet, Bu Davaya Bağla
                          </Button>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground flex items-center gap-1.5 px-1 mt-2">
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
                  className="w-full h-14 text-lg font-semibold bg-[hsl(345,80%,40%)] hover:bg-[hsl(345,80%,35%)] shadow-lg transition-all duration-300 hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed" size="lg">
                  {isAnalyzing ? (<><Loader2 className="w-5 h-5 mr-2 animate-spin" />Analiz Ediliyor...</>) : (<><Wand2 className="w-5 h-5 mr-2" />Analizi Başlat</>)}
                </Button>
                {analysisData?.ozet && (
                  <div className="glass-card rounded-xl p-6">
                    <label className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <AlertCircle className="w-4 h-4 text-primary" />
                      Belge Özeti
                    </label>
                    <p className="text-sm text-muted-foreground leading-relaxed italic">"{analysisData.ozet}"</p>
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
                  className={`w-full h-16 text-xl font-bold shadow-lg transition-all duration-300 hover:scale-[1.02] ${(isValidated && outputDirHandle)
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-gray-400 cursor-not-allowed opacity-50"
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
      </main>

      {/* Faz 6: Toplu Yükleme Hazırlık Ekranı — fileQueue.length > 1 olduğunda
          analiz başlamadan önce belge türü ve e-posta ayarları burada toplanır. */}
      <BatchPrepScreen
        isOpen={showBatchPrep}
        files={pendingBatchFiles}
        onCancel={handleBatchPrepCancel}
        onStart={handleBatchPrepStart}
      />

      {/* Email Modal */}
      <EmailModal
        isOpen={isEmailModalOpen}
        onClose={() => setIsEmailModalOpen(false)}
        onConfirm={(to, cc, shouldSend, tebligTarihi, perRecipientMessages, extraAttachments) => {
          handleFinalProcess(to, cc, shouldSend, tebligTarihi, perRecipientMessages, extraAttachments);
        }}
        isLoading={emailModalLoading}
        // Faz 6: confirmPerFile açıkken hazırlık ekranındaki ayarlar prefill olur.
        defaultTo={batchPrep?.emailPrefill.to ?? []}
        defaultCc={batchPrep?.emailPrefill.cc ?? []}
        defaultSendEmail={batchPrep?.emailPrefill.sendEmail}
        defaultTebligTarihi={batchPrep?.emailPrefill.tebligTarihi}
        batchCount={fileQueue.length > 1 ? processedBatch.length + 1 : 0}
        totalFiles={fileQueue.length}
        analysisContext={{
          muvekkil_adi: (finalData || analysisData)?.muvekkil_kodu || (finalData || analysisData)?.muvekkil_adi,
          muvekkiller: (finalData || analysisData)?.muvekkiller,
          belge_turu_kodu: (finalData || analysisData)?.belge_turu_kodu,
          tarih: (finalData || analysisData)?.tarih,
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
            await handleFinalProcess([], [], false, undefined, undefined, undefined, newCase);
          }
        }}
      />
    </div>
  );
};

export default Index;
