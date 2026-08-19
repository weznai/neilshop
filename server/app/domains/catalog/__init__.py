"""商品域：前台目录（列表/详情/分类树/集合/搜索/评价）+ 后台商品/变体/分类/集合管理。

分层：router（HTTP 编排，前台 router.py / 后台 router_admin.py）→ service（业务与事务）
→ repository（纯数据访问）。批量化查询（stock 单条 GROUP BY 聚合、分类子树单查询 BFS）
为 test_perf 断言对象，repository 中保持原样，禁止退化为逐商品查询。

对外兼容 shim：app/routers/{catalog,admin_catalog}.py、app/schemas/catalog.py。
"""
