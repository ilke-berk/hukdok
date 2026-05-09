import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Eye, History } from "lucide-react";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";
import {
  ActivityReportModal,
  ActivityReport,
} from "@/components/ActivityReportModal";

interface HistoryRow {
  id: number;
  report_date: string;
  total_documents: number;
  mailed_documents: number;
  unmailed_documents: number;
  error_documents: number;
  is_acknowledged: boolean;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

const ActivityHistory = () => {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ActivityReport | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiClient.fetch("/api/activity/history?days=30");
      if (!res.ok) throw new Error("Liste alınamadı");
      const data = await res.json();
      setRows(Array.isArray(data) ? data : []);
    } catch {
      toast.error("Geçmiş yüklenemedi.");
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleOpen = async (id: number) => {
    setOpeningId(id);
    try {
      const res = await apiClient.fetch(`/api/activity/history/${id}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      setDetail({
        ...data,
        has_unmailed: data.unmailed_documents > 0,
      } as ActivityReport);
    } catch {
      toast.error("Rapor detayı yüklenemedi.");
    } finally {
      setOpeningId(null);
    }
  };

  const totalSummary = rows.reduce(
    (acc, r) => ({
      total: acc.total + r.total_documents,
      mailed: acc.mailed + r.mailed_documents,
      unmailed: acc.unmailed + r.unmailed_documents,
      errors: acc.errors + r.error_documents,
    }),
    { total: 0, mailed: 0, unmailed: 0, errors: 0 }
  );

  return (
    <>
      <Header />
      <main className="container mx-auto px-6 py-8 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <History className="h-5 w-5 text-primary" />
              Aktivite Geçmişim
            </CardTitle>
            <CardDescription>
              Son 30 gün içinde işlediğiniz belgelerin günlük raporları. Bir satıra tıklayarak
              o günün detaylı belge listesini görebilirsiniz.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Özet kartı */}
            {!loading && rows.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="rounded-lg border px-4 py-3 bg-muted/30">
                  <p className="text-xs text-muted-foreground">Toplam belge</p>
                  <p className="text-2xl font-bold">{totalSummary.total}</p>
                </div>
                <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-4 py-3">
                  <p className="text-xs text-green-700 dark:text-green-400">E-posta ile iletildi</p>
                  <p className="text-2xl font-bold text-green-700 dark:text-green-400">
                    {totalSummary.mailed}
                  </p>
                </div>
                <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
                  <p className="text-xs text-amber-700 dark:text-amber-400">E-postasız</p>
                  <p className="text-2xl font-bold text-amber-700 dark:text-amber-400">
                    {totalSummary.unmailed}
                  </p>
                </div>
                <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3">
                  <p className="text-xs text-red-700 dark:text-red-400">Hatalı</p>
                  <p className="text-2xl font-bold text-red-700 dark:text-red-400">
                    {totalSummary.errors}
                  </p>
                </div>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : rows.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                Son 30 gün içinde size ait rapor bulunamadı.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tarih</TableHead>
                    <TableHead className="text-center">Toplam</TableHead>
                    <TableHead className="text-center">Mailli</TableHead>
                    <TableHead className="text-center">Mailsiz</TableHead>
                    <TableHead className="text-center">Hatalı</TableHead>
                    <TableHead className="text-center">Durum</TableHead>
                    <TableHead className="text-right">İşlem</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((r) => (
                    <TableRow
                      key={r.id}
                      className="cursor-pointer hover:bg-muted/40"
                      onClick={() => handleOpen(r.id)}
                    >
                      <TableCell className="font-mono text-sm">
                        {formatDate(r.report_date)}
                      </TableCell>
                      <TableCell className="text-center font-medium">{r.total_documents}</TableCell>
                      <TableCell className="text-center text-green-600 dark:text-green-400">
                        {r.mailed_documents}
                      </TableCell>
                      <TableCell className="text-center text-amber-600 dark:text-amber-400">
                        {r.unmailed_documents}
                      </TableCell>
                      <TableCell className="text-center text-red-600 dark:text-red-400">
                        {r.error_documents}
                      </TableCell>
                      <TableCell className="text-center text-xs">
                        {r.is_acknowledged ? (
                          <span className="text-green-600">✓ Onaylandı</span>
                        ) : (
                          <span className="text-amber-600">⏳ Bekliyor</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={openingId !== null}
                          onClick={(e) => { e.stopPropagation(); handleOpen(r.id); }}
                        >
                          {openingId === r.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <>
                              <Eye className="h-4 w-4 mr-1" />
                              Detay
                            </>
                          )}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      {detail && (
        <ActivityReportModal
          report={detail}
          onClose={() => setDetail(null)}
          readOnly
        />
      )}
    </>
  );
};

export default ActivityHistory;
