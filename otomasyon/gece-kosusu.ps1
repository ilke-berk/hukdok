<#
 gece-kosusu.ps1 - Sertlestirme paketlerini gece gozetimsiz yurutur.

 Her paket icin SIFIR-context'li bir claude oturumu acar (.claude/skills/faz-devam),
 ardindan AYRI bir temiz oturumla denetletir (.claude/skills/faz-denetle).
 Durum tek dogruluk kaynaginda tutulur: docs/guvenilirlik-sertlestirme-uygulama-takibi.md

 Kullanim (repo kokunden):
   powershell -ExecutionPolicy Bypass -File otomasyon\gece-kosusu.ps1
   powershell -ExecutionPolicy Bypass -File otomasyon\gece-kosusu.ps1 -MaxPaket 5 -KirliAgacKabul

 Durdurmak icin: otomasyon\DURDUR adinda bos bir dosya olustur (paket sinirinda durur).
 Bu script ASLA push/ssh/deploy yapmaz; sabah inceleme + push + deploy karari kullanicidadir.
 NOT: Bu dosya bilerek ASCII yazildi (PS 5.1 BOM'suz UTF-8'i ANSI okur, Turkce karakter bozulur).
#>
param(
    [int]$MaxPaket = 3,
    [int]$PaketZamanAsimiDk = 180,
    [int]$DenetimZamanAsimiDk = 45,
    [switch]$KirliAgacKabul
)

$ErrorActionPreference = "Stop"
$otomasyonDir = $PSScriptRoot
$repoKok = Split-Path -Parent $otomasyonDir
Set-Location $repoKok

$logDir = Join-Path $otomasyonDir "loglar"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$kosuId = Get-Date -Format "yyyyMMdd-HHmmss"
$anaLog = Join-Path $logDir ("gece_{0}.log" -f $kosuId)
$durdurDosya = Join-Path $otomasyonDir "DURDUR"
$takipDosya = Join-Path $repoKok "docs\guvenilirlik-sertlestirme-uygulama-takibi.md"

function Yaz([string]$mesaj) {
    $satir = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mesaj
    Write-Host $satir
    Add-Content -Path $anaLog -Value $satir -Encoding UTF8
}

# --- claude CLI'yi bul (npm shim .ps1 ise yanindaki .cmd tercih edilir: cmd.exe ile kosacagiz) ---
$claudeYol = $null
try { $claudeYol = (Get-Command claude -ErrorAction Stop).Source } catch {}
if ($null -eq $claudeYol) { Yaz "HATA: claude CLI PATH'te bulunamadi."; exit 1 }
if ($claudeYol.ToLower().EndsWith(".ps1")) {
    $aday = $claudeYol.Substring(0, $claudeYol.Length - 4) + ".cmd"
    if (Test-Path $aday) { $claudeYol = $aday }
}
Yaz ("claude: " + $claudeYol)

