<#
.SYNOPSIS
    GLOWMAG 销售演示旅程脚本 —— 对运行中的 :8000 用真实 API 讲完一个顾客的完整故事。
.DESCRIPTION
    全新随机邮箱顾客视角，十步走完：逛 → 注册 → 加购/合并 → 试算($31.10) → 下单支付
    → AI 客服 → 后台发货 → 退货退款 → 指标对账 → 收尾统计。每步打印带标题的步骤块，
    任一步失败立即停止并打印响应体；步骤间 0.3s 间隔。不依赖 jq（ConvertFrom-Json）。
    前提：:8000 已运行（根目录 start.ps1 或手动 uvicorn）；种子数据已就绪。
.EXAMPLE
    .\scripts\demo.ps1                     # 完整十步旅程
.EXAMPLE
    .\scripts\demo.ps1 -SkipReturn         # 跳过第 8 步退货（收尾演示用）
.EXAMPLE
    .\scripts\demo.ps1 -Port 8010          # 非默认端口
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$SkipReturn
)

$ErrorActionPreference = 'Stop'
$Base = "http://127.0.0.1:$Port"

# ---------- 工具函数 ----------

function Fmt-Money {
    param([int]$Cents)
    return '$' + ($Cents / 100).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
}

function Step-Header {
    param([int]$Index, [string]$Title)
    Write-Host ""
    Write-Host ("=" * 62)
    Write-Host (" STEP {0}/10 · {1}" -f $Index, $Title)
    Write-Host ("=" * 62)
}

function Fail-Exit {
    param([string]$Label, [object]$Resp, [string]$Body)
    Write-Host ""
    Write-Host ("=" * 62) -ForegroundColor Red
    $code = ''
    if ($null -ne $Resp) { $code = " HTTP $([int]$Resp.StatusCode)" }
    Write-Host ("[FAIL] $Label$code") -ForegroundColor Red
    if ($Body) { Write-Host $Body -ForegroundColor Red }
    Write-Host "演示在此步终止。请把上方响应体反馈给开发。" -ForegroundColor Red
    exit 1
}

function Invoke-Api {
    param(
        [string]$Label,
        [string]$Method = 'GET',
        [string]$Path,
        [object]$Body = $null,
        [hashtable]$Headers = @{},
        [switch]$RawText
    )
    $req = @{ Uri = "$Base$Path"; Method = $Method; TimeoutSec = 60; UseBasicParsing = $true; ErrorAction = 'Stop' }
    if ($Headers.Count -gt 0) { $req.Headers = $Headers }
    if ($null -ne $Body) {
        $req.Body = ($Body | ConvertTo-Json -Depth 6)
        $req.ContentType = 'application/json'
    }
    try {
        $r = Invoke-WebRequest @req
    } catch {
        $resp = $_.Exception.Response
        $text = ''
        if ($resp) {
            try {
                $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
                $text = $sr.ReadToEnd()
            } catch { $text = "<no body: $($_.Exception.Message)>" }
        }
        Fail-Exit -Label "$Label → $Method $Path" -Resp $resp -Body $text
    }
    $token = $null
    if ($r.Headers -and $r.Headers['X-Cart-Token']) { $token = @($r.Headers['X-Cart-Token'])[0] }
    # PS 5.1 对无 charset 的 application/json 按 Latin-1 解码 → 手工按 UTF-8 重读字节流
    $text = ''
    if ($r.RawContentStream) {
        $r.RawContentStream.Position = 0
        $sr = New-Object System.IO.StreamReader($r.RawContentStream, [Text.Encoding]::UTF8)
        $text = $sr.ReadToEnd()
    } else { $text = [string]$r.Content }
    $json = $null
    if (-not $RawText -and $text) {
        try { $json = $text | ConvertFrom-Json } catch { $json = $null }
    }
    return @{ Status = [int]$r.StatusCode; Json = $json; Text = $text; CartToken = $token }
}

