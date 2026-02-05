interface QueueStatusProps {
    totalFiles: number;
    currentIndex: number;
    processedCount: number;
}

export const QueueStatus = ({ totalFiles, currentIndex, processedCount }: QueueStatusProps) => {
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
                <div className="flex gap-1.5 ml-4">
                    {Array.from({ length: totalFiles }).map((_, i) => (
                        <div
                            key={i}
                            className={`w-2.5 h-2.5 rounded-full transition-all duration-300 ${i < processedCount
                                    ? "bg-green-500 shadow-sm shadow-green-500/50"
                                    : i === currentIndex
                                        ? "bg-blue-500 animate-pulse shadow-sm shadow-blue-500/50"
                                        : "bg-gray-300 dark:bg-gray-600"
                                }`}
                            title={
                                i < processedCount
                                    ? "Tamamlandı"
                                    : i === currentIndex
                                        ? "İşleniyor"
                                        : "Bekliyor"
                            }
                        />
                    ))}
                </div>
            </div>
        </div>
    );
};
