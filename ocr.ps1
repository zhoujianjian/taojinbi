param(
    [Parameter(Mandatory=$true)][string]$ImagePath,
    [string]$OutFile = ""
)

# Windows built-in OCR (Windows.Media.Ocr)
# Output format:
#   L <TAB> line text <TAB> x0 <TAB> y0 <TAB> width <TAB> height
#   W <TAB> word text <TAB> cx <TAB> cy
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = $null
foreach ($lang in @("zh-Hans-CN", "zh-Hans", "zh-CN")) {
    try {
        $language = New-Object Windows.Globalization.Language $lang
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
        if ($engine) { break }
    } catch { }
}
if (-not $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
}
if (-not $engine) { Write-Output "NO_OCR_ENGINE"; exit 1 }

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$lines = @()
foreach ($line in $result.Lines) {
    $words = $line.Words
    if ($words.Count -eq 0) { continue }
    $x0 = [double]::MaxValue
    $y0 = [double]::MaxValue
    $x1 = 0.0
    $y1 = 0.0
    foreach ($w in $words) {
        $r = $w.BoundingRect
        if ($r.X -lt $x0) { $x0 = $r.X }
        if ($r.Y -lt $y0) { $y0 = $r.Y }
        if (($r.X + $r.Width) -gt $x1) { $x1 = $r.X + $r.Width }
        if (($r.Y + $r.Height) -gt $y1) { $y1 = $r.Y + $r.Height }
    }
    $bw = [int]($x1 - $x0)
    $bh = [int]($y1 - $y0)
    $lines += (@("L", $line.Text, [string][int]$x0, [string][int]$y0, [string]$bw, [string]$bh) -join [char]9)
    foreach ($w in $words) {
        $r = $w.BoundingRect
        $lines += (@("W", $w.Text, [string][int]($r.X + $r.Width / 2), [string][int]($r.Y + $r.Height / 2)) -join [char]9)
    }
}

if ($OutFile -ne "") {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($OutFile, $lines, $utf8)
} else {
    $lines | ForEach-Object { Write-Output $_ }
}
