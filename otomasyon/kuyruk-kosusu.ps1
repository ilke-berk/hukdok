<#
 kuyruk-kosusu.ps1 - gorevler/KUYRUK.md'deki isleri SERIT bazli paralel yurutur.

 Seritler (ayni anda serit basina EN FAZLA bir gorev):
   backend  -> ANA dizinde kosar (konteyner ./backend'i bind-mount eder; pytest yalniz
               ana dizindeki kodu dogru test eder - bu yuzden backend seridir, seri'dir)
   frontend -> C:\dev altinda ayri git worktree'de kosar (vitest host'ta, kendi node_modules)
   docs     -> ayri worktree'de kosar, test yok

 Dongu: hazir gorevleri bos seritlere dagit -> biten isciyi AYRI temiz context'le denetle ->
 GECTI ise worktree dallarini ana dala TEK TEK birlestir (birlesme sonrasi ana dizinde tam
 vitest; kirmizi ise merge geri alinir) -> KUYRUK.md'de isaretle -> sirada ne varsa devam.

 Kullanim (repo kokunden):
   powershell -ExecutionPolicy Bypass -File otomasyon\kuyruk-kosusu.ps1
   powershell -ExecutionPolicy Bypass -File otomasyon\kuyruk-kosusu.ps1 -MaxGorev 4 -MaxSaat 6

 Durdurmak: otomasyon\DURDUR dosyasi olustur (yeni gorev baslatmaz, calisanlari bitirir).
 Bu script ASLA push/ssh/deploy yapmaz. Sabah inceleme + push + deploy kullanicidadir.
 NOT: Dosya bilerek ASCII (PS 5.1 BOM'suz UTF-8'i ANSI okur).
#>
param(
    [int]$MaxGorev = 8,
    [double]$MaxSaat = 8.0,
    [int]$GorevZamanAsimiDk = 180,
    [int]$DenetimZamanAsimiDk = 45,
    [string]$WorktreeKok = "C:\dev\hukudok-wt",
    [switch]$KirliAgacKabul
)

$ErrorActionPreference = "Stop"
$otomasyonDir = $PSScriptRoot
$repoKok = Split-Path -Parent $otomasyonDir
Set-Location $repoKok

$kuyrukDosya = Join-Path $repoKok "gorevler\KUYRUK.md"
$logDir = Join-Path $otomasyonDir "loglar"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$kosuId = Get-Date -Format "yyyyMMdd-HHmmss"
$anaLog = Join-Path $logDir ("kuyruk_{0}.log" -f $kosuId)
$durdurDosya = Join-Path $otomasyonDir "DURDUR"
$bitisZamani = (Get-Date).AddHours($MaxSaat)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Yaz([string]$mesaj) {
    $satir = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $mesaj
    Write-Host $satir
    # OneDrive/tail kaynakli gecici dosya kilidi loglamayi OLDUREMEZ (2026-08-11
    # gecesi Add-Content IOException'i EAP=Stop ile tum kosucuyu devirdi).
    for ($y = 1; $y -le 3; $y++) {
        try { Add-Content -Path $anaLog -Value $satir -Encoding UTF8 -ErrorAction Stop; break }
        catch { Start-Sleep -Milliseconds 300 }
    }
}

# Kuyruk dosyasi OneDrive altinda - gecici paylasim kilitlerine karsi tekrar dene.
function DosyaDene([scriptblock]$islem) {
    for ($d = 1; $d -le 5; $d++) {
        try { return (& $islem) } catch { if ($d -eq 5) { throw }; Start-Sleep -Milliseconds 400 }
    }
}

# --- claude CLI ---
$claudeYol = $null
try { $claudeYol = (Get-Command claude -ErrorAction Stop).Source } catch {}
if ($null -eq $claudeYol) { Yaz "HATA: claude CLI PATH'te yok."; exit 1 }
if ($claudeYol.ToLower().EndsWith(".ps1")) {
    $aday = $claudeYol.Substring(0, $claudeYol.Length - 4) + ".cmd"
    if (Test-Path $aday) { $claudeYol = $aday }
}