function Get-CartToken {
    param($Api)
    if ($Api.CartToken) { return $Api.CartToken }
    if ($Api.Json -and $Api.Json.token) { return [string]$Api.Json.token }
    return $null
}

# ---------- 前提检查 ----------

Write-Host ""
Write-Host "============================================================"
Write-Host " GLOWMAG 销售演示旅程 · $Base · $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "============================================================"

try {
    $health = Invoke-WebRequest -Uri "$Base/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Host "[前置检查失败] $Base/api/health 不通 —— 请先在仓库根运行 .\start.ps1" -ForegroundColor Red
    Write-Host "（或手动：cd server; .venv\Scripts\python.exe -m uvicorn app.main:app --port $Port）"
    exit 1
}
Write-Host ("[前置检查] /api/health OK → {0}" -f $health.Content)

# ---------- 旅程状态 ----------
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$email = "demo$stamp$(Get-Random -Minimum 100 -Maximum 999)@glowmag.com"
$password = 'GlowDemo2026'
$addr = @{
    full_name = 'Demo Buyer'
    line1     = '123 Market Street'
    city      = 'San Francisco'
    state     = 'CA'
    zip       = '94103'
    country   = 'US'
    phone     = '+14155550188'
}
$userToken = $null; $opsToken = $null; $guestToken = $null
$orderNo = $null; $orderItemId = 0; $rmaNo = $null; $refundAmount = 0; $refundShip = 0
$trackingNo = '9400' + (Get-Random -Minimum 100000000 -Maximum 999999999) + (Get-Random -Minimum 10000000 -Maximum 99999999)

# ================= STEP 1 · 逛 =================
Step-Header 1 '逛 · 商品列表与搜索'
$lst = Invoke-Api -Label '商品列表' -Path "/api/catalog/products?page=1&size=3"
Write-Host ("商品总数 {0}，展示前 3 款：" -f $lst.Json.total)
$i = 0
foreach ($p in @($lst.Json.items)) {
    $i++
    $price = Fmt-Money $p.price_min
    if ($p.price_max -and $p.price_max -ne $p.price_min) { $price = (Fmt-Money $p.price_min) + '-' + (Fmt-Money $p.price_max) }
    $stock = 0; if ($p.stock_summary) { $stock = [int]$p.stock_summary.total }
    Write-Host ("  {0}. {1,-22} {2,-17} 库存 {3}" -f $i, $p.title, $price, $stock)
}
Start-Sleep -Milliseconds 300

$srch = Invoke-Api -Label '搜索 bare' -Path '/api/catalog/search?q=bare'
$hits = @($srch.Json.products)
Write-Host ("搜索 q=bare 命中 {0} 款：{1}" -f $hits.Count, (($hits | ForEach-Object { $_.title }) -join ' / '))

Start-Sleep -Milliseconds 300
$sale = Invoke-Api -Label '促销筛选' -Path '/api/catalog/products?on_sale=true&size=6'
Write-Host ("on_sale=true 划线价特惠 {0} 款：{1}" -f $sale.Json.total, (($sale.Json.items | ForEach-Object { $_.title }) -join ' / '))

Start-Sleep -Milliseconds 300
$bgId = Invoke-Api -Label 'Bare Gems 详情（取 id）' -Path '/api/catalog/products/bare-gems'
$dist = Invoke-Api -Label '评分分布' -Path ("/api/catalog/reviews/distribution?product_id={0}" -f $bgId.Json.id)
$distTxt = (($dist.Json.distribution.PSObject.Properties | Sort-Object Name -Descending | ForEach-Object { "{0}星×{1}" -f $_.Name, $_.Value }) -join ' · ')
Write-Host ("评分分布端点：Bare Gems 均分 {0:N2}（{1} 条评价）—— {2}" -f ($dist.Json.rating_avg / 100), $dist.Json.rating_count, $distTxt)

