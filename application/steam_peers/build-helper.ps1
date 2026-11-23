$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Le compilateur .NET Framework x64 est introuvable.' }
$peerDir = $PSScriptRoot
$sources = @((Join-Path $peerDir 'TrackerSteamPeers.cs'), (Join-Path $peerDir 'ETWPingMonitor.cs'),
    (Join-Path $peerDir 'SteamLogTail.cs'), (Join-Path $peerDir 'SteamAvatarRequests.cs'))
$references = @('Steamworks.NET.dll', 'Microsoft.Diagnostics.Tracing.TraceEvent.dll',
    'Microsoft.Diagnostics.FastSerialization.dll', 'OSExtensions.dll') | ForEach-Object { '/reference:' + (Join-Path $peerDir $_) }
$arguments = @('/nologo', '/target:exe', '/platform:x64', '/optimize+',
    ('/out:' + (Join-Path $peerDir 'TrackerSteamPeersV8.exe')), '/reference:System.Web.Extensions.dll',
    '/reference:System.Drawing.dll') + $references + $sources
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw "La compilation du lecteur Steam a échoué ($LASTEXITCODE)." }
