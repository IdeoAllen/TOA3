# -*- coding: utf-8 -*-
"""架构说明：模块隔离与扩展约定（Agent/开发速查）。"""

MODULE_ISOLATION = """
1. 业务页禁止互相 import 对方 UI；共享逻辑放 services/ 或 integrations/
2. 页面按需懒加载（shell._ensure_page），启动不实例化全部模块
3. 重计算放 *_service，UI 线程只调服务；长任务后续可接 job_scheduler
4. 三方系统只经 get_client(name)，禁止业务写 URL/密钥
5. 菜单扩展：config/app.yml 增项 + MIGRATED_MODULES 登记即可；侧栏分组可折叠
6. 功能出售：config/feature_packs.yml 定义 SKU；授权 features 可写 pack_id
"""
