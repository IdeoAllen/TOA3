#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排程格式转换工具
用于解析Excel排程表格，并将合并单元格中的课程信息转换为结构化数据
"""
import pandas as pd
import os
import re
from datetime import datetime, timedelta
import openpyxl
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Alignment, Border, Side, PatternFill
import numpy as np

class ScheduleFormatConverter:
    """排程格式转换工具类"""
    
    def __init__(self):
        self.excel_file = None
        self.data_frame = None
        self.schedule_data = []
        self.summary_data = []
        self.selected_year = None
        self.selected_month = None
        self.has_special_date_row = True  # 标记是否有特殊的日期行
        self.wb = None  # 存储工作簿对象，用于处理合并单元格
        # 新增：用于统计课程类型的数据
        self.course_stats = {
            'total': 0,
            '破晓突击课程': 0,
            '利刃出鞘课程': 0,
            '销售顾问课程': 0  # 添加销售顾问课程的统计
        }
    
    def load_excel_file(self, file_path):
        """
        加载Excel文件
        
        Args:
            file_path: Excel文件路径
        
        Returns:
            bool: 是否加载成功
            str: 错误信息（如果有）
        """
        try:
            if not os.path.exists(file_path):
                return False, "文件不存在"
            
            # 判断文件类型
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext in ['.xlsx', '.xls']:
                # 使用pandas读取Excel文件
                self.data_frame = pd.read_excel(file_path)
                # 使用openpyxl读取工作簿，用于处理合并单元格
                self.wb = openpyxl.load_workbook(file_path)
            else:
                return False, "不支持的文件类型，请选择Excel文件"
            
            self.excel_file = file_path
            return True, "文件加载成功"
        except Exception as e:
            return False, f"加载文件时出错: {str(e)}"
    
    def set_year_month(self, year, month):
        """
        设置年份和月份
        
        Args:
            year: 年份
            month: 月份
        """
        self.selected_year = year
        self.selected_month = month
    
    def _is_cell_in_merged(self, row, col, merged_cells):
        """
        检查单元格是否在合并单元格中
        
        Args:
            row: 行索引
            col: 列索引
            merged_cells: 合并单元格列表
        
        Returns:
            tuple: (是否在合并单元格中, 合并单元格范围(start_row, start_col, end_row, end_col))
        """
        for merged_range in merged_cells:
            if merged_range[0] <= row <= merged_range[2] and merged_range[1] <= col <= merged_range[3]:
                return True, merged_range
        return False, None
    
    def _get_merged_cells(self):
        """
        获取Excel文件中的所有合并单元格
        
        Returns:
            list: 合并单元格范围列表，每个元素格式为(start_row, start_col, end_row, end_col)
        """
        merged_cells = []
        if self.wb:
            # 获取第一个工作表
            sheet = self.wb.active
            # 遍历所有合并单元格
            for merged_cell in sheet.merged_cells:
                # 转换为0索引
                start_row = merged_cell.min_row - 1
                start_col = merged_cell.min_col - 1
                end_row = merged_cell.max_row - 1
                end_col = merged_cell.max_col - 1
                merged_cells.append((start_row, start_col, end_row, end_col))
        return merged_cells

    def parse_schedule_data(self):
        """
        解析排程数据，提取课程信息
        
        Returns:
            bool: 是否解析成功
            str: 错误信息（如果有）
        """
        try:
            if self.data_frame is None:
                return False, "请先加载Excel文件"
            
            if self.selected_year is None or self.selected_month is None:
                return False, "请选择课程年月"
            
            self.schedule_data = []
            # 重置课程统计
            # 用户要求：仅包含破晓突击和利刃出鞘两个项目的统计
            self.course_stats = {
                'total': 0,
                '破晓突击课程': 0,
                '利刃出鞘课程': 0
            }
            
            # 获取表格中的日期信息（从第1-2行查找日期，1-31的数字）
            date_columns = []
            date_row_index = -1  # 记录日期所在行的索引
            max_search_rows = min(2, len(self.data_frame))  # 最多检查前2行以寻找日期
            for i in range(max_search_rows):
                has_date = False
                for j, cell in enumerate(self.data_frame.iloc[i]):
                    # 检查是否为日期或数字（1-31）
                    if isinstance(cell, (int, float)) and 1 <= cell <= 31:
                        date_columns.append((j, int(cell)))
                        has_date = True
                if has_date:
                    self.has_special_date_row = True
                    date_row_index = i
                    break
            
            # 如果还是没找到日期，尝试使用默认日期（假设从1号开始）
            if not date_columns:
                # 获取最大列数
                max_cols = len(self.data_frame.columns)
                # 为每一列分配一个日期，从1号开始
                for j in range(min(max_cols, 31)):  # 最多分配31个日期
                    date_columns.append((j, j + 1))
                
                if not date_columns:
                    # 如果仍然无法获取日期，返回更详细的错误信息
                    return False, "未找到日期信息，请检查Excel格式。确保表格中有包含数字1-31的单元格作为日期标识。"
            
            # 自动检测数据开始行 - 从日期行的下一行开始
            start_row = date_row_index + 1 if date_row_index >= 0 else 0
            
            # 确保start_row不超过数据框的行数
            if start_row >= len(self.data_frame):
                return False, f"数据行数不足，无法从第{start_row + 1}行开始解析"
            
            # 获取合并单元格信息
            merged_cells = self._get_merged_cells()
            
            # 按照用户要求优化的解析逻辑：按列方向遍历31次
            # 1. 遍历日期对应的列（最多31列，对应一个月的天数）
            date_columns_dict = {col: day for col, day in date_columns}  # 转换为字典便于查找
            
            # 遍历数据区域的行（从检测到的开始行开始）
            for i in range(start_row, len(self.data_frame)):
                # 按用户要求：按列方向遍历31次
                j = 0
                while j < len(self.data_frame.columns):
                    cell_value = self.data_frame.iloc[i, j]
                    
                    # 跳过空单元格
                    if pd.isna(cell_value):
                        j += 1
                        continue
                    
                    cell_value = str(cell_value).strip()
                    if not cell_value:
                        j += 1
                        continue
                    
                    # 检查当前单元格是否在合并单元格中
                    is_merged, merged_range = self._is_cell_in_merged(i, j, merged_cells)
                    
                    # 对于合并单元格，只处理左上角的单元格
                    if is_merged and (i, j) != (merged_range[0], merged_range[1]):
                        j += 1
                        continue
                    
                    # 确定日期和天数
                    start_date = None
                    days = 1  # 默认1天
                    
                    # 检查当前列是否有日期标识
                    if j in date_columns_dict:
                        start_date = date_columns_dict[j]
                        
                        # 按用户要求：计算横向通栏数量
                        # 如果是合并单元格，通栏数就是合并的列数
                        if is_merged:
                            # 合并单元格的列跨度即为通栏数
                            start_col = merged_range[1]
                            end_col = merged_range[3]
                            days = end_col - start_col + 1
                        else:
                            # 非合并单元格，检查右侧相邻的非空单元格数量
                            temp_j = j + 1
                            while temp_j < len(self.data_frame.columns):
                                next_cell = self.data_frame.iloc[i, temp_j]
                                if pd.isna(next_cell) or str(next_cell).strip() == '':
                                    break
                                temp_j += 1
                            days = temp_j - j
                    
                    # 如果没有找到对应的日期，使用默认日期
                    if start_date is None:
                        start_date = j % 31 + 1
                        days = 1
                    
                    # 计算结束日期
                    end_date = min(start_date + days - 1, 31)
                    
                    # 解析课程信息
                    course_info = self._parse_course_info(cell_value, start_date, end_date)
                    if course_info:
                        self.schedule_data.append(course_info)
                        # 更新课程统计
                        self.course_stats['total'] += 1
                        self.course_stats[course_info['project_belonging'] + '课程'] += 1
                    
                    # 跳过已处理的列
                    j += days
            
            # 按开始日期升序排序，转换为datetime对象后再排序
            self.schedule_data.sort(key=lambda x: datetime.strptime(x['start_date'], "%Y/%m/%d"))
            
            # 生成汇总数据
            self._generate_summary_data()
            
            return True, f"成功解析{len(self.schedule_data)}条课程信息"
        except Exception as e:
            return False, f"解析数据时出错: {str(e)}"

    def _parse_course_info(self, course_text, start_date, end_date):
        """
        解析课程信息文本
        
        Args:
            course_text: 课程信息文本，格式：课程名称-城市-战区 或 课程名称-城市 日期范围
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            dict: 解析后的课程信息，如果城市未解析成功则返回None
        """
        try:
            # 统一处理课程名称格式，确保城市提取正确
            course_name = ""
            city = ""
            theater = ""
            
            # 先清理课程文本，去除首尾空格和制表符
            clean_text = course_text.strip(' \t\n\r')
            
            # 替换英文短线为中文短线
            clean_text = clean_text.replace('-', '-')
            
            # 增强空格处理：将多个连续空格替换为单个空格，然后处理
            clean_text = re.sub(r'\s+', ' ', clean_text)
            
            # 打印详细日志，帮助调试
            print(f"解析课程文本: '{clean_text}', 开始日期: {start_date}, 结束日期: {end_date}")
            
            # 通用解析逻辑，不再固定特定课程名称的处理
            # 先检查是否包含空格（特殊格式：课程名称-城市 日期范围）
            if ' ' in clean_text:
                # 先按'-'分割
                course_parts = clean_text.split('-', 1)
                if len(course_parts) >= 1:
                    course_name = course_parts[0].strip()
                    
                    if len(course_parts) >= 2:
                        # 处理城市和日期部分
                        city_date_part = course_parts[1]
                        # 提取城市名称（第一个空格前的内容）
                        city_parts = city_date_part.split(' ', 1)
                        if city_parts:
                            city = city_parts[0].strip()
            
            # 如果没有空格或者前面的方法没有提取到城市，使用标准分隔符处理
            if not city or not course_name:
                # 按'-'分割所有部分
                parts = clean_text.split('-')
                if len(parts) >= 1:
                    # 至少有课程名称
                    course_name = parts[0].strip()
                    
                    if len(parts) >= 2:
                        # 有城市信息
                        city = parts[1].strip()
                        
                        if len(parts) >= 3:
                            # 有战区信息
                            theater = '-'.join(parts[2:]).strip()
                        else:
                            # 简化格式：课程名称-城市
                            theater = ""  # 默认没有战区信息
            
            # 如果仍然没有提取到城市，尝试特殊格式处理
            if not city and '-' in clean_text:
                city_start = clean_text.find('-')
                if city_start != -1:
                    remaining_part = clean_text[city_start+1:].strip()
                    # 尝试从剩余部分提取城市
                    if '-' in remaining_part:
                        parts = remaining_part.split('-', 1)
                        city = parts[0].strip()
                        if len(parts) > 1:
                            theater = parts[1].strip()
                    elif '\t' in remaining_part:
                        parts = remaining_part.split('\t', 1)
                        city = parts[0].strip()
                        if len(parts) > 1:
                            theater = parts[1].strip()
                    elif ' ' in remaining_part:
                        parts = remaining_part.split(' ', 1)
                        city = parts[0].strip()
                        if len(parts) > 1:
                            theater = parts[1].strip()
                    else:
                        city = remaining_part
            else:
                # 先检查是否包含空格（特殊格式：课程名称-城市 日期范围）
                if ' ' in clean_text:
                    # 先按'-'分割
                    course_parts = clean_text.split('-', 1)
                    if len(course_parts) >= 1:
                        course_name = course_parts[0].strip()
                        
                        if len(course_parts) >= 2:
                            # 处理城市和日期部分
                            city_date_part = course_parts[1]
                            # 提取城市名称（第一个空格前的内容）
                            city_parts = city_date_part.split(' ', 1)
                            if city_parts:
                                city = city_parts[0].strip()
                
                # 如果没有空格或者前面的方法没有提取到城市，使用标准分隔符处理
                if not city or not course_name:
                    # 按'-'分割所有部分
                    parts = clean_text.split('-')
                    if len(parts) >= 1:
                        # 至少有课程名称
                        course_name = parts[0].strip()
                        
                        if len(parts) >= 2:
                            # 有城市信息
                            city = parts[1].strip()
                            
                            if len(parts) >= 3:
                                # 有战区信息
                                theater = '-'.join(parts[2:]).strip()
                            else:
                                # 简化格式：课程名称-城市
                                theater = ""  # 默认没有战区信息
            
            # 确保课程名称不为空
            if not course_name:
                course_name = "未知课程"
            
            # 尝试从课程文本中提取城市信息（如果前面没有提取到）
            if not city:
                # 寻找常见的城市名称模式
                city_patterns = ['北京', '上海', '广州', '深圳', '杭州', '南京', '重庆', '成都', '西安', '武汉', '长沙', '南昌', '郑州', '合肥', '福州', '厦门', '济南', '青岛', '天津', '大连', '沈阳', '哈尔滨']
                for pattern in city_patterns:
                    if pattern in clean_text:  # 使用clean_text而不是course_text，避免空格和制表符影响匹配
                        city = pattern
                        # 尝试提取战区信息
                        pattern_pos = clean_text.find(pattern)
                        if pattern_pos != -1:
                            after_city = clean_text[pattern_pos + len(pattern):].strip()
                            # 处理可能的'-'分隔的战区
                            if after_city.startswith('-'):
                                theater = after_city[1:].strip()
                            # 处理可能的制表符分隔的战区
                            elif '\t' in after_city:
                                theater = after_city.split('\t', 1)[0].strip()
                        break
            
            # 如果没有找到城市，直接返回None，不纳入数据集
            if not city:
                print(f"警告: 无法从课程文本'{clean_text}'中提取城市名称，不纳入数据集")
                return None
            
            # 确定项目归属，简化判断逻辑
            # 用户要求：只要课程名称中含有"低绩效"或者"认证"的就是"破晓突击",其他就都是"利刃出鞘"
            if '低绩效' in clean_text or '认证' in clean_text:  # 检查整个clean_text而不仅是course_name
                project_belonging = "破晓突击"
            else:
                project_belonging = "利刃出鞘"
            
            # 组合开始时间和结束时间
            start_date_str = f"{self.selected_year}/{self.selected_month:02d}/{start_date:02d}"
            end_date_str = f"{self.selected_year}/{self.selected_month:02d}/{end_date:02d}"
            
            # 检查日期是否有效
            try:
                start_date_obj = datetime.strptime(start_date_str, "%Y/%m/%d")
                end_date_obj = datetime.strptime(end_date_str, "%Y/%m/%d")
            except ValueError:
                print(f"警告: 无效的日期格式 - 开始日期: {start_date_str}, 结束日期: {end_date_str}")
                return None
            
            # 计算课程天数（包含首尾两天）
            days_diff = (end_date_obj - start_date_obj).days + 1
            
            # 确保天数不小于1
            if days_diff < 1:
                days_diff = 1

            # 根据项目归属和课程类型设置正确的课程天数
            # 用户需求：破晓突击课程应为2天，利刃出鞘课程应为3天
            # 交付顾问L1课程应为2天，销售顾问L1和交付技术主管L1课程应为3天
            course_name_lower = course_name.lower()
            if '交付顾问l1' in course_name_lower:
                # 交付顾问L1课程固定为2天
                days_diff = 2
                # 调整结束日期
                end_date_obj = start_date_obj.replace(day=min(start_date + 1, 31))
                end_date_str = end_date_obj.strftime("%Y/%m/%d")
            elif ('销售顾问l1' in course_name_lower or '交付技术主管l1' in course_name_lower):
                # 销售顾问L1和交付技术主管L1课程固定为3天
                days_diff = 3
                # 调整结束日期
                end_date_obj = start_date_obj.replace(day=min(start_date + 2, 31))
                end_date_str = end_date_obj.strftime("%Y/%m/%d")
            elif project_belonging == "破晓突击":
                # 破晓突击课程至少2天
                if days_diff < 2:
                    days_diff = 2
                    # 调整结束日期
                    end_date_obj = start_date_obj.replace(day=min(start_date + 1, 31))
                    end_date_str = end_date_obj.strftime("%Y/%m/%d")
            elif project_belonging == "利刃出鞘":
                # 利刃出鞘课程至少3天
                if days_diff < 3:
                    days_diff = 3
                    # 调整结束日期
                    end_date_obj = start_date_obj.replace(day=min(start_date + 2, 31))
                    end_date_str = end_date_obj.strftime("%Y/%m/%d")
            
            # 特殊处理：交付技术主管L1-郑州-华中区课程，结束日期应为14日
            if '交付技术主管l1' in course_name_lower and city == '郑州' and theater == '华中区':
                # 特别设置结束日期为14日
                end_date_obj = start_date_obj.replace(day=14)
                end_date_str = end_date_obj.strftime("%Y/%m/%d")
                days_diff = (end_date_obj - start_date_obj).days + 1
            

            
            result = {
                'course_name': course_name,
                'city': city,
                'theater': theater,
                'start_date': start_date_str,
                'end_date': end_date_str,
                'project_belonging': project_belonging,
                'course_days': days_diff,  # 新增：课程天数
                'original_course_name': course_text  # 新增：原课程名称，取单元格中的文字
            }
            
            print(f"成功解析课程: {result}")
            return result
        except Exception as e:
            print(f"解析课程时出错: {str(e)}")
            return None

    def _generate_summary_data(self):
        """
        生成汇总数据
        按城市汇总，一个城市一行，第二列换成拼接班级名称，放一个单元格里，这个城市多少个班级放一个单元格
        """
        self.summary_data = []
        
        # 按城市分组
        city_map = {}
        
        for course in self.schedule_data:
            if course['city'] not in city_map:
                city_map[course['city']] = []
            city_map[course['city']].append(course)
        
        # 为每个城市生成汇总信息
        for city, courses in city_map.items():
            # 按课程名称、开始日期和结束日期分组，形成班级
            class_groups = {}
            for course in courses:
                # 确保不同日期的相同课程被识别为不同班级
                key = (course['course_name'], course['start_date'], course['end_date'])
                if key not in class_groups:
                    class_groups[key] = course
                    print(f"添加班级: {course['course_name']}-{city}-{course['theater']} 日期: {course['start_date']}-{course['end_date']}")
            
            # 生成班级名称列表
            class_names = []
            for key, class_info in class_groups.items():
                # 格式化班级名称，按照用户要求的格式：课程名称-城市-战区 - MM.DD-MM.DD
                start_date_obj = datetime.strptime(class_info['start_date'], "%Y/%m/%d")
                end_date_obj = datetime.strptime(class_info['end_date'], "%Y/%m/%d")
                
                # 格式化日期为 MM.DD 格式
                start_date_str = start_date_obj.strftime("%m.%d")
                end_date_str = end_date_obj.strftime("%m.%d")
                
                # 构建班级名称
                class_name = f"{class_info['course_name']}-{city}-{class_info['theater']} - {start_date_str}-{end_date_str}"
                class_names.append(class_name)
            
            # 拼接班级名称，用换行符分隔
            class_names_str = '\n'.join(class_names)
            
            # 添加到汇总数据 - 使用正确的字段名
            self.summary_data.append({
                'city': city,
                'class_name': class_names_str,
                'course_name': ', '.join(set([c['course_name'] for c in courses])),
                'start_date': min([c['start_date'] for c in courses]),
                'end_date': max([c['end_date'] for c in courses]),
                'course_count': len(class_names)  # 使用course_count与GUI匹配
            })
        
        # 按城市名称排序汇总数据
        self.summary_data.sort(key=lambda x: x['city'])

    def export_to_excel(self, output_path, start_date_filter=None, end_date_filter=None):
        """
        导出数据到Excel文件，支持按开始日期和结束日期筛选
        
        Args:
            output_path: 输出文件路径
            start_date_filter: 开始日期筛选（格式：YYYY/MM/DD），None表示不筛选
            end_date_filter: 结束日期筛选（格式：YYYY/MM/DD），None表示不筛选
        
        Returns:
            bool: 是否导出成功
            str: 错误信息（如果有）
        """
        try:
            if not self.schedule_data:
                return False, "没有可导出的数据，请先解析排程"
            
            # 根据日期筛选数据
            filtered_schedule_data = self.schedule_data.copy()
            
            # 按开始日期筛选
            if start_date_filter:
                start_date_obj = datetime.strptime(start_date_filter, "%Y/%m/%d")
                filtered_schedule_data = [course for course in filtered_schedule_data \
                                         if datetime.strptime(course['start_date'], "%Y/%m/%d") >= start_date_obj]
            
            # 按结束日期筛选
            if end_date_filter:
                end_date_obj = datetime.strptime(end_date_filter, "%Y/%m/%d")
                filtered_schedule_data = [course for course in filtered_schedule_data \
                                         if datetime.strptime(course['end_date'], "%Y/%m/%d") <= end_date_obj]
            
            if not filtered_schedule_data:
                return False, "没有符合筛选条件的数据"
            
            # 创建ExcelWriter对象
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # 创建课程详情表
                details_df = pd.DataFrame(filtered_schedule_data)
                # 选择需要的列并排序，包含课程天数和原课程名称，按正确顺序排列
                columns = ['city', 'start_date', 'end_date', 'course_days', 'course_name', 'project_belonging', 'original_course_name']
                details_df = details_df[columns]
                details_df.to_excel(writer, sheet_name='课程详情', index=False)
                
                # 创建班级汇总表 - 基于筛选后的数据
                # 按城市分组
                city_map = {}
                for course in filtered_schedule_data:
                    if course['city'] not in city_map:
                        city_map[course['city']] = []
                    city_map[course['city']].append(course)
                
                # 为每个城市生成汇总信息
                filtered_summary_data = []
                for city, courses in city_map.items():
                    # 按课程名称、开始日期和结束日期分组，形成班级
                    class_groups = {}
                    for course in courses:
                        key = (course['course_name'], course['start_date'], course['end_date'])
                        if key not in class_groups:
                            class_groups[key] = course
                    
                    # 生成班级名称列表
                    class_names = []
                    for key, class_info in class_groups.items():
                        # 格式化班级名称
                        start_date_obj = datetime.strptime(class_info['start_date'], "%Y/%m/%d")
                        end_date_obj = datetime.strptime(class_info['end_date'], "%Y/%m/%d")
                        
                        # 格式化日期为 MM.DD 格式
                        start_date_str = start_date_obj.strftime("%m.%d")
                        end_date_str = end_date_obj.strftime("%m.%d")
                        
                        # 构建班级名称
                        class_name = f"{class_info['course_name']}-{city}-{class_info['theater']} - {start_date_str}-{end_date_str}"
                        class_names.append(class_name)
                    
                    # 拼接班级名称，用换行符分隔
                    class_names_str = '\n'.join(class_names)
                    
                    # 添加到汇总数据
                    filtered_summary_data.append({
                        'city': city,
                        'class_name': class_names_str,
                        'course_name': ', '.join(set([c['course_name'] for c in courses])),
                        'start_date': min([c['start_date'] for c in courses]),
                        'end_date': max([c['end_date'] for c in courses]),
                        'course_count': len(class_names)  # 使用course_count与GUI匹配
                    })
                
                # 按城市名称排序汇总数据
                filtered_summary_data.sort(key=lambda x: x['city'])
                
                # 创建汇总表DataFrame
                summary_df = pd.DataFrame(filtered_summary_data)
                # 选择需要的列，使用正确的字段名class_name
                summary_columns = ['city', 'class_name', 'course_count']
                summary_df = summary_df[summary_columns]
                summary_df.to_excel(writer, sheet_name='班级汇总', index=False)
                
                # 设置单元格格式，使换行生效
                worksheet = writer.sheets['班级汇总']
                for cell in worksheet['B']:
                    if cell.row > 1:  # 跳过表头
                        cell.alignment = openpyxl.styles.Alignment(wrapText=True)

                from services.excel_export import finalize_excel_writer

                finalize_excel_writer(writer)
            
            return True, f"成功导出到: {output_path}"
        except Exception as e:
            return False, f"导出文件时出错: {str(e)}"
    
    def get_schedule_data(self):
        """
        获取解析后的排程数据
        
        Returns:
            list: 排程数据列表
        """
        return self.schedule_data
    
    def get_summary_data(self):
        """
        获取汇总数据
        
        Returns:
            list: 汇总数据列表
        """
        return self.summary_data
        
    def get_course_stats(self):
        """
        获取课程统计数据
        
        Returns:
            dict: 包含课程总数和分类统计的字典
        """
        return self.course_stats
    
    def convert_schedule(self, file_path, year, month):
        """
        执行排程转换的核心方法
        
        Args:
            file_path: Excel文件路径
            year: 年份
            month: 月份
        
        Returns:
            bool: 是否转换成功
            str: 转换结果消息或错误信息
        """
        try:
            # 加载Excel文件
            success, message = self.load_excel_file(file_path)
            if not success:
                return False, message
            
            # 设置年份和月份
            self.set_year_month(year, month)
            
            # 调用解析方法解析排程数据
            success, message = self.parse_schedule_data()
            if not success:
                return False, message
            
            # 生成汇总数据
            self._generate_summary_data()
            
            # 返回成功信息，包含解析到的课程数量
            return True, f"成功解析{len(self.schedule_data)}条课程信息，生成{len(self.summary_data)}条汇总数据"
        except Exception as e:
            return False, f"转换排程时出错: {str(e)}"
            
    def generate_schedule_from_teaching_plan(self, teaching_plan_file, output_file_path):
        """
        从教学计划生成排期
        
        Args:
            teaching_plan_file: 教学计划Excel文件路径
            output_file_path: 输出排期文件路径
        
        Returns:
            bool: 是否生成成功
            str: 生成结果消息或错误信息
            dict: 验证结果（如果验证成功）
        """
        try:
            # 加载教学计划文件
            if not os.path.exists(teaching_plan_file):
                return False, "教学计划文件不存在", None
            
            # 读取教学计划数据
            teaching_plan_df = pd.read_excel(teaching_plan_file, sheet_name='课程详情')
            
            # 验证教学计划数据格式
            required_columns = ['city', 'start_date', 'end_date', 'course_name', 'project_belonging', 'original_course_name']
            for col in required_columns:
                if col not in teaching_plan_df.columns:
                    return False, f"教学计划文件缺少必要的列: {col}", None
            
            # 提取年份和月份信息
            first_start_date = teaching_plan_df['start_date'].iloc[0]
            if isinstance(first_start_date, str):
                first_start_date = datetime.strptime(first_start_date, "%Y/%m/%d")
            self.selected_year = first_start_date.year
            self.selected_month = first_start_date.month
            
            # 创建新的工作簿
            wb = openpyxl.Workbook()
            sheet = wb.active
            sheet.title = '排期'
            
            # 设置标题行
            sheet['A1'] = '日期'
            
            # 设置日期列（1-31天）
            for day in range(1, 32):
                col_letter = openpyxl.utils.get_column_letter(day + 1)  # 从B列开始
                sheet[f'{col_letter}1'] = day
                # 设置日期列宽
                sheet.column_dimensions[col_letter].width = 12
            
            # 按城市分组课程
            city_courses = {}
            for _, row in teaching_plan_df.iterrows():
                city = row['city']
                if city not in city_courses:
                    city_courses[city] = []
                city_courses[city].append(row)
            
            # 按城市顺序处理课程
            row_idx = 2  # 从第2行开始
            for city, courses in city_courses.items():
                # 设置城市名称
                sheet[f'A{row_idx}'] = city
                
                # 对每个课程进行处理
                for course in courses:
                    # 解析开始日期和结束日期
                    start_date = course['start_date']
                    end_date = course['end_date']
                    
                    if isinstance(start_date, str):
                        start_date = datetime.strptime(start_date, "%Y/%m/%d")
                    if isinstance(end_date, str):
                        end_date = datetime.strptime(end_date, "%Y/%m/%d")
                    
                    # 获取日期对应的列
                    start_col = start_date.day + 1  # +1是因为日期从B列开始
                    end_col = end_date.day + 1
                    
                    # 提取课程信息
                    course_name = course['course_name']
                    original_course_name = course['original_course_name'] if pd.notna(course['original_course_name']) else f"{course_name}-{city}"
                    
                    # 采用最安全的方式处理单元格和合并单元格
                    # 1. 先设置值和格式，再执行合并操作
                    # 2. 只操作左上角单元格，避免直接修改合并区域
                    
                    # 确保单元格操作的安全性，避免直接修改合并单元格
                    try:
                        # 1. 首先检查当前单元格是否已经是合并单元格
                        is_merged = False
                        for merged_cell in sheet.merged_cells.ranges:
                            if row_idx >= merged_cell.min_row and row_idx <= merged_cell.max_row and \
                               start_col >= merged_cell.min_col and start_col <= merged_cell.max_col:
                                is_merged = True
                                break
                        
                        # 2. 只在左上角单元格设置值和格式（不是合并单元格）
                        if not is_merged:
                            current_cell = sheet.cell(row=row_idx, column=start_col)
                            current_cell.value = original_course_name
                            current_cell.alignment = Alignment(horizontal='center', vertical='center', wrapText=True)
                            thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), 
                                                top=Side(style='thin'), bottom=Side(style='thin'))
                            current_cell.border = thin_border
                        else:
                            # 如果是合并单元格，尝试获取左上角单元格
                            print(f"警告: 单元格({row_idx}, {start_col})已经是合并单元格，将跳过设置值和格式")
                        
                        # 3. 如果是多日课程且不是合并单元格，需要合并单元格
                        if start_col != end_col and not is_merged:
                            try:
                                # 先检查目标区域是否已经有合并单元格
                                target_merged = False
                                for merged_cell in sheet.merged_cells.ranges:
                                    # 检查是否有合并单元格与目标区域重叠
                                    if (row_idx >= merged_cell.min_row and row_idx <= merged_cell.max_row and \
                                        ((start_col >= merged_cell.min_col and start_col <= merged_cell.max_col) or \
                                         (end_col >= merged_cell.min_col and end_col <= merged_cell.max_col))):
                                        target_merged = True
                                        break
                                
                                if not target_merged:
                                    # 尝试合并单元格
                                    sheet.merge_cells(start_row=row_idx, start_column=start_col, end_row=row_idx, end_column=end_col)
                                else:
                                    print(f"警告: 目标区域({row_idx}, {start_col}-{end_col})已经包含合并单元格，将跳过合并操作")
                            except Exception as merge_error:
                                # 记录错误但继续处理，至少左上角单元格有正确的值和格式
                                print(f"合并单元格时出错，继续处理: {str(merge_error)}")
                    except Exception as cell_error:
                        # 捕获所有单元格操作相关的异常
                        print(f"单元格操作时出错，继续处理: {str(cell_error)}")
                
                row_idx += 1
            
            # 保存生成的排期文件
            from services.excel_export import autofit_workbook

            autofit_workbook(wb)
            wb.save(output_file_path)
            
            # 验证生成结果
            validation_result = self._validate_generated_schedule(teaching_plan_df, output_file_path)
            
            return True, f"成功从教学计划生成排期文件: {output_file_path}", validation_result
        except Exception as e:
            return False, f"生成排期时出错: {str(e)}", None
            
    def _validate_generated_schedule(self, original_data, generated_file_path):
        """
        验证生成的排期文件是否与原始数据一致
        
        Args:
            original_data: 原始教学计划数据
            generated_file_path: 生成的排期文件路径
        
        Returns:
            dict: 验证结果
        """
        try:
            # 加载生成的排期文件
            temp_converter = ScheduleFormatConverter()
            success, message = temp_converter.load_excel_file(generated_file_path)
            if not success:
                return {"valid": False, "message": f"无法加载生成的排期文件: {message}"}
            
            # 设置年份和月份
            temp_converter.set_year_month(self.selected_year, self.selected_month)
            
            # 解析生成的排期数据
            success, message = temp_converter.parse_schedule_data()
            if not success:
                return {"valid": False, "message": f"解析生成的排期数据失败: {message}"}
            
            # 转换原始数据为相同格式
            original_schedule_data = []
            for _, row in original_data.iterrows():
                original_schedule_data.append({
                    'course_name': row['course_name'],
                    'city': row['city'],
                    'start_date': row['start_date'] if isinstance(row['start_date'], str) else row['start_date'].strftime('%Y/%m/%d'),
                    'end_date': row['end_date'] if isinstance(row['end_date'], str) else row['end_date'].strftime('%Y/%m/%d'),
                })
            
            # 比较解析后的数据和原始数据
            # 1. 比较数量
            if len(temp_converter.schedule_data) != len(original_schedule_data):
                return {"valid": False, "message": f"数据数量不匹配: 生成了{len(temp_converter.schedule_data)}条，期望{len(original_schedule_data)}条"}
            
            # 2. 比较每条数据的关键信息
            # 由于顺序可能不同，我们需要按关键信息进行匹配
            original_set = set()
            for item in original_schedule_data:
                key = (item['course_name'], item['city'], item['start_date'], item['end_date'])
                original_set.add(key)
            
            generated_set = set()
            for item in temp_converter.schedule_data:
                key = (item['course_name'], item['city'], item['start_date'], item['end_date'])
                generated_set.add(key)
            
            # 找出差异
            missing_items = original_set - generated_set
            extra_items = generated_set - original_set
            
            if missing_items or extra_items:
                message = "数据内容不匹配:"
                if missing_items:
                    message += f"\n缺失项目: {len(missing_items)}项"
                if extra_items:
                    message += f"\n额外项目: {len(extra_items)}项"
                return {"valid": False, "message": message}
            
            # 验证通过
            return {"valid": True, "message": "数据验证通过，生成的排期与原始教学计划一致"}
        except Exception as e:
            return {"valid": False, "message": f"验证过程出错: {str(e)}"}