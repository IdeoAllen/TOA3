# -*- coding: utf-8 -*-
"""TOA2 简历提取引擎（已脱离 common.app_config，供 TOA3 service 调用）。"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from typing import Dict, List, Optional

logger = logging.getLogger("TOA3.resume_extractor.engine")

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

try:
    import PyPDF2
except ImportError:
    try:
        import pypdf as PyPDF2  # type: ignore
    except ImportError:
        PyPDF2 = None  # type: ignore

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None  # type: ignore

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore
    np = None  # type: ignore

def _resolve_poppler_path() -> str | None:
    try:
        from services.integrations.config import integration_config

        tip = str((integration_config("ocr") or {}).get("poppler_path") or "").strip()
        if tip and os.path.isdir(tip):
            return tip
    except Exception:
        pass
    for candidate in [
        r"C:\Program Files\poppler\Library\bin",
        r"C:\poppler\Library\bin",
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]:
        if os.path.isdir(candidate):
            return candidate
    return None


DEFAULT_CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "西安", "重庆",
    "苏州", "天津", "长沙", "郑州", "东莞", "青岛", "沈阳", "宁波", "昆明", "无锡",
    "合肥", "福州", "厦门", "哈尔滨", "济南", "大连", "温州", "石家庄", "南宁", "贵阳",
    "南昌", "金华", "常州", "南通", "徐州", "佛山", "泉州", "珠海", "惠州", "中山",
    "绍兴", "台州", "烟台", "嘉兴", "太原", "潍坊", "临沂", "洛阳", "盐城",
    "张家港", "昆山", "常熟", "义乌", "桂林", "海口", "三亚", "兰州", "银川", "西宁",
]

# 职务 / 版式词，禁止当姓名（助教简历 PPT 常见「现场助教」抢在真名之前）
_NAME_NOISE_EXACT = {
    "现场助教",
    "助教",
    "简历",
    "求职",
    "应聘",
    "基本信息",
    "个人信息",
    "专业领域",
    "工作经历",
    "教育经历",
    "教育背景",
    "自我评价",
    "项目经历",
    "实践经历",
    "个人优势",
    "联系方式",
    "求职信息",
    "求职意向",
    "订纸板",
    "开机房",
    "主修课程",
}
_NAME_NOISE_SUB = (
    "助教",
    "顾问",
    "主管",
    "经理",
    "总监",
    "培训",
    "运营",
    "简历",
    "现场",
    "交付",
    "销售",
    "技术",
    "学历",
    "年龄",
    "本科",
    "硕士",
    "博士",
    "品牌",
    "汽车",
    "行业",
    "项目",
    "专业",
    "领域",
    "活动",
    "服务",
    "产品",
    "市场",
    "公司",
    "学校",
    "经历",
    "优势",
    "意向",
    "纸板",
    "商检",
    "加班",
)
# Boss/招聘下载名：【职位_城市 …】姓名 年限.pdf
_BOSS_FILENAME_NAME_RE = re.compile(
    r"】\s*(.+?)\s+"
    r"(?:"
    r"\d+年以上|"
    r"\d+年以内|"
    r"\d+年应届生|"
    r"\d+年|"
    r"应届生|"
    r"应届"
    r")\b",
)


class ResumeExtractor:
    def __init__(self):
        self._setup_tesseract_path()
        self.path_config = {"data_dir": ".", "output_dir": "."}
        self.cities = self._load_chinese_cities()
        if not self.cities:
            logger.warning("城市列表为空，城市提取可能不准确")

        self.name_pattern = (
            r"姓名[：:\s]*([\u4e00-\u9fa5]{2,4})|^([\u4e00-\u9fa5]{2,4})\s*$|"
            r"([\u4e00-\u9fa5]{2,4})\s*先生|([\u4e00-\u9fa5]{2,4})\s*女士"
        )
        self.phone_pattern = r"(1[3-9]\d{9})"
        self.wechat_pattern = (
            r"微信[：:\s]*([a-zA-Z0-9_\-]{5,20})|微信号[：:\s]*([a-zA-Z0-9_\-]{5,20})|"
            r"[a-zA-Z][a-zA-Z0-9_\-]{4,19}"
        )

    def _setup_tesseract_path(self):
        """探测本机 Tesseract；无依赖 TOA2 GUI / app_config。"""
        if pytesseract is None:
            return
        try:
            candidates = [
                shutil.which("tesseract") or "",
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
            ]
            try:
                from services.integrations.config import integration_config

                tip = str((integration_config("ocr") or {}).get("tesseract_path") or "").strip()
                if tip:
                    candidates.insert(0, tip)
            except Exception:
                pass
            for path in candidates:
                if path and os.path.isfile(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    logger.info("Tesseract OCR 路径: %s", path)
                    return
            logger.warning("未找到 Tesseract OCR")
        except Exception as e:
            logger.warning("设置 Tesseract 路径失败: %s", e)

    def _load_chinese_cities(self) -> List[str]:
        return list(DEFAULT_CITIES)

    def preprocess_image_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """预处理图像以提高OCR准确性"""
        # 检查图像是否为空
        if image is None or image.size == 0:
            return image
        
        # 转换为灰度图
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        # 检查灰度图是否为空
        if gray is None or gray.size == 0:
            return image
        
        # 应用自适应阈值
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                      cv2.THRESH_BINARY, 11, 2)
        
        # 检查阈值处理后的图像是否为空
        if thresh is None or thresh.size == 0:
            return gray
        
        # 降噪
        kernel = np.ones((1, 1), np.uint8)
        opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
        
        # 检查处理后的图像是否为空或大小为0
        if opening is None or opening.size == 0:
            return thresh
        
        return opening

    def extract_text_from_image(self, image: np.ndarray) -> str:
        """从图像中提取文本"""
        try:
            if pytesseract is None or image is None or image.size == 0:
                return ""

            # 预处理图像
            processed_img = self.preprocess_image_for_ocr(image)
            if processed_img is None or processed_img.size == 0:
                return ""

            text = pytesseract.image_to_string(processed_img, lang="chi_sim+eng")
            if text and text.strip():
                return text
            return ""
        except Exception as e:
            print(f"从图像提取文本时出错: {str(e)}")
            return ""

    def extract_phone_from_image_areas(self, pdf_path: str) -> List[str]:
        """从PDF中可能包含电话号码的图像区域提取电话号码"""
        phone_numbers = []
        try:
            # 检查PDF文件是否存在
            if not os.path.exists(pdf_path):
                print(f"PDF文件不存在: {pdf_path}")
                return phone_numbers
            
            # 转换PDF的第一页为图像（加入poppler路径回退并捕获异常）
            try:
                if convert_from_path is None:
                    return phone_numbers
                poppler_path = _resolve_poppler_path()
                images = convert_from_path(
                    pdf_path, dpi=200, first_page=1, last_page=1, poppler_path=poppler_path
                )
            except Exception as ce:
                print(f"将PDF转换为图像时出错: {str(ce)}")
                return phone_numbers
            # 检查是否成功转换为图像
            if not images:
                print(f"无法将PDF转换为图像: {pdf_path}")
                return phone_numbers
                
            image = images[0]
            if cv2 is None or np is None:
                return phone_numbers
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # 检查图像是否为空
            if image is None or image.size == 0:
                print(f"转换后的图像为空: {pdf_path}")
                return phone_numbers
            
            # 转换为灰度图
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            # 使用Canny边缘检测
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            
            # 查找轮廓
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 筛选出可能是电话号码区域的轮廓
            phone_regions = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                # 电话号码区域通常较窄且较长
                if 30 < w < 400 and 8 < h < 60:
                    phone_regions.append((x, y, w, h))
            
            # 对可能的电话号码区域进行OCR
            for (x, y, w, h) in phone_regions:
                # 扩大区域以确保完整捕获号码
                expanded_x = max(0, x - 15)
                expanded_y = max(0, y - 10)
                expanded_w = min(img_cv.shape[1] - expanded_x, w + 30)
                expanded_h = min(img_cv.shape[0] - expanded_y, h + 20)
                
                # 裁剪区域
                region = img_cv[expanded_y:expanded_y+expanded_h, expanded_x:expanded_x+expanded_w]
                
                # 检查裁剪后的区域是否为空
                if region is None or region.size == 0:
                    continue
                
                # 对区域进行预处理以提高OCR准确性
                # 转换为灰度图
                region_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                
                # 检查灰度图是否为空
                if region_gray is None or region_gray.size == 0:
                    continue
                
                # 应用阈值处理
                _, region_thresh = cv2.threshold(region_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                
                # 检查区域图像是否为空或大小为0
                if region_thresh is None or region_thresh.size == 0:
                    continue
                
                # 对区域进行OCR
                text = pytesseract.image_to_string(region_thresh, config='--psm 7')
                
                # 检查OCR结果是否为空
                if not text.strip():
                    continue
                
                # 查找电话号码
                phone_match = re.search(self.phone_pattern, text)
                if phone_match:
                    phone_number = phone_match.group(0)
                    # 验证手机号格式
                    phone_digits = re.sub(r'\D', '', phone_number)
                    if len(phone_digits) >= 11 and phone_digits.startswith(('13', '14', '15', '16', '17', '18', '19')):
                        phone_numbers.append(phone_digits[:11])
                    
        except Exception as e:
            print(f"查找电话号码区域时出错: {str(e)}")
        
        return phone_numbers

    def find_phone_number_regions(self, image: np.ndarray) -> List[tuple]:
        """查找图像中可能包含电话号码的区域"""
        regions = []
        
        try:
            # 检查图像是否为空
            if image is None or image.size == 0:
                return regions
            
            # 转换为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
            
            # 二值化
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # 查找轮廓
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 检查是否找到了轮廓
            if not contours:
                return regions
            
            # 筛选可能包含电话号码的区域
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                
                # 过滤太小或太大的区域
                if w < 20 or h < 10 or w > 500 or h > 100:
                    continue
                
                # 计算宽高比
                aspect_ratio = w / h
                if aspect_ratio < 2 or aspect_ratio > 10:  # 电话号码通常是长条形的
                    continue
                
                # 检查区域是否有效
                if w <= 0 or h <= 0:
                    continue
                
                regions.append((x, y, w, h))
                
        except Exception as e:
            print(f"查找电话号码区域时出错: {str(e)}")
        
        return regions

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从PDF中提取文本"""
        text = ""
        try:
            # 检查PDF文件是否存在
            if not os.path.exists(pdf_path):
                print(f"PDF文件不存在: {pdf_path}")
                return text
            
            # 检查PDF文件是否为空
            if os.path.getsize(pdf_path) == 0:
                print(f"PDF文件为空: {pdf_path}")
                return text
            
            # 首先尝试直接提取文本
            with open(pdf_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                
                # 检查PDF是否有页面
                if len(reader.pages) == 0:
                    print(f"PDF文件没有页面: {pdf_path}")
                    return text
                
                # 检查PDF页数是否过多
                max_pages = 10
                if len(reader.pages) > max_pages:
                    print(f"PDF文件页数过多 ({len(reader.pages)}页)，仅处理前{max_pages}页。")
                
                # 检查PDF是否只有一页且为空白页
                if len(reader.pages) == 1:
                    first_page_text = reader.pages[0].extract_text()
                    if not first_page_text or not first_page_text.strip():
                        print(f"PDF文件 {os.path.basename(pdf_path)} 第一页为空白页，继续尝试OCR。")
                        # 不立即返回，保留text为空以便后续OCR流程执行
                
                # 检查PDF页数，限制在10页以内
                if len(reader.pages) > max_pages:
                    pages_to_process = reader.pages[:max_pages]
                elif len(reader.pages) == 0:
                    print(f"PDF文件没有页面: {pdf_path}")
                    return text
                else:
                    pages_to_process = reader.pages
                
                for page in pages_to_process:
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception as e:
                        print(f"提取PDF页面文本时出错: {str(e)}")
                        continue
            
            # 如果直接提取的文本太少，尝试OCR整个PDF
            if len(text.strip()) < 100:
                print(f"PDF文本提取较少，尝试OCR方法: {pdf_path}")
                ocr_text = self._ocr_pdf_pages(pdf_path, max_pages=10)
                if ocr_text:
                    text += ocr_text

        except Exception as e:
            print(f"从PDF {pdf_path} 提取文本时出错: {str(e)}")

        return text

    def _ocr_pdf_pages(self, pdf_path: str, max_pages: int = 10) -> str:
        """图片型 PDF：pdf2image / PyMuPDF 渲染后 OCR。"""
        images = []
        try:
            if convert_from_path is not None:
                poppler_path = _resolve_poppler_path()
                images = convert_from_path(
                    pdf_path,
                    dpi=200,
                    last_page=max_pages,
                    poppler_path=poppler_path,
                ) or []
        except Exception as e:
            print(f"转换PDF为图像时出错: {str(e)}")
            images = []

        if not images:
            try:
                import fitz  # PyMuPDF
                import io

                if Image is None:
                    return ""
                doc = fitz.open(pdf_path)
                for i, page in enumerate(doc):
                    if i >= max_pages:
                        break
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
                doc.close()
            except Exception as e:
                print(f"PyMuPDF 渲染 PDF 失败: {e}")
                return ""

        parts: list[str] = []
        for image in images:
            try:
                page_text = ""
                if cv2 is not None and np is not None:
                    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                    page_text = self.extract_text_from_image(img_cv)
                elif pytesseract is not None and Image is not None:
                    page_text = pytesseract.image_to_string(image, lang="chi_sim+eng") or ""
                if page_text and page_text.strip():
                    parts.append(page_text)
            except Exception as e:
                print(f"OCR处理PDF页面时出错: {str(e)}")
        return "\n".join(parts) + ("\n" if parts else "")

    def extract_city(self, text: str, filename: str = None, file_path: str = None) -> Optional[str]:
        """提取城市信息并进行增强校验，当文本中未找到时从文件名或目录名提取"""
        try:
            # 检查文本是否为空
            if text and isinstance(text, str):
                # 先尝试查找"城市"或"地点"等关键词后的城市名
                city_patterns = [
                    r'城市[：:\s]*([\u4e00-\u9fa5]+)',
                    r'地点[：:\s]*([\u4e00-\u9fa5]+)',
                    r'所在城市[：:\s]*([\u4e00-\u9fa5]+)',
                    r'工作地点[：:\s]*([\u4e00-\u9fa5]+)',
                    r'居住地[：:\s]*([\u4e00-\u9fa5]+)',
                    r'地址[：:\s]*([\u4e00-\u9fa5]+)',
                    r'所在地区[：:\s]*([\u4e00-\u9fa5]+)',
                    r'户籍所在地[：:\s]*([\u4e00-\u9fa5]+)',
                    r'现在所在地[：:\s]*([\u4e00-\u9fa5]+)',
                    r'所在地[：:\s]*([\u4e00-\u9fa5]+)'
                ]
                
                # 从文本中提取可能的城市名（支持城市名后面跟区域的情况）
                for pattern in city_patterns:
                    match = re.search(pattern, text)
                    if match:
                        matched_text = match.group(1)
                        # 检查匹配的文本中是否包含我们城市列表中的任何城市
                        for city in self.cities:
                            if matched_text.startswith(city):
                                return city
                
                # 如果没有找到关键词，直接在所有城市中查找
                found_cities = []
                for city in self.cities:
                    # 查找所有匹配位置
                    for match in re.finditer(city, text):
                        start, end = match.span()
                        # 检查匹配前是否是中文字符（避免部分匹配）
                        if start > 0 and re.match(r'[\u4e00-\u9fa5]', text[start-1]):
                            continue
                        # 检查匹配后是否是中文字符且不是城市名的一部分
                        if end < len(text) and re.match(r'[\u4e00-\u9fa5]', text[end]):
                            # 允许城市名后面跟着区域名（如"上海浦东"）
                            continue
                        # 检查是否已经添加了这个城市
                        if city not in found_cities:
                            found_cities.append(city)
                        break  # 找到一个有效匹配就够了
                
                # 如果找到多个城市，返回最可能的一个（最长的匹配且优先级更高的城市）
                if found_cities:
                    # 定义主要城市优先级（一线和新一线城市优先）
                    priority_cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "西安", "重庆"]
                    
                    # 优先返回主要城市
                    for priority_city in priority_cities:
                        if priority_city in found_cities:
                            return priority_city
                    
                    # 否则返回最长的匹配
                    return max(found_cities, key=len)
            
            # 如果文本中没有找到城市，尝试从文件名提取
            if filename and isinstance(filename, str):
                print(f"尝试从文件名提取城市: {filename}")
                # 在文件名中查找城市
                for city in self.cities:
                    if city in filename:
                        print(f"从文件名提取到城市: {city}")
                        return city
            
            # 如果文件名中也没有找到城市，尝试从文件路径（目录名）中提取
            if file_path and isinstance(file_path, str):
                print(f"尝试从文件路径提取城市: {file_path}")
                # 在文件路径中查找城市
                for city in self.cities:
                    if city in file_path:
                        print(f"从文件路径提取到城市: {city}")
                        return city
            
        except Exception as e:
            print(f"提取城市信息时出错: {str(e)}")
        
        # 如果没有找到城市，返回None
        return None

    def looks_like_person_name(self, value: str) -> bool:
        """中文姓名：2–4 字，拒职务/城市/版式词；含「…市」一律拒。"""
        s = (value or "").strip()
        if not re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", s):
            return False
        if s.endswith("市") or s.endswith("省") or s.endswith("区") or s.endswith("县"):
            return False
        if s in _NAME_NOISE_EXACT:
            return False
        if any(tok in s for tok in _NAME_NOISE_SUB):
            return False
        cities = set(self.cities or DEFAULT_CITIES)
        if s in cities:
            return False
        # 城市名+市（张家港市）
        if s.endswith("市") and s[:-1] in cities:
            return False
        bare = s[:-1] if s.endswith("市") else s
        if any(c.startswith(bare) or bare.startswith(c) for c in cities if len(c) >= 2):
            # 过宽会误伤真名；仅拦完整城市别名
            pass
        if s in {c + "市" for c in cities}:
            return False
        return True

    def looks_like_display_name(self, value: str) -> bool:
        """招聘文件名上的称呼：中文名 / 英文名 / ava曹 混写。"""
        s = (value or "").strip()
        if not s or len(s) > 16:
            return False
        if s in _NAME_NOISE_EXACT:
            return False
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", s):
            return self.looks_like_person_name(s)
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]{1,15}", s):
            return True
        if re.fullmatch(r"[A-Za-z]{1,12}\s*[\u4e00-\u9fa5]{1,4}", s):
            return True
        return False

    def extract_name_from_boss_filename(self, filename: str | None) -> Optional[str]:
        """Boss/招聘包文件名：】姓名 3年.pdf → 姓名（优先于正文误提）。"""
        if not filename:
            return None
        stem = os.path.splitext(os.path.basename(filename))[0]
        stem = re.sub(r"\s*\(\d+\)\s*$", "", stem).strip()
        m = _BOSS_FILENAME_NAME_RE.search(stem)
        if not m:
            return None
        name = m.group(1).strip()
        # 去掉可能夹带的城市尾巴
        name = re.sub(r"^[【\[]?.+[】\]]", "", name).strip() or name
        if self.looks_like_display_name(name):
            return name
        return None

    def extract_name_from_filename(self, filename: str | None) -> Optional[str]:
        """文件名启发式：Boss 模式优先，否则取末尾真人名。"""
        boss = self.extract_name_from_boss_filename(filename)
        if boss:
            return boss
        if not filename:
            return None
        stem = os.path.splitext(os.path.basename(filename))[0]
        candidates: list[str] = []
        for seg in re.split(r"[-_—–\s.]+", stem):
            seg = seg.strip()
            if self.looks_like_person_name(seg):
                candidates.append(seg)
        for chunk in re.findall(r"[\u4e00-\u9fa5]{2,4}", stem):
            if self.looks_like_person_name(chunk):
                candidates.append(chunk)
        return candidates[-1] if candidates else None

    def extract_name(self, text: str, filename: str | None = None) -> Optional[str]:
        """姓名：招聘文件名 > 正文「姓名：」 > 纯名行 > 文件名兜底。"""
        boss = self.extract_name_from_boss_filename(filename)
        if boss:
            return boss

        if text:
            # 仅认带「姓名」标签的分组，避免 ^中文$ 误吃职务行
            labeled = re.search(
                r"姓名[：:\s]*([\u4e00-\u9fa5]{2,4})",
                text,
            )
            if labeled and self.looks_like_person_name(labeled.group(1)):
                return labeled.group(1)

            lines = text.split("\n")
            for line in lines[:30]:
                line = line.strip()
                if not line:
                    continue
                if any(
                    kw in line
                    for kw in (
                        "简历",
                        "求职",
                        "应聘",
                        "电话",
                        "邮箱",
                        "出生",
                        "性别",
                        "教育",
                        "经验",
                        "工作",
                        "年龄",
                        "学历",
                        "品牌",
                        "专业领域",
                        "服务过",
                        "经历",
                        "优势",
                        "课程",
                        "公司",
                    )
                ):
                    continue
                if self.looks_like_person_name(line):
                    return line
                for cand in re.findall(r"[\u4e00-\u9fa5]{2,4}", line):
                    if self.looks_like_person_name(cand):
                        return cand

        return self.extract_name_from_filename(filename)

    def extract_phone(self, text: str) -> Optional[str]:
        """提取电话/手机信息（容忍空格/横线分隔）。"""
        if not text:
            return None

        def _norm_phone(raw: str) -> Optional[str]:
            digits = re.sub(r"\D", "", raw or "")
            if len(digits) >= 11 and digits[:11].startswith(
                ("13", "14", "15", "16", "17", "18", "19")
            ):
                return digits[:11]
            return None

        phone_patterns = [
            r"手机[号]?[：:\s]*([0-9\s\-－]+)",
            r"电话[：:\s]*([0-9\s\-－]+)",
            r"联系方式[：:\s]*([0-9\s\-－]+)",
            r"联系电话[：:\s]*([0-9\s\-－]+)",
            r"移动电话[：:\s]*([0-9\s\-－]+)",
            r"Tel[：:\s]*([0-9\s\-－]+)",
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                phone = _norm_phone(match.group(1))
                if phone:
                    return phone

        # 全文扫 11 位手机（允许中间空格：135 8489 8806）
        spaced = re.findall(r"(1[3-9](?:[\s\-－]?\d){9})", text)
        for raw in spaced:
            phone = _norm_phone(raw)
            if phone:
                return phone
        for raw in re.findall(self.phone_pattern, text):
            phone = _norm_phone(raw)
            if phone:
                return phone
        return None

    def extract_wechat(self, text: str) -> Optional[str]:
        """提取微信号信息"""
        if not text:
            return None
        
        # 先尝试查找"微信"或"微信号"等关键词后的号码
        wechat_patterns = [
            r'微信[：:\s]*([a-zA-Z0-9_\-]{5,20})',
            r'微信号[：:\s]*([a-zA-Z0-9_\-]{5,20})',
            r'wechat[：:\s]*([a-zA-Z0-9_\-]{5,20})'
        ]
        
        for pattern in wechat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                wechat_id = match.group(1)
                # 验证微信号格式
                if 5 <= len(wechat_id) <= 20 and re.match(r'^[a-zA-Z0-9_-]+$', wechat_id):
                    return wechat_id
        
        # 如果没有找到关键词，使用通用模式
        matches = re.findall(self.wechat_pattern, text)
        if matches:
            # 返回第一个匹配项
            wechat_id = matches[0]
            # 验证微信号格式
            if 5 <= len(wechat_id) <= 20 and re.match(r'^[a-zA-Z0-9_-]+$', wechat_id):
                return wechat_id
                
        # 如果没有找到微信号，返回None
        return None

    def _apply_filename_fallbacks(self, result: Dict[str, str], filename: str) -> Dict[str, str]:
        """姓名误提职务词、或手机/微信缺失时，从文件名补全。"""
        name = result.get("姓名")
        if not self.looks_like_display_name(str(name or "")):
            inferred = self.extract_name_from_filename(filename)
            if inferred:
                result["姓名"] = inferred
        stem = os.path.splitext(os.path.basename(filename or ""))[0]
        if not result.get("手机号"):
            m = re.search(r"(1[3-9]\d{9})", stem)
            if m:
                result["手机号"] = m.group(1)
        if not result.get("微信号"):
            # 避免把扩展相关英文误当微信；仅取明确夹在分隔符中的 id
            w = re.search(r"(?:微信|wx|wechat)[-_:]?([a-zA-Z][a-zA-Z0-9_\-]{4,19})", stem, re.I)
            if w:
                result["微信号"] = w.group(1)
            elif result.get("手机号"):
                # 国内常见：未单独留微信时等同手机号
                result["微信号"] = result["手机号"]
        return result

    def process_resume(self, file_path: str) -> Dict[str, str]:
        """处理单个简历文件"""
        print(f"正在处理: {os.path.basename(file_path)}")
        
        # 检查文件扩展名
        if not file_path.lower().endswith('.pdf'):
            print(f"不支持的文件类型: {file_path}")
            return {
                "文件名": os.path.basename(file_path),
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return {
                "文件名": os.path.basename(file_path),
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否可读
        if not os.access(file_path, os.R_OK):
            print(f"无法读取文件: {file_path}")
            return {
                "文件名": os.path.basename(file_path),
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        max_file_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_file_size:
            print(f"文件 {os.path.basename(file_path)} 太大 ({file_size / (1024*1024):.1f}MB)，跳过处理。")
            return {
                "文件名": os.path.basename(file_path),
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否为空
        if file_size == 0:
            print(f"文件为空: {os.path.basename(file_path)}")
            return {
                "文件名": os.path.basename(file_path),
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 提取基本信息
        text = self.extract_text_from_pdf(file_path)
        filename = os.path.basename(file_path)
        
        # 专门提取手机号（针对图片中的手机号）
        phone_numbers = self.extract_phone_from_image_areas(file_path)
        
        result = {
            "文件名": filename,
            "城市": self.extract_city(text, filename, file_path),  # 传递文件名和文件路径以支持从文件名和目录名提取城市
            "姓名": self.extract_name(text, filename),
            "手机号": self.extract_phone(text),
            "微信号": self.extract_wechat(text)
        }
        
        # 如果常规方法没找到手机号，但图像方法找到了，使用图像方法的结果
        if not result["手机号"] and phone_numbers:
            # 验证从图像中提取的手机号格式
            for phone in phone_numbers:
                phone_digits = re.sub(r'\D', '', phone)
                if len(phone_digits) >= 11 and phone_digits.startswith(('13', '14', '15', '16', '17', '18', '19')):
                    result["手机号"] = phone_digits[:11]  # 使用找到的第一个有效手机号
                    print(f"  从图像中提取到手机号: {result['手机号']}")
                    break
        
        return self._apply_filename_fallbacks(result, filename)

    def process_text_file(self, file_path: str) -> Dict[str, str]:
        """处理文本文件"""
        filename = os.path.basename(file_path)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否可读
        if not os.access(file_path, os.R_OK):
            print(f"无法读取文件: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        max_file_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_file_size:
            print(f"文件 {filename} 太大 ({file_size / (1024*1024):.1f}MB)，跳过处理。")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否为空
        if file_size == 0:
            print(f"文件为空: {filename}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 读取文本内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            print(f"读取文件 {filename} 时出错: {str(e)}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 提取基本信息
        result = {
            "文件名": filename,
            "城市": self.extract_city(text, filename, file_path),  # 传递文件名和文件路径以支持从文件名和目录名提取城市
            "姓名": self.extract_name(text, filename),
            "手机号": self.extract_phone(text),
            "微信号": self.extract_wechat(text)
        }
        
        return self._apply_filename_fallbacks(result, filename)
    
    def process_image_file(self, file_path: str) -> Dict[str, str]:
        """处理图片文件"""
        filename = os.path.basename(file_path)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否可读
        if not os.access(file_path, os.R_OK):
            print(f"无法读取文件: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        max_file_size = 50 * 1024 * 1024  # 50MB
        if file_size > max_file_size:
            print(f"文件 {filename} 太大 ({file_size / (1024*1024):.1f}MB)，跳过处理。")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否为空
        if file_size == 0:
            print(f"文件为空: {filename}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 使用OCR提取文本（本机 pytesseract → integrations OCR）
        text = ""
        try:
            if Image is None:
                raise RuntimeError("Pillow 不可用")
            image = Image.open(file_path)
            if pytesseract is not None:
                text = pytesseract.image_to_string(image, lang="chi_sim+eng") or ""
        except Exception as e:
            print(f"处理图片文件 {filename} 时出错: {str(e)}")

        if not (text or "").strip():
            try:
                from services.integrations import get_client
                from services.integrations.config import integration_enabled

                if integration_enabled("ocr"):
                    raw = get_client("ocr").recognize_image(file_path, lang="chi_sim+eng")
                    if isinstance(raw, dict):
                        text = str(raw.get("text") or "")
                    else:
                        text = str(raw or "")
            except Exception as e:
                print(f"integrations OCR 失败 {filename}: {e}")

        if not (text or "").strip():
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None,
            }

        return self._apply_filename_fallbacks(
            {
                "文件名": filename,
                "城市": self.extract_city(text, filename, file_path),
                "姓名": self.extract_name(text, filename),
                "手机号": self.extract_phone(text),
                "微信号": self.extract_wechat(text),
            },
            filename,
        )

    def process_pptx_file(self, file_path: str) -> Dict[str, str]:
        """处理 PPTX 简历（抽取形状/表格文本）。"""
        filename = os.path.basename(file_path)
        if not os.path.exists(file_path):
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None,
            }
        try:
            from pptx import Presentation
            from pptx.enum.shapes import MSO_SHAPE_TYPE

            prs = Presentation(file_path)
            parts: list[str] = []

            def _shape_text(shape) -> None:
                if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        line = "".join(run.text for run in para.runs) or (para.text or "")
                        if line.strip():
                            parts.append(line)
                if getattr(shape, "has_table", False) and shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text and cell.text.strip():
                                parts.append(cell.text)
                if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                    for child in shape.shapes:
                        _shape_text(child)

            for slide in prs.slides:
                for shape in slide.shapes:
                    _shape_text(shape)
            text = "\n".join(parts)
        except Exception as e:
            print(f"处理PPTX文件 {filename} 时出错: {str(e)}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None,
            }

        return self._apply_filename_fallbacks(
            {
                "文件名": filename,
                "城市": self.extract_city(text, filename, file_path),
                "姓名": self.extract_name(text, filename),
                "手机号": self.extract_phone(text),
                "微信号": self.extract_wechat(text),
            },
            filename,
        )

    def process_docx_file(self, file_path: str) -> Dict[str, str]:
        """处理DOCX简历文件"""
        filename = os.path.basename(file_path)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"文件不存在: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 检查文件是否可读
        if not os.access(file_path, os.R_OK):
            print(f"无法读取文件: {file_path}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 读取DOCX文本（包含段落与表格文本）
        try:
            from docx import Document
            doc = Document(file_path)
            
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            table_texts = []
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            table_texts.append(cell.text)
            
            text = "\n".join(paragraphs + table_texts)
        except Exception as e:
            print(f"处理DOCX文件 {filename} 时出错: {str(e)}")
            return {
                "文件名": filename,
                "城市": None,
                "姓名": None,
                "手机号": None,
                "微信号": None
            }
        
        # 提取基本信息
        result = {
            "文件名": filename,
            "城市": self.extract_city(text, filename, file_path),
            "姓名": self.extract_name(text, filename),
            "手机号": self.extract_phone(text),
            "微信号": self.extract_wechat(text)
        }
        
        return self._apply_filename_fallbacks(result, filename)
    
    def process_directory(self, directory_path: str) -> List[Dict[str, str]]:
        """处理目录及子目录下的所有简历文件"""
        # 检查目录路径是否存在
        if not os.path.exists(directory_path):
            print(f"目录不存在: {directory_path}")
            return []
        
        results = []
        supported_extensions = [
            ".pdf",
            ".docx",
            ".pptx",
            ".txt",
            ".md",
            ".png",
            ".jpg",
            ".jpeg",
            ".bmp",
            ".tif",
            ".tiff",
            ".webp",
        ]

        # 设置文件大小限制为50MB
        max_file_size = 50 * 1024 * 1024

        # 使用os.walk递归遍历目录及子目录
        for root, dirs, files in os.walk(directory_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                lower = filename.lower()
                if not any(lower.endswith(ext) for ext in supported_extensions):
                    print(f"跳过不支持的文件类型: {filename}")
                    continue

                try:
                    file_size = os.path.getsize(file_path)
                except OSError as e:
                    print(f"无法获取文件大小 {file_path}: {e}")
                    continue

                if file_size > max_file_size:
                    print(f"文件 {filename} 太大 ({file_size / (1024*1024):.1f}MB)，跳过处理。")
                    continue

                if lower.endswith(".pdf"):
                    result = self.process_resume(file_path)
                elif lower.endswith(".docx"):
                    result = self.process_docx_file(file_path)
                elif lower.endswith(".pptx"):
                    result = self.process_pptx_file(file_path)
                elif lower.endswith((".txt", ".md")):
                    result = self.process_text_file(file_path)
                elif lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")):
                    result = self.process_image_file(file_path)
                else:
                    print(f"不支持的文件类型: {filename}")
                    continue

                results.append(result)

        return results

def main():
    # 检查Tesseract OCR是否可用
    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        print("错误: 未找到Tesseract OCR引擎。请确保已安装Tesseract并将其添加到系统PATH中。")
        return
    except Exception as e:
        print(f"检查Tesseract OCR引擎时出错: {str(e)}")
        return
    
    # 设置简历目录路径
    resume_directory = input("请输入PDF简历文件所在目录的路径: ").strip()
    
    # 处理用户可能输入的引号
    if resume_directory.startswith('"') and resume_directory.endswith('"'):
        resume_directory = resume_directory[1:-1]
    elif resume_directory.startswith("'") and resume_directory.endswith("'"):
        resume_directory = resume_directory[1:-1]
    
    # 展开用户路径中的~符号
    resume_directory = os.path.expanduser(resume_directory)
    
    # 检查目录路径是否存在
    if not os.path.exists(resume_directory):
        print("指定的目录不存在!")
        return
    
    # 检查是否为目录
    if not os.path.isdir(resume_directory):
        print("指定的路径不是目录!")
        return
    
    # 检查目录是否为空
    files = [f for f in os.listdir(resume_directory) if os.path.isfile(os.path.join(resume_directory, f)) and f.lower().endswith(('.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg'))]
    if not files:
        print("指定的目录中没有找到支持的简历文件(PDF/DOCX/TXT/图片)!")
        return
    
    print(f"找到 {len(files)} 个简历文件，开始处理...")
    
    # 如果文件数量过多，询问用户是否继续
    if len(files) > 100:
        confirm = input(f"目录中包含 {len(files)} 个简历文件，处理可能需要较长时间。是否继续？(y/n): ")
        if confirm.lower() != 'y':
            print("用户取消操作。")
            return
    
    # 创建提取器并处理目录
    extractor = ResumeExtractor()
    results = extractor.process_directory(resume_directory)
    
    # 检查处理结果是否为空
    if not results:
        print("未能提取任何信息!")
        return
    
    # 过滤掉所有字段都为空的结果
    filtered_results = [result for result in results if any(result[key] for key in result if key != "文件名")]
    
    if not filtered_results:
        print("未能提取任何信息!")
        return
    
    # 转换为DataFrame并保存为Excel
    df = pd.DataFrame(filtered_results)
    
    # 添加备注列，格式为：姓名 + "助教-" + 城市 + "-" + 手机号 + 行号信息
    # 模拟Excel中的CONCAT(B2,"助教-",C2,"-",D2)格式并添加行号
    df['备注'] = df.apply(lambda row: 
                         f"{row['姓名'] if pd.notna(row['姓名']) and row['姓名'] else ''}助教-{row['城市'] if pd.notna(row['城市']) and row['城市'] else '--'}-{row['手机号'] if pd.notna(row['手机号']) and row['手机号'] else ''}(行{row.name+2})" 
                         if any(pd.notna(row[col]) and row[col] for col in ['姓名', '城市', '手机号']) else '', 
                         axis=1)
    
    # 确保格式正确，即使姓名为空也保持助教-前缀
    df['备注'] = df['备注'].str.replace('^助教--', '助教-')
    
    # 使用模块输出目录
    try:
        from services.storage_paths import module_output_dir

        output_dir = str(module_output_dir("resume_extractor", create=True))
    except Exception as e:
        print(f"获取输出目录配置时出错: {e}")
        output_dir = os.path.dirname(resume_directory)
    
    # 确保output目录存在
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "简历信息提取结果.xlsx")

    # 检查输出文件路径
    if not output_file:
        print("输出文件路径不能为空!")
        return

    # 确保输出文件的目录存在
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as e:
            print(f"创建输出目录时出错: {str(e)}")
            return

    try:
        from services.excel_export import dataframe_to_xlsx

        dataframe_to_xlsx(df, output_file)
        print(f"处理完成! 结果已保存到 {output_file}")
    except Exception as e:
        print(f"保存Excel文件时出错: {str(e)}")
        return
    
    print(f"共处理了 {len(filtered_results)} 份简历")
    
    # 显示提取结果统计
    print("\n提取结果统计:")
    for column in ["城市", "姓名", "手机号", "微信号"]:
        extracted_count = df[column].notna().sum()
        print(f"{column}: {extracted_count}/{len(df)} ({(extracted_count/len(df)*100):.1f}%)")

if __name__ == "__main__":
    main()