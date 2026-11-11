# Validación ejecutada — Kafka local

Fecha: **7 de noviembre de 2026**, contexto del usuario America/Santiago.
Workspace: `Desarrollo EP3-EP4`; cambios únicamente en `infra-barriodigital`.
Este documento registra observaciones de esta ejecución, no garantiza el estado futuro.

## Entorno y preparación

- Docker Desktop 4.98.0; Engine 29.9.2; Compose 5.6.1; contexto `desktop-linux`.
- Motor Linux/WSL2, 8 CPU lógicas, 7.71 GiB visibles para Docker.
- Windows: 15.92 GiB de RAM total; inicialmente aproximadamente 5.61 GiB libres.
  Inmediatamente antes del primer `up`: aproximadamente 4.22 GiB libres.
- Antes de empezar: 0 imágenes, contenedores y volúmenes.
- `G:`: 13.03 GiB libres; `C:`: aproximadamente 98.5 GiB libres inicialmente.
- Puertos 19092, 29092, 39092 y 8090 sin listeners ni reservas IPv4 incompatibles.
- Docker no estaba en PATH. La primera descarga falló porque no se encontraba
  `docker-credential-desktop`. Se resolvió añadiendo la carpeta de Docker al PATH
  del proceso; no se leyó ni modificó ninguna credencial o configuración persistente.

Imágenes descargadas y utilizadas:

| Imagen | Digest observado | Tamaño informado |
|---|---|---:|
| `apache/kafka:3.9.1` | `sha256:4ceccc577f03f51f6af8dbfda55194d0d892f4fa7913ffbded567ce3895622ed` | 562654878 bytes |
| `ghcr.io/kafbat/kafka-ui:v1.5.0` | `sha256:7cda86a33344160309fdb65146332e4da65db81a945614f2fe32e210803f6fd1` | 634783712 bytes |

Los tags están fijados en Compose. Los digests anteriores documentan lo descargado
en esta ejecución; no se afirma que un tag sea inmutable.

## Comprobaciones realizadas

| Prueba | Resultado observado |
|---|---|
| `docker compose --env-file kafka/compose.empty.env -f compose.kafka.yml config --quiet` | PASS, salida 0 |
| Enumeración de servicios Compose | Exactamente siete servicios |
| `up -d --wait --wait-timeout 300` | PASS, los siete servicios healthy |
| Sintaxis Bash: `bash -n` para todos los scripts | PASS |
| Parser PowerShell de `kafka-local.ps1` | PASS, sin errores |
| Controlador PowerShell `Start` | PASS: recursos, up, init y verificación |
| Versión CLI Kafka dentro de la imagen | `3.9.1` |
| Biblioteca ZooKeeper incluida | `/opt/kafka/libs/zookeeper-3.8.4.jar` |
| IDs ZooKeeper persistidos | 1, 2 y 3, comprobados leyendo sus respectivos `myid` |
| Quorum ZooKeeper | Nodo 3 líder; nodos 1 y 2 seguidores |
| Configuración efectiva de kafka-1 | `broker.id=1`, tres endpoints `zookeeper.connect`, listeners INTERNAL/EXTERNAL; sin `process.roles` |
| Verificación de ambos tópicos | PASS: particiones, RF, líderes, ISR y seis propiedades explícitas |
| Segunda ejecución de `init-topics.sh` | PASS, sin recreación, mismos TopicId y configuración |
| Metadata Kafka desde Windows | PASS en localhost:19092, :29092 y :39092 |
| Kafka UI `/` | HTTP 200 |
| Kafka UI `/actuator/health` | `UP` |
| Kafka UI `/api/clusters` | `ONLINE`, 3 brokers, controlador `ZOOKEEPER` |
| Kafka UI `/api/clusters/barriodigital-local/topics` | Dos tópicos de negocio y uno de prueba; ISR completo; cero particiones subreplicadas |
| Publicación y consumo en tópico controlado | PASS: registro idéntico recuperado |
| Estado Git | Solo archivos nuevos; ningún archivo previamente versionado modificado |

Durante la consulta inicial de UI, su caché todavía indicaba cero tópicos. Una
consulta posterior confirmó los tres tópicos y nueve particiones online; no se
consideró aquella primera respuesta como evidencia de los tópicos creados.

## Estado de los contenedores al cierre

Todos pertenecen al proyecto `barriodigital-kafka`. No se iniciaron servicios EP4.