function BaslatClaude([string]$argSatiri, [string]$outLog, [string]$errLog, [string]$dizin) {
    $cmdSatiri = '/s /c ""' + $claudeYol + '" ' + $argSatiri + '"'
    return Start-Process -FilePath "$env:ComSpec" -ArgumentList $cmdSatiri -WorkingDirectory $dizin `
           -NoNewWindow -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
}

function OldurAgac([int]$islemNo) { cmd /c ("taskkill /pid {0} /t /f >nul 2>&1" -f $islemNo) }

# --- kuyruk okuma/yazma ---
function KuyrukOku {
    $liste = @()
    $tumSatirlar = DosyaDene { [System.IO.File]::ReadAllLines($kuyrukDosya, [System.Text.Encoding]::UTF8) }
    foreach ($s in $tumSatirlar) {
        if ($s -match '^- \[( |x)\] (G\d+) \| bant:(backend|frontend|docs) \| bagimli:([^ |]+) \|') {
            $liste += [pscustomobject]@{
                Bitti   = ($Matches[1] -eq 'x')
                Id      = $Matches[2]
                Bant    = $Matches[3]
                Bagimli = @($Matches[4].Split(',') | Where-Object { $_ -and $_ -ne '-' })
                Bloke   = ($s -match 'BLOKE')
            }
        }
    }
    return ,$liste
}

function KuyrukIsaretle([string]$id) {
    $satirlar = DosyaDene { [System.IO.File]::ReadAllLines($kuyrukDosya, [System.Text.Encoding]::UTF8) }
    for ($j = 0; $j -lt $satirlar.Count; $j++) {
        if ($satirlar[$j] -match ('^- \[ \] ' + $id + ' \|')) {
            $satirlar[$j] = $satirlar[$j] -replace '^- \[ \]', '- [x]'
            break
        }
    }
    DosyaDene { [System.IO.File]::WriteAllLines($kuyrukDosya, $satirlar, $utf8NoBom) } | Out-Null
    # KUYRUK degisikligi COMMIT'lenmeli: kirli kalirsa AnaTemizMi sonraki backend
    # gorevlerini ve merge'leri sonsuza dek bloklar (2026-08-11 gecesi tespit).
    cmd /c "git add gorevler/KUYRUK.md >nul 2>&1"
    cmd /c ("git commit -m ""chore: kuyruk durumu - {0} tamam"" >nul 2>&1" -f $id)
    Yaz ("TAMAMLANDI: " + $id)
}

function KuyrukBloke([string]$id, [string]$sebep) {
    $satirlar = DosyaDene { [System.IO.File]::ReadAllLines($kuyrukDosya, [System.Text.Encoding]::UTF8) }
    for ($j = 0; $j -lt $satirlar.Count; $j++) {
        if (($satirlar[$j] -match ('^- \[ \] ' + $id + ' \|')) -and ($satirlar[$j] -notmatch 'BLOKE')) {
            $satirlar[$j] = $satirlar[$j] + ' | BLOKE(' + $sebep + ')'
            break
        }
    }
    DosyaDene { [System.IO.File]::WriteAllLines($kuyrukDosya, $satirlar, $utf8NoBom) } | Out-Null
    cmd /c "git add gorevler/KUYRUK.md >nul 2>&1"
    cmd /c ("git commit -m ""chore: kuyruk durumu - {0} BLOKE"" >nul 2>&1" -f $id)
    Yaz ("BLOKE: {0} - {1}" -f $id, $sebep)
}

function Hazir($g, $tum) {
    if ($g.Bitti -or $g.Bloke) { return $false }
    foreach ($b in $g.Bagimli) {
        $dep = $tum | Where-Object { $_.Id -eq $b } | Select-Object -First 1
        if ($null -eq $dep) { return $false }
        if (-not $dep.Bitti) { return $false }
    }
    return $true
}

function AnaTemizMi {
    $kirli = @(cmd /c "git status --porcelain 2>nul" | Where-Object { $_ -and ($_ -notmatch '\.claude[/\\]') })
    return ($kirli.Count -eq 0)
}

# --- claude arguman setleri ---
$ortakAraclar  = '"Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git show:*)" "Bash(npm:*)" "Bash(npx:*)"'
$yasakOrtak    = '"Bash(git push:*)" "Bash(ssh:*)" "Bash(scp:*)" "Bash(gcloud:*)" "Bash(git reset:*)" "Bash(git checkout:*)" "Bash(git restore:*)" "Bash(git merge:*)" "Bash(git worktree:*)"'
$izinBackend   = $ortakAraclar + ' "Bash(docker compose:*)" "Bash(git add:*)" "Bash(git commit:*)"'
$izinWorktree  = $ortakAraclar + ' "Bash(git add:*)" "Bash(git commit:*)"'
$yasakBackend  = $yasakOrtak
$yasakWorktree = $yasakOrtak + ' "Bash(docker:*)"'
$denetBackend  = $ortakAraclar + ' "Bash(docker compose:*)"'
$denetWorktree = $ortakAraclar

# --- serit durumu ---
$seritler = @{ backend = $null; frontend = $null; docs = $null }
$birlesmeBekleyen = New-Object System.Collections.ArrayList
$baslatilan = 0
$bitirilen = 0

function GorevBaslat($gorev) {
    $id = $gorev.Id
    $dizin = $repoKok
    $dal = ""
    if ($gorev.Bant -eq 'backend') {
        if (-not (AnaTemizMi)) { return $false }   # ana dizin kirliyken backend gorevi baslatma
    } else {
        $dal = "gorev/" + $id
        $wt = Join-Path $WorktreeKok $id
        if (Test-Path $wt) { KuyrukBloke $id "eski worktree duruyor - elle incele"; return $false }
        cmd /c ('git worktree add -b "' + $dal + '" "' + $wt + '" HEAD >nul 2>&1')
        if ($LASTEXITCODE -ne 0) { KuyrukBloke $id "worktree/dal olusturulamadi (dal artigi olabilir)"; return $false }
        $dizin = $wt
        if ($gorev.Bant -eq 'frontend') {
            Yaz ("{0}: worktree kuruldu, npm ci kosuyor (birkac dakika)..." -f $id)
            cmd /c ('npm --prefix "' + (Join-Path $wt 'frontend') + '" ci >nul 2>&1')
            if ($LASTEXITCODE -ne 0) {
                cmd /c ('git worktree remove --force "' + $wt + '" >nul 2>&1')
                cmd /c ('git branch -D "' + $dal + '" >nul 2>&1')
                KuyrukBloke $id "npm ci basarisiz"
                return $false
            }
        }
    }
    $out = Join-Path $logDir ("gorev_{0}_{1}.out.log" -f $kosuId, $id)
    $err = Join-Path $logDir ("gorev_{0}_{1}.err.log" -f $kosuId, $id)
    if ($gorev.Bant -eq 'backend') { $izin = $izinBackend; $yasak = $yasakBackend }
    else { $izin = $izinWorktree; $yasak = $yasakWorktree }
    $arg = '-p "Oku ve harfiyen uygula: .claude/skills/gorev-devam/SKILL.md GOREV: ' + $id + '" --permission-mode acceptEdits --allowedTools ' + $izin + ' --disallowedTools ' + $yasak
    $proc = BaslatClaude $arg $out $err $dizin
    $seritler[$gorev.Bant] = @{ Gorev = $gorev; Proc = $proc; Dizin = $dizin; Dal = $dal; Out = $out; Baslangic = (Get-Date) }
    $script:baslatilan++
    Yaz ("BASLADI: {0} ({1}) dizin: {2}" -f $id, $gorev.Bant, $dizin)
    return $true
}

function SeritIsle([string]$bant) {
    $s = $seritler[$bant]
    if ($null -eq $s) { return }
    $id = $s.Gorev.Id
    if (-not $s.Proc.HasExited) {
        if (((Get-Date) - $s.Baslangic).TotalMinutes -gt $GorevZamanAsimiDk) {
            OldurAgac $s.Proc.Id
            $seritler[$bant] = $null
            KuyrukBloke $id ("zaman asimi " + $GorevZamanAsimiDk + " dk")
        }
        return
    }
    $cikis = $s.Proc.ExitCode
    $seritler[$bant] = $null
    if ($cikis -ne 0) { KuyrukBloke $id ("claude cikis kodu " + $cikis + " - kota/ag olabilir"); return }
    $son = ""
    if (Test-Path $s.Out) { $son = (Get-Content $s.Out -Tail 30) -join "`n" }
    if ($son -match "BLOKE") { KuyrukBloke $id "isci BLOKE birakti - gorev dosyasindaki DURUM satirina bak"; return }

    Yaz ("ISCI BITTI: {0} - denetim (temiz context) basliyor..." -f $id)
    $dOut = Join-Path $logDir ("denetim_{0}_{1}.out.log" -f $kosuId, $id)
    $dErr = Join-Path $logDir ("denetim_{0}_{1}.err.log" -f $kosuId, $id)
    if ($bant -eq 'backend') { $dIzin = $denetBackend } else { $dIzin = $denetWorktree }
    $dArg = '-p "Oku ve harfiyen uygula: .claude/skills/gorev-denetle/SKILL.md GOREV: ' + $id + '" --allowedTools ' + $dIzin
    $dp = BaslatClaude $dArg $dOut $dErr $s.Dizin
    $dBitti = $dp.WaitForExit($DenetimZamanAsimiDk * 60000)
    if (-not $dBitti) { OldurAgac $dp.Id; KuyrukBloke $id "denetim zaman asimi"; return }
    $dSon = ""
    if (Test-Path $dOut) { $dSon = (Get-Content $dOut -Tail 10) -join "`n" }
    if ($dSon -match "SONUC: RET") { KuyrukBloke $id ("denetim RET - rapor: " + $dOut); return }
    if ($dSon -notmatch "SONUC: GECTI") { KuyrukBloke $id "denetim net sonuc vermedi"; return }
    Yaz ("DENETIM GECTI: " + $id)

    if ($bant -eq 'backend') {
        KuyrukIsaretle $id
        $script:bitirilen++
    } else {
        [void]$birlesmeBekleyen.Add(@{ Id = $id; Dal = $s.Dal; Wt = $s.Dizin; Bant = $bant })
        Yaz ("{0} birlesme kuyrugunda (ana dizin bosalinca birlesecek)." -f $id)
    }
}

