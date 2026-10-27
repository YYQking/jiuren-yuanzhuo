param(
    [switch]$SkipBuild,
    [switch]$NoBackup,
    [string]$TargetRoot = ""
)

# 一次更新，两处同时刷新。用户 2026-10-27 明确要求：「以后更新同时更新这两处」——
# 桌面\九人圆桌\ 里自己点开的那份，和 发给别人的\ 里发给别人的 zip。
#
# 顺序：打包 → 备份旧版（只留一份）→ 换上新的 + 新说明书 → 用干净副本重做 zip → 校验。
# 任何一步失败都 throw，绝不留下半新的目录或半个 zip。

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$target = Join-Path $desktop '九人圆桌'
if ($TargetRoot) { $target = $TargetRoot }   # 仅用于测试部署流程本身
$shareDir = Join-Path $target '发给别人的'
$backupDir = Join-Path $target '备份'
$shareZip = Join-Path $shareDir '九人圆桌-发给别人用.zip'
$py = 'C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

$env:PYTHONPATH = "$root;$root\.qt-build-runtime"
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue

function Get-Hash16([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.Substring(0, 16)
}

# 1. 打包
if (-not $SkipBuild) {
    Write-Output '打包中…'
    & $py -m PyInstaller (Join-Path $root '九人圆桌-Qt.spec') --noconfirm `
        --distpath (Join-Path $root 'dist-qt') --workpath (Join-Path $root 'build-qt') *> (Join-Path $root 'artifacts\build-qt.log')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，见 artifacts\build-qt.log" }
    $work = Join-Path $root 'build-qt'
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}

$builtDir = Join-Path $root 'dist-qt\九人圆桌-Qt'
$builtExe = Join-Path $builtDir '九人圆桌-Qt.exe'
if (-not (Test-Path -LiteralPath $builtExe)) { throw "打包产物缺失：$builtExe" }
$newHash = Get-Hash16 $builtExe

# 2. 暂存"自己用"的目录：改好 exe 名字，重新生成说明书
$stage = Join-Path $env:TEMP ("deploy-" + [guid]::NewGuid().ToString('N'))
$stageApp = Join-Path $stage 'app'
New-Item -ItemType Directory -Path $stageApp -Force | Out-Null
Get-ChildItem -LiteralPath $builtDir -Force | Copy-Item -Destination $stageApp -Recurse -Force
Rename-Item -LiteralPath (Join-Path $stageApp '九人圆桌-Qt.exe') -NewName '九人圆桌.exe'
& $py (Join-Path $root 'tools\build_manual_txt.py') (Join-Path $stageApp '使用说明.txt') | Out-Null
if ($LASTEXITCODE -ne 0) { throw '生成使用说明.txt 失败' }

# 3. 目录骨架（首次运行时创建）
foreach ($d in @($target, $shareDir, $backupDir)) {
    if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

# 4. 备份旧版：内容相同就不重复备份；只保留一份
$currentExe = Join-Path $target '九人圆桌.exe'
if (-not $NoBackup -and (Test-Path -LiteralPath $currentExe)) {
    if ((Get-Hash16 $currentExe) -ne $newHash) {
        Get-ChildItem -LiteralPath $backupDir -Force |
            Where-Object { $_.Name -ne '说明.txt' } |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
        foreach ($item in @($currentExe, (Join-Path $target '_internal'), (Join-Path $target '使用说明.txt'))) {
            if (Test-Path -LiteralPath $item) { Move-Item -LiteralPath $item -Destination $backupDir -Force }
        }
        Write-Output '已把上一版移入 备份\'
    } else {
        Write-Output '版本未变，跳过备份'
    }
}

# 5. 换成新版
foreach ($item in @($currentExe, (Join-Path $target '_internal'), (Join-Path $target '使用说明.txt'))) {
    if (Test-Path -LiteralPath $item) { Remove-Item -LiteralPath $item -Recurse -Force }
}
Get-ChildItem -LiteralPath $stageApp -Force | Copy-Item -Destination $target -Recurse -Force

# 6. 重做分享 zip：用干净副本打包，绝不把 发给别人的\ 和 备份\ 套进去
$shareStage = Join-Path $stage 'share\九人圆桌'
New-Item -ItemType Directory -Path $shareStage -Force | Out-Null
foreach ($name in @('九人圆桌.exe', '_internal', '使用说明.txt')) {
    Copy-Item -LiteralPath (Join-Path $stageApp $name) -Destination $shareStage -Recurse -Force
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\make_share_zip.ps1') `
    -SourceDir $shareStage -OutputZip $shareZip -RootName '九人圆桌' | Out-Null
if ($LASTEXITCODE -ne 0) { throw '生成分享 zip 失败' }

# 7. 校验两处都真的更新了
$deployedExe = Join-Path $target '九人圆桌.exe'
if ((Get-Hash16 $deployedExe) -ne $newHash) { throw '自己用那份的 exe 与打包产物不一致' }
if (-not (Test-Path -LiteralPath (Join-Path $target '_internal\Qt6Core.dll'))) { throw '_internal 不完整' }

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($shareZip)
try {
    $entry = $zip.Entries | Where-Object { $_.FullName -eq '九人圆桌/九人圆桌.exe' }
    if (-not $entry) { throw 'zip 里没有 九人圆桌/九人圆桌.exe' }
    $manifest = Join-Path $env:TEMP ("zipcheck-" + [guid]::NewGuid().ToString('N') + '.exe')
    try {
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $manifest, $true)
        if ((Get-Hash16 $manifest) -ne $newHash) { throw 'zip 里的 exe 与打包产物不一致' }
    } finally {
        if (Test-Path -LiteralPath $manifest) { Remove-Item -LiteralPath $manifest -Force }
    }
    $bad = @($zip.Entries | Where-Object { $_.FullName -like '*\*' -or $_.FullName -match 'ai-settings|\.key$|secret|hotspots.*\.json|备份|发给别人的' })
    if ($bad.Count -gt 0) { throw "zip 内容不合格：$($bad[0].FullName)" }
    $count = $zip.Entries.Count
} finally { $zip.Dispose() }

$manual = Join-Path $target '使用说明.txt'
$bytes = [System.IO.File]::ReadAllBytes($manual)
$bom = ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
if (-not $bom) { throw '使用说明.txt 缺少 BOM，对方打开会乱码' }

$zipMB = [math]::Round((Get-Item -LiteralPath $shareZip).Length / 1MB, 1)
$stamp = (Get-Item -LiteralPath $deployedExe).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')

Get-ChildItem -LiteralPath $stage -Recurse -Force | Out-Null
Remove-Item -LiteralPath $stage -Recurse -Force

Write-Output "完成：两处都已更新"
Write-Output "  自己用   $target\九人圆桌.exe   构建于 $stamp   哈希 $newHash"
Write-Output "  发给别人 $shareZip   ${zipMB}MB   $count 个条目"
Write-Output "  说明书   $((Get-Item -LiteralPath $manual).Length) 字节，带 BOM"