# ================= STEP 2 · 注册 =================
Step-Header 2 '注册 · 随机邮箱新顾客 + 地址簿'
Start-Sleep -Milliseconds 300
$reg = Invoke-Api -Label '注册' -Method POST -Path '/api/account/register' -Body @{ email = $email; password = $password; name = 'Demo Buyer' }
$userToken = $reg.Json.token
Write-Host ("新顾客注册成功：{0}（触发欢迎券邮件 WELCOME20）" -f $email)
Write-Host ("JWT token 已签发（user_id={0}）" -f $reg.Json.user.id)

Start-Sleep -Milliseconds 300
$addrRes = Invoke-Api -Label '地址簿新增' -Method POST -Path '/api/account/addresses' -Headers @{ Authorization = "Bearer $userToken" } -Body $addr
Write-Host ("地址簿 +1：{0}, {1}, {2} {3}（默认地址）" -f $addr.city, $addr.state, $addr.zip, $addr.country)

# ================= STEP 3 · 车 =================
Step-Header 3 '车 · 游客加购两件 → 登录合并'
Start-Sleep -Milliseconds 300
$guestCart = Invoke-Api -Label '游客购物车' -Path '/api/cart'
$guestToken = Get-CartToken $guestCart
Write-Host ("游客购物车 token：{0}" -f $guestToken)
$cartHeaders = @{ 'X-Cart-Token' = $guestToken }

