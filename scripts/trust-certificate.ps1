param(
    [Parameter(Mandatory=$true)][ValidateSet('Status','Trust')][string]$Action,
    [Parameter(Mandatory=$true)][string]$CertificatePath
)
$ErrorActionPreference = 'Stop'
$hearthCert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new((Resolve-Path -LiteralPath $CertificatePath).Path)
# The Cert: PowerShell provider is not always initialized in Python-launched
# Windows PowerShell. Query the Windows store directly instead of treating a
# missing provider as an absent certificate.
$hearthStore = [System.Security.Cryptography.X509Certificates.X509Store]::new('Root', 'CurrentUser')
try {
    $hearthFlags = if ($Action -eq 'Trust') { 'ReadWrite' } else { 'ReadOnly' }
    $hearthStore.Open($hearthFlags)
    $hearthMatches = $hearthStore.Certificates.Find('FindByThumbprint', $hearthCert.Thumbprint, $false)
    if ($Action -eq 'Trust' -and $hearthMatches.Count -eq 0) {
        $hearthStore.Add($hearthCert)
        $hearthMatches = $hearthStore.Certificates.Find('FindByThumbprint', $hearthCert.Thumbprint, $false)
    }
    @{ trusted = ($hearthMatches.Count -gt 0) } | ConvertTo-Json -Compress
} finally {
    $hearthStore.Close()
    $hearthCert.Dispose()
}