function BirlesmeleriDene {
    if ($birlesmeBekleyen.Count -eq 0) { return }
    if ($null -ne $seritler['backend']) { return }   # ana dizinde isci calisiyor
    if (-not (AnaTemizMi)) { return }                # ana dizin kirli (yarim is) - birlesme riskli
    $islenecek = @($birlesmeBekleyen.ToArray())
    $birlesmeBekleyen.Clear()
    foreach ($b in $islenecek) {
        $once = (cmd /c "git rev-parse HEAD 2>nul") | Select-Object -First 1
        cmd /c ('git merge --no-ff --no-edit "' + $b.Dal + '" >nul 2>&1')
        if ($LASTEXITCODE -ne 0) {
            cmd /c "git merge --abort >nul 2>&1"
            KuyrukBloke $b.Id "merge cakismasi - worktree ve dal korundu, sabah birlestir"
            continue
        }
        if ($b.Bant -eq 'frontend') {
            Yaz ("{0}: birlesme sonrasi tam vitest (ana dizinde)..." -f $b.Id)
            cmd /c ('npm --prefix "' + (Join-Path $repoKok 'frontend') + '" test >nul 2>&1')
            if ($LASTEXITCODE -ne 0) {
                cmd /c ('git reset --hard ' + $once + ' >nul 2>&1')
                KuyrukBloke $b.Id "entegrasyon testi kirmizi - merge geri alindi, worktree korundu"
                continue
            }
        }
        KuyrukIsaretle $b.Id
        $script:bitirilen++
        cmd /c ('git worktree remove "' + $b.Wt + '" >nul 2>&1')
        cmd /c ('git branch -d "' + $b.Dal + '" >nul 2>&1')
        Yaz ("BIRLESTI: {0} (dal ve worktree temizlendi)" -f $b.Id)
    }
}

