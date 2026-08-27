# -*- coding: utf-8 -*-
"""
水印相机风格服务（自 TOA2 watermark_processor 迁移）。

为图片添加时间 / 日期星期 / 地点 /「水印相机」角标。
"""
from __future__ import annotations

import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
GRADUATION_KEYWORDS = ("集体合影", "结业合影", "结业典礼", "结业照")

# 目录分类关键字（相对路径匹配）
CATEGORY_RULES = (
    ("ta_checkin", ("助教打卡",)),
    ("classroom_setup", ("教室布置",)),
    ("student_checkin", ("学员签到",)),
    ("group_photo", ("集体合影", "结业合影")),
    ("signed_docs", ("签署文件",)),
    ("materials", ("剩余物料",)),
    ("delivery_ppt", ("交付PPT", "助教简历")),
    ("teaching", ("授课期间",)),
)

CATEGORY_LABELS = {
    "ta_checkin": "助教打卡",
    "classroom_setup": "教室布置",
    "student_checkin": "学员签到",
    "group_photo": "集体合影",
    "signed_docs": "签署文件",
    "materials": "物料处置",
    "delivery_ppt": "交付PPT",
    "teaching": "授课照片",
    "other": "其他",
}


class WatermarkProcessor:
    """按「水印相机」样片样式绘制并批量处理图片。"""

    def __init__(self):
        self._font_cache = {}

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def collect_images(self, root_dir: str) -> List[str]:
        """递归收集目录下全部图片路径。"""
        results: List[str] = []
        if not root_dir or not os.path.isdir(root_dir):
            return results
        for dirpath, _, filenames in os.walk(root_dir):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    results.append(os.path.join(dirpath, name))
        results.sort()
        return results

    def apply_watermark(
        self,
        image_path: str,
        date_text: str,
        location: str,
        time_text: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> bool:
        """
        给单张图片加水印并保存。

        Args:
            image_path: 原图路径
            date_text: 日期，支持 YYYY.MM.DD / YYYY-MM-DD / YYYY/MM/DD
            location: 地址文案
            time_text: 可选 HH:MM；为空则优先读 EXIF，再回退文件修改时间
            output_path: 输出路径，默认覆盖原文件
        """
        try:
            with Image.open(image_path) as src:
                img = src.convert("RGBA")
                # 保留 EXIF，便于覆盖保存时写回
                exif_bytes = src.info.get("exif")

            display_time = (time_text or "").strip() or self._resolve_time(image_path, img)
            date_line = self._build_date_location_line(date_text, location)
            result = self._draw_watermark(img, display_time, date_line)

            save_path = output_path or image_path
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            self._save_image(result, save_path, exif_bytes)
            return True
        except Exception as exc:
            logger.error("加水印失败 %s: %s", image_path, exc, exc_info=True)
            return False

    def process_directory(
        self,
        root_dir: str,
        location: str,
        start_date: str,
        end_date: str,
        start_time: str = "09:00",
        end_time: str = "18:00",
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        overwrite: bool = True,
        # 兼容旧参数
        date_text: Optional[str] = None,
        time_text: Optional[str] = None,
    ) -> Tuple[int, int, List[str]]:
        """
        递归处理班级目录内图片，按子目录业务规则分配日期/时间后加水印。

        规则概要（以班级名中的开课/结课日为准）：
        - 01 助教打卡：开课前一天起，早晚各一张（早约 08:30，晚 17-19）
        - 02 教室布置：开课前一天，15-19 点
        - 03 授课期间：课程期内均分（约每天 2-3 张量级），默认 09-17 点
        - 0301 学员签到：课程期内，08-09 点
        - 0310 集体合影：最后一天
        - 04 签署文件 / 06 物料处置：最后一天，12-19 点
        """
        del date_text, time_text, start_time, end_time
        start_dt = self.parse_date(start_date)
        end_dt = self.parse_date(end_date)
        if not start_dt or not end_dt:
            raise ValueError("开始日期或结束日期无效")
        if end_dt.date() < start_dt.date():
            raise ValueError("结束日期不能早于开始日期")

        images = self.collect_images(root_dir)
        plan = self.plan_watermark_datetimes(root_dir, images, start_dt, end_dt)
        success = 0
        failed_paths: List[str] = []
        total = len(images)

        for index, path in enumerate(images, start=1):
            if progress_callback:
                progress_callback(index, total, path)
            out = path if overwrite else self._sibling_output_path(path)
            date_for_photo, time_for_photo = plan[path]
            ok = self.apply_watermark(
                path,
                date_for_photo,
                location,
                time_text=time_for_photo,
                output_path=out,
            )
            if ok:
                success += 1
            else:
                failed_paths.append(path)

        return success, len(failed_paths), failed_paths

    def generate_preview_image(
        self,
        photo_path: str,
        date_text: str,
        location: str,
        time_text: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_time: str = "09:00",
        end_time: str = "18:00",
        root_dir: Optional[str] = None,
        all_images: Optional[List[str]] = None,
        max_side: int = 720,
    ) -> Optional[Image.Image]:
        """生成预览图（不写盘）。优先按班级目录规则分配日期时间。"""
        del start_time, end_time
        try:
            with Image.open(photo_path) as src:
                img = src.convert("RGBA")

            display_date = (date_text or "").strip()
            display_time = (time_text or "").strip()

            start_dt = self.parse_date(start_date) if start_date else None
            end_dt = self.parse_date(end_date) if end_date else None
            if start_dt and end_dt:
                root = root_dir or os.path.dirname(photo_path)
                images = all_images or self.collect_images(root)
                if photo_path not in images:
                    images = sorted(set(images + [photo_path]))
                plan = self.plan_watermark_datetimes(root, images, start_dt, end_dt)
                display_date, planned_time = plan.get(photo_path, (display_date, display_time))
                if not display_time:
                    display_time = planned_time
            if not display_time:
                display_time = self._resolve_time(photo_path, img)
            if not display_date:
                display_date = datetime.now().strftime("%Y.%m.%d")

            date_line = self._build_date_location_line(display_date, location)
            result = self._draw_watermark(img, display_time, date_line)
            w, h = result.size
            if max(w, h) > max_side:
                scale = max_side / max(w, h)
                result = result.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            return result
        except Exception as exc:
            logger.error("生成预览失败: %s", exc, exc_info=True)
            return None

    # ------------------------------------------------------------------ #
    # 班级目录日期 / 时间规划
    # ------------------------------------------------------------------ #
    @staticmethod
    def classify_image(image_path: str, root_dir: Optional[str] = None) -> str:
        """按相对路径归类图片所属业务目录。"""
        rel = image_path
        if root_dir:
            try:
                rel = os.path.relpath(image_path, root_dir)
            except ValueError:
                rel = image_path
        text = rel.replace("\\", "/")
        for category, keywords in CATEGORY_RULES:
            if any(k in text for k in keywords):
                return category
        return "other"

    @staticmethod
    def category_label(category: str) -> str:
        return CATEGORY_LABELS.get(category, category)

    @staticmethod
    def is_graduation_photo(image_path: str) -> bool:
        """路径或文件名含集体合影相关关键字。"""
        text = (image_path or "").replace("\\", "/").lower()
        return any(keyword.lower() in text for keyword in GRADUATION_KEYWORDS)

    def plan_watermark_datetimes(
        self,
        root_dir: str,
        images: List[str],
        start_dt: datetime,
        end_dt: datetime,
    ) -> dict:
        """
        为班级目录内全部图片规划 (日期字符串, 时间字符串)。

        返回: {image_path: ("YYYY.MM.DD", "HH:MM")}
        """
        start_day = start_dt.date()
        end_day = end_dt.date()
        day_before = start_day - timedelta(days=1)
        course_days = self._date_range(start_day, end_day)
        ta_days = self._date_range(day_before, end_day)

        groups: dict = {key: [] for key, _ in CATEGORY_RULES}
        groups["other"] = []
        for path in images:
            groups[self.classify_image(path, root_dir)].append(path)

        plan: dict = {}

        # 01 助教打卡：开课前一天起，早晚各一张
        ta_slots = []
        for day in ta_days:
            morning = self._jitter_hhmm(8, 30, jitter_minutes=5)
            evening = self.random_time_in_range(17 * 60, 19 * 60)
            ta_slots.append((day, morning))
            ta_slots.append((day, evening))
        self._assign_slots(plan, groups["ta_checkin"], ta_slots)

        # 02 教室布置：开课前一天 15-19
        setup_slots = [
            (day_before, self.random_time_in_range(15 * 60, 19 * 60))
            for _ in groups["classroom_setup"]
        ]
        self._assign_slots(plan, groups["classroom_setup"], setup_slots)

        # 0301 学员签到：课程期每天尽量 1 张，08-09
        checkin_slots = []
        if groups["student_checkin"]:
            for i, _ in enumerate(groups["student_checkin"]):
                day = course_days[i % len(course_days)]
                checkin_slots.append((day, self.random_time_in_range(8 * 60, 9 * 60)))
        self._assign_slots(plan, groups["student_checkin"], checkin_slots)

        # 0310 集体合影：最后一天（下午居多）
        group_slots = [
            (end_day, self.random_time_in_range(16 * 60, 18 * 60))
            for _ in groups["group_photo"]
        ]
        self._assign_slots(plan, groups["group_photo"], group_slots)

        # 03 其他授课照片：课程期均分，约每天 2-3 张量级；时间 09-17
        teaching_slots = self._build_even_day_slots(
            groups["teaching"],
            course_days,
            time_lo=9 * 60,
            time_hi=17 * 60,
            prefer_per_day=(2, 3),
        )
        self._assign_slots(plan, groups["teaching"], teaching_slots)

        # 04 / 06：最后一天 12-19
        closing_paths = groups["signed_docs"] + groups["materials"]
        closing_slots = [
            (end_day, self.random_time_in_range(12 * 60, 19 * 60))
            for _ in closing_paths
        ]
        self._assign_slots(plan, closing_paths, closing_slots)

        # 其他 / 交付PPT 下图片：课程期随机，09-18
        leftover = groups["other"] + groups["delivery_ppt"]
        other_slots = [
            (random.choice(course_days), self.random_time_in_range(9 * 60, 18 * 60))
            for _ in leftover
        ]
        self._assign_slots(plan, leftover, other_slots)

        return plan

    @staticmethod
    def _date_range(start_day, end_day):
        days = []
        cur = start_day
        while cur <= end_day:
            days.append(cur)
            cur += timedelta(days=1)
        return days or [start_day]

    @staticmethod
    def _format_day(day) -> str:
        return day.strftime("%Y.%m.%d")

    @staticmethod
    def _jitter_hhmm(hour: int, minute: int, jitter_minutes: int = 0) -> str:
        base = hour * 60 + minute
        if jitter_minutes > 0:
            base += random.randint(-jitter_minutes, jitter_minutes)
        base = max(0, min(base, 23 * 60 + 59))
        return f"{base // 60:02d}:{base % 60:02d}"

    def _build_even_day_slots(
        self,
        paths: List[str],
        days: List,
        time_lo: int,
        time_hi: int,
        prefer_per_day: Tuple[int, int] = (2, 3),
    ) -> List[Tuple]:
        """把照片均匀分到各授课日，同日时间升序，更贴近真实拍摄。"""
        del prefer_per_day
        if not paths:
            return []
        if not days:
            days = [datetime.now().date()]
        n = len(paths)
        dcount = len(days)
        day_indices: dict = {d: [] for d in days}
        for i in range(n):
            day_indices[days[i % dcount]].append(i)
        assignments: List[Optional[Tuple]] = [None] * n
        for day, idxs in day_indices.items():
            times = sorted(self.random_time_in_range(time_lo, time_hi) for _ in idxs)
            for idx, t in zip(idxs, times):
                assignments[idx] = (day, t)
        return [a if a is not None else (days[-1], self.random_time_in_range(time_lo, time_hi)) for a in assignments]

    def _assign_slots(self, plan: dict, paths: List[str], slots: List[Tuple]) -> None:
        for i, path in enumerate(paths):
            if i < len(slots):
                day, time_text = slots[i]
            elif slots:
                day, time_text = slots[i % len(slots)]
                if isinstance(time_text, str) and ":" in time_text:
                    # 超出槽位时时间再随机扰动，避免完全重复
                    hm = self.parse_hhmm(time_text) or (12 * 60)
                    time_text = self.random_time_in_range(max(0, hm - 30), min(23 * 60 + 59, hm + 30))
            else:
                day = datetime.now().date()
                time_text = self.random_time_in_range(9 * 60, 18 * 60)
            plan[path] = (self._format_day(day), time_text)

    def pick_date_for_image(
        self,
        image_path: str,
        start_dt: datetime,
        end_dt: datetime,
        root_dir: Optional[str] = None,
    ) -> datetime:
        """兼容旧逻辑：按规则取单张日期（批量请用 plan_watermark_datetimes）。"""
        plan = self.plan_watermark_datetimes(root_dir or os.path.dirname(image_path), [image_path], start_dt, end_dt)
        date_text, _ = plan[image_path]
        return self.parse_date(date_text) or start_dt

    @staticmethod
    def parse_hhmm(value: str) -> Optional[int]:
        """解析 HH:MM，返回当日分钟数。"""
        text = (value or "").strip()
        try:
            dt = datetime.strptime(text, "%H:%M")
            return dt.hour * 60 + dt.minute
        except ValueError:
            return None

    def resolve_time_range(self, start_time: str, end_time: str) -> Tuple[int, int]:
        """解析用户起止时间（不再强制裁到 09-18，以支持助教早签/晚签）。"""
        start_m = self.parse_hhmm(start_time)
        end_m = self.parse_hhmm(end_time)
        if start_m is None or end_m is None:
            raise ValueError("开始时间或结束时间格式应为 HH:MM")
        if end_m < start_m:
            raise ValueError("结束时间不能早于开始时间")
        return start_m, end_m

    @staticmethod
    def random_time_in_range(start_minutes: int, end_minutes: int) -> str:
        """在分钟区间内随机生成 HH:MM。"""
        if end_minutes < start_minutes:
            start_minutes, end_minutes = end_minutes, start_minutes
        minute = random.randint(start_minutes, end_minutes)
        return f"{minute // 60:02d}:{minute % 60:02d}"

    @staticmethod
    def extract_dates_from_folder_name(folder_path: str) -> Tuple[Optional[str], Optional[str]]:
        """从目录名解析 YYYYMMDD-YYYYMMDD，返回 (开始日期, 结束日期) 字符串。"""
        name = os.path.basename(folder_path.rstrip("\\/"))
        match = re.search(r"(20\d{6})\D+(20\d{6})", name)
        if not match:
            return None, None
        try:
            start = datetime.strptime(match.group(1), "%Y%m%d")
            end = datetime.strptime(match.group(2), "%Y%m%d")
            return start.strftime("%Y.%m.%d"), end.strftime("%Y.%m.%d")
        except ValueError:
            return None, None

    # 兼容旧接口名称
    def generate_watermarked_photo(
        self,
        template_type="simple",
        photo_path=None,
        output_path=None,
        date_time=None,
        location=None,
        progress_callback=None,
        watermark_params=None,
        use_image_watermark=False,
    ):
        """兼容旧调用：date_time 可为 HH:MM 或完整日期时间。"""
        del template_type, watermark_params, use_image_watermark
        if progress_callback:
            progress_callback(30)
        time_text, date_text = self._split_datetime_fields(date_time)
        if not date_text:
            date_text = datetime.now().strftime("%Y.%m.%d")
        if progress_callback:
            progress_callback(70)
        ok = self.apply_watermark(
            photo_path,
            date_text,
            location or "",
            time_text=time_text,
            output_path=output_path,
        )
        if progress_callback:
            progress_callback(100)
        return ok

    def get_all_styles(self):
        return {"watermark_camera": {"name": "水印相机"}}

    def get_style_params(self, style_name):
        return {"name": style_name}

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def _draw_watermark(self, img: Image.Image, time_text: str, date_line: str) -> Image.Image:
        width, height = img.size
        base = img.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 字号相对短边，保证横竖图比例接近样片
        short = min(width, height)
        time_size = max(28, int(short * 0.078))
        info_size = max(12, int(short * 0.028))
        brand_size = max(10, int(short * 0.016))
        pin_size = max(14, int(info_size * 1.15))

        time_font = self._load_font(time_size, bold=True)
        info_font = self._load_font(info_size, bold=False)
        brand_font = self._load_font(brand_size, bold=False)

        # 垂直位置：时间中心约 75.8%，信息行约 87.3%（对齐样片）
        time_cy = int(height * 0.758)
        info_cy = int(height * 0.873)

        self._draw_text_centered(
            draw,
            time_text,
            (width // 2, time_cy),
            time_font,
            fill=(255, 255, 255, 255),
            shadow=True,
        )

        self._draw_info_line_centered(
            overlay,
            draw,
            date_line,
            (width // 2, info_cy),
            info_font,
            pin_size,
        )

        # 右下角「水印相机」
        brand = "水印相机"
        brand_bbox = draw.textbbox((0, 0), brand, font=brand_font)
        brand_w = brand_bbox[2] - brand_bbox[0]
        brand_h = brand_bbox[3] - brand_bbox[1]
        margin_x = max(8, int(width * 0.018))
        margin_y = max(6, int(height * 0.018))
        brand_x = width - margin_x - brand_w
        brand_y = height - margin_y - brand_h
        self._draw_text_with_shadow(
            draw,
            brand,
            (brand_x, brand_y),
            brand_font,
            fill=(255, 255, 255, 200),
            shadow_fill=(0, 0, 0, 90),
        )

        return Image.alpha_composite(base, overlay)

    def _draw_info_line_centered(
        self,
        overlay: Image.Image,
        draw: ImageDraw.ImageDraw,
        date_line: str,
        center: Tuple[int, int],
        font: ImageFont.FreeTypeFont,
        pin_size: int,
    ) -> None:
        """绘制「日期 星期 [红钉] 地址」，整行水平居中。"""
        # date_line 格式：前半「日期 星期」，后半为地址；用分隔标记拆分
        if "|||" in date_line:
            left_text, location = date_line.split("|||", 1)
        else:
            left_text, location = date_line, ""

        left_text = left_text.strip()
        location = location.strip()
        gap = max(6, pin_size // 3)
        pin = self._create_pin_icon(pin_size)

        left_bbox = draw.textbbox((0, 0), left_text, font=font) if left_text else (0, 0, 0, 0)
        loc_bbox = draw.textbbox((0, 0), location, font=font) if location else (0, 0, 0, 0)
        left_w = left_bbox[2] - left_bbox[0]
        loc_w = loc_bbox[2] - loc_bbox[0]
        pin_w, pin_h = pin.size

        total_w = left_w + gap + pin_w + gap + loc_w
        cx, cy = center
        x = cx - total_w // 2
        # 以文字中线对齐
        left_h = left_bbox[3] - left_bbox[1]
        text_top = cy - left_h // 2

        if left_text:
            self._draw_text_with_shadow(
                draw,
                left_text,
                (x - left_bbox[0], text_top - left_bbox[1]),
                font,
                fill=(255, 255, 255, 255),
            )
            x += left_w + gap

        pin_y = cy - pin_h // 2
        overlay.paste(pin, (int(x), int(pin_y)), pin)
        x += pin_w + gap

        if location:
            loc_h = loc_bbox[3] - loc_bbox[1]
            loc_top = cy - loc_h // 2
            self._draw_text_with_shadow(
                draw,
                location,
                (x - loc_bbox[0], loc_top - loc_bbox[1]),
                font,
                fill=(255, 255, 255, 255),
            )

    def _draw_text_centered(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        center: Tuple[int, int],
        font: ImageFont.ImageFont,
        fill=(255, 255, 255, 255),
        shadow: bool = True,
    ) -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = center[0] - tw // 2 - bbox[0]
        y = center[1] - th // 2 - bbox[1]
        if shadow:
            self._draw_text_with_shadow(draw, text, (x, y), font, fill=fill)
        else:
            draw.text((x, y), text, font=font, fill=fill)

    def _draw_text_with_shadow(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        xy: Tuple[float, float],
        font: ImageFont.ImageFont,
        fill=(255, 255, 255, 255),
        shadow_fill=(0, 0, 0, 120),
    ) -> None:
        x, y = xy
        # 轻微外发光/阴影，贴近样片可读性
        for dx, dy in ((1, 1), (1, 0), (0, 1), (-1, 0), (0, -1)):
            draw.text((x + dx, y + dy), text, font=font, fill=shadow_fill)
        draw.text((x, y), text, font=font, fill=fill)

    def _create_pin_icon(self, size: int) -> Image.Image:
        """绘制红色定位钉图标。"""
        size = max(10, size)
        icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(icon)
        # 头：圆
        head_d = int(size * 0.62)
        head_x = (size - head_d) // 2
        head_y = int(size * 0.05)
        draw.ellipse(
            (head_x, head_y, head_x + head_d, head_y + head_d),
            fill=(230, 50, 50, 255),
        )
        # 内白点
        inner = max(2, head_d // 3)
        ix = head_x + (head_d - inner) // 2
        iy = head_y + (head_d - inner) // 2
        draw.ellipse((ix, iy, ix + inner, iy + inner), fill=(255, 255, 255, 255))
        # 尖角
        tip_y = size - 1
        tip_x = size // 2
        left = head_x + int(head_d * 0.12)
        right = head_x + head_d - int(head_d * 0.12)
        mid_y = head_y + int(head_d * 0.72)
        draw.polygon([(left, mid_y), (right, mid_y), (tip_x, tip_y)], fill=(230, 50, 50, 255))
        return icon

    # ------------------------------------------------------------------ #
    # 文案 / 时间 / 字体
    # ------------------------------------------------------------------ #
    def _build_date_location_line(self, date_text: str, location: str) -> str:
        date_obj = self._parse_date(date_text)
        if date_obj:
            date_fmt = date_obj.strftime("%Y.%m.%d")
            weekday = WEEKDAY_CN[date_obj.weekday()]
            left = f"{date_fmt}  {weekday}"
        else:
            left = (date_text or "").strip()
        return f"{left}|||{(location or '').strip()}"

    def parse_date(self, date_text: str) -> Optional[datetime]:
        """解析界面填写的日期字符串。"""
        text = (date_text or "").strip()
        if not text:
            return None
        # 去掉可能附带的星期
        text = re.sub(r"\s*星期[一二三四五六日天].*$", "", text).strip()
        for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日", "%Y%m%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    # 兼容旧内部调用名
    _parse_date = parse_date

    def _resolve_time(self, image_path: str, img: Optional[Image.Image] = None) -> str:
        exif_dt = self._read_exif_datetime(image_path, img)
        if exif_dt:
            return exif_dt.strftime("%H:%M")
        try:
            mtime = os.path.getmtime(image_path)
            return datetime.fromtimestamp(mtime).strftime("%H:%M")
        except OSError:
            return datetime.now().strftime("%H:%M")

    def _read_exif_datetime(
        self, image_path: str, img: Optional[Image.Image] = None
    ) -> Optional[datetime]:
        try:
            source = img
            close_needed = False
            if source is None:
                source = Image.open(image_path)
                close_needed = True
            exif = source.getexif()
            if close_needed:
                source.close()
            if not exif:
                return None
            # 36867 DateTimeOriginal, 306 DateTime
            raw = exif.get(36867) or exif.get(306)
            if not raw:
                return None
            return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
        except Exception:
            return None

    def _split_datetime_fields(self, value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        text = (value or "").strip()
        if not text:
            return None, None
        if re.fullmatch(r"\d{1,2}:\d{2}", text):
            return text, None
        match = re.match(
            r"(\d{4}[./\-年]\d{1,2}[./\-月]\d{1,2}日?)\s*(\d{1,2}:\d{2})?",
            text,
        )
        if match:
            return match.group(2), match.group(1)
        return text, None

    def _load_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        key = (size, bold)
        if key in self._font_cache:
            return self._font_cache[key]

        candidates: List[str] = []
        if bold:
            candidates.extend(
                [
                    r"C:\Windows\Fonts\msyhbd.ttc",
                    r"C:\Windows\Fonts\msyhbd.ttf",
                    r"C:\Windows\Fonts\simhei.ttf",
                    r"C:\Windows\Fonts\arialbd.ttf",
                    "/System/Library/Fonts/PingFang.ttc",
                    "/Library/Fonts/Arial Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                ]
            )
        candidates.extend(
            [
                r"C:\Windows\Fonts\msyh.ttc",
                r"C:\Windows\Fonts\msyh.ttf",
                r"C:\Windows\Fonts\simhei.ttf",
                r"C:\Windows\Fonts\arial.ttf",
                "/System/Library/Fonts/PingFang.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )

        font = None
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                font = ImageFont.truetype(path, size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        self._font_cache[key] = font
        return font

    def _save_image(self, img: Image.Image, save_path: str, exif_bytes=None) -> None:
        ext = os.path.splitext(save_path)[1].lower()
        rgb = img.convert("RGB")
        if ext in {".png"}:
            img.convert("RGBA").save(save_path, "PNG")
        elif ext in {".webp"}:
            rgb.save(save_path, "WEBP", quality=95)
        elif ext in {".bmp"}:
            rgb.save(save_path, "BMP")
        elif ext in {".tif", ".tiff"}:
            rgb.save(save_path, "TIFF")
        else:
            save_kwargs = {"quality": 95, "optimize": True}
            if exif_bytes:
                save_kwargs["exif"] = exif_bytes
            rgb.save(save_path, "JPEG", **save_kwargs)

    @staticmethod
    def _sibling_output_path(path: str) -> str:
        root, ext = os.path.splitext(path)
        return f"{root}_watermarked{ext}"


def process_folder_to_output(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    watermark_text: str,
    start_date: str | None = None,
    end_date: str | None = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[int, int, List[str], str]:
    """
    批量加水印并写入 output_dir（保留相对路径）。

    watermark_text 作为地点文案；若未给日期则尝试从目录名解析，否则用当天。
    """
    src = Path(source_dir)
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    processor = WatermarkProcessor()
    images = processor.collect_images(str(src))
    if not images:
        return 0, 0, [], str(out_root)

    start = (start_date or "").strip()
    end = (end_date or "").strip()
    if not start or not end:
        auto_s, auto_e = processor.extract_dates_from_folder_name(str(src))
        start = start or auto_s or datetime.now().strftime("%Y.%m.%d")
        end = end or auto_e or start

    location = (watermark_text or "").strip() or "未填写地点"
    start_dt = processor.parse_date(start)
    end_dt = processor.parse_date(end)
    if not start_dt or not end_dt:
        raise ValueError("日期无效，请使用 YYYY.MM.DD 格式")
    if end_dt.date() < start_dt.date():
        raise ValueError("结束日期不能早于开始日期")

    plan = processor.plan_watermark_datetimes(str(src), images, start_dt, end_dt)
    success = 0
    failed: List[str] = []
    total = len(images)

    for index, path in enumerate(images, start=1):
        if progress_callback:
            progress_callback(index, total, path)
        try:
            rel = os.path.relpath(path, str(src))
        except ValueError:
            rel = os.path.basename(path)
        dest = out_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        date_for_photo, time_for_photo = plan[path]
        ok = processor.apply_watermark(
            path,
            date_for_photo,
            location,
            time_text=time_for_photo,
            output_path=str(dest),
        )
        if ok:
            success += 1
        else:
            failed.append(path)

    return success, len(failed), failed, str(out_root)
