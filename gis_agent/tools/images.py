from pathlib import Path
from typing import Any

from gis_agent.persistence.images import save_image
from gis_agent.tools.base import Tool


def make_image_tool(directory: Path) -> Tool:
    count = [0]

    def _read_image(path: str, crop: list[int] | None = None) -> dict[str, Any]:
        res = save_image(path=path, crop=crop, directory=directory)
        if res.get("ok"):
            count[0] += 1
            res["read_image_calls"] = count[0]
            if count[0] >= 3:
                res["budget_notice"] = (
                    f"本会话已调用 read_image {count[0]} 次。"
                    "若 layout_diagnostics 全部警告为 false 且无明显遮挡/裁切，"
                    "请立即导出最终 PNG+SVG 并调用 finish_task，严禁继续连续切块微调。"
                )
        return res

    return Tool(
        name="read_image",
        description=(
            "读取本地静态 PNG、JPEG 或 WebP，下一次模型请求会实际包含图片。"
            "省略 crop 时查看整图；crop 为原图像素坐标 [left, top, right, bottom]，右下边界不包含。"
            "用于查看地图、图例和标注；需要再次查看时重新调用。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "crop": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0},
                    "minItems": 4,
                    "maxItems": 4,
                    "description": "原图像素区域 [left, top, right, bottom]，省略时读取整图。",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        function=_read_image,
    )
