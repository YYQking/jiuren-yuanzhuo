$ErrorActionPreference = 'Stop'

$sourceRoot = Join-Path $PSScriptRoot '九人圆桌桌面版-修复版'
$desktopRoot = [Environment]::GetFolderPath('Desktop')
$destinationRoot = Join-Path $desktopRoot '九人圆桌桌面版'
$shortcutPath = Join-Path $desktopRoot '九人圆桌.lnk'

if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot '九人圆桌.exe'))) {
    throw 'Prepared executable is missing.'
}
if ((Test-Path -LiteralPath $destinationRoot) -or (Test-Path -LiteralPath $shortcutPath)) {
    throw 'Desktop destination already exists; refusing to overwrite it.'
}

Copy-Item -LiteralPath $sourceRoot -Destination $destinationRoot -Recurse
$sourceFiles = @(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File)
$destinationFiles = @(Get-ChildItem -LiteralPath $destinationRoot -Recurse -File)
if ($destinationFiles.Count -ne $sourceFiles.Count) {
    throw 'Desktop package file count does not match.'
}
foreach ($sourceFile in $sourceFiles) {
    $relative = $sourceFile.FullName.Substring($sourceRoot.Length + 1)
    $destinationFile = Join-Path $destinationRoot $relative
    if (-not (Test-Path -LiteralPath $destinationFile)) {
        throw "Desktop package is missing: $relative"
    }
    if ((Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $destinationFile -Algorithm SHA256).Hash) {
        throw "Desktop package content differs: $relative"
    }
}

$exePath = Join-Path $destinationRoot '九人圆桌.exe'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exePath
$shortcut.WorkingDirectory = $destinationRoot
$shortcut.IconLocation = "$exePath,0"
$shortcut.Description = '九人圆桌 · 头脑风暴桌面版'
$shortcut.WindowStyle = 1
$shortcut.Save()

$check = $shell.CreateShortcut($shortcutPath)
if ($check.TargetPath -ne $exePath -or $check.WorkingDirectory -ne $destinationRoot) {
    throw 'Desktop shortcut target is incorrect.'
}

$savedQtPlatform = [Environment]::GetEnvironmentVariable('QT_QPA_PLATFORM', 'Process')
$appProcess = $null
try {
    [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', $null, 'Process')
    $appProcess = Start-Process -FilePath $check.TargetPath -WorkingDirectory $check.WorkingDirectory -PassThru
    $mainWindow = & (Join-Path $PSScriptRoot 'verify-main-window.ps1') -ProcessId $appProcess.Id
    [pscustomobject]@{
        DesktopShortcut = $shortcutPath
        DesktopExecutable = $exePath
        FilesVerified = $destinationFiles.Count
        StartupCheck = "Passed: visible $($mainWindow.ClassName) main window ($($mainWindow.Width)x$($mainWindow.Height))"
    } | Format-List
} finally {
    if ($null -ne $appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force
    }
    [Environment]::SetEnvironmentVariable('QT_QPA_PLATFORM', $savedQtPlatform, 'Process')
}
