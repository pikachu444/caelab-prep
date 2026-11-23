param(
    [switch]$InstallOnly,
    [switch]$DryRun,
    [switch]$CreateShortcut,
    [switch]$ForceReinstall,
    [switch]$Console
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$pythonw = Join-Path $venv 'Scripts\pythonw.exe'
$stamp = Join-Path $venv '.caelab_prep_env.sha256'
$batch = Join-Path $root 'CAELab_Prep_Install_And_Run.bat'

if ($DryRun) {
    Write-Host "Dry run: CAELab Prep environment at $venv"
    if ($ForceReinstall) {
        Write-Host 'Would reinstall .[gui,cad].'
    } else {
        Write-Host 'Would reuse a healthy, current environment or install .[gui,cad].'
    }
    if ($CreateShortcut) { Write-Host 'Would create CAELab Prep.lnk on the Desktop.' }
    if (-not $InstallOnly) { Write-Host 'Would start CAELab Prep.' }
    return
}

function Find-PathApplication($name) {
    Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue |
        Where-Object { $_.Source -notlike '*\WindowsApps\*' } |
        Select-Object -First 1 -ExpandProperty Source
}

function Test-Application($executable, $arguments) {
    try {
        & $executable @arguments *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-Python {
    $probe = 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 13)'
    $py = Find-PathApplication 'py.exe'
    if ($py) {
        foreach ($version in '-3.13', '-3.12', '-3.11') {
            if (Test-Application $py @($version, '-I', '-B', '-c', $probe)) { return $py, $version }
        }
    }
    $systemPython = Find-PathApplication 'python.exe'
    if ($systemPython -and (Test-Application $systemPython @('-I', '-B', '-c', $probe))) {
        return $systemPython
    }
}

function Test-Environment {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { return $false }
    $imports = 'import sys; assert sys.prefix != sys.base_prefix; import PySide6, vtk, gmsh, caelab_prep'
    if (-not $uv) { $imports += ', pip' }
    Test-Application $python @('-I', '-B', '-c', $imports)
}

try {
    # Use the current PowerShell installation's cmdlets when launched from another PowerShell version.
    Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility')
    $pathBytes = [Text.Encoding]::UTF8.GetBytes($root.ToUpperInvariant())
    $pathHash = (Get-FileHash -InputStream ([IO.MemoryStream]::new($pathBytes))).Hash
    $mutex = [Threading.Mutex]::new($false, "Local\CAELabPrep-$pathHash")
    try { $null = $mutex.WaitOne() }
    catch [Threading.AbandonedMutexException] { }

    Push-Location -LiteralPath $root
    try {
        $uv = Find-PathApplication 'uv.exe'
        if (-not $uv -and $env:USERPROFILE) {
            $candidate = Join-Path $env:USERPROFILE '.local\bin\uv.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $uv = $candidate }
        }
        if (-not $uv -and $env:LOCALAPPDATA) {
            $candidate = Join-Path $env:LOCALAPPDATA 'hermes\bin\uv.exe'
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $uv = $candidate }
        }

        $existing = Get-Item -LiteralPath $venv -Force -ErrorAction SilentlyContinue
        if ($existing -and ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "The environment path must be inside this checkout: $venv"
        }
        $hash = (Get-FileHash -LiteralPath (Join-Path $root 'pyproject.toml') -Algorithm SHA256).Hash
        $healthy = Test-Environment
        $current = $healthy -and (Test-Path -LiteralPath $stamp -PathType Leaf) -and
            (([string](Get-Content -LiteralPath $stamp -Raw)).Trim() -eq $hash)

        if ($ForceReinstall -or -not $current) {
            if ($uv -and -not (Test-Application $uv @('--version'))) {
                $uv = $null
                $healthy = Test-Environment
            }
            if (-not $healthy) {
                if (-not $uv) {
                    $basePython = @(Find-Python)
                    if (-not $basePython.Count) {
                        throw 'Python 3.11~3.13 또는 uv가 필요합니다. Python 설치: https://www.python.org/downloads/'
                    }
                }
                if ($existing) {
                    if ($existing.FullName -ne $venv) { throw "Unexpected environment path: $($existing.FullName)" }
                    Remove-Item -LiteralPath $existing.FullName -Recurse -Force
                }
                if ($uv) {
                    & $uv venv --seed --python '>=3.11,<3.14' $venv
                } else {
                    $launcherArgs = @($basePython | Select-Object -Skip 1)
                    & $basePython[0] @launcherArgs -I -m venv $venv
                }
                if ($LASTEXITCODE -ne 0) { throw 'CAELab Prep 가상환경을 만들 수 없습니다.' }
            }

            if (Test-Path -LiteralPath $stamp) { Remove-Item -LiteralPath $stamp -Force }
            if ($uv) {
                $options = @(if ($ForceReinstall) { '--reinstall' })
                & $uv pip install --python $python @options -e '.[gui,cad]'
            } else {
                $options = @(if ($ForceReinstall) { '--force-reinstall' })
                & $python -I -m pip install @options -e '.[gui,cad]'
            }
            if ($LASTEXITCODE -ne 0 -or -not (Test-Environment)) {
                throw 'CAELab Prep 의존성을 설치하거나 불러올 수 없습니다.'
            }
            Set-Content -LiteralPath $stamp -Value $hash -Encoding ASCII
        }

        if ($CreateShortcut) {
            $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory)
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut((Join-Path $desktop 'CAELab Prep.lnk'))
            $shortcut.TargetPath = $batch
            $shortcut.WorkingDirectory = $root
            $shortcut.Save()
        }

        if (-not $InstallOnly) {
            $windowStyle = if ($Console) { 'Normal' } else { 'Hidden' }
            $launchPython = if (-not $Console -and (Test-Path -LiteralPath $pythonw -PathType Leaf)) { $pythonw } else { $python }
            Start-Process -FilePath $launchPython -ArgumentList '-m', 'caelab_prep', 'gui' -WorkingDirectory $root -WindowStyle $windowStyle
        }
    } finally {
        Pop-Location
        $mutex.ReleaseMutex()
        $mutex.Dispose()
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
