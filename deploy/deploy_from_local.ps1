# Deploy backend Bujito vers le VPS (secours local).
# Usage :
#   .\deploy\deploy_from_local.ps1
#   .\deploy\deploy_from_local.ps1 -SshKey "$env:USERPROFILE\.ssh\bujito_deploy"
#
# Prérequis : clé SSH (ed25519) autorisée pour root@VPS.

[CmdletBinding()]
param(
    [string]$SshHost = "vps120167.serveur-vps.net",
    [string]$SshUser = "root",
    [string]$SshKey = "$env:USERPROFILE\.ssh\bujito_deploy",
    [string]$DeployPath = "/home/paisible/web/apibudig.capslockdev.com/public_html",
    [string]$SystemdService = "bujito_backend",
    [string]$HealthUrl = "https://apibudig.capslockdev.com/api/"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SshKey)) {
    Write-Error @"
Clé SSH introuvable : $SshKey

Crée-en une :
  ssh-keygen -t ed25519 -f `$env:USERPROFILE\.ssh\bujito_deploy -N ""
Puis ajoute la .pub dans /root/.ssh/authorized_keys sur le VPS.
"@
}

Write-Host "[deploy] SSH $SshUser@$SshHost"
Write-Host "[deploy] path  $DeployPath"
Write-Host "[deploy] svc   $SystemdService"

# Script bash exécuté sur le VPS (chemins injectés littéralement).
$remoteScript = @"
set -euo pipefail
echo "[deploy] pull + migrate (paisible)"
su - paisible -c "cd '$DeployPath' && git fetch origin && git checkout main && git reset --hard origin/main && SYSTEMD_SERVICE='$SystemdService' bash deploy/remote_update.sh --already-pulled"
echo "[deploy] restart $SystemdService (root)"
systemctl restart '$SystemdService'
systemctl is-active --quiet '$SystemdService'
systemctl --no-pager --full status '$SystemdService' | head -n 15
echo "[deploy] OK"
"@

ssh -i $SshKey -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new `
    "${SshUser}@${SshHost}" $remoteScript

Write-Host "[deploy] health check $HealthUrl"
$code = 0
try {
    $response = Invoke-WebRequest -Uri $HealthUrl -Method GET -TimeoutSec 30 -UseBasicParsing
    $code = [int]$response.StatusCode
} catch {
    $resp = $_.Exception.Response
    if ($null -ne $resp -and $null -ne $resp.StatusCode) {
        $code = [int]$resp.StatusCode.value__
        if ($code -eq 0) { $code = [int]$resp.StatusCode }
    } else {
        throw
    }
}

Write-Host "[deploy] HTTP $code"
if ($code -ge 500 -or $code -eq 0) {
    Write-Error "Health check failed (HTTP $code)"
}

Write-Host "[deploy] done"
