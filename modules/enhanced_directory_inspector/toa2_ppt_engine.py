#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
交付材料生成 PPT 导出引擎（自 TOA2 移植，无 tkinter）。
"""

from __future__ import annotations

import logging
import os
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Cm, Inches, Pt

from services.config_service import project_root
from services.mapping_rules import get_rule, resolve_rule_to_image, resolve_rule_to_images
from services.storage_paths import bundled_templates_dir, module_output_dir, user_templates_dir

logger = logging.getLogger(__name__)

try:
    PPTX_AVAILABLE = True
except Exception:  # pragma: no cover
    PPTX_AVAILABLE = False


class EnhancedDirectoryInspectorPPT:
    """交付材料生成 PPT 导出类"""

    def __init__(self, parent=None, project_type: str = "lixiao"):
        self.parent = parent
        self.selected_dir = None
        self.base_dir_name = ""
        self.log_content = ""
        # lixiao/liren = 利刃；poxiao = 破晓
        self.project_type = project_type or "lixiao"
        self.match_mode = "exact"
        self.last_output_path: str | None = None
        self.status_var = None

    def set_directory(self, directory):
        """设置要检查的目录"""
        if os.path.exists(directory) and os.path.isdir(directory):
            self.selected_dir = directory
            self.base_dir_name = os.path.basename(directory)
            self.log(f"已选择目录: {self.base_dir_name}")
            return True
        self.log(f"错误: 目录不存在或不是有效的目录: {directory}", error=True)
        return False

    def set_match_mode(self, mode):
        """设置匹配模式"""
        self.match_mode = mode
        self.log(f"已设置匹配模式: {mode}")

    def log(self, message, error=False, warning=False):
        """记录日志（logging + 内存缓冲，供页面展示）。"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_type = "ERROR" if error else "WARNING" if warning else "INFO"
        log_message = f"[{timestamp}] [{log_type}] {message}\n"
        self.log_content += log_message
        if error:
            logger.error("%s", message)
        elif warning:
            logger.warning("%s", message)
        else:
            logger.info("%s", message)
        if self.parent is not None:
            try:
                if hasattr(self.parent, "log") and callable(self.parent.log):
                    self.parent.log(message, error, warning)
                elif hasattr(self.parent, "update_log") and callable(self.parent.update_log):
                    self.parent.update_log(log_message, error)
            except Exception:
                pass

    def _find_template_file(self):
        """查找适合的 PPT 模板（bundled deliverables + 用户模板）。"""
        if self.project_type in ("liren", "lixiao"):
            candidates = [
                "deliverables/lixiao.pptx",
                "deliverables/利刃交付材料模版.pptx",
                "利刃交付材料模版.pptx",
                "lixiao.pptx",
            ]
            self.log(f"项目类型: {self.project_type}，使用利刃项目模板")
        elif self.project_type == "poxiao":
            candidates = [
                "deliverables/poxiao.pptx",
                "deliverables/破晓交付材料模版.pptx",
                "破晓交付材料模版.pptx",
                "poxiao.pptx",
            ]
            self.log(f"项目类型: {self.project_type}，使用破晓项目模板")
        else:
            candidates = [
                "deliverables/lixiao.pptx",
                "deliverables/poxiao.pptx",
                "利刃交付材料模版.pptx",
                "破晓交付材料模版.pptx",
            ]
            self.log(f"项目类型: {self.project_type}，尝试所有可用模板")

        search_roots = [
            bundled_templates_dir(),
            user_templates_dir(),
            project_root() / "assets" / "templates",
            project_root() / "templates",
        ]
        for rel in candidates:
            name = Path(rel).name
            for root in search_roots:
                for path in (root / rel, root / name, root / "deliverables" / name):
                    self.log(f"尝试查找模板: {path}")
                    if path.is_file():
                        self.log(f"找到模板文件: {path}")
                        return str(path)

        self.log("错误: 未找到适合的模板文件", error=True)
        self.log(f"请将模板放到: {bundled_templates_dir() / 'deliverables'}")
        return None

    def export_to_ppt(self, output_path: str | Path | None = None):
        """导出增强版 PPT。成功返回输出路径字符串，失败返回 None。"""
        if not self.selected_dir:
            self.log("错误: 未选择目录", error=True)
            return None

        if not PPTX_AVAILABLE:
            self.log("错误: python-pptx 库未安装，无法导出 PPT 文档", error=True)
            return None

        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
        else:
            export_dir = module_output_dir("enhanced_directory_inspector", create=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = export_dir / f"{self.base_dir_name}_交付材料_{timestamp}.pptx"

        if self._export_ppt(str(out)):
            self.last_output_path = str(out)
            self.log(f"PPT文档已成功导出到: {out}")
            return str(out)
        self.last_output_path = None
        return None

    def _replace_class_name(self, prs, class_name):
        """在PPT的所有幻灯片中替换班级名称占位符"""
        try:
            # 定义班级名称的占位符关键词
            class_name_keywords = ['班级名称', '模板班级名称']
            
            # 遍历所有幻灯片
            for slide in prs.slides:
                # 遍历幻灯片中的所有形状
                for shape in slide.shapes:
                    # 检查形状是否有文本框
                    if hasattr(shape, 'text_frame') and shape.text_frame:
                        # 遍历文本框中的所有段落
                        for paragraph in shape.text_frame.paragraphs:
                            # 遍历段落中的所有文本运行
                            for run in paragraph.runs:
                                # 检查并替换占位符
                                for keyword in class_name_keywords:
                                    if keyword in run.text:
                                        # 替换文本内容，保留原有格式
                                        run.text = run.text.replace(keyword, class_name)
                                        self.log(f"在幻灯片 {prs.slides.index(slide) + 1} 中替换班级名称: {keyword} -> {class_name}")
            
            return True
        except Exception as e:
            self.log(f"替换班级名称失败: {str(e)}", error=True)
            return False

    def _export_ppt(self, output_path):
        """使用精确位置布局逻辑执行PPT导出操作"""
        try:
            # 查找模板文件
            template_path = self._find_template_file()
            if not template_path:
                return False
                
            # 使用模板创建新的PPT文档
            prs = Presentation(template_path)
            
            # 设置幻灯片尺寸为宽屏格式（16:9）
            prs.slide_width = Inches(13.33)
            prs.slide_height = Inches(7.5)
            
            # 确保PPT文件有足够的幻灯片
            if len(prs.slides) < 2:
                self.log("错误: 模板幻灯片数量不足，至少需要2张幻灯片", error=True)
                return False
            
            # 替换所有幻灯片中的班级名称
            class_name = self.base_dir_name
            self._replace_class_name(prs, class_name)
            
            # 处理幻灯片1 - 物料全景和教室布置（利刃和破晓都有4个图片位）
            self._process_first_slide(prs, 0, template_path)
            
            # 处理幻灯片2 - 助教打卡和签到表（利刃和破晓都有7个图片位）
            self._process_second_slide(prs, 1, template_path)
            
            # 如果是破晓项目，处理第三页（2个图片位）
            if self.project_type == "poxiao":
                self.log("开始处理破晓项目特有第三页幻灯片")
                # 处理第三页 - 礼品和服务页面
                self._process_gift_service_slide(prs, 2, template_path)
            
            # 保存PPT文件
            prs.save(output_path)
            
            # 检查文件是否创建成功
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / 1024  # KB
                self.log(f"PPT文件创建成功: {output_path}")
                self.log(f"文件大小: {file_size:.2f} KB")
                return True
            else:
                self.log(f"错误: PPT文件创建失败: {output_path}", error=True)
                return False
        except Exception as e:
            self.log(f"导出PPT过程中发生错误: {str(e)}", error=True)
            traceback.print_exc()
            return False

    def _process_first_slide(self, presentation, slide_index, template_path):
        """处理第一张幻灯片 - 按照用户要求显示特定目录的图片（利刃和破晓都有4个图片位）"""
        slide = presentation.slides[slide_index]
        self.log(f"[{self.project_type.upper()}] 开始处理第一张幻灯片（4个图片位）")
        
        # 为破晓项目和利刃项目提供不同的目录路径选择
        if self.project_type == "poxiao":  # 破晓项目目录路径
            # 破晓项目的备选目录路径列表
            wall_materials_dirs = [
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '04-上墙物料-钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片', '04-上墙物料-钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT', '04-上墙物料-钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片', '04-上墙物料'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT', '04-上墙物料'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片')
            ]
            
            classroom_panorama_dirs = [
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '01-布置完成的全景照片-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片', '01-布置完成的全景照片-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT', '01-布置完成的全景照片-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片')
            ]
            
            material_water_dirs = [
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '05-当站全部物料拆箱合照(含水)-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片', '05-当站全部物料拆箱合照(含水)-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT', '05-当站全部物料拆箱合照(含水)-PPT'),
                os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉'),
                os.path.join(self.selected_dir, '03-教室布置照片')
            ]
            
            # 查找可用的目录
            wall_materials_dir = self._find_available_directory(wall_materials_dirs)
            classroom_panorama_dir = self._find_available_directory(classroom_panorama_dirs)
            material_water_dir = self._find_available_directory(material_water_dirs)
            
            self.log(f"[破晓项目] 找到上墙物料目录: {wall_materials_dir}")
            self.log(f"[破晓项目] 找到教室全景目录: {classroom_panorama_dir}")
            self.log(f"[破晓项目] 找到物料拆箱目录: {material_water_dir}")
        else:  # 利刃项目使用原有目录路径
            # 为利刃项目准备基础目录路径
            wall_materials_dir = os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '04-上墙物料-钉钉')
            classroom_panorama_dir = os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '01-布置完成的全景照片-PPT')
            material_water_dir = os.path.join(self.selected_dir, '03-教室布置照片-PPT&钉钉', '05-当站全部物料拆箱合照(含水)-PPT')
        
        # 获取上墙物料目录的图片
        wall_materials_photos = []
        if wall_materials_dir and os.path.isdir(wall_materials_dir):
            wall_materials_photos = self._get_image_files(wall_materials_dir)
            self.log(f"在 {wall_materials_dir} 中找到 {len(wall_materials_photos)} 张图片")
            # 若直放目录没有图片，递归子目录抓取
            if not wall_materials_photos:
                self.log(f"{wall_materials_dir} 直放没有图片，递归子目录抓取")
                wall_materials_photos = self._get_all_images_in_directory(wall_materials_dir, recursive=True)
                self.log(f"递归在 {wall_materials_dir} 中找到 {len(wall_materials_photos)} 张图片")
        else:
            self.log(f"警告: 上墙物料目录不存在: {wall_materials_dir}", warning=True)
        
        # 获取教室布置全景照片目录的图片
        classroom_panorama_photos = []
        if classroom_panorama_dir and os.path.isdir(classroom_panorama_dir):
            classroom_panorama_photos = self._get_image_files(classroom_panorama_dir)
            self.log(f"在 {classroom_panorama_dir} 中找到 {len(classroom_panorama_photos)} 张图片")
            # 若直放目录没有图片，递归子目录抓取
            if not classroom_panorama_photos:
                self.log(f"{classroom_panorama_dir} 直放没有图片，递归子目录抓取")
                classroom_panorama_photos = self._get_all_images_in_directory(classroom_panorama_dir, recursive=True)
                self.log(f"递归在 {classroom_panorama_dir} 中找到 {len(classroom_panorama_photos)} 张图片")
        else:
            self.log(f"警告: 教室布置全景照片目录不存在: {classroom_panorama_dir}", warning=True)
        
        # 获取物料拆箱合照目录的图片
        material_water_photos = []
        if material_water_dir and os.path.isdir(material_water_dir):
            material_water_photos = self._get_image_files(material_water_dir)
            self.log(f"在 {material_water_dir} 中找到 {len(material_water_photos)} 张图片")
            # 若直放目录没有图片，递归子目录抓取
            if not material_water_photos:
                self.log(f"{material_water_dir} 直放没有图片，递归子目录抓取")
                material_water_photos = self._get_all_images_in_directory(material_water_dir, recursive=True)
                self.log(f"递归在 {material_water_dir} 中找到 {len(material_water_photos)} 张图片")
        else:
            self.log(f"警告: 物料拆箱合照目录不存在: {material_water_dir}", warning=True)
        
        # 调试：记录幻灯片上的所有形状
        self.log(f"幻灯片包含 {len(slide.shapes)} 个形状")
        
        # 获取所有形状并筛选图片占位符
        all_shapes = self._find_all_shapes(slide.shapes)
        placeholder_shapes = [s for s in all_shapes if self._is_picture_placeholder(s)]
        self.log(f"检测到潜在图片占位符 {len(placeholder_shapes)} 个，按阅读顺序排序")
        # 排序：先按行(top)，再按列(left)
        placeholder_shapes = self._sort_shapes_reading_order(placeholder_shapes)
        
        # 获取可用的图片位置数量
        available_positions = len(placeholder_shapes)
        self.log(f"找到 {available_positions} 个可用的图片位置（需要4个图片位）")
        
        # 确保处理4个图片位置，无论找到多少占位符
        for i in range(4):
            if i < available_positions:
                shape = placeholder_shapes[i]
                
                # 根据项目类型和位置确定使用的图片
                if self.project_type in ("liren", "lixiao"):  # 利刃
                    self.log(f"[利刃项目] 处理第一张幻灯片第{i+1}个位置，应用前缀+序号匹配")
                    target_image = None
                    rule = get_rule("交付材料生成", self.project_type, template_path, slide_index+1, i+1)
                    if rule:
                        self.log(f"[利刃项目] 处理第一张幻灯片第{i+1}个位置，应用规则: {rule}")
                        target_image = resolve_rule_to_image(self.selected_dir, rule)
                    else:
                        self.log(f"[利刃项目] 未找到位置{i+1}的规则，使用默认逻辑")
                        if i == 0:
                            target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 1, recursive=True)
                            self.log(f"[利刃项目] 位置1需要匹配: 03开头图1")
                        elif i == 1:
                            target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 2, recursive=True)
                            self.log(f"[利刃项目] 位置2需要匹配: 03开头图2")
                        elif i == 2:
                            target_image = self._find_image_by_prefix_and_index(self.selected_dir, '01', 1, recursive=True)
                            self.log(f"[利刃项目] 位置3需要匹配: 01开头图1")
                        elif i == 3:
                            target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 3, recursive=True)
                            self.log(f"[利刃项目] 位置4需要匹配: 03开头图3")
                    if target_image:
                        self.log(f"[利刃项目] 在第一页第{i+1}个位置添加图片")
                        self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, target_image)
                        self.log(f"图片添加完成：{os.path.basename(target_image)}")
                    else:
                        self.log(f"[利刃项目] 未找到第{i+1}个位置图片，留空", warning=True)
                elif self.project_type == "poxiao":  # 破晓项目精准匹配逻辑
                    self.log(f"[破晓项目] 处理第一张幻灯片第{i+1}个位置，应用前缀+序号匹配")
                    target_image = None
                    
                    # 根据位置匹配前缀+序号
                    if i == 0:  # 第1个位置 -> 03开头的图1
                        target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 1, recursive=True)
                        self.log(f"[破晓项目] 位置1需要匹配: 03开头图1")
                    elif i == 1:  # 第2个位置 -> 03开头的图2
                        target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 2, recursive=True)
                        self.log(f"[破晓项目] 位置2需要匹配: 03开头图2")
                    elif i == 2:  # 第3个位置 -> 01开头的图1
                        target_image = self._find_image_by_prefix_and_index(self.selected_dir, '01', 1, recursive=True)
                        self.log(f"[破晓项目] 位置3需要匹配: 01开头图1")
                    elif i == 3:  # 第4个位置 -> 03开头的图3
                        target_image = self._find_image_by_prefix_and_index(self.selected_dir, '03', 3, recursive=True)
                        self.log(f"[破晓项目] 位置4需要匹配: 03开头图3")
                    
                    # 如果找到匹配的图片，添加到幻灯片
                    if target_image:
                        self.log(f"[破晓项目] 在第一页第{i+1}个位置添加指定前缀图片")
                        self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, target_image)
                        self.log(f"图片添加完成：{os.path.basename(target_image) if target_image else str(target_image)}")
                    else:
                        # 如果没有找到前缀匹配的图片，回退到原有逻辑
                        self.log(f"[破晓项目] 未找到指定前缀图片，回退到原有逻辑", warning=True)
                        # 使用原有逻辑处理
                        if i == 0 or i == 1:  # 第1、2个位置使用上墙物料图片
                            if wall_materials_photos:
                                img_index = i if i < len(wall_materials_photos) else 0
                                img_to_use = wall_materials_photos[img_index]
                                self.log(f"在第一页第{i+1}个位置添加上墙物料图片")
                                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                                self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                            else:
                                self.log(f"警告: 上墙物料目录中没有图片，第{i+1}个位置留空")
                        elif i == 2:  # 第3个位置使用教室布置全景照片
                            if classroom_panorama_photos:
                                img_to_use = classroom_panorama_photos[0]
                                self.log(f"在第一页第{i+1}个位置添加教室布置全景照片")
                                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                                self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                            else:
                                self.log(f"警告: 教室布置全景照片目录中没有图片，第{i+1}个位置留空")
                        elif i == 3:  # 第4个位置使用物料拆箱合照
                            if material_water_photos:
                                img_to_use = material_water_photos[0]
                                self.log(f"在第一页第{i+1}个位置添加物料拆箱合照")
                                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                                self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                            else:
                                self.log(f"警告: 物料拆箱合照目录中没有图片，第{i+1}个位置留空")
                else:  # 其他项目使用原有逻辑
                    # 根据位置确定使用的图片
                    if i == 0 or i == 1:  # 第1、2个位置使用上墙物料图片
                        if wall_materials_photos:
                            # 为第1、2个位置选择合适的图片
                            img_index = i if i < len(wall_materials_photos) else 0
                            img_to_use = wall_materials_photos[img_index]
                            self.log(f"在第一页第{i+1}个位置添加上墙物料图片")
                            self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                            self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                        else:
                            self.log(f"警告: 上墙物料目录中没有图片，第{i+1}个位置留空")
                    elif i == 2:  # 第3个位置使用教室布置全景照片
                        if classroom_panorama_photos:
                            img_to_use = classroom_panorama_photos[0]
                            self.log(f"在第一页第{i+1}个位置添加教室布置全景照片")
                            self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                            self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                        else:
                            self.log(f"警告: 教室布置全景照片目录中没有图片，第{i+1}个位置留空")
                    elif i == 3:  # 第4个位置使用物料拆箱合照
                        if material_water_photos:
                            img_to_use = material_water_photos[0]
                            self.log(f"在第一页第{i+1}个位置添加物料拆箱合照")
                            self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                            self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                        else:
                            self.log(f"警告: 物料拆箱合照目录中没有图片，第{i+1}个位置留空")
            else:
                # 未找到占位符时，使用默认位置直接添加图片
                default_positions = [
                    (1000, 1000, 3500, 2500),
                    (5000, 1000, 3500, 2500),
                    (1000, 4000, 3500, 2500),
                    (5000, 4000, 3500, 2500),
                ]
                if i < len(default_positions):
                    left, top, width, height = default_positions[i]
                    img_to_use = None
                    if self.project_type in ("liren", "lixiao", "poxiao"):
                        if i in (0, 1) and wall_materials_photos:
                            img_index = i if i < len(wall_materials_photos) else 0
                            img_to_use = wall_materials_photos[img_index]
                            self.log(f"在第一页默认位置{i+1}添加上墙物料图片")
                        elif i == 2 and classroom_panorama_photos:
                            img_to_use = classroom_panorama_photos[0]
                            self.log(f"在第一页默认位置{i+1}添加教室布置全景照片")
                        elif i == 3 and material_water_photos:
                            img_to_use = material_water_photos[0]
                            self.log(f"在第一页默认位置{i+1}添加物料拆箱合照")
                    if img_to_use:
                        self._add_image_to_position(slide, left, top, width, height, img_to_use)
                        self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
                    else:
                        self.log(f"警告: 没有可用图片添加到第一页默认位置{i+1}")

    def _process_second_slide(self, presentation, slide_index, template_path):
        """处理第二张幻灯片 - 助教打卡照片和签到表（利刃和破晓都有7个图片位）"""
        slide = presentation.slides[slide_index]
        self.log(f"[{self.project_type.upper()}] 开始处理第二张幻灯片（7个图片位）")
        
        # 根据项目类型使用不同的目录查找策略
        if self.project_type == "poxiao":  # 破晓项目目录路径
            # 破晓项目的助教打卡照片备选目录列表
            assistant_photo_dirs = [
                os.path.join(self.selected_dir, '02-助教打卡照片-PPT'),
                os.path.join(self.selected_dir, '02-助教打卡照片'),
                os.path.join(self.selected_dir, '02-助教打卡照片-PPT&钉钉'),
                os.path.join(self.selected_dir, '02-助教打卡照片-PPT'),
                os.path.join(self.selected_dir, '02-助教打卡照片（最后一天）-PPT'),
                os.path.join(self.selected_dir, '02-助教打卡照片（最后一天完整版）-PPT')
            ]
            
            # 破晓项目的签到表照片备选目录列表
            sign_in_photo_dirs = [
                os.path.join(self.selected_dir, '01-签到表照片-PPT'),
                os.path.join(self.selected_dir, '01-签到表照片（最后一天完整版）-PPT'),
                os.path.join(self.selected_dir, '01-签到表照片'),
                os.path.join(self.selected_dir, '01-签到表照片-PPT&钉钉'),
                os.path.join(self.selected_dir, '01-签到表照片（最后一天）-PPT')
            ]
            
            self.log("[破晓项目] 使用破晓项目专用的目录查找策略")
        else:  # 利刃项目使用原有目录路径
            assistant_photo_dirs = [
                os.path.join(self.selected_dir, '02-助教打卡照片-PPT'),
                os.path.join(self.selected_dir, '02-助教打卡照片')
            ]
            
            sign_in_photo_dirs = [
                os.path.join(self.selected_dir, '01-签到表照片-PPT'),
                os.path.join(self.selected_dir, '01-签到表照片（最后一天完整版）-PPT'),
                os.path.join(self.selected_dir, '01-签到表照片')
            ]
            
            self.log("[利刃项目] 使用利刃项目专用的目录查找策略")
        
        # 获取幻灯片上所有形状（包括组合形状内的形状）
        all_shapes = self._find_all_shapes(slide.shapes)
        
        # 记录所有形状的信息用于调试
        self.log(f"在第二页幻灯片中找到 {len(all_shapes)} 个形状")
        for i, shape in enumerate(all_shapes):
            if hasattr(shape, 'width') and hasattr(shape, 'height'):
                self.log(f"形状 {i}: 类型={shape.shape_type}, 宽={shape.width}, 高={shape.height}")
        
        # 查找适合放置照片的占位符 - 使用更灵活的尺寸范围和处理大数值
        placeholder_shapes = []
        for shape in all_shapes:
            # 寻找特定大小的矩形，这些可能是照片占位符
            if hasattr(shape, 'shape_type') and shape.shape_type == 1:  # AUTO_SHAPE (矩形等)
                if hasattr(shape, 'width') and hasattr(shape, 'height'):
                    width = shape.width
                    height = shape.height
                    
                    # 处理大数值尺寸 - 针对模板中发现的大尺寸占位符
                    # 助教打卡占位符 (约 160万-170万宽，230万-240万高)
                    if (width > 1500000 and width < 1800000) and (height > 2200000 and height < 2500000):
                        placeholder_shapes.append((shape, "assistant"))
                        self.log(f"找到助教打卡图片占位符: 宽={width}, 高={height}")
                    # 签到表占位符 (约 450万宽，230万-240万高)
                    elif (width > 4000000 and width < 5000000) and (height > 2200000 and height < 2500000):
                        placeholder_shapes.append((shape, "sign_in"))
                        self.log(f"找到签到表图片占位符: 宽={width}, 高={height}")
        
        # 分离助教打卡和签到表占位符
        assistant_placeholders = [s for s, t in placeholder_shapes if t == "assistant"]
        sign_in_placeholders = [s for s, t in placeholder_shapes if t == "sign_in"]
        
        # 助教打卡图片按位置排序
        assistant_placeholders.sort(key=lambda x: (x.top, x.left))
        # 签到表图片按位置排序
        sign_in_placeholders.sort(key=lambda x: (x.top, x.left))
        
        # 合并排序后的占位符 - 确保总共处理7个位置
        # 对于利刃和破晓模板，通常是6个助教打卡和1个签到表位置
        sorted_placeholders = []
        
        # 优先添加助教打卡占位符（最多6个）
        sorted_placeholders.extend(assistant_placeholders[:6])
        
        # 然后添加签到表占位符（最多1个）
        if sign_in_placeholders:
            sorted_placeholders.append(sign_in_placeholders[0])
        
        # 处理第1-6张图片（助教打卡照片）
        assistant_rule = get_rule("交付材料生成", self.project_type, template_path, slide_index+1, "1-6")
        assistant_photos = []
        if assistant_rule:
            self.log(f"[规则系统] 应用助教打卡照片规则: {assistant_rule}")
            assistant_photos = resolve_rule_to_images(self.selected_dir, assistant_rule)
            self.log(f"[规则系统] 找到 {len(assistant_photos)} 张助教打卡照片")
        else:
            self.log(f"[规则系统] 未找到助教打卡照片规则，使用默认逻辑")
            
            # 查找助教打卡照片
            assistant_photos = []
            for dir_path in assistant_photo_dirs:
                if os.path.exists(dir_path):
                    photos = self._get_all_images_in_directory(dir_path)
                    if photos:
                        assistant_photos.extend(photos)
                        self.log(f"从目录 {os.path.basename(dir_path)} 找到 {len(photos)} 张助教打卡照片")
                        break
            
            # 如果没有在指定目录找到，递归搜索根目录
            if not assistant_photos:
                self.log("未在指定目录找到助教打卡照片，递归搜索根目录")
                
                all_root_photos = self._get_all_images_in_directory(self.selected_dir, recursive=True)
                # 过滤出可能是助教打卡的照片（基于文件名或内容）
                for photo in all_root_photos:
                    if any(keyword in os.path.basename(photo).lower() for keyword in ['助教', '打卡', 'photo']):
                        assistant_photos.append(photo)
                    if len(assistant_photos) >= 6:  # 最多取6张
                        break
        
        # 处理第7张图片（签到表照片）
        sign_in_rule = get_rule("交付材料生成", self.project_type, template_path, slide_index+1, 7)
        sign_in_photos = []
        if sign_in_rule:
            self.log(f"[规则系统] 应用签到表照片规则: {sign_in_rule}")
            sign_in_photos = resolve_rule_to_images(self.selected_dir, sign_in_rule)
            self.log(f"[规则系统] 找到 {len(sign_in_photos)} 张签到表照片")
        else:
            self.log(f"[规则系统] 未找到签到表照片规则，使用默认逻辑")
            
            # 查找签到表照片
            sign_in_photos = []
            for dir_path in sign_in_photo_dirs:
                if os.path.exists(dir_path):
                    photos = self._get_all_images_in_directory(dir_path)
                    if photos:
                        sign_in_photos.extend(photos)
                        self.log(f"从目录 {os.path.basename(dir_path)} 找到 {len(photos)} 张签到表照片")
                        break
            
            # 如果没有在指定目录找到，递归搜索根目录
            if not sign_in_photos:
                self.log("未在指定目录找到签到表照片，递归搜索根目录")
                
                all_root_photos = self._get_all_images_in_directory(self.selected_dir, recursive=True)
                # 过滤出可能是签到表的照片，同时排除已找到的助教照片
                for photo in all_root_photos:
                    if photo not in assistant_photos and any(keyword in os.path.basename(photo).lower() for keyword in ['签到', 'sign', '表', 'list']):
                        sign_in_photos.append(photo)
                        break  # 只需要一张签到表照片
        
        # 处理每个占位符位置
        for i, shape in enumerate(sorted_placeholders):
            # 判断当前位置是否是助教打卡还是签到表
            is_assistant = i < 6  # 前6个位置是助教打卡，第7个位置是签到表
            
            img_to_use = None
            if is_assistant and i < len(assistant_photos):
                img_to_use = assistant_photos[i]
                self.log(f"在第二页第{i+1}个位置添加助教打卡照片")
                # 添加新图片
                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
            elif not is_assistant and sign_in_photos:
                img_to_use = sign_in_photos[0]
                self.log(f"在第二页第{i+1}个位置添加签到表照片")
                # 添加新图片
                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, img_to_use)
                self.log(f"图片添加完成：{os.path.basename(img_to_use) if img_to_use else str(img_to_use)}")
            else:
                self.log(f"警告: 没有可用图片添加到第二页第{i+1}个位置")

    def _get_image_files(self, directory):
        """获取目录中所有图片文件（非递归）"""
        return self._get_all_images_in_directory(directory, recursive=False)

    def _find_all_shapes(self, shapes):
        """
        递归获取所有形状，包括组合形状内的形状
        
        :param shapes: 形状集合
        :return: 包含所有形状的列表
        """
        all_shapes = []
        for shape in shapes:
            all_shapes.append(shape)
            # 如果是组合形状，递归获取内部形状
            if hasattr(shape, 'shape_type') and shape.shape_type == 6:  # GROUP_SHAPE
                all_shapes.extend(self._find_all_shapes(shape.shapes))
        return all_shapes

    def _is_picture_placeholder(self, shape):
        """
        判断形状是否为图片占位符
        
        :param shape: 形状对象
        :return: 如果是图片占位符返回True，否则返回False
        """
        try:
            placeholder_format = getattr(shape, 'placeholder_format', None)
            placeholder_type = getattr(placeholder_format, 'type', None)
            
            if placeholder_type == 18:
                return True
            else:
                return False
        except Exception as e:
            self.log(f"调试：访问placeholder_format时发生异常 - {str(e)}")
            # 如果发生异常，尝试检查是否为矩形形状
            return shape.shape_type == 1

    def _add_image_to_position(self, slide, left, top, width, height, image_path, keep_aspect_ratio=True):
        """
        将图片添加到幻灯片的指定位置
        
        :param slide: 幻灯片对象
        :param left: 左侧位置
        :param top: 顶部位置
        :param width: 宽度
        :param height: 高度
        :param image_path: 图片文件路径
        :param keep_aspect_ratio: 是否保持宽高比
        """
        if not image_path or not os.path.exists(image_path):
            self.log(f"警告: 图片文件不存在: {image_path}", warning=True)
            return
            
        try:
            # 直接使用add_picture方法添加图片到指定位置
            # 这样可以避免依赖形状是否为占位符的检查
            if keep_aspect_ratio:
                # 添加图片并保持宽高比
                pic = slide.shapes.add_picture(image_path, left, top, width=width)
                # 调整高度以保持宽高比
                original_height = pic.height
                original_width = pic.width
                if original_width > 0:
                    new_height = int((original_height / original_width) * width)
                    pic.height = new_height
            else:
                # 强制设置指定的宽高
                pic = slide.shapes.add_picture(image_path, left, top, width=width, height=height)
                
            self.log(f"图片已添加到PPT: {os.path.basename(image_path)}")
            
        except Exception as e:
            self.log(f"错误: 添加图片时发生异常 - {str(e)}", error=True)

    def _get_all_images_in_directory(self, directory, recursive=False):
        """
        获取目录中的所有图片文件
        
        :param directory: 目录路径
        :param recursive: 是否递归搜索子目录
        :return: 图片文件路径列表
        """
        if not directory or not os.path.exists(directory):
            self.log(f"警告: 目录不存在或为空: {directory}", warning=True)
            return []
            
        image_files = []
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif')
        
        try:
            if recursive:
                # 递归遍历目录
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        if file.lower().endswith(image_extensions):
                            file_path = os.path.join(root, file)
                            image_files.append(file_path)
            else:
                # 只遍历当前目录
                for file in os.listdir(directory):
                    file_path = os.path.join(directory, file)
                    if os.path.isfile(file_path) and file.lower().endswith(image_extensions):
                        image_files.append(file_path)
                        
            # 按文件名排序
            image_files.sort()
            self.log(f"在目录 {directory} 中找到 {len(image_files)} 张图片")
              
        except Exception as e:
            self.log(f"错误: 搜索图片文件时发生异常 - {str(e)}", error=True)
            return []
            
        return image_files

    def _find_image_by_prefix_and_index(self, directory, prefix, index, recursive=False):
        """
        根据前缀和序号查找图片文件
        
        :param directory: 目录路径
        :param prefix: 文件名前缀
        :param index: 图片序号
        :param recursive: 是否递归搜索
        :return: 找到的图片文件路径，未找到则返回None
        """
        if not directory or not os.path.exists(directory):
            self.log(f"警告: 目录不存在: {directory}", warning=True)
            return None
            
        try:
            # 获取所有图片文件
            all_images = self._get_all_images_in_directory(directory, recursive=recursive)
            
            # 根据前缀和序号匹配图片
            target_pattern = f"{prefix}-.*{index}.*"
            import re
            
            for image_path in all_images:
                filename = os.path.basename(image_path)
                if re.match(target_pattern, filename):
                    return image_path
            
            # 如果没有找到精确匹配，尝试更宽松的匹配
            for image_path in all_images:
                filename = os.path.basename(image_path)
                if prefix in filename and str(index) in filename:
                    return image_path
            
            self.log(f"未找到匹配的图片: 前缀={prefix}, 序号={index}", warning=True)
            return None
            
        except Exception as e:
            self.log(f"查找图片时发生错误: {str(e)}", error=True)
            return None

    def _sort_shapes_reading_order(self, shapes, row_tolerance=300000):
        rows = []
        keyed = []
        for shp in shapes:
            top = getattr(shp, 'top', None)
            left = getattr(shp, 'left', None)
            if top is not None and left is not None:
                keyed.append((shp, int(top), int(left)))
        keyed.sort(key=lambda t: (t[1], t[2]))
        for shp, top, left in keyed:
            placed = False
            for row in rows:
                if abs(row['top'] - top) <= row_tolerance:
                    row['items'].append((shp, left))
                    placed = True
                    break
            if not placed:
                rows.append({'top': top, 'items': [(shp, left)]})
        rows.sort(key=lambda r: r['top'])
        sorted_shapes = []
        for row in rows:
            row['items'].sort(key=lambda it: it[1])
            sorted_shapes.extend([it[0] for it in row['items']])
        return sorted_shapes

    def _process_gift_service_slide(self, presentation, slide_index, template_path):
        """处理第三张幻灯片 - 礼品和服务页面（破晓项目，2个图片位）"""
        slide = presentation.slides[slide_index]
        self.log("[破晓项目] 开始处理第三张幻灯片（2个图片位）")
        
        # 获取幻灯片上所有形状（包括组合形状内的形状）
        all_shapes = self._find_all_shapes(slide.shapes)
        
        # 查找礼品/服务图片占位符
        placeholder_shapes = []
        for shape in all_shapes:
            if self._is_picture_placeholder(shape):
                placeholder_shapes.append(shape)
            else:
                # 兼容破晓项目特定尺寸范围
                if (getattr(shape, 'shape_type', None) == 1 and
                    (getattr(shape, 'width', 0) > 2000000 and getattr(shape, 'width', 0) < 5000000) and
                    (getattr(shape, 'height', 0) > 2000000 and getattr(shape, 'height', 0) < 4000000)):
                    placeholder_shapes.append(shape)
        
        # 排序：阅读顺序（先行后列）
        placeholder_shapes = self._sort_shapes_reading_order(placeholder_shapes)
        
        # 获取可用的图片位置数量
        available_positions = len(placeholder_shapes)
        self.log(f"在第三页找到 {available_positions} 个图片占位符，需要2个图片位")
        
        # 按用户要求的精确路径匹配
        if self.project_type == "poxiao":  # 破晓项目
            gift_photos = [
                os.path.join(self.selected_dir, '03-教室布置照片PPT&钉钉', '04-衣服&奖品-PPT', '12.jpg'),
                os.path.join(self.selected_dir, '03-教室布置照片PPT&钉钉', '04-衣服&奖品-PPT', '13.jpg')
            ]
        else:
            gift_photos = []
        
        # 添加图片到幻灯片
        for i, photo_path in enumerate(gift_photos[:available_positions]):
            if os.path.exists(photo_path):
                shape = placeholder_shapes[i]
                self._add_image_to_position(slide, shape.left, shape.top, shape.width, shape.height, photo_path)
                self.log(f"成功将图片添加到第三页位置{i+1}: {os.path.basename(photo_path)}")
            else:
                self.log(f"警告: 未找到第三页位置{i+1}需要的图片: {photo_path}", warning=True)

    def _find_available_directory(self, directory_list):
        """从目录列表中查找第一个存在的目录
        
        :param directory_list: 目录路径列表
        :return: 第一个存在的目录路径，如果没有找到则返回None
        """
        for directory in directory_list:
            if os.path.exists(directory):
                return directory
        return None

if __name__ == "__main__":
    # 示例用法
    import sys
    
    if len(sys.argv) > 1:
        dir_path = sys.argv[1]
        ppt_exporter = EnhancedDirectoryInspectorPPT()
        if ppt_exporter.set_directory(dir_path):
            ppt_exporter.export_to_ppt()
        else:
            print(f"错误: 无效的目录路径: {dir_path}")
    else:
        print("用法: python enhanced_directory_inspector_ppt.py <目录路径>")