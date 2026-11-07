<#
  盘点技能.ps1  —— 只读技能盘点（升级前后基线比对用）

  用途
    1) 盘点本机「用户自装技能」与「DSH 自带技能」，产出可机器比对的 JSON 基线；
    2) 用 -Compare 与旧基线比对，输出 added / removed / changed；
    3) 对每个技能做可加载性自检，把「文件在、DSH 不认」这类失效显式标出来。

  判据说明
    - 磁盘目录数 ≠ 可用技能数。池 4（插件技能）经 junction 存放，磁盘遍历会漏，
      只能靠会话可见清单人工核对，本脚本只给提示位。
    - 目录级 SHA256 汇总 = 对「相对路径:文件SHA256」按序拼接后取 SHA256，
      与文件名大小写、遍历顺序无关。

  只读。不修改任何技能文件，不接进 setup.ps1。

  用法
    powershell -NoProfile -File 盘点技能.ps1 -OutFile D:\path\基线.json
    powershell -NoProfile -File 盘点技能.ps1 -Compare D:\path\基线.json
#>

[CmdletBinding()]
param(
    [string]$OutFile = '',
    [string]$Compare = '',
    [string]$SkillRoot = (Join-Path $env:USERPROFILE '.agents\skills'),
    [string]$DshPackage = ''
)

$ErrorActionPreference = 'Stop'

function Get-DirDigest {
    param([string]$Dir)
    $files = @(Get-ChildItem -LiteralPath $Dir -Recurse -File -ErrorAction SilentlyContinue)
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($f in $files) {
        $rel = $f.FullName.Substring($Dir.Length).TrimStart('\')
        $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
        $lines.Add($rel.ToLowerInvariant() + ':' + $h)
    }
    $joined = (($lines | Sort-Object) -join "`n")
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($joined)
        $digest = (($sha.ComputeHash($bytes)) | ForEach-Object { $_.ToString('x2') }) -join ''
    } finally { $sha.Dispose() }
    $total = 0L
    if ($files.Count -gt 0) { $total = [long](($files | Measure-Object Length -Sum).Sum) }
    [pscustomobject]@{
        Files  = $files.Count
        Bytes  = $total
        Digest = $digest
    }
}

function Get-Frontmatter {
    param([string]$SkillDir)
    $p = Join-Path $SkillDir 'SKILL.md'
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    $lines = @(Get-Content -LiteralPath $p -TotalCount 40 -Encoding UTF8)
    if ($lines.Count -lt 3) { return $null }
    if ($lines[0].Trim() -ne '---') { return $null }
    $end = -1
    for ($i = 1; $i -lt $lines.Count; $i++) {
        if ($lines[$i].Trim() -eq '---') { $end = $i; break }
    }
    if ($end -lt 0) { return $null }
    $name = ''
    $desc = ''
    for ($i = 1; $i -lt $end; $i++) {
        $l = $lines[$i]
        if ($l -match '^name:\s*(.+)$') { $name = $Matches[1].Trim().Trim('"').Trim("'") }
        elseif ($l -match '^description:\s*(.*)$') { $desc = $Matches[1].Trim() }
    }
    [pscustomobject]@{ Name = $name; Description = $desc }
}

function Test-Loadable {
    param([string]$SkillDir, $Fm, [int]$NameCount)
    if (-not (Test-Path -LiteralPath (Join-Path $SkillDir 'SKILL.md'))) { return 'NO_SKILL_MD' }
    if ($null -eq $Fm) { return 'FM_BROKEN' }
    if ([string]::IsNullOrWhiteSpace($Fm.Name)) { return 'FM_NO_NAME' }
    $d = [string]$Fm.Description
    if ($d.Length -gt 0) {
        $quoted = $d.StartsWith('"') -or $d.StartsWith("'") -or $d.StartsWith('>') -or $d.StartsWith('|')
        if (-not $quoted -and $d.Contains(': ')) { return 'FM_RISKY' }
    }
    if ($NameCount -gt 1) { return 'DUP_NAME' }
    return 'OK'
}

function Get-VersionInfo {
    param([string]$SkillDir, $Fm)
    $metaPath = Join-Path $SkillDir '_meta.json'
    if (Test-Path -LiteralPath $metaPath) {
        try {
            $j = Get-Content -LiteralPath $metaPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($j.version) {
                return [pscustomobject]@{ Version = [string]$j.version; Source = '_meta.json' }
            }
        } catch { }
    }
    if ($Fm -and $Fm.Name) {
        return [pscustomobject]@{ Version = '' ; Source = 'frontmatter' }
    }
    return [pscustomobject]@{ Version = '' ; Source = 'none' }
}

