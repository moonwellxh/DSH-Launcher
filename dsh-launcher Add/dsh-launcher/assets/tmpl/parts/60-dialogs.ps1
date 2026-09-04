function Show-UpgradeDialog {
    param([string]$Title, [string]$Instruction)
    # 读模型目录（用任一现有会话读全局目录）
    $listVal = Invoke-DshRpc 'session.list' @{}
    $catSid = $null
    foreach ($it in @($listVal.items)) {
        if (-not $it.origin) { $catSid = $it.sessionId; break }
    }
    $catalog = @()
    $currentModel = ''
    if ($catSid) {
        $m = Invoke-DshRpc 'session.models' @{ sessionId = $catSid }
        $currentModel = [string]$m.current.model
        foreach ($g in $m.groups) {
            foreach ($md in $g.models) {
                $catalog += [pscustomobject]@{
                    provider = [string]$g.id
                    model    = [string]$md.id
                    name     = [string]$md.name
                    efforts  = @($md.reasoning.efforts | ForEach-Object { [string]$_.id })
                    defaultEffort = [string]$md.reasoning.defaultEffort
                }
            }
        }
    }
    if ($catalog.Count -eq 0) {
        [System.Windows.Forms.MessageBox]::Show('无法读取模型目录，请确认 DSH 已启动。', $Title, 'OK', 'Error')
        return
    }
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $Title
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 10)
    $form.AutoSize = $true
    $form.AutoSizeMode = 'GrowAndShrink'
    $panel = New-Object System.Windows.Forms.FlowLayoutPanel
    $panel.FlowDirection = 'TopDown'
    $panel.WrapContents = $false
    $panel.AutoSize = $true
    $panel.Padding = New-Object System.Windows.Forms.Padding(16, 12, 16, 12)
    $lblTitle = New-Object System.Windows.Forms.Label
    $lblTitle.Text = $Title
    $lblTitle.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 11, [System.Drawing.FontStyle]::Bold)
    $lblTitle.AutoSize = $true
    $panel.Controls.Add($lblTitle)
    $rowM = New-Object System.Windows.Forms.FlowLayoutPanel
    $rowM.FlowDirection = 'LeftToRight'; $rowM.WrapContents = $false; $rowM.AutoSize = $true
    $rowM.Margin = New-Object System.Windows.Forms.Padding(0, 10, 0, 0)
    $lblM = New-Object System.Windows.Forms.Label; $lblM.Text = '模型：'; $lblM.AutoSize = $true
    $cmbModel = New-Object System.Windows.Forms.ComboBox
    $cmbModel.DropDownStyle = 'DropDownList'; $cmbModel.Width = 280
    $modelMap = @{}
    foreach ($c in $catalog) { $modelMap[[string]$c.name] = $c; [void]$cmbModel.Items.Add([string]$c.name) }
    $rowM.Controls.AddRange(@($lblM, $cmbModel))
    $panel.Controls.Add($rowM)
    $rowE = New-Object System.Windows.Forms.FlowLayoutPanel
    $rowE.FlowDirection = 'LeftToRight'; $rowE.WrapContents = $false; $rowE.AutoSize = $true
    $rowE.Margin = New-Object System.Windows.Forms.Padding(0, 8, 0, 0)
    $lblE = New-Object System.Windows.Forms.Label; $lblE.Text = '推理等级：'; $lblE.AutoSize = $true
    $cmbEffort = New-Object System.Windows.Forms.ComboBox
    $cmbEffort.DropDownStyle = 'DropDownList'; $cmbEffort.Width = 160
    $rowE.Controls.AddRange(@($lblE, $cmbEffort))
    $panel.Controls.Add($rowE)
    $updateEfforts = {
        $cmbEffort.Items.Clear()
        $name = [string]$cmbModel.SelectedItem
        if ($modelMap.ContainsKey($name)) {
            $c = $modelMap[$name]
            foreach ($e in @($c.efforts)) { [void]$cmbEffort.Items.Add($e) }
            $def = $c.defaultEffort
            if ($cmbEffort.Items.Contains($def)) { $cmbEffort.SelectedItem = $def }
            elseif ($cmbEffort.Items.Count -gt 0) { $cmbEffort.SelectedIndex = 0 }
        }
    }
    $cmbModel.Add_SelectedIndexChanged($updateEfforts)
    $preIdx = 0
    for ($i = 0; $i -lt $cmbModel.Items.Count; $i++) {
        $nm = [string]$cmbModel.Items[$i]
        if ($modelMap.ContainsKey($nm) -and $modelMap[$nm].model -eq $currentModel) { $preIdx = $i; break }
    }
    if ($cmbModel.Items.Count -gt 0) { $cmbModel.SelectedIndex = $preIdx }
    & $updateEfforts
    $lblP = New-Object System.Windows.Forms.Label
    $lblP.Text = '提示词（可编辑）：'; $lblP.AutoSize = $true
    $lblP.Margin = New-Object System.Windows.Forms.Padding(0, 12, 0, 0)
    $panel.Controls.Add($lblP)
    $txtPrompt = New-Object System.Windows.Forms.TextBox
    $txtPrompt.Multiline = $true
    $txtPrompt.ScrollBars = 'Vertical'
    $txtPrompt.WordWrap = $true
    $txtPrompt.Width = 460
    $txtPrompt.Height = 150
    $txtPrompt.Text = $Instruction
    $panel.Controls.Add($txtPrompt)
    $rowB = New-Object System.Windows.Forms.FlowLayoutPanel
    $rowB.FlowDirection = 'LeftToRight'; $rowB.WrapContents = $false; $rowB.AutoSize = $true
    $rowB.Margin = New-Object System.Windows.Forms.Padding(0, 14, 0, 0)
    $btnSubmit = New-Object System.Windows.Forms.Button
    $btnSubmit.Text = '提交运行'; $btnSubmit.Size = New-Object System.Drawing.Size(120, 34)
    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text = '取消'; $btnCancel.Size = New-Object System.Drawing.Size(80, 34)
    $btnCancel.Margin = New-Object System.Windows.Forms.Padding(12, 0, 0, 0)
    $rowB.Controls.AddRange(@($btnSubmit, $btnCancel))
    $panel.Controls.Add($rowB)
    $form.Controls.Add($panel)
    $form.AcceptButton = $btnSubmit
    $form.CancelButton = $btnCancel
    $btnCancel.Add_Click({ $form.Close() })
    $btnSubmit.Add_Click({
        $name = [string]$cmbModel.SelectedItem
        if (-not $modelMap.ContainsKey($name)) { [System.Windows.Forms.MessageBox]::Show('请选择模型', $Title, 'OK', 'Warning'); return }
        $sel = $modelMap[$name]
        $provider = $sel.provider
        $model = $sel.model
        $effort = $cmbEffort.SelectedItem
        $promptText = $txtPrompt.Text
        if ([string]::IsNullOrWhiteSpace($promptText)) { [System.Windows.Forms.MessageBox]::Show('提示词为空', $Title, 'OK', 'Warning'); return }
        try {
            $wsVal = Invoke-DshRpc 'workspace.create' @{ path = $upgradeDir }
            $wsId = $wsVal.workspace.workspaceId
            try { Invoke-DshRpc 'workspace.rename' @{ workspaceId = $wsId; title = 'DSH 升级' } | Out-Null } catch {}
            try { Invoke-DshRpc 'workspace.insertBefore' @{ workspaceId = $wsId } | Out-Null } catch {}
            $sess = Invoke-DshRpc 'session.create' @{ workspaceId = $wsId }
            $sid = $sess.sessionId
            $sm = @{ sessionId = $sid; provider = $provider; model = $model }
            if ($effort) { $sm.reasoningEffort = [string]$effort }
            Invoke-DshRpc 'session.selectModel' $sm | Out-Null
            Invoke-DshRpc 'session.prompt' @{ sessionId = $sid; mode = 'queue'; content = @(@{ type = 'text'; text = $promptText }) } | Out-Null
            $form.Close()
            Open-Url $webUrl
            $notify.ShowBalloonTip(3000, 'DSH 升级', '升级任务已提交运行。', 'Info')
        } catch {
            [System.Windows.Forms.MessageBox]::Show("提交失败：$($_.Exception.Message)", $Title, 'OK', 'Error')
        }
    })
    $form.ShowDialog()
    $form.Dispose()
}
__MODE_UPGRADE_INSTRUCTION____MODE_UPGRADE_SUFFIX__function Show-SyncDirectionDialog([string]$text) {
    # 同步方向确认弹窗：返回 'upload' / 'pull' / 'cancel'
    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'DSH 启动脚本同步方向确认'
    $f.StartPosition = 'CenterScreen'
    $f.FormBorderStyle = 'FixedDialog'
    $f.MaximizeBox = $false
    $f.MinimizeBox = $false
    $f.ClientSize = New-Object System.Drawing.Size(560, 215)
    $lbl = New-Object System.Windows.Forms.Label
    $lbl.Text = $text
    $lbl.SetBounds(16, 16, 528, 125)
    $lbl.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
    $script:dialogResult = 'cancel'
    $bUp = New-Object System.Windows.Forms.Button
    $bUp.Text = '上传到 GitHub'
    $bUp.SetBounds(16, 152, 160, 38)
    $bUp.Add_Click({ $script:dialogResult = 'upload'; $f.Close() })
    $bPull = New-Object System.Windows.Forms.Button
    $bPull.Text = '拉取 GitHub 版本'
    $bPull.SetBounds(190, 152, 170, 38)
    $bPull.Add_Click({ $script:dialogResult = 'pull'; $f.Close() })
    $bCancel = New-Object System.Windows.Forms.Button
    $bCancel.Text = '取消'
    $bCancel.SetBounds(374, 152, 100, 38)
    $bCancel.Add_Click({ $script:dialogResult = 'cancel'; $f.Close() })
    $f.Controls.Add($lbl)
    $f.Controls.Add($bUp)
    $f.Controls.Add($bPull)
    $f.Controls.Add($bCancel)
    [void]$f.ShowDialog()
    $f.Dispose()
    return $script:dialogResult
}
