import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { InsightTag } from "./InsightTag";
import { SectionCard } from "./SectionCard";

const rows = [
    { title: "新能源汽车海外渠道加速铺设", type: "industryNews" as const, heat: "高", source: "行业媒体", time: "10 分钟前" },
    { title: "竞品发布智能座舱 OTA 计划", type: "newProduct" as const, heat: "中", source: "企业公告", time: "32 分钟前" },
    { title: "欧盟电池法规更新回收条款", type: "regulation" as const, heat: "高", source: "法规库", time: "1 小时前" },
    { title: "头部客户披露年度采购预算", type: "financialReport" as const, heat: "中", source: "财报摘要", time: "2 小时前" },
];

export function DataTableCard() {
    return (
        <SectionCard title="重点情报列表" description="按热度、来源可信度和业务相关性综合排序。">
            <div className="insight-table-wrap overflow-x-auto rounded-[var(--insight-radius-lg)] border border-border">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>动态标题</TableHead>
                            <TableHead>类型</TableHead>
                            <TableHead>热度</TableHead>
                            <TableHead>来源</TableHead>
                            <TableHead>时间</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {rows.map((row) => (
                            <TableRow key={row.title}>
                                <TableCell className="font-semibold">{row.title}</TableCell>
                                <TableCell>
                                    <InsightTag business={row.type} />
                                </TableCell>
                                <TableCell>
                                    <InsightTag status={row.heat === "高" ? "warning" : "info"}>{row.heat}</InsightTag>
                                </TableCell>
                                <TableCell className="text-muted-foreground">{row.source}</TableCell>
                                <TableCell className="text-muted-foreground">{row.time}</TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        </SectionCard>
    );
}