# ---------- 解析 DSH 包位置（池 3）----------
if (-not $DshPackage) {
    $dshCmd = Get-Command 'dsh.cmd' -ErrorAction SilentlyContinue
    if ($dshCmd) {
        $nm = Join-Path (Split-Path -Parent $dshCmd.Source) 'node_modules'
        $candidate = Join-Path $nm '@deepseek-ai\dsh'
        if (Test-Path -LiteralPath $candidate) { $DshPackage = $candidate }
    }
}

$bundledRoots = @()
if ($DshPackage) {
    $bundledRoots = @(
        [pscustomobject]@{ Rel = 'dsh-agent-preset\skills';              Path = (Join-Path $DshPackage 'node_modules\@deepseek-ai\dsh-agent-preset\skills') },
        [pscustomobject]@{ Rel = 'dsh-skill-office\assets';              Path = (Join-Path $DshPackage 'node_modules\@deepseek-ai\dsh-skill-office\assets') },
        [pscustomobject]@{ Rel = 'dsh-sandbox-windows-acl\assets';       Path = (Join-Path $DshPackage 'node_modules\@deepseek-ai\dsh-sandbox-windows-acl\assets') }
    )
}

# ---------- 收集 ----------
$skills = New-Object System.Collections.Generic.List[object]
$warnings = New-Object System.Collections.Generic.List[string]

$userDirs = @()
if (Test-Path -LiteralPath $SkillRoot) {
    $userDirs = @(Get-ChildItem -LiteralPath $SkillRoot -Directory | Where-Object { $_.Name -notmatch '^_' })
}

# 先算出全部 frontmatter 的 name，供重名判定
$fmMap = @{}
foreach ($d in $userDirs) { $fmMap[$d.FullName] = Get-Frontmatter -SkillDir $d.FullName }
$nameTally = @{}
foreach ($d in $userDirs) {
    $fm = $fmMap[$d.FullName]
    if ($fm -and $fm.Name) {
        if ($nameTally.ContainsKey($fm.Name)) { $nameTally[$fm.Name] = $nameTally[$fm.Name] + 1 }
        else { $nameTally[$fm.Name] = 1 }
    }
}

foreach ($d in $userDirs) {
    $fm = $fmMap[$d.FullName]
    $nc = 0
    if ($fm -and $fm.Name -and $nameTally.ContainsKey($fm.Name)) { $nc = $nameTally[$fm.Name] }
    $dg = Get-DirDigest -Dir $d.FullName
    $vi = Get-VersionInfo -SkillDir $d.FullName -Fm $fm
    $skills.Add([pscustomobject]@{
        Pool     = 'user'
        Name     = $d.Name
        Version  = $vi.Version
        VerSrc   = $vi.Source
        Files    = $dg.Files
        Bytes    = $dg.Bytes
        Sha256   = $dg.Digest
        Loadable = (Test-Loadable -SkillDir $d.FullName -Fm $fm -NameCount $nc)
    })
}

$bundledCount = 0
foreach ($br in $bundledRoots) {
    if (-not (Test-Path -LiteralPath $br.Path)) { continue }
    foreach ($d in @(Get-ChildItem -LiteralPath $br.Path -Directory)) {
        $fm = Get-Frontmatter -SkillDir $d.FullName
        $dg = Get-DirDigest -Dir $d.FullName
        $vi = Get-VersionInfo -SkillDir $d.FullName -Fm $fm
        $skills.Add([pscustomobject]@{
            Pool     = 'bundled'
            Name     = $d.Name
            Version  = $vi.Version
            VerSrc   = $vi.Source
            Files    = $dg.Files
            Bytes    = $dg.Bytes
            Sha256   = $dg.Digest
            Loadable = (Test-Loadable -SkillDir $d.FullName -Fm $fm -NameCount 1)
        })
        $bundledCount++
    }
}

foreach ($s in $skills) { if ($s.Loadable -ne 'OK') { $warnings.Add($s.Pool + '/' + $s.Name + ' => ' + $s.Loadable) } }
$userTotal = @($skills | Where-Object { $_.Pool -eq 'user' }).Count
$userOk = @($skills | Where-Object { $_.Pool -eq 'user' -and $_.Loadable -eq 'OK' }).Count
$bundledTotal = @($skills | Where-Object { $_.Pool -eq 'bundled' }).Count

