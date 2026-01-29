import { Card, CardContent } from "@/components/ui/card";
import { Wand2, Loader2 } from "lucide-react";

interface AnalysisPendingProps {
  isAnalyzing?: boolean;
}

export const AnalysisPending = ({ isAnalyzing = false }: AnalysisPendingProps) => {
  return (
    <Card className="glass-card animate-fade-in h-full flex items-center justify-center">
      <CardContent className="py-20 w-full">
        <div className="flex flex-col items-center justify-center text-center space-y-4">
          <div className="glass p-6 rounded-full relative">
            {isAnalyzing ? (
              <Loader2 className="w-12 h-12 text-primary animate-spin" />
            ) : (
              <Wand2 className="w-12 h-12 text-primary" />
            )}
          </div>
          <div className="space-y-2">
            <h3 className="text-xl font-semibold text-foreground">
              {isAnalyzing ? "Analiz Yapılıyor..." : "Analiz Bekleniyor"}
            </h3>
            <p className="text-sm text-muted-foreground max-w-md">
              {isAnalyzing
                ? "Yapay zeka belgenizi inceliyor, lütfen bekleyin."
                : 'Dosyanızı yükleyin ve "Analizi Başlat" butonuna tıklayın. Sonuçlar burada görüntülenecektir.'}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