| Contenedor | Estado | Reinicios | OOMKilled | Memoria observada |
|---|---|---:|---|---:|
| `barriodigital-kafka-zookeeper-1-1` | running / healthy | 0 | false | 53.68 MiB |
| `barriodigital-kafka-zookeeper-2-1` | running / healthy | 0 | false | 57.07 MiB |
| `barriodigital-kafka-zookeeper-3-1` | running / healthy | 0 | false | 55.73 MiB |
| `barriodigital-kafka-kafka-1-1` | running / healthy | 0 | false | 273.4 MiB |
| `barriodigital-kafka-kafka-2-1` | running / healthy | 0 | false | 275.8 MiB |
| `barriodigital-kafka-kafka-3-1` | running / healthy | 0 | false | 278.2 MiB |
| `barriodigital-kafka-kafka-ui-1` | running / healthy | 0 | false | 268.5 MiB |

## Tópicos de negocio

| Tópico | TopicId conservado al repetir init | Particiones | RF | min ISR |
|---|---|---:|---:|---:|
| `bd.requests.events.v1` | `uccHVEvqQMK2EyLeVYvCbw` | 3 | 3 | 2 |
| `bd.requests.analytics.v1` | `NnTQOB9qTMuJLucPOlGQiQ` | 3 | 3 | 2 |

La distribución observada fue la misma en ambos tópicos:

| Partición | Líder | Réplicas | ISR |
|---:|---:|---|---|
| 0 | 2 | 2,3,1 | 2,3,1 |
| 1 | 3 | 3,1,2 | 3,1,2 |
| 2 | 1 | 1,2,3 | 1,2,3 |

Los líderes y el orden de las réplicas pueden cambiar; el verificador exige un
líder válido y el conjunto ISR completo, no estos órdenes particulares.

Configuración comprobada en ambos: `cleanup.policy=delete`, `min.insync.replicas=2`,
`retention.bytes=67108864`, `segment.bytes=16777216`, `segment.ms=3600000`.
Retención temporal: events `604800000` ms; analytics `86400000` ms.
Kafka UI informó cero mensajes y offsets finales 0 en todas sus particiones.

## Prueba de publicación y consumo

Se ejecutó `kafka-local.ps1 -Action Smoke`. El script creó `bd.local.smoke.v1`,
publicó con `acks=all` e idempotencia y leyó desde los offsets capturados previamente.

```text
PASS: produced and consumed identical record; topic=bd.local.smoke.v1 partition=1 offset=0
{"testId":"cd34f74e-4d2f-47e5-8424-5b7a51e108c8","source":"infra-local-smoke"}
```

Kafka UI corroboró un mensaje en ese tópico, offset máximo 1 en la partición 1,
nueve réplicas sincronizadas y cero particiones subreplicadas. El tópico permanece
como evidencia, con retención de una hora; no se ejecutó su eliminación.

## Recursos medidos

- Suma del muestreo `docker stats`: aproximadamente **1.23 GiB** de memoria.
  No incluye toda la memoria del host, caché y sobrecarga de WSL2/Docker.
- Límites configurados agregados: **4.25 GiB**.
- CPU al muestrear en reposo: aproximadamente 3.7% acumulado en la escala Docker
  donde 100% equivale a una CPU lógica. Durante los CLI, kafka-1 llegó cerca de 100%.
- `docker system df`: 2 imágenes, **1.199 GB**; 6 volúmenes, **767.6 MB**;
  7 capas escribibles de contenedor, aproximadamente **913.4 kB**; sin build cache.
- Espacio final observado: `G:` **13.03 GiB** libres; `C:` **97.29 GiB** libres.
- RAM libre final de Windows: aproximadamente **2.35 GiB**. No iniciar aún toda
  la arquitectura simultáneamente sin volver a evaluar memoria.
- El filesystem virtual del volumen informó aproximadamente 953 GiB disponibles;
  es un disco virtual de crecimiento dinámico, no espacio físico reservado del host.

## Alcance y pruebas pendientes

No hubo pruebas obligatorias bloqueadas: configuración, arranque, quorum, brokers,
UI, tópicos, ISR, listeners y publicación/consumo se ejecutaron correctamente.

No se ejecutaron: caída de un broker, pérdida de quorum, restart/stop-start,
recuperación tras reiniciar Docker/Windows, expiración de retención por tiempo,
pruebas de carga, grupos persistentes/lag de aplicaciones, integración Java o
regresión RabbitMQ. La persistencia está configurada mediante seis volúmenes y se
comprobaron IDs persistidos; no se declara ensayada la recuperación tras un reinicio.

Kafka emitió su aviso genérico sobre nombres con puntos y guiones bajos. Los nombres
definidos usan puntos y no guiones bajos; no se observó colisión de métricas.

Los contenedores se dejan **iniciados**. Para detenerlos conservando todos los datos:

```powershell
.\kafka\kafka-local.ps1 -Action Stop
```

No se realizaron commits, pushes, limpieza ni cambios en archivos EP4. No se
leyeron archivos `.env` reales. Los detalles operativos están en [README-Kafka.md](../README-Kafka.md).
