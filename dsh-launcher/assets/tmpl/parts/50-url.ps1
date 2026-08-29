function Open-Url([string]$url) {
    # DSH Web URL 优先用已安装的主应用（PWA）；打开失败/未装才回退普通浏览器
    if ($url -eq $webUrl) {
        if (Open-DshApp $url) { return }
    }
    # 多级兜底打开 URL：Start-Process → Process.Start → explorer.exe；全失败则抛错
    $lastErr = $null
    try { Start-Process $url -ErrorAction Stop; return } catch { $lastErr = $_.Exception }
    try { [System.Diagnostics.Process]::Start($url) | Out-Null; return } catch { if (-not $lastErr) { $lastErr = $_.Exception } }
    try { Start-Process -FilePath 'explorer.exe' -ArgumentList @($url) -ErrorAction Stop; return } catch { if (-not $lastErr) { $lastErr = $_.Exception } }
    throw "无法打开 $url：$($lastErr.Message)"
}
