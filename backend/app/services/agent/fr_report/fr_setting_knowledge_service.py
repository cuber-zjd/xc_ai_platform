import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrSettingKnowledgeEntry:
    """FineReport 属性面板到 CPT 写法的受控知识条目。"""

    entry_id: str
    title: str
    panel: str
    keywords: tuple[str, ...]
    cpt_nodes: tuple[str, ...]
    applies_to: tuple[str, ...]
    prefer_when: tuple[str, ...]
    avoid_when: tuple[str, ...]
    verification: tuple[str, ...]
    evidence_hint: tuple[str, ...] = field(default_factory=tuple)

    def to_read(self) -> dict[str, Any]:
        return {
            "entryId": self.entry_id,
            "title": self.title,
            "panel": self.panel,
            "keywords": list(self.keywords),
            "cptNodes": list(self.cpt_nodes),
            "appliesTo": list(self.applies_to),
            "preferWhen": list(self.prefer_when),
            "avoidWhen": list(self.avoid_when),
            "verification": list(self.verification),
            "evidenceHint": list(self.evidence_hint),
        }


class FrSettingKnowledgeService:
    """FineReport 设置知识库。

    这是“只读参考索引”，不是规则引擎。它只提示 Agent 可参考哪些 CPT 节点、
    哪些场景适合或不适合，最终修改仍必须以当前 CPT、参考案例和预览结果为准。
    """

    def __init__(self) -> None:
        self._entries = self._build_entries()

    def search(self, query: str, *, limit: int = 6) -> dict[str, Any]:
        normalized_query = self._normalize(query)
        tokens = [item for item in re.split(r"[\s,，、。；;:/\\|]+", normalized_query) if item]
        scored: list[tuple[int, FrSettingKnowledgeEntry, list[str]]] = []
        for entry in self._entries:
            score, reasons = self._score(entry, normalized_query, tokens)
            if score > 0:
                scored.append((score, entry, reasons))
        scored.sort(key=lambda item: (-item[0], item[1].entry_id))
        hits = []
        for score, entry, reasons in scored[: max(1, min(limit, 12))]:
            item = entry.to_read()
            item["score"] = score
            item["matchedReasons"] = reasons[:8]
            hits.append(item)
        return {
            "summary": f"找到 {len(hits)} 条 FineReport 设置参考。" if hits else "没有找到足够相关的 FineReport 设置参考。",
            "query": query,
            "hits": hits,
            "strictUsePolicy": [
                "这些条目只是属性面板与 CPT 节点的参考，不是自动改写规则。",
                "写入前仍必须读取当前 CPT 片段或完整 WorkBook，并优先延续当前报表已有 XML 写法。",
                "真实报表案例和 FineReport 预览结果优先级高于本知识库。",
                "不得因为命中某条知识就跳过数据库字段、单元格绑定、样式继承和布局影响检查。",
            ],
        }

    def list_entries(self) -> list[dict[str, Any]]:
        return [entry.to_read() for entry in self._entries]

    def _score(self, entry: FrSettingKnowledgeEntry, query: str, tokens: list[str]) -> tuple[int, list[str]]:
        haystacks = {
            "title": self._normalize(entry.title),
            "panel": self._normalize(entry.panel),
            "keywords": self._normalize(" ".join(entry.keywords)),
            "applies": self._normalize(" ".join(entry.applies_to)),
            "nodes": self._normalize(" ".join(entry.cpt_nodes)),
        }
        score = 0
        reasons: list[str] = []
        for name, text in haystacks.items():
            if query and query in text:
                score += 8 if name in {"title", "keywords"} else 4
                reasons.append(f"{name} 包含完整查询")
        for keyword in entry.keywords:
            normalized_keyword = self._normalize(keyword)
            if len(normalized_keyword) >= 2 and normalized_keyword in query:
                score += 7
                reasons.append(f"用户描述命中关键词 {keyword}")
        for phrase in (*entry.applies_to, *entry.prefer_when):
            normalized_phrase = self._normalize(phrase)
            if len(normalized_phrase) >= 3 and any(part and part in query for part in re.split(r"[，,、/]+", normalized_phrase)):
                score += 2
                reasons.append("用户描述命中适用场景")
                break
        for token in tokens:
            if len(token) < 2:
                continue
            for name, text in haystacks.items():
                if token in text:
                    score += 4 if name in {"title", "keywords"} else 2
                    reasons.append(f"{name} 命中 {token}")
                    break
        return score, reasons

    def _normalize(self, value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).lower()

    def _build_entries(self) -> list[FrSettingKnowledgeEntry]:
        return [
            FrSettingKnowledgeEntry(
                entry_id="cell-format-number",
                title="数字/货币/百分比/科学计数显示格式",
                panel="单元格元素/单元格属性-格式",
                keywords=("数字", "取整", "不显示小数", "#0", "小数位", "货币", "百分比", "科学计数", "格式"),
                cpt_nodes=("C/NumberFormat", "FormatAttr", "Attributes format", "DSColumn"),
                applies_to=("数据单元格显示口径", "金额/涨跌/增减/数量的小数位控制", "不改变业务计算但改变展示"),
                prefer_when=("用户说不显示小数、保留 N 位、显示百分比、货币符号", "SQL 字段计算已正确但预览格式不符合"),
                avoid_when=("用户要求改变计算口径、四舍五入参与后续计算", "字段本身应由 SQL 聚合或转换类型保证"),
                verification=("预览文本符合小数位要求", "原 DSColumn/公式绑定未丢失", "导出结果格式同步符合预期"),
                evidence_hint=("读取目标单元格 <C> 节点", "搜索 NumberFormat/FormatAttr", "必要时参考同类数据单元格"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="cell-format-date",
                title="日期/时间显示格式",
                panel="单元格元素/单元格属性-格式",
                keywords=("日期", "时间", "yyyy", "MM", "dd", "年月日", "日期格式", "时间型"),
                cpt_nodes=("C/DateFormat", "C/NumberFormat", "TableData/Query", "DSColumn"),
                applies_to=("日期字段展示", "年月日格式", "预览日期换行或格式错误"),
                prefer_when=("用户只要求显示格式改变", "当前字段是日期类型且 FineReport 可识别格式节点"),
                avoid_when=("FineReport 预览不吃单元格日期格式", "字段已被 SQL 转成字符串或需拼接年月日"),
                verification=("预览日期文本格式正确", "列宽足够且不异常换行", "SQL 输出字段与单元格绑定一致"),
                evidence_hint=("先读目标日期单元格", "再读对应 TableData SQL", "必要时在 SQL 中 FORMAT 显示字段"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="cell-ds-column-expand",
                title="数据列绑定、分组、横向/纵向扩展",
                panel="单元格元素-数据列/单元格属性-扩展",
                keywords=("数据列", "数据集", "分组", "列表", "横向扩展", "纵向扩展", "父格", "扩展方向", "排序"),
                cpt_nodes=("C/O[@t='DSColumn']", "Attributes dsName columnName", "Expand", "RG", "cellSortAttr"),
                applies_to=("把数据库字段绑定到单元格", "市场/地区横向展开", "日期/明细纵向展开", "分组汇总"),
                prefer_when=("需求是字段放错、横向表头顺序、明细行/列扩展", "SQL 保持长表由 FineReport 展开更自然"),
                avoid_when=("只是静态表头文案修改", "字段名未经过数据库结构或数据集 SQL 验证"),
                verification=("预览行列扩展方向正确", "表头与数据列对齐", "父格关系没有破坏合并区域"),
                evidence_hint=("读取相关数据单元格 <C>", "读取 TableData SQL", "检查 Expand dir 与 RG 写法"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="style-font-background-border",
                title="字体、背景、边框和基础样式",
                panel="单元格属性-样式-文本/单元格",
                keywords=("字体", "字号", "加粗", "颜色", "背景", "边框", "外边框", "内边框", "表头蓝底", "样式"),
                cpt_nodes=("StyleList", "Style", "FRFont", "Background", "Border", "FineColor", "C@s"),
                applies_to=("表头样式", "数据区样式", "边框补齐", "背景色和字体色"),
                prefer_when=("用户明确改视觉样式", "需要延续当前报表已有 StyleList"),
                avoid_when=("只改数据口径或 SQL", "多个单元格共用同一 style 且修改会误伤其他区域"),
                verification=("预览样式区域正确", "共享样式没有误伤无关单元格", "导出/打印保持边框和背景"),
                evidence_hint=("先查目标单元格 s 属性", "读取 StyleList", "必要时克隆 Style 再改 C@s"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="style-alignment-text-control",
                title="水平/垂直对齐、自动换行、缩进、文本方向",
                panel="单元格属性-样式-对齐",
                keywords=("水平对齐", "垂直对齐", "居中", "右对齐", "自动换行", "缩进", "文本方向", "行间距", "段间距"),
                cpt_nodes=("Style", "horizontal_alignment", "vertical_alignment", "TextAttr", "C@s", "ColumnWidth", "RowHeight"),
                applies_to=("表头居中", "数字右对齐", "文本换行", "长日期显示"),
                prefer_when=("用户关注文本排版或显示不完整", "隐藏列/字段变长后需要联动排版"),
                avoid_when=("内容本身错误应改数据绑定或 SQL", "列宽/行高才是主要问题时只改对齐"),
                verification=("预览不遮挡、不溢出", "列宽行高与换行策略匹配", "合并单元格内对齐符合预期"),
                evidence_hint=("读取 StyleList 与 ColumnWidth/RowHeight", "对照预览截图判断是否需要尺寸联动"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="cell-shape-display-mode",
                title="单元格形态：数据字典、条形码、公式状态、金额线",
                panel="单元格属性-形态",
                keywords=("形态", "数据字典", "条形码", "公式状态", "金额线", "显示形态"),
                cpt_nodes=("C/CellGUIAttr", "C/Widget", "Dictionary", "Barcode", "CellElement", "HighlightList"),
                applies_to=("代码转中文显示", "条码/二维码展示", "金额线或特殊状态展示"),
                prefer_when=("用户说用字典显示中文、显示条码、金额线", "值和展示文本需要分离"),
                avoid_when=("只是下拉输入控件，应看 Widget/ComboBox", "数据本身要转换时可能应改 SQL"),
                verification=("预览显示值正确", "原始值仍可用于排序/过滤/写回", "导出表现符合业务预期"),
                evidence_hint=("搜索 Dictionary/Barcode/CellGUIAttr", "参考已有形态类报表案例"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="cell-other-print-export-pagination",
                title="显示、打印导出、分页和内容提示",
                panel="单元格属性-其他",
                keywords=("打印", "导出", "分页", "行前分页", "列后分页", "内容提示", "超出隐藏", "显示内容", "导出背景"),
                cpt_nodes=("C/CellAttr", "ReportPageAttr", "PageAttr", "Visible", "Print", "Export", "RowHeight", "ColumnWidth"),
                applies_to=("某些内容只预览不导出", "分页控制", "文本超出隐藏", "打印导出背景控制"),
                prefer_when=("用户要求打印/导出/分页/显示隐藏差异", "预览与导出表现需要不同"),
                avoid_when=("普通隐藏整列/整行优先看 ReportPageAttr 的 HC/HR", "数据过滤不应通过显示隐藏伪装"),
                verification=("预览、打印、导出分别验证", "分页位置正确", "隐藏内容不影响数据集执行"),
                evidence_hint=("读取目标单元格和 ReportPageAttr", "检查是否已有分页或导出设置"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="floating-elements",
                title="悬浮元素：图片、图表、水印和说明元素",
                panel="悬浮元素",
                keywords=("悬浮元素", "图片", "logo", "水印", "图表", "浮动", "添加元素"),
                cpt_nodes=("FloatElement", "FloatElementList", "Picture", "Chart", "WidgetChart"),
                applies_to=("添加 logo/水印", "浮动图表", "说明图片不占单元格网格"),
                prefer_when=("用户要求图片或图表浮在报表上", "不希望改变单元格布局"),
                avoid_when=("图片应绑定在某个单元格内", "需要参与表格扩展或打印分页的内容"),
                verification=("预览位置、层级和打印效果正确", "不遮挡数据区", "图片资源路径可访问"),
                evidence_hint=("搜索 FloatElement/Picture/Chart", "参考带图片或图表的 CPT"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="widget-input-control",
                title="控件：数字、文本、日期、下拉和校验",
                panel="控件设置",
                keywords=("控件", "数字控件", "文本控件", "日期控件", "下拉", "可用", "可见", "水印", "校验", "允许小数", "最大值", "最小值"),
                cpt_nodes=("C/Widget", "TextEditor", "NumberEditor", "DateEditor", "ComboBox", "WidgetAttr", "Reg"),
                applies_to=("填报输入", "参数输入", "单元格下拉", "数字校验"),
                prefer_when=("用户明确说输入框、下拉框、允许小数、校验", "需要用户在报表中编辑或选择"),
                avoid_when=("只是数据展示格式，应优先 NumberFormat/DateFormat", "候选值过大时应避免每个单元格重复查字典"),
                verification=("控件在预览/填报模式可用", "校验规则正确", "下拉候选有数据且性能可接受"),
                evidence_hint=("读取目标单元格 Widget", "读取参数栏或参考 ComboBox 案例", "必要时查询候选数据"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="conditional-highlight",
                title="条件属性：按公式高亮、颜色、字体和背景变化",
                panel="条件属性",
                keywords=("条件属性", "高亮", "条件", "正数", "负数", "大于", "小于", "颜色", "涨跌红绿"),
                cpt_nodes=("HighlightList", "DefaultHighlight", "FormulaCondition", "HighlightAction", "Foreground", "Background"),
                applies_to=("正负数颜色", "超过阈值高亮", "条件背景/字体变化"),
                prefer_when=("用户要求满足条件时变色或隐藏", "数据值本身不变只改视觉反馈"),
                avoid_when=("条件影响筛选或计算结果，应改 SQL/filter", "公式引用坐标未确认时不能硬猜"),
                verification=("正负/阈值样例都验证", "公式使用当前单元格 $$$ 或正确引用", "样式与已有条件不冲突"),
                evidence_hint=("读取目标单元格 HighlightList", "查询样例数据覆盖正负/阈值"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="hyperlink-drilldown",
                title="超级链接：跳转明细、外部链接和参数联动",
                panel="超级链接",
                keywords=("超级链接", "跳转", "钻取", "明细", "链接", "打开", "联动", "传参"),
                cpt_nodes=("Hyperlink", "JavaScript", "Parameter", "ReportletHyperlink", "URLHyperlink"),
                applies_to=("点击单元格跳明细报表", "打开外部 URL", "带参数联动"),
                prefer_when=("用户要求点击查看明细或跳转", "当前值需要作为参数传给另一个报表"),
                avoid_when=("只是展示 URL 文本", "目标报表路径或参数名未知且无法读取"),
                verification=("点击行为可用", "参数值传递正确", "无权限或路径不存在时有可读失败提示"),
                evidence_hint=("读取目标单元格超链节点", "读取目标报表参数或参考超链案例"),
            ),
            FrSettingKnowledgeEntry(
                entry_id="writeback-submit",
                title="填报写回、提交和校验",
                panel="填报/控件/其他",
                keywords=("填报", "写回", "提交", "校验", "新增行", "删除行", "主键", "报送"),
                cpt_nodes=("ReportWriteAttr", "ReportWebAttr", "SubmitJob", "Widget", "Reg", "TableData"),
                applies_to=("填报报表", "单元格编辑并写回数据库", "提交前校验"),
                prefer_when=("用户要求可编辑、保存、提交、校验规则", "需要区分只读字段和可写字段"),
                avoid_when=("普通查看报表不应加填报配置", "没有主键/写回表/权限边界时不要直接提交"),
                verification=("以 op=write 预览", "提交按钮、校验、写回字段和主键正确", "版本和权限边界清晰"),
                evidence_hint=("读取 ReportWriteAttr/ReportWebAttr", "检查 Widget 与数据库字段对应关系"),
            ),
        ]


fr_setting_knowledge_service = FrSettingKnowledgeService()
