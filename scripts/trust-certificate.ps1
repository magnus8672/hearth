param(
    [Parameter(Mandatory=$true)][ValidateSet('Status','Trust')][string]$Action,
    [Parameter(Mandatory=$true)][string]$CertificatePath
)
$ErrorActionPreference = 'Stop'
$hearthCert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2((Resolve-Path -LiteralPath $CertificatePath).Path)
$hearthStorePath = 'Cert:\CurrentUser\Root\' + $hearthCert.Thumbprint
if ($Action -eq 'Trust' -and -not (Test-Path -LiteralPath $hearthStorePath)) {
    Import-Certificate -FilePath $CertificatePath -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null
}
@{ trusted = (Test-Path -LiteralPath $hearthStorePath) } | ConvertTo-Json -Compress
