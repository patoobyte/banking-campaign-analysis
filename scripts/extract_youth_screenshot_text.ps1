# Offline OCR for the six user-supplied youth-account screenshot sections.
# Uses Windows' installed OCR engine; never opens the campaign URL.
param([Parameter(Mandatory=$true)][string]$ImageFolder, [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
function Await-WindowsOperation($operation,$resultType) {
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 } |
        Select-Object -First 1
    $task=$method.MakeGenericMethod(@($resultType)).Invoke($null,@($operation))
    return $task.GetAwaiter().GetResult()
}
$fileType=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$streamType=[Windows.Storage.Streams.IRandomAccessStreamWithContentType,Windows.Storage.Streams,ContentType=WindowsRuntime]
$decoderType=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$bitmapType=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
$ocrType=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$resultType=[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
$ocr=$ocrType::TryCreateFromUserProfileLanguages()
if($null -eq $ocr) {throw 'Windows OCR is unavailable.'}
$sections=@()
foreach($number in 1..6) {
    $path=Join-Path $ImageFolder "$number.png"
    if(-not [IO.File]::Exists($path)) {throw "Missing screenshot $number.png"}
    $file=Await-WindowsOperation ($fileType::GetFileFromPathAsync([IO.Path]::GetFullPath($path))) $fileType
    $stream=Await-WindowsOperation ($file.OpenReadAsync()) $streamType
    try {
        $decoder=Await-WindowsOperation ($decoderType::CreateAsync($stream)) $decoderType
        $image=Await-WindowsOperation ($decoder.GetSoftwareBitmapAsync()) $bitmapType
        $result=Await-WindowsOperation ($ocr.RecognizeAsync($image)) $resultType
        $sections+= "Screenshot section $number (top to bottom):`r`n" + $result.Text.Trim()
        Write-Host "Section $number OCR characters: $($result.Text.Length)"
    } finally {$stream.Dispose()}
}
$text="OCR TRANSCRIPTION OF SIX USER-SUPPLIED SCREENSHOTS; NOT RENDERED HTML TEXT. OCR can misread amounts, terms, and CTAs: check the corresponding screenshot before making claims.`r`n`r`n" + ($sections -join "`r`n`r`n")
$parent=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($OutputPath))
[IO.Directory]::CreateDirectory($parent) | Out-Null
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath),$text,[Text.UTF8Encoding]::new($false))
Write-Host "Total OCR characters: $($text.Length)"
