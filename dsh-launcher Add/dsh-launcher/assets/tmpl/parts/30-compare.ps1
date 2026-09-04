function Test-NewerVersion([string]$cur, [string]$new) {
    if ([string]::IsNullOrWhiteSpace($cur) -or [string]::IsNullOrWhiteSpace($new)) { return $false }
    function Parse-V([string]$s) {
        $m = [regex]::Match($s, '^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?')
        if (-not $m.Success) { return $null }
        return @{ major=[int]$m.Groups[1].Value; minor=[int]$m.Groups[2].Value; patch=[int]$m.Groups[3].Value; pre=$m.Groups[4].Value }
    }
    $a = Parse-V $cur; $b = Parse-V $new
    if ($null -eq $a -or $null -eq $b) { return $false }
    if ($b.major -ne $a.major) { return $b.major -gt $a.major }
    if ($b.minor -ne $a.minor) { return $b.minor -gt $a.minor }
    if ($b.patch -ne $a.patch) { return $b.patch -gt $a.patch }
    if ($a.pre -eq '' -and $b.pre -ne '') { return $false }
    if ($a.pre -ne '' -and $b.pre -eq '') { return $true }
    # prerelease 按 . 分段比较，数字段数值比较（rc.10 > rc.2，字符串比较会错序）
    $ap = $a.pre -split '\.'; $bp = $b.pre -split '\.'
    for ($i = 0; $i -lt [Math]::Max($ap.Count, $bp.Count); $i++) {
        $ai = if ($i -lt $ap.Count) { $ap[$i] } else { $null }
        $bi = if ($i -lt $bp.Count) { $bp[$i] } else { $null }
        if ($null -eq $ai -and $null -eq $bi) { continue }
        if ($null -eq $ai) { return $false }   # b 更长 → b 更新
        if ($null -eq $bi) { return $true }    # a 更长 → a 更新
        $an = 0; $bn = 0
        $aiIsNum = [int]::TryParse($ai, [ref]$an)
        $biIsNum = [int]::TryParse($bi, [ref]$bn)
        if ($aiIsNum -and $biIsNum) {
            if ($bn -ne $an) { return $bn -gt $an }
        } else {
            $cmp = [string]::Compare($bi, $ai, [StringComparison]::OrdinalIgnoreCase)
            if ($cmp -ne 0) { return $cmp -gt 0 }
        }
    }
    return $false
}
