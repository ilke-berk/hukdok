import { useState } from "react";
import { Header } from "@/components/Header";
import { FileUpload } from "@/components/FileUpload";
import { AnalysisResults } from "@/components/AnalysisResults";
import { AnalysisPending } from "@/components/AnalysisPending";
import { QueueStatus } from "@/components/QueueStatus";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Wand2, Loader2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";


import { EmailModal } from "@/components/email/EmailModal";


interface AnalysisData {
  tarih: string;
  belge_turu_kodu: string;
  muvekkil_kodu: string;
  muvekkil_adi?: string;
  muvekkiller?: string[];
  karsi_taraf?: string; // Yeni alan
  belgede_gecen_isimler: string[];
  esas_no: string;
  avukat_kodu: string;
  durum: string;
  ofis_dosya_no: string;
  yedek1: string;
  yedek2: string;
  ozet: string;
  generated_filename: string;
  hash: string;
}

const Index = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

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

                // Handle success
                setAnalysisData({
                  tarih: resultData.tarih || "",
                  belge_turu_kodu: resultData.belge_turu_kodu || "",
                  muvekkil_kodu: resultData.muvekkil_adi || "",
                  muvekkiller: resultData.muvekkiller || [],
                  karsi_taraf: resultData.karsi_taraf || "", // Yeni alan
                  belgede_gecen_isimler: resultData.belgede_gecen_isimler || [],
                  esas_no: resultData.esas_no || "",
                  avukat_kodu: resultData.avukat_kodu || "XXX",
                  durum: resultData.durum || "G",
                  ofis_dosya_no: resultData.ofis_dosya_no || "000000000",
                  yedek1: "X",
                  yedek2: "XX",
                  ozet: resultData.ozet || "",
                  generated_filename: "",
                  hash: resultData.hash || "",
                });
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
                  avukat_kodu: resultData.avukat_kodu || "XXX",
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

  const handleValidationChange = (isValid: boolean, data: AnalysisData) => {
    setIsValidated(isValid);
    setFinalData(data);
  };



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
  const handleFinalProcess = async (toEmails: string[], ccEmails: string[], shouldSendEmail: boolean, tebligTarihi?: string) => {
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
      if (dataToUse.avukat_kodu) formData.append("avukat_kodu", dataToUse.avukat_kodu);
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

      const response = await apiClient.fetch("/confirm", {
        method: "POST",
        body: formData
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || "Kayıt işlemi sırasında bir hata oluştu.");
      }

      console.log("Confirmation complete:", result);

      // TRACK PROCESSED FILE FOR BATCH (Web modunda dosya objesi kullanılır)
      let updatedBatch = [...processedBatch];
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
      }
    } catch (error: any) {
      console.error("Confirmation error:", error);
      toast.error(error.message || "Beklenmedik bir hata oluştu.");
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container max-w-screen-2xl mx-auto px-6 py-8">
        <div className="grid lg:grid-cols-2 gap-8">
          <div className="space-y-6">
            <FileUpload
              onFileSelect={handleFileSelect}
              selectedFile={selectedFile}
              onClearFile={handleClearFile}
              isAnalyzing={isAnalyzing}
              isComplete={!!analysisData}
            />
            {selectedFile && (
              <>
                {/* Queue Status Indicator */}
                <QueueStatus
                  totalFiles={fileQueue.length}
                  currentIndex={currentFileIndex}
                  processedCount={processedCount}
                />

                <Button
                  data-analyze-btn
                  onClick={handleAnalyze}
                  disabled={isAnalyzing || isProcessing}
                  className="w-full h-14 text-lg font-semibold bg-[hsl(345,80%,40%)] hover:bg-[hsl(345,80%,35%)] shadow-lg transition-all duration-300 hover:scale-[1.02]"
                  size="lg"
                >
                  {isAnalyzing ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                      Analiz Ediliyor...
                    </>
                  ) : (
                    <>
                      <Wand2 className="w-5 h-5 mr-2" />
                      Analizi Başlat
                    </>
                  )}
                </Button>
                {analysisData?.ozet && (
                  <div className="glass-card rounded-xl p-6">
                    <Label className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <AlertCircle className="w-4 h-4 text-primary" />
                      Belge Özeti
                    </Label>
                    <p className="text-sm text-muted-foreground leading-relaxed italic">
                      "{analysisData.ozet}"
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
          <div className="flex flex-col gap-4">
            {analysisData ? (
              <>
                <AnalysisResults data={analysisData} onValidationChange={handleValidationChange} />
                <Button
                  onClick={handleConfirmClick}
                  disabled={isProcessing || !isValidated}
                  className={`w-full h-16 text-xl font-bold shadow-lg transition-all duration-300 hover:scale-[1.02] ${isValidated
                    ? "bg-green-600 hover:bg-green-700"
                    : "bg-gray-400 cursor-not-allowed opacity-50"
                    }`}
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="w-6 h-6 mr-2 animate-spin" />
                      İşleniyor (SharePoint & Kayıt)...
                    </>
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
        defaultTo={[]} // Gelecekte buraya otomatik sorumlu avukatları ekleyebiliriz
        defaultCc={[]}
        batchCount={fileQueue.length > 1 ? processedBatch.length + 1 : 0} // +1 because current file is not added yet when modal opens
      />
    </div>
  );
};

export default Index;
