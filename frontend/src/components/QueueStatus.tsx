import { X } from "lucide-react";

interface QueueStatusProps {
    totalFiles: number;
    currentIndex: number;
    processedCount: number;
    onRemoveFile?: (index: number) => void;
}

export const QueueStatus = ({ totalFiles, currentIndex, processedCount, onRemoveFile }: QueueStatusProps) => {
    // Don't show queue status for single file
    if (totalFiles <= 1) return null;

    return (
        <div className="glass-card rounded-xl p-4 mb-4 animate-fade-in">
            <div className="flex items-center justify-between">
                <div className="flex-1">
                    <p className="text-sm font-semibold text-foreground">
                        📁 Dosya {currentIndex + 1} / {totalFiles}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                        ✅ {processedCount} tamamlandı · ⏳ {totalFiles - processedCount} bekliyor
                    </p>
                </div>
                <div className="flex gap-2 ml-4 items-center">
                    {Array.from({ length: totalFiles }).map((_, i) => {
                        const isDone = i < processedCount;
                        const isCurrent = i === currentIndex;
                        const isFuture = i > currentIndex;
                        const removable = isFuture && !!onRemoveFile;

                        const dot = (
                            <div
                                className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${isDone
                                        ? "bg-green-500 shadow-sm shadow-green-500/50"
                                        : isCurrent
                                            ? "bg-blue-500 animate-pulse shadow-sm shadow-blue-500/50"
                                            : "bg-gray-300 dark:bg-gray-600"
                                    }`}
                                title={
                                    isDone
                                        ? "Tamamlandı"
                                        : isCurrent
                                            ? "İşleniyor"
                                            : "Bekliyor"
                                }
                            />
                        );

                        if (!removable) {
                            return <div key={i}>{dot}</div>;
                        }

                        return (
                            <div key={i} className="relative group p-1 -m-1">
                                {dot}
                                <button
                                    type="button"
                                    onClick={() => onRemoveFile?.(i)}
                                    title="Kuyruktan çıkar"
                                    className="absolute -top-1 -right-1 hidden group-hover:flex items-center justify-center w-4 h-4 rounded-full bg-destructive text-destructive-foreground shadow hover:scale-110 transition-transform"
                                >
                                    <X className="w-2.5 h-2.5" />
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};
