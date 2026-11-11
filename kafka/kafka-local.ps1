param(
    [ValidateSet('Start', 'Verify', 'Smoke', 'Stop', 'Status', 'Logs', 'Config')]
    [string]$Action = 'Status',
    [string]$DockerPath
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $DockerPath) {
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) { $DockerPath = $command.Source }
    else {
        $candidates = @(
            "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe",
            "$env:ProgramFiles\Docker\Docker\resources\bin\docker.exe"
        )
        $DockerPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
}
if (-not $DockerPath -or -not (Test-Path -LiteralPath $DockerPath)) {
    throw 'Docker not found. Pass -DockerPath with the full path to docker.exe.'
}
# Process-local PATH also lets Docker find its credential helper; no settings are read.
$env:PATH = "$(Split-Path -Parent $DockerPath);$env:PATH"
$composeArgs = @('compose', '--project-directory', $repo, '--env-file',
    (Join-Path $PSScriptRoot 'compose.empty.env'), '-f', (Join-Path $repo 'compose.kafka.yml'))

function Invoke-Compose {
    & $DockerPath @composeArgs @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $args (exit $LASTEXITCODE)" }
}

function Assert-Resources {
    $infoText = & $DockerPath info --format '{{json .}}'
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop Linux engine is unavailable.' }
    $info = $infoText | ConvertFrom-Json
    if ($info.OSType -ne 'linux' -or $info.MemTotal -lt 5GB) {
        throw 'This cluster requires a Linux engine with at least 5 GiB available to Docker.'
    }
    $running = @(Invoke-Compose ps --status running --quiet)
    $os = Get-CimInstance Win32_OperatingSystem
    $free = [double]$os.FreePhysicalMemory * 1KB
    Write-Host ('Windows free RAM: {0:N2} GiB; Docker memory: {1:N2} GiB' -f ($free / 1GB), ($info.MemTotal / 1GB))
    if ($running.Count -eq 0 -and $free -lt 3GB) {
        throw 'Less than 3 GiB free RAM before cold start. Free resources manually; nothing was stopped or deleted.'
    }
    foreach ($root in @([IO.Path]::GetPathRoot($repo), "$env:SystemDrive\") | Select-Object -Unique) {
        $drive = [IO.DriveInfo]::new($root)
        Write-Host ('Disk {0}: {1:N2} GiB free' -f $root, ($drive.AvailableFreeSpace / 1GB))
        if ($drive.AvailableFreeSpace -lt 3GB) { throw "Insufficient disk headroom on $root (minimum 3 GiB)." }
    }
    Write-Host 'Container limits total 4.25 GiB. Also check the host drive holding Docker Desktop disk data if relocated.'
    if ($running.Count -eq 0) {
        $occupied = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
            Where-Object { $_.Port -in @(19092, 29092, 39092, 8090) }
        if ($occupied) { throw "Required ports already in use: $($occupied.Port -join ', ')" }
    }
}

function Assert-Cluster {
    $ids = @(Invoke-Compose ps --all --quiet)
    if ($ids.Count -ne 7) { throw "Expected 7 containers; found $($ids.Count)." }
    foreach ($id in $ids) {
        $state = & $DockerPath inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' $id
        if ($LASTEXITCODE -ne 0 -or $state -ne 'running healthy') { throw "Container $id is $state" }
    }
    $leaders = 0
    $followers = 0
    foreach ($node in 1..3) {
        $mode = Invoke-Compose exec -T "zookeeper-$node" timeout 5 /bin/bash /workspace/scripts/health-zookeeper.sh
        Write-Host "zookeeper-${node}: $mode"
        if ($mode -eq 'Mode: leader') { $leaders++ }
        if ($mode -eq 'Mode: follower') { $followers++ }
    }
    if ($leaders -ne 1 -or $followers -ne 2) { throw 'Expected one ZooKeeper leader and two followers.' }
    Invoke-Compose exec -T kafka-1 /bin/bash /workspace/scripts/verify-topics.sh
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8090/actuator/health' -TimeoutSec 15
    if ($health.status -ne 'UP') { throw 'Kafka UI health is not UP.' }
    $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8090/' -TimeoutSec 15
    if ($page.StatusCode -ne 200) { throw 'Kafka UI root page did not return HTTP 200.' }
    Write-Host 'PASS: seven healthy containers, ZooKeeper quorum, topics, Kafka UI HTTP 200 / UP.'
}

Invoke-Compose config --quiet
switch ($Action) {
    'Config' { Invoke-Compose config --services }
    'Start' {
        Assert-Resources
        Invoke-Compose up -d --wait --wait-timeout 300
        Invoke-Compose exec -T kafka-1 /bin/bash /workspace/scripts/init-topics.sh
        Assert-Cluster
    }
    'Verify' { Assert-Cluster }
    'Smoke' { Invoke-Compose exec -T kafka-1 /bin/bash /workspace/scripts/smoke-test.sh }
    'Stop' { Invoke-Compose stop --timeout 45 }
    'Status' { Invoke-Compose ps --all }
    'Logs' { Invoke-Compose logs --tail 100 }
}
