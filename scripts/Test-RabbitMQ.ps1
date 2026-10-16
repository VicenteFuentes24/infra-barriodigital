param(
    [Parameter(Mandatory = $true)]
    [PSCredential] $Credential,
    [string] $ManagementUrl = 'http://localhost:15672'
)

$ErrorActionPreference = 'Stop'
$script:Checks = 0
$networkCredential = $Credential.GetNetworkCredential()
$basicAuth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
    $networkCredential.UserName + ':' + $networkCredential.Password
))
$headers = @{ Authorization = 'Basic ' + $basicAuth }
$baseUrl = $ManagementUrl.TrimEnd('/')
$definitionsPath = Join-Path $PSScriptRoot '../rabbitmq/definitions.json'
$definitions = Get-Content -LiteralPath $definitionsPath -Raw | ConvertFrom-Json

function Invoke-RabbitApi {
    param([string] $Method, [string] $Path, $Body)
    $options = @{
        Method = $Method
        Uri = $baseUrl + '/api/' + $Path
        Headers = $headers
        TimeoutSec = 15
    }
    if ($null -ne $Body) {
        $options.ContentType = 'application/json'
        $options.Body = $Body | ConvertTo-Json -Depth 20 -Compress
    }
    try {
        $response = Invoke-RestMethod @options
    }
    catch {
        throw "Fallo API RabbitMQ ($Method $Path): $($_.Exception.Message)"
    }
    return $response
}

function Get-ReadyQueues {
    param([string] $VhostPath)
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $queues = @(Invoke-RabbitApi 'GET' "queues/$VhostPath")
        $ready = $true
        foreach ($policy in $definitions.policies) {
            $target = @($queues | Where-Object { $_.name -match $policy.pattern })
            if ($target.Count -ne 1 -or
                $target[0].effective_policy_definition.'dead-letter-exchange' -cne $policy.definition.'dead-letter-exchange' -or
                $target[0].effective_policy_definition.'dead-letter-routing-key' -cne $policy.definition.'dead-letter-routing-key') {
                $ready = $false
                break
            }
        }
        if ($ready) { return $queues }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "Management no muestra las politicas DLX esperadas en el vhost $VhostPath tras 30 segundos."
}

function Assert-Check {
    param([bool] $Condition, [string] $Message)
    if (-not $Condition) { throw $Message }
    $script:Checks++
}

# El vhost real solo se inspecciona; todos los mensajes de prueba van a uno temporal.
$vhost = [Uri]::EscapeDataString($definitions.vhosts[0].name)
$liveExchanges = @(Invoke-RabbitApi 'GET' "exchanges/$vhost")
$liveQueues = @(Get-ReadyQueues $vhost)
$liveBindings = @(Invoke-RabbitApi 'GET' "bindings/$vhost")
$livePolicies = @(Invoke-RabbitApi 'GET' "policies/$vhost")
foreach ($exchange in $definitions.exchanges) {
    $actual = @($liveExchanges | Where-Object { $_.name -ceq $exchange.name })
    Assert-Check ($actual.Count -eq 1) "Exchange ausente: $($exchange.name)"
    Assert-Check ($actual[0].type -ceq $exchange.type -and $actual[0].durable -and -not $actual[0].auto_delete -and -not $actual[0].internal) "Exchange incompatible: $($exchange.name)"
}
foreach ($queue in $definitions.queues) {
    $actual = @($liveQueues | Where-Object { $_.name -ceq $queue.name })
    Assert-Check ($actual.Count -eq 1) "Cola ausente: $($queue.name)"
    Assert-Check ($actual[0].durable -and -not $actual[0].auto_delete -and $actual[0].arguments.'x-queue-type' -eq 'classic') "Cola incompatible: $($queue.name)"
    Assert-Check ($null -eq $actual[0].arguments.'x-dead-letter-exchange' -and $null -eq $actual[0].arguments.'x-dead-letter-routing-key') "La cola sobrescribe la politica DLX: $($queue.name)"
    if ($queue.name.EndsWith('.dlq')) {
        Assert-Check ($null -eq $actual[0].effective_policy_definition.'dead-letter-exchange') "La DLQ no debe reenviar mensajes: $($queue.name)"
    }
}
foreach ($binding in $definitions.bindings) {
    $actual = @($liveBindings | Where-Object {
        $_.source -ceq $binding.source -and $_.destination -ceq $binding.destination -and
        $_.destination_type -ceq 'queue' -and $_.routing_key -ceq $binding.routing_key
    })
    Assert-Check ($actual.Count -eq 1) "Binding ausente: $($binding.source) -> $($binding.destination) [$($binding.routing_key)]"
}
foreach ($policy in $definitions.policies) {
    $actual = @($livePolicies | Where-Object { $_.name -ceq $policy.name })
    Assert-Check ($actual.Count -eq 1) "Politica ausente: $($policy.name)"
    Assert-Check ($actual[0].pattern -ceq $policy.pattern -and $actual[0].'apply-to' -eq 'queues' -and $actual[0].priority -eq $policy.priority -and $actual[0].definition.'dead-letter-exchange' -ceq 'cmd.dead.dlx' -and $actual[0].definition.'dead-letter-routing-key' -ceq $policy.definition.'dead-letter-routing-key') "Politica incompatible: $($policy.name)"
    $target = @($liveQueues | Where-Object { $_.name -match $policy.pattern })
    Assert-Check ($target.Count -eq 1 -and $target[0].effective_policy_definition.'dead-letter-routing-key' -ceq $policy.definition.'dead-letter-routing-key') "Politica DLX no aplicada: $($policy.name)"
}

