"""会员域：account（账户/地址/心愿单/隐私）/ points（积分）/ referrals（推荐有礼）/ subscriptions（订阅月盒）。

分层：router_*（HTTP 编排）→ service_*（业务与事务）→ repository（纯数据访问）。
对外兼容 shim：app/routers/{account,points,referrals,subscriptions}.py、
app/schemas/{account,referrals,subscriptions}.py、app/services/referrals.py。
"""
