param(
    [Parameter(Mandatory = $true)][string]$SourceDir,
    [Parameter(Mandatory = $true)][string]$OutputZip,
    [string]$RootName = ""
)

# 打包一个可以直接发给别人的程序文件夹。
#
# 两个必须做对的地方：
# 1. ZIP 规范要求条目名用正斜杠。.NET Framework 的 CreateFromDirectory 会写成
#    反斜杠，Windows 资源管理器能容忍，别的解压工具可能解出乱名字。
# 2. 绝不发布没有验证过的包：先建到临时文件，验证条目数、分隔符、CRC 与敏感
#    文件，全部通过才移动到目标路径。中途失败不会留下半个坏包。

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$SourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
if (-not $RootName) { $RootName = Split-Path -Leaf $SourceDir }
$tmp = Join-Path $env:TEMP ("share-" + [guid]::NewGuid().ToString('N') + ".zip")

try {
    $files = Get-ChildItem -LiteralPath $SourceDir -Recurse -File -Force
    if ($files.Count -eq 0) { throw "源目录为空：$SourceDir" }

    $fs = [System.IO.File]::Open($tmp, [System.IO.FileMode]::Create)
    $archive = [System.IO.Compression.ZipArchive]::new($fs, [System.IO.Compression.ZipArchiveMode]::Create)
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($SourceDir.Length + 1).Replace('\', '/')
        $entry = $archive.CreateEntry("$RootName/$relative", [System.IO.Compression.CompressionLevel]::Optimal)
        $target = $entry.Open()
        $input = [System.IO.File]::OpenRead($file.FullName)
        try { $input.CopyTo($target) } finally { $input.Dispose(); $target.Dispose() }
    }
    $archive.Dispose()
    $fs.Dispose()

    $zip = [System.IO.Compression.ZipFile]::OpenRead($tmp)
    try {
        if ($zip.Entries.Count -ne $files.Count) {
            throw "条目数不符：$($zip.Entries.Count) != $($files.Count)"
        }
        $backslash = @($zip.Entries | Where-Object { $_.FullName -like '*\*' })
        if ($backslash.Count -gt 0) { throw "条目名用了反斜杠，不符合 ZIP 规范：$($backslash[0].FullName)" }
        $forbidden = @($zip.Entries | Where-Object { $_.FullName -match 'ai-settings|\.key$|secret|hotspots.*\.json' })
        if ($forbidden.Count -gt 0) { throw "包内包含本机设置或缓存：$($forbidden[0].FullName)" }
        foreach ($entry in $zip.Entries) {
            $stream = $entry.Open()
            $buffer = New-Object byte[] 65536
            while ($stream.Read($buffer, 0, $buffer.Length) -gt 0) { }
            $stream.Dispose()
        }
    } finally { $zip.Dispose() }

    Move-Item -LiteralPath $tmp -Destination $OutputZip -Force
    $size = [math]::Round((Get-Item -LiteralPath $OutputZip).Length / 1MB, 1)
    Write-Output "OK 条目=$($files.Count) 大小=${size}MB 顶层目录=$RootName"
} finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}
