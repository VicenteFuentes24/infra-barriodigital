# RabbitMQ local - BarrioDigital EP3/EP4

`compose.rabbitmq.yml` es un proyecto Compose independiente llamado
`barriodigital-rabbitmq`. No reemplaza ni modifica `compose.yml`.
Solo inicia RabbitMQ Management y un inicializador de topologia.
Requisitos: Docker Desktop con contenedores Linux, Docker Compose v2 o superior
y PowerShell para el script de validacion.

## Variables

`.env.rabbitmq.example` contiene valores de ejemplo sin credenciales reales.
Compose exige usuario y password no vacios; no hay credenciales por defecto
incluidas en el repositorio. Se pueden proporcionar en la sesion PowerShell o
en un archivo local `.env.rabbitmq`, ignorado por Git.

| Variable | Valor de ejemplo / uso |
| --- | --- |
| `RABBITMQ_DEFAULT_USER` | Obligatoria: usuario administrador exclusivo del entorno local |
| `RABBITMQ_DEFAULT_PASS` | Obligatoria: password local, sin reutilizar secretos de otros sistemas |
| `RABBITMQ_IMAGE` | `rabbitmq:4.3.6-management`; admite referencia por digest |
| `RABBITMQ_TOPOLOGY_IMAGE` | `curlimages/curl:8.21.0`; admite referencia por digest |
| `RABBITMQ_AMQP_PORT` | `5672` en el host |
| `RABBITMQ_MANAGEMENT_PORT` | `15672` en el host |
| `BARRIODIGITAL_NETWORK_NAME` | `infra-barriodigital_barriodigital-net` |

El vhost es `barriodigital`, compartido por el broker y `definitions.json`.
El hostname fijo `barriodigital-rabbitmq` mantiene estable la identidad del nodo.
Las variables `RABBITMQ_DEFAULT_*` crean el usuario y el vhost en el primer inicio
con un volumen vacio. Cambiarlas no rota credenciales de un volumen existente;
la rotacion se administra en RabbitMQ, sin borrar los datos.
Si se utiliza `.env.rabbitmq`, usar comillas simples en passwords con `$` para
evitar interpolacion de Compose y cambiar `--env-file` en los comandos siguientes.

## Inicio en PowerShell

Desde la carpeta de infraestructura:

```powershell
Set-Location 'G:\Desarrollo EP3-EP4\infra-barriodigital'
$rabbitCredential = Get-Credential -Message 'Credenciales nuevas para RabbitMQ local'
$env:RABBITMQ_DEFAULT_USER = $rabbitCredential.UserName
$env:RABBITMQ_DEFAULT_PASS = $rabbitCredential.GetNetworkCredential().Password
$rabbitCompose = @('--env-file', '.env.rabbitmq.example', '-f', 'compose.rabbitmq.yml')
docker compose @rabbitCompose config -q
```

`config -q` valida sin mostrar el password. La variable de la sesion tiene
precedencia sobre el ejemplo vacio. No utilizar `config` sin `-q` al compartir
salidas, porque muestra variables resueltas.

La red externa debe existir antes de iniciar. Si el Compose anterior ya esta
iniciado, usar su red existente; si no, crearla sin levantar los otros servicios:

```powershell
docker network ls --format '{{.Name}}'
$rabbitNetwork = 'infra-barriodigital_barriodigital-net'
$previousComposeProject = 'infra-barriodigital'
docker network inspect $rabbitNetwork *> $null
if ($LASTEXITCODE -ne 0) {
    docker network create --driver bridge --label "com.docker.compose.project=$previousComposeProject" --label 'com.docker.compose.network=barriodigital-net' $rabbitNetwork
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la red compartida.' }
}
$env:BARRIODIGITAL_NETWORK_NAME = $rabbitNetwork
docker compose @rabbitCompose up -d --wait --wait-timeout 300 rabbitmq
if ($LASTEXITCODE -ne 0) { throw 'RabbitMQ no alcanzo el estado healthy.' }
docker compose @rabbitCompose run --rm --no-deps rabbitmq-topology
if ($LASTEXITCODE -ne 0) { throw 'No se pudo importar la topologia.' }
```

Si la evaluacion anterior usa otro nombre de proyecto con `-p`, ajustar
`$rabbitNetwork` al nombre real de su red y `$previousComposeProject` a ese proyecto.
Las etiquetas permiten que `compose.yml` reconozca la red incluso si RabbitMQ
se inicia primero. El valor por defecto corresponde al
proyecto `infra-barriodigital` y la clave `barriodigital-net` del Compose actual.
No combinar los dos archivos con varios `-f`: se administran por separado.
El inicializador tambien participa en un `up -d` completo; el inicio en dos pasos
anterior espera el healthcheck y permite comprobar su resultado inmediatamente.

El healthcheck espera a que el broker cree `.erlang.cookie` y ejecuta los
diagnosticos como usuario `rabbitmq` mediante `gosu`. Asi evita que el diagnostico
temprano cree ese archivo como root y provoque errores `eacces` en el primer
arranque. El timeout por comprobacion es 30 segundos y el periodo inicial 90
segundos. Un error de espera no borra datos; revisar `ps -a` y los logs antes de
reintentar. No eliminar el volumen para solucionar un problema de healthcheck.