Start-Sleep -Milliseconds 300
$bgDetail = Invoke-Api -Label 'Bare Gems 详情' -Path '/api/catalog/products/bare-gems'
$bgVar = @($bgDetail.Json.variants)[0]
$glueDetail = Invoke-Api -Label 'Magic Glue 详情' -Path '/api/catalog/products/magic-glue'
$glueVar = @($glueDetail.Json.variants)[0]
Write-Host ("变体现查：Bare Gems · {0}（variant {1}，{2}）/ Magic Glue · {3}（variant {4}，{5}）" -f `
        $bgVar.option1_value, $bgVar.id, (Fmt-Money $bgVar.price), $glueVar.option1_value, $glueVar.id, (Fmt-Money $glueVar.price))

Start-Sleep -Milliseconds 300
$add1 = Invoke-Api -Label '加购 Bare Gems' -Method POST -Path '/api/cart/items' -Headers $cartHeaders -Body @{ variant_id = $bgVar.id; qty = 1 }
if ($add1.CartToken) { $guestToken = $add1.CartToken; $cartHeaders['X-Cart-Token'] = $guestToken }
Start-Sleep -Milliseconds 300
$add2 = Invoke-Api -Label '加购 Magic Glue' -Method POST -Path '/api/cart/items' -Headers $cartHeaders -Body @{ variant_id = $glueVar.id; qty = 1 }
if ($add2.CartToken) { $guestToken = $add2.CartToken; $cartHeaders['X-Cart-Token'] = $guestToken }
Write-Host ("游客车 2 件，小计 {0}" -f (Fmt-Money $add2.Json.subtotal_cents))

Start-Sleep -Milliseconds 300
$merge = Invoke-Api -Label '合并购物车' -Method POST -Path '/api/cart/merge' -Headers @{ Authorization = "Bearer $userToken" } -Body @{ token = $guestToken }
Write-Host ("登录合并完成：登录车 {0} 件，小计 {1}（游客车已并入账户）" -f @($merge.Json.items).Count, (Fmt-Money $merge.Json.subtotal_cents))

# ================= STEP 4 · 算 =================
Step-Header 4 '算 · 结账试算 + WELCOME20（口径 $31.10）'
Start-Sleep -Milliseconds 300
$prev = Invoke-Api -Label '结账试算' -Method POST -Path '/api/checkout/preview' -Headers @{ Authorization = "Bearer $userToken" } `
    -Body @{ state = 'CA'; code = 'WELCOME20'; email = $email; shipping_method = 'standard' }
$j = $prev.Json
Write-Host ("  小计 subtotal        {0,10}" -f (Fmt-Money $j.subtotal))
Write-Host ("  折扣码 {0}        {1,10}  （新客 8 折，max `$10）" -f $j.code, ('-' + (Fmt-Money $j.code_discount)))
Write-Host ("  运费 shipping（standard）{0,10}" -f (Fmt-Money $j.shipping_fee))
Write-Host ("  税 tax（CA 7.35%）       {0,10}" -f (Fmt-Money $j.tax))
Write-Host ("  -------------------------------" -f '')
Write-Host ("  应付 grand total         {0,10}" -f (Fmt-Money $j.grand_total)) -ForegroundColor Yellow
if ($j.grand_total -ne 3110) {
    Write-Host ("[WARN] 金额口径偏差：期望 `$31.10，实际 $(Fmt-Money $j.grand_total)（种子价或税费配置可能变动）") -ForegroundColor Yellow
}

# ================= STEP 5 · 买 =================
Step-Header 5 '买 · 下单 → 支付意图 → 模拟支付 → 积分入账'
Start-Sleep -Milliseconds 300
$place = Invoke-Api -Label '下单' -Method POST -Path '/api/checkout/place' -Headers @{ Authorization = "Bearer $userToken" } `
    -Body @{ email = $email; address = $addr; shipping_method = 'standard'; code = 'WELCOME20' }
$orderNo = $place.Json.order_no
$grand = [int]$place.Json.grand_total
Write-Host ("下单成功：{0} · 应付 {1}（库存已预扣、购物车已清空）" -f $orderNo, (Fmt-Money $grand))

Start-Sleep -Milliseconds 300
$intent = Invoke-Api -Label '创建支付意图' -Method POST -Path '/api/payments/create-intent' -Body @{ order_no = $orderNo }
$provider = [string]$intent.Json.provider; if (-not $provider) { $provider = 'mock（默认链）' }
Write-Host ("支付意图 {0} · provider={1} · amount={2}" -f $intent.Json.payment_intent, $provider, (Fmt-Money $intent.Json.amount))

Start-Sleep -Milliseconds 300
$pay = Invoke-Api -Label '模拟支付' -Method POST -Path '/api/payments/mock-pay' -Body @{ order_no = $orderNo; succeed = $true }
$statusText = switch ([int]$pay.Json.order_status) { 0 { 'PENDING' } 1 { 'PAID' } 2 { 'FULFILLING' } 3 { 'SHIPPED' } 4 { 'DELIVERED' } 5 { 'COMPLETED' } 6 { 'CANCELED' } 7 { 'REFUNDED' } default { "status_$($_)" } }
Write-Host ("支付成功 → 订单 {0} · 状态 {1}（支付流水 status={2}）" -f $orderNo, $statusText, $pay.Json.payment_status)

Start-Sleep -Milliseconds 300
$pts = Invoke-Api -Label '积分三视图' -Path '/api/points' -Headers @{ Authorization = "Bearer $userToken" }
Write-Host ("积分入账：余额 {0}（冻结 {1} · 可用 {2}）—— `$1=10 分，确认收货后解冻" -f $pts.Json.balance, $pts.Json.frozen, $pts.Json.usable)

Start-Sleep -Milliseconds 300
$od = Invoke-Api -Label '订单详情' -Path "/api/orders/$orderNo" -Headers @{ Authorization = "Bearer $userToken" }
$bgItem = @($od.Json.items) | Where-Object { $_.title -like 'Bare Gems*' } | Select-Object -First 1
$orderItemId = [int]$bgItem.id
Write-Host ("订单行：{0}（order_item_id={1}，{2} × {3}）—— 供第 8 步退货引用" -f $bgItem.title, $orderItemId, (Fmt-Money $bgItem.unit_price), $bgItem.qty)

# ================= STEP 6 · AI 客服 =================
Step-Header 6 'AI 客服 · 订单查询（脱敏单号后 4 位）'
Start-Sleep -Milliseconds 300
$chat = Invoke-Api -Label 'AI 对话' -Method POST -Path '/api/ai/chat' -Body @{ message = "where is my order $orderNo"; order_no = $orderNo }
$reply = [string]$chat.Json.reply
$mask = $orderNo -replace '^(.{4}).*(.{4})$', '$1****$2'
$firstLine = ($reply -split "`n")[0].Replace($orderNo, $mask)
Write-Host ("intent={0} · 单号已脱敏为 {1}" -f $chat.Json.intent, $mask)
Write-Host ("GlowBot ▸ {0}" -f $firstLine)

# ================= STEP 7 · 后台 =================
Step-Header 7 '后台 · ops 看板 → 发货 → 物流轨迹'
Start-Sleep -Milliseconds 300
$opsLogin = Invoke-Api -Label 'ops 登录' -Method POST -Path '/api/account/login' -Body @{ email = 'ops@glowmag.com'; password = 'glowmag123' }
$opsToken = $opsLogin.Json.token
$opsHeaders = @{ Authorization = "Bearer $opsToken" }
Write-Host ("ops@glowmag.com 登录成功（后台 11 页可用，当前积分 {0}）" -f $opsLogin.Json.user.points)

Start-Sleep -Milliseconds 300
$dash = Invoke-Api -Label '运营看板' -Path '/api/admin/ops/dashboard' -Headers $opsHeaders
Write-Host ("今日看板：GMV {0} · 订单 {1} 单（含本旅程 +1）" -f (Fmt-Money $dash.Json.today.gmv_cents), $dash.Json.today.orders)

Start-Sleep -Milliseconds 300
$ship = Invoke-Api -Label '订单发货' -Method POST -Path "/api/admin/trade/orders/$orderNo/ship" -Headers $opsHeaders -Body @{ carrier = 'usps'; tracking_no = $trackingNo }
Write-Host ("发货完成：{0} · USPS 运单 {1}" -f $ship.Json.shipment_no, $trackingNo)

Start-Sleep -Milliseconds 300
$track = Invoke-Api -Label '物流轨迹' -Path ("/api/orders/track?no={0}&email={1}" -f $orderNo, [uri]::EscapeDataString($email))
$trackStatus = switch ([int]$track.Json.status) { 0 { 'PENDING' } 1 { 'PAID' } 2 { 'FULFILLING' } 3 { 'SHIPPED 已发货' } 4 { 'DELIVERED' } 5 { 'COMPLETED' } 6 { 'CANCELED' } 7 { 'REFUNDED' } default { "status_$($_)" } }
Write-Host ("免登录轨迹查询：订单状态 {0} · 承运 {1} · 运单 {2}" -f $trackStatus, (@($track.Json.shipments)[0].carrier), (@($track.Json.shipments)[0].tracking_no))

# ================= STEP 8 · 退货 =================
if ($SkipReturn) {
    Step-Header 8 '退货 · 已按 -SkipReturn 跳过'
    Write-Host '退货/退款/回补库存链路本次不演示（完整口径见 §22 旅程表）。'
} else {
    Step-Header 8 '退货 · RMA 质量 → 批准 → 收货 → 退款'
    Start-Sleep -Milliseconds 300
    $rma = Invoke-Api -Label '提交 RMA' -Method POST -Path '/api/returns' -Headers @{ Authorization = "Bearer $userToken" } `
        -Body @{ order_no = $orderNo; order_item_id = $orderItemId; qty = 1; reason = 2; reason_detail = 'Quality issue: chipped on first wear' }
    $rmaNo = $rma.Json.rma_no
    Write-Host ("顾客提交 RMA：{0} · 理由 2=质量问题 · 数量 1（30 天窗口内）" -f $rmaNo)

    Start-Sleep -Milliseconds 300
    $appr = Invoke-Api -Label '批准 RMA' -Method POST -Path "/api/admin/trade/rmas/$rmaNo/approve" -Headers $opsHeaders
    Write-Host ("后台批准：status={0} · 退货标签 {1}" -f $appr.Json.status, $appr.Json.label_url)

    Start-Sleep -Milliseconds 300
    $recv = Invoke-Api -Label 'RMA 收货' -Method POST -Path "/api/admin/trade/rmas/$rmaNo/receive" -Headers $opsHeaders
    Write-Host ("仓库收货：status={0} · 回补库存 {1} 件（stock_movements 留痕）" -f $recv.Json.status, $recv.Json.restock_qty)

    Start-Sleep -Milliseconds 300
    $ref = Invoke-Api -Label 'RMA 退款' -Method POST -Path "/api/admin/trade/rmas/$rmaNo/refund" -Headers $opsHeaders
    $refundAmount = [int]$ref.Json.refund_amount
    $refundShip = [int]$ref.Json.refund_shipping
    Write-Host ("退款完成（实付比例口径）：货款 {0} + 退运费 {1} = 实退合计 {2} · RMA status={3}" -f `
            (Fmt-Money ($refundAmount - $refundShip)), (Fmt-Money $refundShip), (Fmt-Money $refundAmount), $ref.Json.status)
    Write-Host "（口径：unit_price × grand_total ÷ subtotal 折算税/折扣分摊，质量问题 reason=2 补 `$4.99 运费）"
}

