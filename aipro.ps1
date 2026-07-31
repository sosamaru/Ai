[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AiProArguments
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$launchers = @(
    @{ Command = "py"; Prefix = @("-3.13") },
    @{ Command = "py"; Prefix = @("-3.12") },
    @{ Command = "py"; Prefix = @("-3.11") },
    @{ Command = "python"; Prefix = @() }
)

foreach ($launcher in $launchers) {
    $command = Get-Command $launcher.Command -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        continue
    }

    [string[]]$prefix = $launcher.Prefix
    & $launcher.Command @prefix -c "import sys" 2>$null
    if ($LASTEXITCODE -ne 0) {
        continue
    }

    & $launcher.Command @prefix -m aipro @AiProArguments
    exit $LASTEXITCODE
}

Write-Host "[FAIL] Python 3.11, 3.12, or 3.13 was not found." -ForegroundColor Red
Write-Host "Install a supported version and enable the Python launcher or PATH option."
exit 1
