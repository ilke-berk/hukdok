import { useState, useEffect, useCallback } from "react";
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
import { Wand2, Loader2, AlertCircle, Link2, Search, X, TestTube2, CheckCircle2, FolderOpen, Gavel } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { useCases } from "@/hooks/useCases";
import { QuickCaseModal } from "@/components/QuickCaseModal";
import { getStoredOutputDir, setStoredOutputDir } from "@/lib/directoryStorage";

import { EmailModal } from "@/components/email/EmailModal";

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
  const { getCases } = useCases();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [outputDirHandle, setOutputDirHandle] = useState<FileSystemDirectoryHandle | null>(null);

  // Email Modal States
  const [isEmailModalOpen, setIsEmailModalOpen] = useState(false);
  const [emailModalLoading, setEmailModalLoading] = useState(false);

  // Multi-file queue states
  const [fileQueue, setFileQueue] = useState<File[]>([]);
  const [currentFileIndex, setCurrentFileIndex] = useState<number>(0);
  const [processedCount, setProcessedCount] = useState<number>(0);

  // Pipeline states for background analysis
  const [nextAnalysisData, setNextAnalysisData] = useState<AnalysisData | null>(null);
  const [isPreloading, setIsPreloading] = useState(false);

  // Batch Mode States
  const [processedBatch, setProcessedBatch] = useState<{ path: string, name: string }[]>([]);

  // --- FAZ 1: Dava Bağlantısı State ---
  // Using explicit generic typing. Will define a dedicated CaseRead interface later in Faz 4
  const [allCases, setAllCases] = useState<IndexCaseData[]>([]);
  const [caseSearch, setCaseSearch] = useState("");
  const [linkedCase, setLinkedCase] = useState<IndexCaseData | null>(null);
  const [isTestMode, setIsTestMode] = useState(false);
  const [casesLoaded, setCasesLoaded] = useState(false);
  const [isQuickCaseModalOpen, setIsQuickCaseModalOpen] = useState(false);

  const location = useLocation();

  // Davaları yükle (bir kere)
  useEffect(() => {
    getCases().then((data: IndexCaseData[]) => {
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

  // Persistent Output Directory Load
  useEffect(() => {
    const loadOutputDir = async () => {
      const storedHandle = await getStoredOutputDir();
      if (storedHandle) {
        setOutputDirHandle(storedHandle);
      }
    };
    loadOutputDir();
  }, []);

  // Arama filtresi
  const filteredCases = allCases.filter(c => {
    if (!caseSearch.trim()) return true;
    const q = caseSearch.toLocaleLowerCase('tr-TR');
    return (
      (c.esas_no || "").toLocaleLowerCase('tr-TR').includes(q) ||
      (c.tracking_no || "").toLocaleLowerCase('tr-TR').includes(q) ||
      (c.court || "").toLocaleLowerCase('tr-TR').includes(q) ||
      (c.responsible_lawyer_name || "").toLocaleLowerCase('tr-TR').includes(q)
    );
  }).slice(0, 8); // Max 8 sonuç

  const handleFileSelect = (files: File | File[]) => {
    // Convert to array for consistent handling
    const fileArray = Array.isArray(files) ? files : [files];

    setFileQueue(fileArray);
    setCurrentFileIndex(0);
    setProcessedCount(0);
    setProcessedBatch([]); // Reset batch
    setSelectedFile(fileArray[0]);
    setAnalysisData(null);
    setNextAnalysisData(null);

    // Notify user about queue
    if (fileArray.length > 1) {
      toast.info(`${fileArray.length} dosya kuyruğa alındı. Pipeline başlatılıyor...`);
    }
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setAnalysisData(null);
    setFileQueue([]);
    setCurrentFileIndex(0);
    setProcessedCount(0);
    setProcessedBatch([]);
    setNextAnalysisData(null);
    // Dava bağlantısını da sıfırla
    setLinkedCase(null);
    setCaseSearch("");
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
                console.log("Stream Complete Data:", resultData);

                const analysisResult: AnalysisData = {
                  tarih: resultData.tarih || "",
                  belge_turu_kodu: resultData.belge_turu_kodu || "",
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
                  court: resultData.court || undefined,          // ← Mahkeme adı
                  suggested_case: resultData.suggested_case || null,
                };
                setAnalysisData(analysisResult);

                // --- FAZ 1: Otomatik Dava Bağlantısı ---
                const suggested = resultData.suggested_case;
                if (suggested && !linkedCase && !isTestMode) {
                  const caseToLink = {
                    id: suggested.case_id,
                    tracking_no: suggested.tracking_no,
                    esas_no: suggested.esas_no,
                    court: suggested.court,
                    responsible_lawyer_name: suggested.responsible_lawyer_name,
                    status: suggested.status,
                    karsi_taraf: suggested.karsi_taraf || "",
                  };

                  // Eşleşen DB kaydındaki tarafları analysisData'ya da yaz
                  // (belgede muvekkiller boş gelse bile DB'den doldur)
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
                    // Eskiden otomatik olarak setLinkedCase(caseToLink) yapıyorduk.
                    // ARTIK YAPMIYORUZ! (Human-in-the-loop: Kullanıcı onayı şart)
                    toast.info(
                      `🎯 Dava eşleşmesi bulundu: ${suggested.esas_no} (Skor: ${suggested.score}) — Lütfen sol panelden doğrulayıp onaylayın!`,
                      { duration: 8000 }
                    );
                  } else if (suggested.confidence === "MEDIUM") {
                    // Sadece öneri olarak kalsın, otomatik bağlama (kullanıcı onayı gereksin)
                    toast.info(
                      `💡 Olası dava önerisi: ${suggested.esas_no} (Skor: ${suggested.score}) — Lütfen sol panelden aratıp doğrulayın veya doğru davayı seçin.`,
                      { duration: 8000 }
                    );
                  }
                  // LOW skor: hiçbir şey yapma, kullanıcı manuel seçsin
                }
                // --- END FAZ 1 ---


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

      // Pipeline: Preload next file in background if available
      if (fileQueue.length > 1 && currentFileIndex < fileQueue.length - 1 && !isPreloading) {
        preloadNextFile(fileQueue[currentFileIndex + 1]);
      }
    }
  };

  // Pipeline: Preload next file in background
  const preloadNextFile = async (nextFile: File) => {
    if (isPreloading) return; // Prevent concurrent preloads

    setIsPreloading(true);
    toast.info("📂 Sıradaki dosya arka planda hazırlanıyor...", { duration: 2000 });

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 300000);

      // Web Mode: FormData ile dosya gönder
      const formData = new FormData();
      formData.append("file", nextFile);

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

                // Store preloaded data
                setNextAnalysisData({
                  tarih: resultData.tarih || "",
                  belge_turu_kodu: resultData.belge_turu_kodu || "",
                  muvekkil_kodu: resultData.muvekkil_adi || "",
                  muvekkiller: resultData.muvekkiller || [],
                  belgede_gecen_isimler: resultData.belgede_gecen_isimler || [],
                  esas_no: resultData.esas_no || "",
                  durum: resultData.durum || "X",
                  ofis_dosya_no: resultData.ofis_dosya_no || "000000000",
                  yedek1: "X",
                  yedek2: "XX",
                  ozet: resultData.ozet || "",
                  generated_filename: "",
                  hash: resultData.hash || "",
                });

                toast.success("✅ Sıradaki dosya hazır!", { duration: 2000 });
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
      setIsPreloading(false);
    }
  };

  const [isProcessing, setIsProcessing] = useState(false);
  const [isValidated, setIsValidated] = useState(false);
  const [finalData, setFinalData] = useState<AnalysisData | null>(null);

  const handleValidationChange = useCallback((isValid: boolean, data: AnalysisData) => {
    setIsValidated(isValid);
    // Yalnızca veri değişmişse güncelleyerek sonsuz döngüyü önle
    setFinalData((prev) => JSON.stringify(prev) === JSON.stringify(data) ? prev : data);
  }, []);

  // Bütün tiklere basıldıktan sonra otomatik dava arama
  useEffect(() => {
    if (isValidated && finalData && !isTestMode) {
      const normalize = (str?: string) => (str || "").toLocaleLowerCase('tr-TR').replace(/[\s\-_/]/g, "");

      const targetEsas = normalize(finalData.esas_no);
      if (!targetEsas) return;

      // Eğer hali hazırda bir dava seçiliyse ve seçili davanın esas numarasıyla 
      // kullanıcının onayladığı esas numarası uyuşuyorsa dokunma.
      // Ama uyuşmuyorsa, yeni girilen esas no'ya göre arama yap.
      if (linkedCase) {
        const linkedEsas = normalize(linkedCase.esas_no) || normalize(linkedCase.tracking_no);
        if (linkedEsas === targetEsas) return;
      }

      const exactMatch = allCases.find((c) => {
        const cEsas = normalize(c.esas_no);
        const cTrack = normalize(c.tracking_no);
        return (cEsas && cEsas === targetEsas) || (cTrack && cTrack === targetEsas);
      });

      if (exactMatch && exactMatch.id !== linkedCase?.id) {
        setLinkedCase(exactMatch);
        toast.success(`🎯 ${exactMatch.esas_no || exactMatch.tracking_no} numaralı dava bulundu ve otomatik eklendi.`, { duration: 5000 });
      }
    }
  }, [isValidated, finalData, isTestMode, allCases, linkedCase]);



  // Step 1: User clicks "Confirm"
  const handleConfirmClick = () => {
    if (!finalData && !analysisData) return;

    // BATCH MODE CHECK
    if (fileQueue.length > 1) {
      const isLastFile = currentFileIndex === fileQueue.length - 1;

      if (!isLastFile) {
        // Not last file -> Process silently (no email modal)
        // Pass empty arrays for emails, false for shouldSendEmail
        handleFinalProcess([], [], false);
        return;
      } else {
        // Last file -> Open modal for BATCH SENDING
        setIsEmailModalOpen(true);
        return;
      }
    }

    // SINGLE MODE
    setIsEmailModalOpen(true);
  };

  // Step 2: User confirms email -> Start Process
  // overrideLinkedCase: QuickCaseModal'dan yeni açılan dava, state güncel olmadan önce geçilir
  const handleFinalProcess = async (toEmails: string[], ccEmails: string[], shouldSendEmail: boolean, tebligTarihi?: string, overrideLinkedCase?: IndexCaseData) => {
    const dataToUse = finalData || analysisData;
    if (!selectedFile || !dataToUse) return;

    // Check if this is a "Batch Final Step"
    const isBatchMode = fileQueue.length > 1;
    const isLastFile = currentFileIndex === fileQueue.length - 1;

    // If batch mode and last file, and sending email is requested -> We need special handling
    // We first save the current file, then trigger batch send

    // For intermediate files in batch mode, modal is skipped so shouldSendEmail comes as false.
    // For single file, modal is shown.

    if (isLastFile || !isBatchMode) {
      setEmailModalLoading(true);
    } else {
      // Intermediate files don't show modal, so no loading on modal
      setIsProcessing(true);
    }

    // BUG FIX: Use the approved 77-character filename from AnalysisResults
    // Add .pdf extension as we are dealing with document files
    let newFilename = dataToUse.generated_filename || "belge_bilinmiyor";
    if (!newFilename.toLowerCase().endsWith(".pdf")) {
      newFilename += ".pdf";
    }

    setIsEmailModalOpen(false);
    setEmailModalLoading(false);
    setIsProcessing(true);

    toast.info("İşlem başlatıldı (SharePoint & E-Posta)...");

    try {
      // Web Mode: FormData ile dosya ve metadata gönder
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("new_filename", newFilename);

      // Optional fields
      if (dataToUse.muvekkil_adi) formData.append("muvekkil_adi", dataToUse.muvekkil_adi);
      if (dataToUse.karsi_taraf) formData.append("karsi_taraf", dataToUse.karsi_taraf);
      if (dataToUse.belge_turu_kodu) formData.append("belge_turu_kodu", dataToUse.belge_turu_kodu);
      if (dataToUse.tarih) formData.append("tarih", dataToUse.tarih);
      if (dataToUse.esas_no) formData.append("esas_no", dataToUse.esas_no);
      if (tebligTarihi) formData.append("teblig_tarihi", tebligTarihi);

      // JSON fields (arrays)
      formData.append("muvekkiller_json", JSON.stringify(dataToUse.muvekkiller || []));
      formData.append("belgede_gecen_isimler_json", JSON.stringify(dataToUse.belgede_gecen_isimler || []));
      formData.append("custom_to_json", JSON.stringify(toEmails));
      formData.append("custom_cc_json", JSON.stringify(ccEmails));
      formData.append("send_email", String(shouldSendEmail));

      // --- FAZ 1: Dava Bağlantısı ---
      const effectiveLinkedCase = overrideLinkedCase || linkedCase;
      if (effectiveLinkedCase?.id) {
        formData.append("linked_case_id", String(effectiveLinkedCase.id));
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
              toast.success("📄 İşlenmiş (PDF/A) dosya indirildi.");
            } else {
              console.error("Download failed, falling back to original");
            }
          } catch (dlErr) {
            console.error("Download fetch error:", dlErr);
          }
        } else {
          // Fallback warning if DOCX
          if (selectedFile.name.toLowerCase().endsWith(".docx") && newFilename.toLowerCase().endsWith(".pdf")) {
            toast.warning("PDF dönüşümü sunucuda yapıldı ancak indirilemedi. Orijinal .docx dosyası .pdf olarak kaydediliyor (açılmayabilir).", { duration: 5000 });
          }
        }

        const success = await saveFileToDisk(blobToSave as File, finalSaveFilename);
        if (success) {
          toast.success(`💾 Dosya şuraya kaydedildi: ${finalSaveFilename}`);
        }
      }

      // TRACK PROCESSED FILE FOR BATCH (Web modunda dosya objesi kullanılır)
      const updatedBatch = [...processedBatch];
      updatedBatch.push({ path: "", name: newFilename }); // Web'de path yok
      setProcessedBatch(updatedBatch);

      if (shouldSendEmail && !isBatchMode) {
        toast.success("✅ Belge arşivlendi ve e-postalar sıraya alındı!");
      } else if (!isBatchMode) {
        toast.success("✅ Belge arşivlendi (E-posta gönderilmedi).");
      } else {
        toast.success(`✅ Dosya işlendi (${currentFileIndex + 1}/${fileQueue.length})`);
      }

      // BATCH EMAIL - Web Mode
      // Web modunda her dosya zaten /confirm sırasında email ile işleniyor
      // Toplu email özelliği şimdilik devre dışı (dosyalar sunucuya tek tek gidiyor)
      if (isBatchMode && isLastFile && shouldSendEmail) {
        toast.info("📧 Tüm dosyalar için e-postalar gönderildi.");
      }

      // Pipeline: Move to next file in queue
      if (fileQueue.length > 1 && currentFileIndex < fileQueue.length - 1) {
        const nextIndex = currentFileIndex + 1;
        setCurrentFileIndex(nextIndex);
        setProcessedCount(prev => prev + 1);
        setSelectedFile(fileQueue[nextIndex]);
        setIsValidated(false);
        setFinalData(null);

        // Use preloaded data if available (instant switch!)
        if (nextAnalysisData) {
          setAnalysisData(nextAnalysisData);
          setNextAnalysisData(null);
          toast.success(`⚡ Dosya ${nextIndex + 1}/${fileQueue.length} anında yüklendi!`);

          // Continue pipeline: preload next file
          if (nextIndex < fileQueue.length - 1 && !isPreloading) {
            preloadNextFile(fileQueue[nextIndex + 1]);
          }
        } else {
          // Preload not ready yet, start fresh analysis
          setAnalysisData(null);
          toast.info(`📁 Dosya ${nextIndex + 1}/${fileQueue.length} yükleniyor...`);
          // Trigger analysis automatically
          setTimeout(() => {
            const analyzeBtn = document.querySelector('[data-analyze-btn]');
            if (analyzeBtn) (analyzeBtn as HTMLButtonElement).click();
          }, 100);
        }
      } else {
        // All files processed!
        const totalFiles = fileQueue.length;
        toast.success(`🎉 Tüm dosyalar tamamlandı! (${totalFiles}/${totalFiles})`);

        // Reset state for next batch
        setAnalysisData(null);
        setFinalData(null);
        setSelectedFile(null);
        setFileQueue([]);
        setProcessedBatch([]); // Clear batch
        setCurrentFileIndex(0);
        setProcessedCount(0);
        setNextAnalysisData(null);
        setIsValidated(false);
        setLinkedCase(null);
        setCaseSearch("");
      }
    } catch (error: unknown) {
      console.error("Confirmation error:", error);
      const errorMessage = error instanceof Error ? error.message : "Beklenmedik bir hata oluştu.";
      toast.error(errorMessage);
    } finally {
      setIsProcessing(false);
    }

    // --- FILE SYSTEM ACCESS API SAVE ---
    // Save the file electronically to the user's selected folder (if available)
    if (outputDirHandle && selectedFile && dataToUse) {
      let saveFilename = dataToUse.generated_filename || "belge_bilinmiyor";
      if (!saveFilename.toLowerCase().endsWith(".pdf")) {
        saveFilename += ".pdf";
      }

      // We need the PROCESSED file (e.g. from backend response) usually.
      // But currently, the backend '/confirm' saves to SharePoint/Server.
      // The 'selectedFile' is the ORIGINAL. 

      // OPTION A: Save the ORIGINAL file with the NEW NAME to Desktop.
      // OPTION B: If backend generates a standardized/stamped PDF, we would need to fetch it.
      // Assuming user wants the ORIGINAL file but renormalized/renamed:

      // If you need the file to be exactly what was uploaded but renamed:
      const success = await saveFileToDisk(selectedFile, saveFilename);
      if (success) {
        toast.success(`💾 Dosya bilgisayarınıza kaydedildi: ${saveFilename}`);
      }
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

            {/* --- FAZ 1: DAVA BAĞLANTISI PANELİ --- */}
            <div className="rounded-xl border border-border/60 bg-card/70 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold flex items-center gap-2">
                  <Link2 className="w-4 h-4 text-primary" />
                  Dava Bağlantısı
                </label>
                <button
                  type="button"
                  onClick={() => {
                    setIsTestMode(prev => {
                      if (!prev) { setLinkedCase(null); toast.info("🧪 TEST modu aktif — dava seçimi zorunlu değil.", { duration: 2500 }); }
                      else { toast.info("TEST modu kapatıldı."); }
                      return !prev;
                    });
                  }}
                  className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border transition-all duration-200 ${isTestMode ? "bg-amber-500/20 border-amber-500/40 text-amber-400" : "bg-muted/50 border-border/50 text-muted-foreground hover:text-foreground"}`}
                >
                  <TestTube2 className="w-3 h-3" />
                  TEST {isTestMode ? "Açık" : "Kapalı"}
                </button>
              </div>

              {isTestMode ? (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-400">
                  <TestTube2 className="w-4 h-4 shrink-0" />
                  <span>Test modunda belge yüklenecek — dava seçimi atlanıyor. Belge <strong>TEST</strong> olarak kaydedilir.</span>
                </div>
              ) : linkedCase ? (
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
                  <button type="button" onClick={() => { setLinkedCase(null); setCaseSearch(""); }} className="text-muted-foreground hover:text-destructive transition-colors" title="Davayı değiştir">
                    <X className="w-4 h-4" />
                  </button>
                </div>
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
                                  // @ts-expect-error We don't have exactly mapped party type here from suggest
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
                <QueueStatus totalFiles={fileQueue.length} currentIndex={currentFileIndex} processedCount={processedCount} />
                <Button data-analyze-btn onClick={handleAnalyze} disabled={isAnalyzing || isProcessing}
                  className="w-full h-14 text-lg font-semibold bg-[hsl(345,80%,40%)] hover:bg-[hsl(345,80%,35%)] shadow-lg transition-all duration-300 hover:scale-[1.02]" size="lg">
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
          <div className="flex flex-col gap-4">
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
                  disabled={isProcessing || !isValidated}
                  className={`w-full h-16 text-xl font-bold shadow-lg transition-all duration-300 hover:scale-[1.02] ${isValidated
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-gray-400 cursor-not-allowed opacity-50"
                    }`}
                >
                  {isProcessing ? (
                    <><Loader2 className="w-6 h-6 mr-2 animate-spin" />İşleniyor (SharePoint & Kayıt)...</>
                  ) : (
                    isValidated ? "✅ Onayla ve İşlemi Tamamla" : "⚠️ Lütfen Tüm Alanları Onaylayın"
                  )}
                </Button>
              </>
            ) : (
              <AnalysisPending isAnalyzing={isAnalyzing} />
            )}
          </div>
        </div>
      </main>

      {/* Email Modal */}
      <EmailModal
        isOpen={isEmailModalOpen}
        onClose={() => setIsEmailModalOpen(false)}
        onConfirm={handleFinalProcess}
        isLoading={emailModalLoading}
        defaultTo={[]}
        defaultCc={[]}
        batchCount={fileQueue.length > 1 ? processedBatch.length + 1 : 0}
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
            await handleFinalProcess([], [], false, undefined, newCase);
          }
        }}
      />
    </div>
  );
};

export default Index;
