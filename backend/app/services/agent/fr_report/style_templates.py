from dataclasses import dataclass


FR_COLOR_OFFSET = 0x1000000


def fr_color(hex_color: str) -> int:
    value = int(hex_color.lstrip("#"), 16)
    return value - FR_COLOR_OFFSET if value >= 0x800000 else value


@dataclass(frozen=True)
class FrReportTextStyle:
    font_family: str
    font_size: int
    bold: bool = False
    color: str = "#000000"

    @property
    def fr_font_style(self) -> int:
        return 1 if self.bold else 0

    @property
    def fr_color(self) -> int:
        return fr_color(self.color)


@dataclass(frozen=True)
class FrReportAreaStyle:
    text: FrReportTextStyle
    background_color: str = "#FFFFFF"
    border_color: str = "#bdcbe6"
    horizontal_alignment: int = 0
    vertical_alignment: int = 0

    @property
    def fr_background_color(self) -> int:
        return fr_color(self.background_color)

    @property
    def fr_border_color(self) -> int:
        return fr_color(self.border_color)


@dataclass(frozen=True)
class FrReportStyleTemplate:
    template_id: str
    name: str
    source_object_path: str
    title: FrReportAreaStyle
    header: FrReportAreaStyle
    body_text: FrReportAreaStyle
    body_number: FrReportAreaStyle
    body_date: FrReportAreaStyle
    title_row_height: int
    header_row_height: int
    data_row_height: int
    default_column_width: int = 2743200
    parameter_bar_height: int = 80
    min_paper_width: int = 100800000
    max_paper_width: int = 180000000
    paper_height: int = 42768000
    paper_margin_top: int = 986400
    paper_margin_left: int = 2743200
    paper_margin_bottom: int = 986400
    paper_margin_right: int = 2743200

    def to_reference(self) -> dict[str, object]:
        return {
            "templateId": self.template_id,
            "name": self.name,
            "sourceObjectPath": self.source_object_path,
            "font": {
                "title": {
                    "family": self.title.text.font_family,
                    "size": 13,
                    "bold": self.title.text.bold,
                },
                "header": {
                    "family": self.header.text.font_family,
                    "size": 10,
                    "bold": self.header.text.bold,
                },
                "body": {
                    "family": self.body_text.text.font_family,
                    "size": 10,
                    "bold": self.body_text.text.bold,
                },
            },
            "colors": {
                "titleBackground": self.title.background_color,
                "headerBackground": self.header.background_color,
                "bodyBackground": self.body_text.background_color,
                "text": self.body_text.text.color,
                "border": self.header.border_color,
            },
            "rowHeights": {
                "title": "13mm",
                "header": "10mm",
                "data": "10mm",
            },
            "alignment": {
                "title": "center/middle",
                "header": "center/middle",
                "text": "left/middle",
                "number": "right/middle",
                "date": "center/middle",
            },
            "paper": {
                "minWidth": self.min_paper_width,
                "maxWidth": self.max_paper_width,
                "height": self.paper_height,
                "margin": {
                    "top": self.paper_margin_top,
                    "left": self.paper_margin_left,
                    "bottom": self.paper_margin_bottom,
                    "right": self.paper_margin_right,
                },
            },
        }


GRAIN_SOYBEAN_WEEKLY_STYLE_TEMPLATE = FrReportStyleTemplate(
    template_id="grain_soybean_weekly",
    name="谷物大豆国际海运费报价-周报",
    source_object_path="webroot/APP/reportlets/数据分析/农产品价格平台/大豆/谷物大豆国际海运费报价-周报.cpt",
    title=FrReportAreaStyle(
        text=FrReportTextStyle(font_family="微软雅黑", font_size=104, bold=True),
        background_color="#FFFFFF",
        border_color="#FFFFFF",
        horizontal_alignment=0,
    ),
    header=FrReportAreaStyle(
        text=FrReportTextStyle(font_family="SimSun", font_size=80, bold=True),
        background_color="#e2eaff",
        border_color="#bdcbe6",
        horizontal_alignment=0,
    ),
    body_text=FrReportAreaStyle(
        text=FrReportTextStyle(font_family="SimSun", font_size=80),
        background_color="#FFFFFF",
        border_color="#bdcbe6",
        horizontal_alignment=1,
    ),
    body_number=FrReportAreaStyle(
        text=FrReportTextStyle(font_family="SimSun", font_size=80),
        background_color="#FFFFFF",
        border_color="#bdcbe6",
        horizontal_alignment=2,
    ),
    body_date=FrReportAreaStyle(
        text=FrReportTextStyle(font_family="SimSun", font_size=80),
        background_color="#FFFFFF",
        border_color="#bdcbe6",
        horizontal_alignment=0,
    ),
    title_row_height=1497600,
    header_row_height=1152000,
    data_row_height=1152000,
)


DEFAULT_STYLE_TEMPLATE = GRAIN_SOYBEAN_WEEKLY_STYLE_TEMPLATE
