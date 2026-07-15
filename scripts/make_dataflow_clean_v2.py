from pathlib import Path
from xml.sax.saxutils import escape


def vertex(id_: str, value: str, style: str, x: int, y: int, w: int, h: int) -> str:
    return (
        f'                <mxCell id="{id_}" value="{escape(value)}" '
        f'style="{escape(style)}" parent="1" vertex="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>'
        f'</mxCell>'
    )


def edge(
    id_: str,
    source: str,
    target: str,
    value: str = "",
    points: list[tuple[int, int]] | None = None,
    dashed: bool = False,
) -> str:
    style = (
        "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;"
        "endArrow=classic;strokeColor=#333333;fontSize=12;"
    )
    if dashed:
        style += "dashed=1;"
    point_xml = ""
    if points:
        point_xml = "<Array as=\"points\">" + "".join(
            f'<mxPoint x="{x}" y="{y}"/>' for x, y in points
        ) + "</Array>"
    return (
        f'                <mxCell id="{id_}" value="{escape(value)}" '
        f'style="{escape(style)}" parent="1" source="{source}" target="{target}" edge="1">'
        f'<mxGeometry relative="1" as="geometry">{point_xml}</mxGeometry>'
        f'</mxCell>'
    )


def main() -> None:
    base = next(Path.cwd().glob("*2026")) / "diagrams"
    out = base / "4_推荐数据流图_清晰版.drawio"

    title = "text;html=1;fontSize=26;fontStyle=1;align=center;verticalAlign=middle;"
    process = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=15;strokeWidth=1.6;fillColor=#dae8fc;strokeColor=#6c8ebf;"
    branch = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=15;strokeWidth=1.6;fillColor=#e1f0d8;strokeColor=#82b366;"
    model = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=15;strokeWidth=1.6;fillColor=#ffe6cc;strokeColor=#d79b00;"
    llm = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=15;strokeWidth=1.6;fillColor=#f8cecc;strokeColor=#b85450;"
    data = "shape=partialRectangle;whiteSpace=wrap;html=1;right=0;fontSize=14;strokeWidth=1.5;fillColor=#ffffff;strokeColor=#00a878;"
    store = "shape=cylinder3d;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;size=15;fontSize=14;strokeWidth=1.5;fillColor=#ffffff;strokeColor=#00a878;"
    note = "rounded=1;whiteSpace=wrap;html=1;arcSize=8;fontSize=14;strokeWidth=1.2;fillColor=#f5f5f5;strokeColor=#666666;dashed=1;"

    nodes = [
        vertex("title", "MovieHub 推荐数据流图", title, 500, 20, 420, 45),
        vertex("front", "前端推荐页面", process, 60, 115, 170, 60),
        vertex("api", "推荐任务接口", process, 300, 115, 170, 60),
        vertex("context", "用户偏好上下文", process, 540, 115, 190, 60),
        vertex("cache", "D1 推荐缓存", data, 820, 95, 170, 45),
        vertex("userdb", "D2 用户行为数据", data, 820, 160, 190, 45),
        vertex("pref", "偏好分解", llm, 90, 290, 170, 60),
        vertex("rag", "RAG 向量检索", branch, 350, 290, 180, 60),
        vertex("kg", "Multi-MoE<br>链接预测", model, 610, 290, 190, 60),
        vertex("tmdb", "TMDB 近期影片<br>补充", process, 890, 290, 190, 60),
        vertex("llm", "外部大模型", note, 90, 405, 170, 55),
        vertex("ragdb", "D3 电影向量库", store, 350, 405, 180, 55),
        vertex("kgdb", "D4 知识图谱数据", store, 610, 405, 190, 55),
        vertex("moviedb", "D5 影片基础数据", store, 890, 405, 190, 55),
        vertex("merge", "候选集合<br>KG / RAG / TMDB", model, 510, 555, 240, 65),
        vertex("filter", "合并去重<br>负反馈过滤", llm, 820, 555, 190, 65),
        vertex("rank", "审核定榜<br>生成解释", llm, 1090, 555, 190, 65),
        vertex("card", "补全卡片信息", process, 1090, 705, 190, 60),
        vertex("log", "D6 推荐日志", data, 540, 730, 170, 45),
        vertex("notice", "D7 用户通知", data, 770, 730, 170, 45),
    ]

    edges = [
        edge("e1", "front", "api", "推荐参数"),
        edge("e2", "api", "cache", "查询"),
        edge("e3", "api", "context", "未命中"),
        edge("e4", "context", "userdb", "读取"),
        edge("e5", "context", "pref", "偏好文本", points=[(635, 240), (175, 240)]),
        edge("e6", "context", "rag", "检索词", points=[(635, 240), (440, 240)]),
        edge("e7", "context", "kg", "种子实体", points=[(635, 240), (705, 240)]),
        edge("e8", "context", "tmdb", "近期偏好", points=[(635, 240), (985, 240)]),
        edge("e9", "pref", "llm", "解析"),
        edge("e10", "rag", "ragdb", "查询"),
        edge("e11", "kg", "kgdb", "查询"),
        edge("e12", "tmdb", "moviedb", "查询"),
        edge("e13", "rag", "merge", "RAG候选", points=[(440, 500)]),
        edge("e14", "kg", "merge", "KG候选", points=[(705, 500)]),
        edge("e15", "tmdb", "merge", "近期候选", points=[(985, 500), (630, 500)]),
        edge("e16", "merge", "filter", "候选"),
        edge("e17", "filter", "rank", "初榜"),
        edge("e18", "rank", "card", "定榜结果"),
        edge("e19", "card", "front", "推荐结果", points=[(1185, 835), (145, 835)]),
        edge("e20", "card", "log", "写入", points=[(1185, 790), (625, 790)]),
        edge("e21", "card", "notice", "写入", points=[(1185, 790), (855, 790)]),
        edge("e22", "card", "cache", "写入", points=[(1185, 90), (905, 90)], dashed=True),
    ]

    xml = """<mxfile host="65bd71144e">
    <diagram name="推荐数据流图" id="recommend-data-flow-clean-v2">
        <mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="1400" pageHeight="900" math="0" shadow="0">
            <root>
                <mxCell id="0"/>
                <mxCell id="1" parent="0"/>
%s
            </root>
        </mxGraphModel>
    </diagram>
</mxfile>
""" % "\n".join(nodes + edges)

    out.write_text(xml, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