# ================= STEP 9 · 对账 =================
Step-Header 9 '对账 · /metrics 请求计数（demo 相关路径汇总）'
Start-Sleep -Milliseconds 300
$mtx = Invoke-Api -Label 'Prometheus 指标' -Path '/metrics' -RawText
$rx = [regex]'glowmag_http_requests_total\{method="(?<m>[^"]+)",path="(?<p>[^"]+)",status="(?<s>\d+)"\}\s+(?<v>\d+)'
$demoPrefixes = @('/api/catalog', '/api/cart', '/api/checkout', '/api/payments', '/api/account', '/api/ai/', '/api/admin', '/api/returns', '/api/orders', '/api/points', '/api/health')
$agg = @{}
foreach ($m in $rx.Matches($mtx.Text)) {
    $p = $m.Groups['p'].Value
    $hit = $false
    foreach ($pre in $demoPrefixes) { if ($p.StartsWith($pre)) { $hit = $true; break } }
    if (-not $hit) { continue }
    $key = $p
    if (-not $agg.ContainsKey($key)) { $agg[$key] = 0 }
    $agg[$key] += [int]$m.Groups['v'].Value
}
Write-Host "路径（{id} 为单号/ID 归并）                累计请求数"
foreach ($k in ($agg.Keys | Sort-Object)) {
    Write-Host ("  {0,-42} {1,5}" -f $k, $agg[$k])
}
Write-Host "（worker 对账/弃购/解冻等批处理不在 HTTP API 内，运行态看 server/scripts/worker.py --loop）"