function KosClaude([string]$argSatiri, [string]$outLog, [string]$errLog, [int]$zamanAsimiDk) {
    # cmd /s /c: tirnakli exe yolu + tirnakli argumanlari guvenle tasir (PS 5.1 NativeCommandError tuzagina girmez)
    $cmdSatiri = '/s /c ""' + $claudeYol + '" ' + $argSatiri + '"'
    $p = Start-Process -FilePath "$env:ComSpec" -ArgumentList $cmdSatiri -WorkingDirectory $repoKok `
         -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
    $bitti = $p.WaitForExit($zamanAsimiDk * 60000)
    if (-not $bitti) {
        cmd /c ("taskkill /pid {0} /t /f >nul 2>&1" -f $p.Id)
        return -999
    }
    return $p.ExitCode
}

# --- on kontroller ---
if (Test-Path $durdurDosya) { Remove-Item -Force $durdurDosya; Yaz "Eski DURDUR bayragi temizlendi." }

cmd /c "docker info >nul 2>&1"
if ($LASTEXITCODE -ne 0) { Yaz "HATA: Docker calismiyor. Docker Desktop'i baslatip tekrar dene."; exit 1 }

$kirli = @(cmd /c "git status --porcelain 2>nul" | Where-Object { $_ -and ($_ -notmatch '\.claude[/\\]') })
if ($kirli.Count -gt 0) {
    if ($KirliAgacKabul) {
        Yaz ("UYARI: calisma agaci kirli ({0} dosya) - skill mevcut isi okuyup uzerine devam edecek." -f $kirli.Count)
    } else {
        Yaz "HATA: calisma agaci kirli. Ya commit/stash et ya da -KirliAgacKabul ile baslat:"
        $kirli | ForEach-Object { Yaz ("  " + $_) }
        exit 1
    }
}

Yaz "Backend konteyneri hazirlaniyor (backend pytest konteynerde kosar)..."
cmd /c "docker compose up -d >nul 2>&1"
$backendHazir = $false
for ($d = 1; $d -le 36; $d++) {
    cmd /c "docker compose exec -T backend python -c ""print(1)"" >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { $backendHazir = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $backendHazir) { Yaz "HATA: backend konteyneri 3 dakikada hazir olmadi."; exit 1 }
Yaz "Backend hazir."

$sunumModu = $false
cmd /c "presentationsettings /start >nul 2>&1"
if ($LASTEXITCODE -eq 0) { $sunumModu = $true; Yaz "Sunum modu acik (makine uyumaz)." }
else { Yaz "UYARI: sunum modu acilamadi - guc ayarlarindan uykuyu elle kapat." }

# --- claude arguman setleri ---
$ortakAraclar = '"Bash(docker compose:*)" "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git show:*)" "Bash(npm:*)" "Bash(npx:*)"'
$yasaklar = '--disallowedTools "Bash(git push:*)" "Bash(ssh:*)" "Bash(scp:*)" "Bash(gcloud:*)" "Bash(git reset:*)" "Bash(git checkout:*)" "Bash(git restore:*)"'
$devamArg = '-p "Oku ve harfiyen uygula: .claude/skills/faz-devam/SKILL.md" --permission-mode acceptEdits --allowedTools ' + $ortakAraclar + ' "Bash(git add:*)" "Bash(git commit:*)" ' + $yasaklar
$denetArg = '-p "Oku ve harfiyen uygula: .claude/skills/faz-denetle/SKILL.md" --allowedTools ' + $ortakAraclar

# --- ana dongu: paket -> denetim -> paket -> ... ---
$tamamlanan = 0
try {
    for ($i = 1; $i -le $MaxPaket; $i++) {
        if (Test-Path $durdurDosya) { Yaz "DURDUR bayragi bulundu - duruyorum."; break }

        $icerik = Get-Content -Path $takipDosya -Raw -Encoding UTF8
        if ($icerik -match "BLOCKED") { Yaz "Takip dosyasinda BLOCKED var - kullanici mudahalesi gerekli."; break }
        if ($icerik -notmatch '- \[ \]') { Yaz "Isaretsiz paket kalmadi - TUM PAKETLER TAMAM."; break }

        Yaz ("--- Paket turu {0}/{1} basliyor ---" -f $i, $MaxPaket)
        $pOut = Join-Path $logDir ("paket_{0}_{1}.out.log" -f $kosuId, $i)
        $pErr = Join-Path $logDir ("paket_{0}_{1}.err.log" -f $kosuId, $i)
        $kod = KosClaude $devamArg $pOut $pErr $PaketZamanAsimiDk
        if ($kod -eq -999) { Yaz ("ZAMAN ASIMI ({0} dk): paket oturumu olduruldu - sabah elle incele." -f $PaketZamanAsimiDk); break }
        if ($kod -ne 0) { Yaz ("HATA: claude cikis kodu {0} (kota/ag/oturum olabilir) - log: {1}" -f $kod, $pOut); break }

        $sonCommit = (cmd /c 'git log -1 --format="%h %s" 2>nul') -join " "
        Yaz ("Paket oturumu bitti. Son commit: " + $sonCommit)

        $pSonuc = ""
        if (Test-Path $pOut) { $pSonuc = (Get-Content $pOut -Tail 30) -join "`n" }
        if ($pSonuc -match "FAZ 6 GECE KAPSAMI DISI") { Yaz "FAZ 6'ya gelindi - gozetimsiz kapsam disi, duruyorum."; break }
        if ($pSonuc -match "TUM PAKETLER TAMAM") { Yaz "Tum paketler tamam."; break }
        if ($pSonuc -match "BLOCKED") { Yaz "Paket BLOCKED birakti - duruyorum."; break }

        Yaz "Denetim oturumu (temiz context) basliyor..."
        $dOut = Join-Path $logDir ("denetim_{0}_{1}.out.log" -f $kosuId, $i)
        $dErr = Join-Path $logDir ("denetim_{0}_{1}.err.log" -f $kosuId, $i)
        $dKod = KosClaude $denetArg $dOut $dErr $DenetimZamanAsimiDk
        if ($dKod -ne 0) { Yaz ("UYARI: denetim oturumu hatali bitti ({0}) - sabah elle incele: {1}" -f $dKod, $dOut); break }

        $dSon = ""
        if (Test-Path $dOut) { $dSon = (Get-Content $dOut -Tail 10) -join "`n" }
        if ($dSon -match "SONUC: RET") {
            Yaz "DENETIM RET VERDI - duruyorum. Commit geri ALINMADI; karar sabaha."
            Yaz ("Denetim raporu: " + $dOut)
            break
        }
        if ($dSon -notmatch "SONUC: GECTI") { Yaz ("UYARI: denetim net sonuc vermedi - sabah incele: " + $dOut); break }
        Yaz "Denetim GECTI."
        $tamamlanan++
    }
}
finally {
    if ($sunumModu) { cmd /c "presentationsettings /stop >nul 2>&1" }
}

Yaz ("=== KOSU BITTI: bu gece {0} paket tamamlandi ===" -f $tamamlanan)
Yaz "Sabah: git log + takip dosyasindaki durum notlari + otomasyon/loglar/denetim_*.log incele."
Yaz "Push + CI takibi + deploy karari sende (deploy icin Claude Code oturumunda 'basla' demen yeterli)."
