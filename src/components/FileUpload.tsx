import { useState, useCallback } from "react";
import { Upload, FileText, X } from "lucide-react";
import { Document, Packer, Paragraph } from "docx";
import { saveAs } from "file-saver";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FileUploadProps {
  onFileSelect: (files: File | File[]) => void;
  selectedFile: File | null;
  onClearFile: () => void;
  isAnalyzing?: boolean;
  isComplete?: boolean;
  title?: string;
  description?: string;
  uploadText?: string;
}

export const FileUpload = ({
  onFileSelect,
  selectedFile,
  onClearFile,
  isAnalyzing = false,
  isComplete = false,
  title = "Adı Değiştirilecek Dosyayı Yükleyiniz",
  description = "PDF, DOCX, DOC, TXT, UDF (UYAP)",
  uploadText = "Dosya Yükle"
}: FileUploadProps) => {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    const validFiles = files.filter(file => isValidFile(file));

    if (validFiles.length === 0) {
      return; // No valid files
    }



    // Send all valid files (or single file for backward compatibility)
    if (validFiles.length === 1) {
      onFileSelect(validFiles[0]);
    } else {
      onFileSelect(validFiles);
    }
  }, [onFileSelect]);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files).filter(isValidFile);
      if (files.length > 0) {
        onFileSelect(files);
      }
    }
  };

  const isValidFile = (file: File) => {
    const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword', 'text/plain', 'application/xml', 'text/xml', 'application/zip'];
    return validTypes.includes(file.type) || file.name.toLowerCase().endsWith('.udf');
  };

  const handleUploadClick = () => {
    document.getElementById("hidden-file-input")?.click();
  };

  return (
    <Card className="glass-card animate-fade-in">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-foreground">
            <FileText className="w-5 h-5 text-primary" />
            {title}
          </CardTitle>

        </div>
      </CardHeader>
      <CardContent>
        {!selectedFile ? (
          <div
            onClick={handleUploadClick}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={cn(
              "border-2 border-dashed rounded-xl p-12 text-center transition-all duration-300",
              isDragging ? "border-primary bg-primary/10 scale-[1.02] glow-primary" : "border-border/50 glass-input",
              "hover:border-primary/60 hover:bg-primary/5 cursor-pointer"
            )}
          >
            <input
              id="hidden-file-input"
              type="file"
              className="hidden"
              multiple
              accept=".pdf,.docx,.doc,.txt,.udf"
              onChange={handleFileInput}
            />
            <Upload className="w-12 h-12 mx-auto mb-4 text-primary drop-shadow-lg" />
            <p className="text-lg font-medium text-foreground mb-2">{uploadText}</p>
            <p className="text-sm text-muted-foreground">
              {description}
            </p>
          </div>
        ) : (
          <div className="glass-input rounded-xl p-6 animate-fade-in">
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center gap-3 flex-1">
                <div className="bg-primary/20 p-3 rounded-lg">
                  <FileText className="w-6 h-6 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-foreground break-all">{selectedFile.name}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={onClearFile}
                disabled={isAnalyzing}
                className="hover:bg-destructive/20 hover:text-destructive"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>

            <div className="glass rounded-lg p-4">
              <div className="flex items-start gap-2 text-sm">
                <div className="text-muted-foreground shrink-0">SONRAKI ADIM</div>
              </div>
              <p className="text-sm text-foreground mt-2">
                {isComplete
                  ? "Lütfen sağ taraftaki verileri kontrol edip eksik alanları doldurunuz."
                  : "Analizi Başlat butonuna basarak devam edebilirsiniz."}
              </p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