# ================= STEP 10 · 收尾 =================
Step-Header 10 '收尾 · 演示数据统计与清理方式'
Start-Sleep -Milliseconds 300
Write-Host "本旅程产生的数据："
Write-Host ("  顾客 1 名：{0}（密码 {1}）" -f $email, $password)
Write-Host ("  订单 1 张：{0} · grand total {1} · 状态 {2}" -f $orderNo, (Fmt-Money $grand), $(if ($SkipReturn) { 'SHIPPED' } else { 'REFUNDED(部分)' }))
if ($rmaNo) { Write-Host ("  RMA 1 张：{0} · 实退 {1}" -f $rmaNo, (Fmt-Money $refundAmount)) }
Write-Host ("  支付 1 笔：mock-pay · 积分 {0} 分（冻结）" -f $pts.Json.balance)
Write-Host "  事务邮件（欢迎券/订单确认/发货/退款）已由服务端投递——开发态打印在 uvicorn 控制台日志"
Write-Host ""
Write-Host "清理演示数据（重置种子库）："
Write-Host "  cd server"
Write-Host "  .venv\Scripts\python.exe scripts\seed.py --reset   # drop_all 后重建"
Write-Host "  .venv\Scripts\python.exe scripts\seed.py          # 重新灌入种子数据"
Write-Host ""
Write-Host ("演示旅程完成 ✔  {0}" -f (Get-Date -Format 'HH:mm:ss')) -ForegroundColor Green
