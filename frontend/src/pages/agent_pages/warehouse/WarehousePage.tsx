import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import WarehouseScene from "./components/WarehouseScene";
import QueryPanel from "./components/QueryPanel";
import { getWarehouseData, queryMaterials } from "./api";
import type { MaterialItem } from "./types";
import { parseStorageBin } from "./types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

export default function WarehousePage() {
  const [, setQueryText] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryResults, setQueryResults] = useState<MaterialItem[]>([]);
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<Set<number>>(new Set());
  const [activeFloor, setActiveFloor] = useState(1);
  
  // 用于弹窗显示储位详情
  const [activeBin, setActiveBin] = useState<string | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);

  const { data: warehouseData } = useQuery({
    queryKey: ["warehouse-data"],
    queryFn: getWarehouseData,
    staleTime: 5 * 60 * 1000,
  });

  const materials = useMemo(() => warehouseData?.materials || [], [warehouseData]);

  const handleQuery = useCallback(async (query: string) => {
    setQueryText(query);
    setIsQuerying(true);
    setSelectedMaterialIds(new Set());
    try {
      const results = await queryMaterials(query);
      setQueryResults(results);
    } catch (error) {
      console.error("查询失败:", error);
      setQueryResults([]);
    } finally {
      setIsQuerying(false);
    }
  }, []);

  const highlightedBins = useMemo(() => {
    const bins = new Set<string>();
    queryResults.forEach((m) => {
      if (!m.storage_bin) return;
      const pos = parseStorageBin(m.storage_bin);
      if (!pos) return;
      const key = `${pos.group}-${pos.level}-${pos.cell}`;
      bins.add(key);
    });
    return bins;
  }, [queryResults]);

  const selectedBins = useMemo(() => {
    const bins = new Set<string>();
    materials.forEach((m) => {
      if (!selectedMaterialIds.has(m.id)) return;
      if (!m.storage_bin) return;
      const pos = parseStorageBin(m.storage_bin);
      if (!pos) return;
      const key = `${pos.group}-${pos.level}-${pos.cell}`;
      bins.add(key);
    });
    return bins;
  }, [materials, selectedMaterialIds]);

  const handleMaterialToggle = useCallback((id: number) => {
    setSelectedMaterialIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleClearSelection = useCallback(() => {
    setSelectedMaterialIds(new Set());
  }, []);

  const handleBinClick = useCallback((binKey: string) => {
    setActiveBin(binKey);
    setIsDetailModalOpen(true);
  }, []);

  const activeBinMaterials = useMemo(() => {
    if (!activeBin) return [];
    const [group, level, cell] = activeBin.split("-").map(Number);
    return materials.filter((m) => {
      if (!m.storage_bin) return false;
      const pos = parseStorageBin(m.storage_bin);
      if (!pos) return false;
      return pos.group === group && pos.level === level && pos.cell === cell;
    });
  }, [activeBin, materials]);

  return (
    <div className="flex h-screen bg-[#F5F5F5]">
      <div className="w-[420px] p-5">
        <QueryPanel
          onQuery={handleQuery}
          isQuerying={isQuerying}
          results={queryResults}
          selectedMaterials={selectedMaterialIds}
          onMaterialToggle={handleMaterialToggle}
          onClearSelection={handleClearSelection}
        />
      </div>
      <div className="flex-1 p-4 relative">
        <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 flex gap-2 p-1.5 bg-white/70 backdrop-blur-xl rounded-2xl border border-white/50 shadow-lg">
          <Button
            variant={activeFloor === 1 ? "default" : "ghost"}
            size="sm"
            onClick={() => setActiveFloor(1)}
            className={`rounded-xl px-6 transition-all ${activeFloor === 1 ? "bg-[#2C3E50] shadow-md scale-105 text-white" : "hover:bg-white/50 text-[#34495E]"}`}
          >
            一楼 (地面层)
          </Button>
          <Button
            variant={activeFloor === 2 ? "default" : "ghost"}
            size="sm"
            onClick={() => setActiveFloor(2)}
            className={`rounded-xl px-6 transition-all ${activeFloor === 2 ? "bg-[#2C3E50] shadow-md scale-105 text-white" : "hover:bg-white/50 text-[#34495E]"}`}
          >
            二楼 (阁楼层)
          </Button>
        </div>
        
        <div className="h-full bg-white rounded-3xl shadow-2xl border border-zinc-200/50 overflow-hidden ring-4 ring-zinc-100/80">
          <WarehouseScene
            materials={materials}
            highlightedBins={highlightedBins}
            selectedBins={selectedBins}
            onBinClick={handleBinClick}
            activeFloor={activeFloor}
          />
        </div>
      </div>

      <Dialog open={isDetailModalOpen} onOpenChange={setIsDetailModalOpen}>
        <DialogContent className="max-w-4xl max-h-[80vh] flex flex-col p-6 rounded-2xl bg-white/95 backdrop-blur-xl border border-zinc-200/50 shadow-2xl">
          <DialogHeader className="mb-4">
            <DialogTitle className="text-xl font-bold flex items-center gap-2">
              <span className="text-[#34495E]">储位详情:</span>
              <Badge variant="outline" className="text-[#2C3E50] bg-zinc-50/80 border-zinc-300">
                {activeBin?.replace(/(\d+)-(\d+)-(\d+)/, (_, group, level, cell) => `${group}组 - ${level}层 - ${cell}格`)}
              </Badge>
            </DialogTitle>
          </DialogHeader>
          
          <ScrollArea className="flex-1 rounded-xl border border-zinc-200/50">
            <Table>
              <TableHeader className="bg-zinc-50/80 sticky top-0 backdrop-blur-sm z-10">
                <TableRow>
                  <TableHead className="text-[#2C3E50]">物料编码</TableHead>
                  <TableHead className="w-[300px] text-[#2C3E50]">物料描述</TableHead>
                  <TableHead className="text-[#2C3E50]">物料组</TableHead>
                  <TableHead className="text-right text-[#2C3E50]">库存数量</TableHead>
                  <TableHead className="text-[#2C3E50]">单位</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {activeBinMaterials.length > 0 ? (
                  activeBinMaterials.map((m) => (
                    <TableRow key={m.id} className="hover:bg-zinc-50/50 transition-colors">
                      <TableCell className="font-mono text-[#34495E]">{m.material_code}</TableCell>
                      <TableCell className="font-medium text-[#2C3E50]">{m.material_desc || "无描述"}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="bg-zinc-100 text-[#34495E] font-normal">
                          {m.material_group || "通用"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-semibold text-[#2C3E50]">{m.unrestricted_qty}</TableCell>
                      <TableCell className="text-[#34495E]">{m.base_uom || "PC"}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={5} className="h-32 text-center text-[#34495E] bg-zinc-50/30 italic">
                      该储位当前没有存货
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
}
