<#
.SYNOPSIS
    GLOWMAG 备份恢复演练一键脚本：把《deploy.md》§4.3 季度恢复演练固化为可重复执行的核验流水线。
.DESCRIPTION
    纪律：没有验证过的备份等于没有备份。本脚本在**临时库**（默认 glowmag_drill）完成
    解压 → 导入 → 数据一致性核验（表数/行数/抽查订单/CHECKSUM/字段比对）→ 应用级验证
    （临时 uvicorn 起恢复库，打 /api/health 与商品接口）→ 清理现场。
    全程只读生产库 glowmag（仅 SELECT 对比），恢复目标仅为 drill 临时库，结束自动 DROP。
.NOTES
    前置：mysql.exe 可用（PATH 或 -MysqlBin 指定）、python 可用（gzip 流式解压）、
    server\.venv 存在（应用级验证）。RootPassword 默认取 GM_MYSQL_ROOT_PASSWORD，
    本机演练机可显式传参。生产环境请勿把密码写入任何文件。
.EXAMPLE
    .\restore-drill.ps1 -BackupFile C:\Users\lihui\AppData\Local\Temp\opencode\drill\glowmag_20260816_131128.sql.gz
.EXAMPLE
    .\restore-drill.ps1 -BackupFile D:\backups\glowmag\glowmag_20261001_030000.sql.gz -KeepDb
#>
[CmdletBinding()]
param(
    [string]$HostName = '127.0.0.1',
    [int]$Port = 3306,
    [string]$SourceDb = 'glowmag',                       # 生产库（只读参照）
    [string]$TempDb = 'glowmag_drill',                   # 临时恢复库（结束 DROP）
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ })]
    [string]$BackupFile,                                  # backup.ps1 产出的 .sql.gz
    [string]$RootPassword,                                # 缺省读 GM_MYSQL_ROOT_PASSWORD
    [string]$AppUser = 'glowmag',
    [string]$AppPassword = 'glowmag123',
    [string]$MysqlBin = 'D:\soft\db\mysql-8.0.22\bin',
    [string]$VenvPython = '',                             # 缺省探测 <仓库根>\server\.venv\Scripts\python.exe
    [int]$AppPort = 8020,
    [string]$SpotOrderNo = 'NS260728D4E5F6',             # 抽查订单号
    [long]$SpotGrandTotal = 3110,                         # 期望 grand_total
    [string]$SpotSlug = 'bare-gems',                      # 抽查商品 slug
    [long]$SpotPrice = 1599,                              # 期望 price_min
    [switch]$KeepDb                                        # 保留临时库现场（排障用）
)

$ErrorActionPreference = 'Stop'
$swTotal = [System.Diagnostics.Stopwatch]::StartNew()
$results = New-Object System.Collections.Generic.List[object]

# ---------- 工具探测 ----------
$mysql = Join-Path $MysqlBin 'mysql.exe'
if (-not (Test-Path -LiteralPath $mysql)) {
    $cmd = Get-Command mysql.exe -ErrorAction SilentlyContinue
    if ($cmd) { $mysql = $cmd.Source } else { throw "未找到 mysql.exe：用 -MysqlBin 指定 bin 目录" }
}
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if (-not $python) { throw '未找到 python（gzip 流式解压依赖）' }
$python = $python.Source
if (-not $VenvPython) {
    $guess = Join-Path $PSScriptRoot '..\server\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $guess) { $VenvPython = (Resolve-Path $guess).Path }
}
if (-not $RootPassword) { $RootPassword = $env:GM_MYSQL_ROOT_PASSWORD }
if (-not $RootPassword) { throw '未提供 root 密码：传 -RootPassword 或设 GM_MYSQL_ROOT_PASSWORD 环境变量' }