Write-Output 'Topologia validada. Probando mensajes en un vhost temporal.'
$testVhost = 'bd-topology-test-' + [Guid]::NewGuid().ToString('N')
$testVhostPath = [Uri]::EscapeDataString($testVhost)
$created = $false
try {
    Invoke-RabbitApi 'PUT' "vhosts/$testVhostPath" @{} | Out-Null
    $created = $true
    $username = [Uri]::EscapeDataString($networkCredential.UserName)
    Invoke-RabbitApi 'PUT' "permissions/$testVhostPath/$username" @{ configure = '.*'; write = '.*'; read = '.*' } | Out-Null
    $testDefinitions = Get-Content -LiteralPath $definitionsPath -Raw | ConvertFrom-Json
    $testDefinitions.vhosts[0].name = $testVhost
    foreach ($section in @('exchanges', 'queues', 'bindings', 'policies')) {
        foreach ($item in $testDefinitions.$section) { $item.vhost = $testVhost }
    }
    Invoke-RabbitApi 'POST' 'definitions' $testDefinitions | Out-Null
    Get-ReadyQueues $testVhostPath | Out-Null

    function Publish-TestMessage {
        param([string] $Exchange, [string] $Key)
        $payload = 'bd-test-' + [Guid]::NewGuid().ToString('N')
        $result = Invoke-RabbitApi 'POST' "exchanges/$testVhostPath/$Exchange/publish" @{
            properties = @{ delivery_mode = 2 }
            routing_key = $Key
            payload = $payload
            payload_encoding = 'string'
        }
        @{ Routed = $result.routed; Payload = $payload }
    }

    function Read-TestMessage {
        param([string] $Queue, [string] $AckMode = 'ack_requeue_false')
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            $messages = @(Invoke-RabbitApi 'POST' "queues/$testVhostPath/$Queue/get" @{
                count = 1; ackmode = $AckMode; encoding = 'auto'
            })
            if ($messages.Count -gt 0) { return $messages[0] }
            Start-Sleep -Milliseconds 100
        }
        throw "No se recibio el mensaje de prueba en $Queue."
    }

    $cases = @(
        @('cmd.direct', 'email.send', 'q.cmd.email'),
        @('cmd.direct', 'crew.ticket', 'q.cmd.crew'),
        @('cmd.direct', 'certificate.gen', 'q.cmd.certificate'),
        @('cmd.topic', 'email.send', 'q.cmd.email'),
        @('cmd.topic', 'email.reminder', 'q.cmd.email'),
        @('cmd.topic', 'crew', 'q.cmd.crew'),
        @('cmd.topic', 'crew.ticket', 'q.cmd.crew'),
        @('cmd.topic', 'crew.ticket.created', 'q.cmd.crew'),
        @('cmd.topic', 'certificate.gen', 'q.cmd.certificate'),
        @('cmd.topic', 'certificate.ready', 'q.cmd.certificate')
    )
    foreach ($case in $cases) {
        $published = Publish-TestMessage $case[0] $case[1]
        Assert-Check $published.Routed "No se enruto $($case[0])/$($case[1])."
        $received = Read-TestMessage $case[2]
        Assert-Check ($received.payload -ceq $published.Payload) "Destino incorrecto para $($case[1])."
    }
    foreach ($case in @(@('cmd.direct', 'email.reminder'), @('cmd.topic', 'email.send.extra'), @('cmd.topic', 'certificate.gen.extra'), @('cmd.topic', 'unknown.key'))) {
        $published = Publish-TestMessage $case[0] $case[1]
        Assert-Check (-not $published.Routed) "Routing key inesperadamente aceptada: $($case[1])."
    }
    foreach ($kind in @('email', 'crew', 'certificate')) {
        $published = Publish-TestMessage 'cmd.topic' "$kind.test"
        Assert-Check $published.Routed "No se enruto el mensaje DLQ de $kind."
        $rejected = Read-TestMessage "q.cmd.$kind" 'reject_requeue_false'
        Assert-Check ($rejected.payload -ceq $published.Payload) "Rechazo incorrecto para $kind."
        $deadLetter = Read-TestMessage "q.cmd.$kind.dlq"
        Assert-Check ($deadLetter.payload -ceq $published.Payload) "DLQ incorrecta para $kind."
        $death = @($deadLetter.properties.headers.'x-death')
        Assert-Check ($death.Count -gt 0 -and $death[0].reason -eq 'rejected' -and $death[0].queue -ceq "q.cmd.$kind") "Falta x-death para $kind."
    }
    foreach ($queue in $testDefinitions.queues) {
        $remaining = @(Invoke-RabbitApi 'POST' "queues/$testVhostPath/$($queue.name)/get" @{
            count = 1; ackmode = 'ack_requeue_false'; encoding = 'auto'
        })
        Assert-Check ($remaining.Count -eq 0) "Mensaje duplicado o mal enrutado en $($queue.name)."
    }
}
finally {
    if ($created) { Invoke-RabbitApi 'DELETE' "vhosts/$testVhostPath" | Out-Null }
}

Write-Output "$script:Checks comprobaciones correctas: topologia, direct, topic, rechazo a DLQ y limpieza del vhost temporal."