$result = [pscustomobject]@{
    GeneratedAt  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Machine      = $env:COMPUTERNAME
    DshVersion   = $(try { (& dsh --version 2>$null) -join ' ' } catch { 'UNKNOWN' })
    SkillRoot    = $SkillRoot
    DshPackage   = $DshPackage
    Counts       = [pscustomobject]@{
        UserDirs      = $userDirs.Count
        UserLoadable  = $userOk
        Bundled       = $bundledTotal
        DiskTotal     = ($userDirs.Count + $bundledTotal)
        Plugin        = 'UNKNOWN (junction, needs session-visible list)'
    }
    Skills       = $skills
    Warnings     = $warnings
}

# ---------- 输出 ----------
Write-Host ''
Write-Host '===== 池 1：用户自装技能 =====' -ForegroundColor Cyan
$skills | Where-Object { $_.Pool -eq 'user' } |
    Select-Object Name, Version, VerSrc, Files, Loadable |
    Sort-Object Name | Format-Table -AutoSize
Write-Host ('池 1 合计：' + $userDirs.Count + ' 个目录，可加载 ' + $userOk + ' 个')
Write-Host ''
Write-Host '===== 池 3：DSH 自带技能 =====' -ForegroundColor Cyan
$skills | Where-Object { $_.Pool -eq 'bundled' } |
    Select-Object Name, Files, Loadable | Sort-Object Name | Format-Table -AutoSize
Write-Host ('池 3 合计：' + $bundledTotal + ' 个')
Write-Host ''
Write-Host '===== 汇总 =====' -ForegroundColor Cyan
Write-Host ('池 1 目录 ' + $userDirs.Count + '　池 1 可加载 ' + $userOk + '　池 3 ' + $bundledTotal)
Write-Host ('磁盘可见合计（池 1 + 池 3）：' + ($userDirs.Count + $bundledTotal))
Write-Host '池 4（插件技能）无法用磁盘遍历得到，请用会话可见技能清单条数人工核对。'

$bad = @($skills | Where-Object { $_.Loadable -ne 'OK' })
if ($bad.Count -gt 0) {
    Write-Host ''
    Write-Host '===== 可加载性异常 =====' -ForegroundColor Yellow
    $bad | Select-Object Pool, Name, Loadable | Format-Table -AutoSize
} else {
    Write-Host '可加载性自检：全部 OK'
}

if ($OutFile) {
    $dir = Split-Path -Parent $OutFile
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding utf8
    Write-Host ('已写出基线：' + $OutFile)
}

# ---------- 比对 ----------
if ($Compare) {
    if (-not (Test-Path -LiteralPath $Compare)) { throw ('基线文件不存在：' + $Compare) }
    $old = Get-Content -LiteralPath $Compare -Raw -Encoding UTF8 | ConvertFrom-Json
    $oldMap = @{}
    foreach ($s in $old.Skills) { $oldMap[[string]$s.Pool + '/' + [string]$s.Name] = [string]$s.Sha256 }
    $newMap = @{}
    foreach ($s in $skills) { $newMap[[string]$s.Pool + '/' + [string]$s.Name] = [string]$s.Sha256 }

    $added = @($newMap.Keys | Where-Object { -not $oldMap.ContainsKey($_) })
    $removed = @($oldMap.Keys | Where-Object { -not $newMap.ContainsKey($_) })
    $changed = @($newMap.Keys | Where-Object { $oldMap.ContainsKey($_) -and $oldMap[$_] -ne $newMap[$_] })

    Write-Host ''
    Write-Host '===== 与基线比对 =====' -ForegroundColor Cyan
    Write-Host ('基线：' + $Compare)
    Write-Host ('基线时间：' + $old.GeneratedAt)
    Write-Host ('added=' + $added.Count + '  removed=' + $removed.Count + '  changed=' + $changed.Count)
    if ($added.Count -gt 0) { Write-Host 'ADDED:'; $added | Sort-Object | ForEach-Object { Write-Host ('  + ' + $_) } }
    if ($removed.Count -gt 0) { Write-Host 'REMOVED:'; $removed | Sort-Object | ForEach-Object { Write-Host ('  - ' + $_) } }
    if ($changed.Count -gt 0) { Write-Host 'CHANGED:'; $changed | Sort-Object | ForEach-Object { Write-Host ('  * ' + $_) } }
    if (($added.Count + $removed.Count + $changed.Count) -eq 0) {
        Write-Host '无差异：技能集合与内容均未变化。'
    }
}