$workDir = Join-Path $env:TEMP 'opencode\drill'
if (-not (Test-Path -LiteralPath $workDir)) { New-Item -ItemType Directory -Path $workDir -Force | Out-Null }
$sqlFile = Join-Path $workDir ("drill_restore_{0}.sql" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Invoke-Mysql {
    param([string[]]$Sql, [string]$Database = '', [switch]$Scalar)
    $args = @("--host=$HostName", "--port=$Port", '-uroot', '--default-character-set=utf8mb4')
    if ($Database) { $args += $Database }
    $args += '-e'
    $args += ($Sql -join ' ')
    $old = $env:MYSQL_PWD
    $env:MYSQL_PWD = $RootPassword
    try {
        $out = & $mysql @args 2>&1
        if ($LASTEXITCODE -ne 0) { throw "mysql 失败：$out" }
        if ($Scalar) { return ($out | Select-Object -Last 1) }
        return $out
    } finally { $env:MYSQL_PWD = $old }
}

function Add-Result {
    param([string]$Item, [string]$Prod, [string]$Drill, [bool]$Ok, [string]$Note = '')
    $script:results.Add([pscustomobject]@{
        核验项 = $Item; 生产库 = $Prod; 恢复库 = $Drill; 结论 = if ($Ok) { 'PASS' } else { 'FAIL' }; 备注 = $Note
    })
    if (-not $Ok) { $script:failed = $true }
}
$failed = $false

# ---------- 1) 建临时库 + 授权 ----------
Write-Output "[1/6] 建临时库 $TempDb 并授权 $AppUser ..."
$hosts = Invoke-Mysql -Sql @("SELECT host FROM mysql.user WHERE user='$AppUser';") | Where-Object { $_ -and $_ -notmatch '^host$' }
Invoke-Mysql -Sql @(
    "DROP DATABASE IF EXISTS ``$TempDb``;",
    "CREATE DATABASE ``$TempDb`` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
)
foreach ($h in $hosts) {
    Invoke-Mysql -Sql @("GRANT ALL PRIVILEGES ON ``$TempDb``.* TO '$AppUser'@'$h';") | Out-Null
}
Invoke-Mysql -Sql @('FLUSH PRIVILEGES;') | Out-Null
Write-Output "      已授权 host：$($hosts -join ', ')"

# ---------- 2) gunzip 解压（python gzip 流式） ----------
Write-Output "[2/6] 解压备份 $BackupFile ..."
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $python -c "import gzip,shutil; f=gzip.open(r'$BackupFile','rb'); o=open(r'$sqlFile','wb'); shutil.copyfileobj(f,o); o.close()"
if ($LASTEXITCODE -ne 0) { throw 'gunzip 解压失败' }
$sqlSize = (Get-Item -LiteralPath $sqlFile).Length
$sw.Stop()
Write-Output ("      解压完成 {0:N2} MB（{1:ss\.fff}s）" -f ($sqlSize / 1MB), $sw.Elapsed)

# ---------- 3) mysql 导入 ----------
Write-Output "[3/6] 导入 $TempDb ..."
$sw.Restart()
$old = $env:MYSQL_PWD
$env:MYSQL_PWD = $RootPassword
try {
    cmd /c "`"$mysql`" --host=$HostName --port=$Port -uroot --default-character-set=utf8mb4 $TempDb < `"$sqlFile`""
    if ($LASTEXITCODE -ne 0) { throw 'mysql 导入失败' }
} finally { $env:MYSQL_PWD = $old }
$sw.Stop()
Write-Output ("      导入完成（{0:ss\.fff}s）" -f $sw.Elapsed)

# ---------- 4) 数据一致性核验 ----------
Write-Output '[4/6] 数据一致性核验 ...'
$t = Invoke-Mysql -Sql @(
    "SELECT table_schema, COUNT(*) FROM information_schema.tables WHERE table_schema IN ('$SourceDb','$TempDb') GROUP BY table_schema;"
)
$cntSrc = ($t | Where-Object { $_ -match ("^$SourceDb`t") }) -replace '.*\s', ''
$cntDrill = ($t | Where-Object { $_ -match ("^$TempDb`t") }) -replace '.*\s', ''
Add-Result '表数量' $cntSrc $cntDrill ($cntSrc -eq $cntDrill)

foreach ($tbl in @('products', 'users', 'orders', 'reviews')) {
    $r = Invoke-Mysql -Sql @(
        "SELECT '$tbl', (SELECT COUNT(*) FROM ``$SourceDb``.``$tbl``), (SELECT COUNT(*) FROM ``$TempDb``.``$tbl``);"
    ) -Scalar
    $parts = ($r -split "`t")
    Add-Result "行数 $tbl" $parts[1] $parts[2] ($parts[1] -eq $parts[2])
}

$o1 = Invoke-Mysql -Sql @("SELECT CONCAT(order_no,'=',grand_total) FROM ``$SourceDb``.orders WHERE order_no='$SpotOrderNo';") -Scalar
$o2 = Invoke-Mysql -Sql @("SELECT CONCAT(order_no,'=',grand_total) FROM ``$TempDb``.orders WHERE order_no='$SpotOrderNo';") -Scalar
Add-Result "抽查订单 $SpotOrderNo" $o1 $o2 (($o1 -eq $o2) -and ($o1 -match ("={0}$" -f $SpotGrandTotal)))

$c1 = (Invoke-Mysql -Sql @("CHECKSUM TABLE ``$SourceDb``.users;") -Scalar) -replace '.*\s', ''
$c2 = (Invoke-Mysql -Sql @("CHECKSUM TABLE ``$TempDb``.users;") -Scalar) -replace '.*\s', ''
Add-Result 'CHECKSUM users' $c1 $c2 ($c1 -eq $c2 -and $c1 -match '^\d+$')

$fSrc = Join-Path $workDir 'u_src.txt'; $fDrill = Join-Path $workDir 'u_drill.txt'
Invoke-Mysql -Database $SourceDb -Sql @('SELECT id,email,name,role,points,tier,total_spent,status,created_at FROM users ORDER BY id;') | Set-Content -LiteralPath $fSrc -Encoding UTF8
Invoke-Mysql -Database $TempDb -Sql @('SELECT id,email,name,role,points,tier,total_spent,status,created_at FROM users ORDER BY id;') | Set-Content -LiteralPath $fDrill -Encoding UTF8
$identical = -not (Compare-Object (Get-Content $fSrc) (Get-Content $fDrill))
$nRows = @(Get-Content $fSrc).Count
Add-Result 'users 全字段比对' "$nRows 行" "$nRows 行" $identical

# ---------- 5) 应用级验证（GM_DB 指向恢复库起临时 uvicorn） ----------
Write-Output "[5/6] 应用级验证（uvicorn :$AppPort → GM_DB=$TempDb）..."
$appOk = $false
$appNote = ''
if ($VenvPython -and (Test-Path -LiteralPath $VenvPython)) {
    if (Get-NetTCPConnection -LocalPort $AppPort -State Listen -ErrorAction SilentlyContinue) {
        throw "端口 $AppPort 被占用，先释放再演练"
    }
    $env:GM_DB = "mysql+pymysql://{0}:{1}@{2}:{3}/{4}?charset=utf8mb4" -f $AppUser, $AppPassword, $HostName, $Port, $TempDb
    $logOut = Join-Path $workDir "uvicorn$AppPort.log"; $logErr = Join-Path $workDir "uvicorn$AppPort.err.log"
    $p = Start-Process -FilePath $VenvPython -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$AppPort") `
        -WorkingDirectory (Join-Path $PSScriptRoot '..\server') -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    try {
        $healthOk = $false; $prodOk = $false; $priceOk = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            if ($p.HasExited) { break }
            try {
                $h = Invoke-WebRequest -Uri "http://127.0.0.1:$AppPort/api/health" -UseBasicParsing -TimeoutSec 3
                if ($h.StatusCode -eq 200 -and $h.Content -match '"ok":\s*true') { $healthOk = $true; break }
            } catch { }
        }
        if ($healthOk) {
            $g = Invoke-WebRequest -Uri "http://127.0.0.1:$AppPort/api/catalog/products/$SpotSlug" -UseBasicParsing -TimeoutSec 5
            if ($g.StatusCode -eq 200) { $prodOk = $true }
            if ($g.Content -match ('"price_min":\s*{0}' -f $SpotPrice)) { $priceOk = $true }
        }
        $appOk = $healthOk -and $prodOk -and $priceOk
        $appNote = "health200=$healthOk product200=$prodOk ${SpotSlug}price=$priceOk"
    } finally {
        if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 500
        Get-NetTCPConnection -LocalPort $AppPort -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
    Add-Result '应用级验证' '/api/health+bare-gems' '见备注' $appOk $appNote
} else {
    Add-Result '应用级验证' '-' '-' $false '未找到 server\.venv\Scripts\python.exe，跳过即 FAIL（演练必须证明库可用）'
}

# ---------- 6) 清理 ----------
Write-Output '[6/6] 清理现场 ...'
if ($KeepDb) {
    Write-Output "      -KeepDb：保留 $TempDb 供排障（记得事后手动 DROP）"
} else {
    Invoke-Mysql -Sql @("DROP DATABASE IF EXISTS ``$TempDb``;") | Out-Null
    Write-Output "      已 DROP $TempDb"
}
Remove-Item -LiteralPath $sqlFile, $fSrc, $fDrill -Force -ErrorAction SilentlyContinue

# ---------- 结论 ----------
$swTotal.Stop()
Write-Output ''
Write-Output ('===== 恢复演练核验结论（备份：{0}，{1:N2} MB） =====' -f (Split-Path $BackupFile -Leaf), ((Get-Item -LiteralPath $BackupFile).Length / 1MB))
$results | Format-Table -AutoSize
Write-Output ("总耗时 {0:mm\:ss\.fff}　临时库：{1}　结论：{2}" -f $swTotal.Elapsed, $TempDb, $(if ($failed) { 'FAIL —— 备份不可用，立即排查！' } else { 'PASS —— 备份可恢复且可用' }))
if ($failed) { exit 1 } else { exit 0 }