# --- on kontroller ---
if (Test-Path $durdurDosya) { Remove-Item -Force $durdurDosya; Yaz "Eski DURDUR bayragi temizlendi." }
if (-not (Test-Path $kuyrukDosya)) { Yaz "HATA: gorevler\KUYRUK.md yok."; exit 1 }
$kuyruk = KuyrukOku
$acikSayi = @($kuyruk | Where-Object { -not $_.Bitti -and -not $_.Bloke }).Count
if ($acikSayi -eq 0) { Yaz "Kuyrukta acik gorev yok."; exit 0 }
Yaz ("Kuyrukta {0} acik gorev var." -f $acikSayi)

$backendGorevVar = @($kuyruk | Where-Object { -not $_.Bitti -and -not $_.Bloke -and $_.Bant -eq 'backend' }).Count -gt 0
if ($backendGorevVar) {
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -ne 0) { Yaz "HATA: Docker calismiyor (backend gorevleri icin sart)."; exit 1 }
    cmd /c "docker compose up -d >nul 2>&1"
    $hazirMi = $false
    for ($d = 1; $d -le 36; $d++) {
        cmd /c "docker compose exec -T backend python -c ""print(1)"" >nul 2>&1"
        if ($LASTEXITCODE -eq 0) { $hazirMi = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $hazirMi) { Yaz "HATA: backend konteyneri hazir olmadi."; exit 1 }
    Yaz "Backend konteyneri hazir."
}