Management UI: http://localhost:15672, con las credenciales locales configuradas.
Si se cambia el puerto del host, ajustar la URL. AMQP desde el host:
`localhost:5672`; desde futuros servicios en la red: `rabbitmq:5672`, vhost
`barriodigital`. No se requiere modificar Azure, MSAL, Supabase ni las rutas HTTP.

## Topologia y responsable unico

`rabbitmq/definitions.json` es la unica fuente de exchanges, colas, bindings y
politicas. `rabbitmq-topology` la importa mediante `POST /api/definitions` despues
del arranque, sin incluir usuarios, passwords ni hashes en ese JSON. El broker
crea sus credenciales desde variables de entorno antes de importar la topologia.
No hay otro mecanismo de importacion al inicio ni declaraciones desde los
microservicios en este paso.

| Exchange | Tipo | Routing key / patron | Destino |
| --- | --- | --- | --- |
| `cmd.direct` | direct | `email.send` | `q.cmd.email` |
| `cmd.direct` | direct | `crew.ticket` | `q.cmd.crew` |
| `cmd.direct` | direct | `certificate.gen` | `q.cmd.certificate` |
| `cmd.topic` | topic | `email.*` | `q.cmd.email` |
| `cmd.topic` | topic | `crew.#` | `q.cmd.crew` |
| `cmd.topic` | topic | `certificate.*` | `q.cmd.certificate` |
| `cmd.dead.dlx` | direct | `q.cmd.email.dlq` | `q.cmd.email.dlq` |
| `cmd.dead.dlx` | direct | `q.cmd.crew.dlq` | `q.cmd.crew.dlq` |
| `cmd.dead.dlx` | direct | `q.cmd.certificate.dlq` | `q.cmd.certificate.dlq` |

Todos los exchanges y las colas son durables; las colas son classic, sin
auto-delete. Cada cola principal tiene una politica que coincide solo con su
nombre exacto y configura `dead-letter-exchange=cmd.dead.dlx` y
`dead-letter-routing-key=<nombre de su DLQ>`. Las DLQ no tienen reenvio automatico,
TTL ni bucles. Un consumidor envia un mensaje a DLQ con reject/nack y
`requeue=false`; `requeue=true` vuelve a la cola principal.

La persistencia utiliza el volumen `barriodigital-rabbitmq_rabbitmq-data`.
Para conservar mensajes, los productores futuros deberan publicarlos como
persistentes (`delivery_mode=2`) y usar publisher confirms. Este entorno es un
unico nodo local, sin alta disponibilidad ni garantia de dead-lettering
at-least-once de un cluster con colas quorum.

La importacion es repetible para esta misma topologia y no elimina objetos
existentes. Si se cambia un tipo de exchange o argumentos inmutables de una cola,
se necesita una migracion planificada: importar de nuevo no corrige objetos
incompatibles. Los futuros servicios deben consumir/publicar usando este contrato;
no declarar otra topologia ni argumentos DLX que sobrescriban las politicas.

## Validacion

```powershell
docker compose @rabbitCompose ps -a
docker compose @rabbitCompose exec -T rabbitmq rabbitmq-diagnostics -q check_running
docker compose @rabbitCompose exec -T rabbitmq rabbitmq-diagnostics -q check_local_alarms
docker compose @rabbitCompose exec -T rabbitmq rabbitmq-diagnostics -q check_port_connectivity
docker compose @rabbitCompose exec -T rabbitmq rabbitmqctl list_exchanges -p barriodigital name type durable
docker compose @rabbitCompose exec -T rabbitmq rabbitmqctl list_queues -p barriodigital name durable arguments policy messages
docker compose @rabbitCompose exec -T rabbitmq rabbitmqctl list_bindings -p barriodigital source_name destination_name routing_key
docker compose @rabbitCompose exec -T rabbitmq rabbitmqctl list_policies -p barriodigital
./scripts/Test-RabbitMQ.ps1 -Credential $rabbitCredential
```

Para otro puerto: agregar `-ManagementUrl 'http://localhost:<puerto>'` al script.
La prueba compara la topologia real con el archivo y crea un vhost temporal
`bd-topology-test-<uuid>`. En ese vhost verifica direct, comodines topic,
keys no enrutables y las tres DLQ rechazando mensajes; lo elimina en `finally`.
No consume ni publica mensajes en las colas de la aplicacion.
Espera hasta 30 segundos a que Management refleje las politicas DLX, tanto en el
vhost real como en el temporal, antes de validar o publicar mensajes de prueba.
La API Management se usa aqui para diagnostico local; los servicios usaran AMQP.
La prueba requiere el usuario administrador local del broker.

## Operacion

Reaplicar la misma definicion:

```powershell
docker compose @rabbitCompose run --rm --no-deps rabbitmq-topology
docker compose @rabbitCompose logs --tail 100 rabbitmq
docker compose @rabbitCompose down
```

`down` conserva el volumen y no elimina la red externa. No usar `down -v` si
se necesitan conservar mensajes. Los puertos estan publicados solo en loopback;
esta configuracion es para desarrollo local, no un despliegue AWS.

Pendiente: productores/consumidores reales, contrato del mensaje, reintentos,
idempotencia, observabilidad y validacion de los flujos de negocio EP3/EP4.

Referencias oficiales:
[importacion de definitions](https://www.rabbitmq.com/docs/definitions),
[dead-letter exchanges y politicas](https://www.rabbitmq.com/docs/dlx),
[API Management](https://www.rabbitmq.com/docs/http-api-reference).
