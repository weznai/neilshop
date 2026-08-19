<#
.SYNOPSIS
    GLOWMAG MySQL 单库备份：mysqldump -> gzip -> 按保留天数清理 -> 异地（R2/S3）上传提醒。
.DESCRIPTION
    对应《高可用架构设计-v2》§5.3/§7.0 穷人高可用纪律：每日备份必须异地。
    密码请走 -Password 参数或 GM_MYSQL_PASSWORD 环境变量，勿写入脚本/计划任务明文。
    服务器（Linux）侧备份走 cron + docker compose exec mysqldump，见 deploy.md §4。
.EXAMPLE
    .\backup.ps1 -HostName 127.0.0.1 -Password $env:GM_MYSQL_PASSWORD
.EXAMPLE
    .\backup.ps1 -BackupDir D:\backups\glowmag -RetainDays 14 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$HostName = '127.0.0.1',
    [int]$Port = 3306,
    [string]$User = 'glowmag',
    [string]$Password,
    [ValidateNotNullOrEmpty()]
    [string]$Database = 'glowmag',
    [string]$BackupDir = '.\backups',
    [ValidateRange(1, 365)]
    [int]$RetainDays = 14
)

$ErrorActionPreference = 'Stop'

# ---------- 参数与密钥校验 ----------
if ([string]::IsNullOrEmpty($Password)) { $Password = $env:GM_MYSQL_PASSWORD }
if ([string]::IsNullOrEmpty($Password)) {
    throw '未提供密码：传 -Password 参数，或预先设置环境变量 GM_MYSQL_PASSWORD'
}

# ---------- mysqldump 自动探测（PATH 优先，再扫常见安装目录） ----------
function Find-Mysqldump {
    $cmd = Get-Command mysqldump.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @(
        "$env:ProgramFiles\MySQL",
        "${env:ProgramFiles(x86)}\MySQL",
        "$env:ProgramFiles\MariaDB*",
        'C:\xampp\mysql\bin'
    )
    foreach ($root in $roots) {
        if (Test-Path $root) {
            $hit = Get-ChildItem -Path $root -Filter mysqldump.exe -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($hit) { return $hit.FullName }
        }
    }
    return $null
}

$mysqldump = Find-Mysqldump
if (-not $mysqldump) {
    throw '未找到 mysqldump：安装 MySQL 客户端或将 bin 目录加入 PATH（服务器侧可改用 docker compose exec mysql mysqldump，见 deploy.md §4）'
}

# ---------- 备份目录与文件名 ----------
if (-not (Test-Path -LiteralPath $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
}
$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$sqlFile = Join-Path $BackupDir ("glowmag_{0}.sql" -f $stamp)
$gzFile  = "$sqlFile.gz"
$sw      = [System.Diagnostics.Stopwatch]::StartNew()

# ---------- 导出（--result-file 由 mysqldump 直接落盘，规避 PowerShell 管道改写编码；MYSQL_PWD 规避命令行泄露密码） ----------
if ($PSCmdlet.ShouldProcess(('{0}:{1}/{2}' -f $HostName, $Port, $Database), 'mysqldump 导出')) {
    $oldPwd = $env:MYSQL_PWD
    $env:MYSQL_PWD = $Password
    try {
        & $mysqldump --host=$HostName --port=$Port --user=$User `
            --single-transaction --quick --hex-blob --routines --triggers --events `
            --default-character-set=utf8mb4 --result-file=$sqlFile $Database
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sqlFile)) {
            throw "mysqldump 失败（exit=$LASTEXITCODE）"
        }
    }
    finally {
        $env:MYSQL_PWD = $oldPwd
    }

    # ---------- gzip 压缩（.NET GZipStream，Windows 无原生 gzip） ----------
    $srcStream = [System.IO.File]::OpenRead($sqlFile)
    try {
        $dstStream = [System.IO.File]::Create($gzFile)
        try {
            $gzStream = New-Object System.IO.Compression.GZipStream($dstStream,
                [System.IO.Compression.CompressionLevel]::Optimal)
            try { $srcStream.CopyTo($gzStream) } finally { $gzStream.Dispose() }
        } finally { $dstStream.Dispose() }
    } finally { $srcStream.Dispose() }
    Remove-Item -LiteralPath $sqlFile -Confirm:$false
}
$sw.Stop()

# ---------- 保留策略：清理超期本地备份 ----------
$cutoff = (Get-Date).AddDays(-$RetainDays)
Get-ChildItem -Path $BackupDir -Filter 'glowmag_*.sql.gz' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
        if ($PSCmdlet.ShouldProcess($_.Name, "删除超过 $RetainDays 天的过期备份")) {
            Remove-Item -LiteralPath $_.FullName -Confirm:$false
        }
    }

# ---------- 清单输出 + 异地纪律提醒（§5.3） ----------
$gzItem = Get-Item -LiteralPath $gzFile -ErrorAction SilentlyContinue
if ($gzItem) {
    Write-Output ('备份完成：{0}（{1:N2} MB，耗时 {2:ss\.fff}s）' -f $gzItem.FullName, ($gzItem.Length / 1MB), $sw.Elapsed)
}
Write-Output "当前本地保留清单（策略 <= $RetainDays 天）："
Get-ChildItem -Path $BackupDir -Filter 'glowmag_*.sql.gz' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Format-Table Name, @{n = 'SizeMB'; e = { '{0:N2}' -f ($_.Length / 1MB) } }, LastWriteTime -AutoSize

Write-Warning '本地备份 != 备份：请立即上传异地存储（R2/S3）—— rclone copy "<备份文件>" r2:glowmag-backups/ （§5.3 每日异地纪律），核对上传成功后方可结束当日运维'