New-Item -ItemType Directory -Force -Path $WorktreeKok | Out-Null

if (-not (AnaTemizMi)) {
    if ($KirliAgacKabul) {
        Yaz "UYARI: ana dizin kirli - backend gorevleri ve birlesmeler ana dizin temizlenene dek BEKLER; worktree gorevleri kosar."
    } else {
        Yaz "HATA: ana dizin kirli. Commit/stash et ya da -KirliAgacKabul ile baslat."
        exit 1
    }
}

# PresentationSettings.exe /start, mod acik kaldigi surece CALISIR DURUMDA KALIR
# (cmd /c ile cagirmak sonsuza dek bloklar - 2026-08-11 gecesi canli yasandi).
# Start-Process ile beklemeden baslatilir, finally'de oldurulunce mod kapanir.
$sunumProc = $null
try {
    $sunumProc = Start-Process -FilePath "presentationsettings" -ArgumentList "/start" -PassThru -WindowStyle Hidden
    Yaz "Sunum modu acik (makine uyumaz)."
} catch { Yaz "UYARI: sunum modu acilamadi - uykuyu elle kapat." }

# --- ana dongu ---
$bosTur = 0
try {
    while ($true) {
        $dur = Test-Path $durdurDosya
        $sureDoldu = (Get-Date) -gt $bitisZamani
        $kuyruk = KuyrukOku

        BirlesmeleriDene

        $birSeyBasladi = $false
        if (-not $dur -and -not $sureDoldu -and $baslatilan -lt $MaxGorev) {
            foreach ($bant in @('backend', 'frontend', 'docs')) {
                if ($null -ne $seritler[$bant]) { continue }
                if ($baslatilan -ge $MaxGorev) { break }
                $aday = $kuyruk | Where-Object { $_.Bant -eq $bant -and (Hazir $_ $kuyruk) } | Select-Object -First 1
                if ($null -ne $aday) {
                    if (GorevBaslat $aday) { $birSeyBasladi = $true }
                    $kuyruk = KuyrukOku   # BLOKE isaretlenmis olabilir
                }
            }
        }

        foreach ($bant in @('backend', 'frontend', 'docs')) { SeritIsle $bant }
        BirlesmeleriDene

        $aktif = @($seritler.Values | Where-Object { $null -ne $_ }).Count
        if ($aktif -eq 0 -and -not $birSeyBasladi) {
            $kuyruk = KuyrukOku
            $hazirVar = $false
            foreach ($g in $kuyruk) { if (Hazir $g $kuyruk) { $hazirVar = $true; break } }
            if ($dur) { Yaz "DURDUR bayragi - duruyorum."; break }
            if ($sureDoldu) { Yaz "MaxSaat doldu - duruyorum."; break }
            if ($baslatilan -ge $MaxGorev) { Yaz "MaxGorev tavanina ulasildi - duruyorum."; break }
            if (-not $hazirVar) {
                if ($birlesmeBekleyen.Count -gt 0) { Yaz "UYARI: birlesme bekleyen dallar kaldi (ana dizin uygun degil) - sabah elle birlestir." }
                Yaz "Baslatilabilir gorev kalmadi - duruyorum."
                break
            }
            $bosTur++
            if ($bosTur -ge 3) { Yaz "Ilerleme yok (hazir gorev var ama baslatilamiyor; ana dizin kirli olabilir) - duruyorum."; break }
        } else {
            $bosTur = 0
        }

        Start-Sleep -Seconds 20
    }
}
finally {
    if ($null -ne $sunumProc) { try { Stop-Process -Id $sunumProc.Id -Force -ErrorAction Stop } catch {} }
}

Yaz ("=== KOSU BITTI: {0} gorev baslatildi, {1} gorev tamamlandi ===" -f $baslatilan, $bitirilen)
Yaz "Sabah: gorevler\KUYRUK.md (BLOKE satirlari!), git log, otomasyon\loglar\denetim_*.log incele."
Yaz "BLOKE cozunce satirdaki ' | BLOKE(...)' ekini sil; birlesmemis dallar icin worktree'ler C:\dev\hukudok-wt altinda korunur."
Yaz "Push + CI + deploy karari sende."
