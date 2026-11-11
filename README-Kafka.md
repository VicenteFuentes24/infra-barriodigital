# Kafka local — BarrioDigital EP5 / EP6

Infraestructura independiente de EP4. No modifica RabbitMQ, microservicios, frontend,
Supabase, Entra ID ni AWS. Esta fase no incorpora aplicaciones Java nuevas.

## Arquitectura y versiones

- Proyecto Compose: `barriodigital-kafka`; red: `barriodigital-kafka-net`.
- Tres contenedores ZooKeeper con IDs 1, 2 y 3, quorum de mayoría (2/3), un líder y
  dos seguidores. Cada uno conserva `myid`, snapshots y transaction logs en su volumen.
- Tres brokers Kafka con IDs 1, 2 y 3 y un volumen propio para cada broker.
- Imagen `apache/kafka:3.9.1` para ambos roles. Incluye **ZooKeeper 3.8.4**, comprobado
  en `/opt/kafka/libs/zookeeper-3.8.4.jar`. Compartir la imagen reduce descargas y disco;
  los seis procesos, contenedores y almacenes siguen siendo independientes.
- Kafka UI: `ghcr.io/kafbat/kafka-ui:v1.5.0`, accesible en <http://localhost:8090>.
  Está en modo de solo lectura; permite inspeccionar sin alterar los tópicos.
- Se invocan directamente `zookeeper-server-start.sh` y `kafka-server-start.sh`,
  con configuraciones propias. Se evita el generador de configuración predeterminado
  de la imagen. **No se ejecuta `kafka-storage format` ni se configura KRaft**.
- ZooKeeper usa 2181/2888/3888 únicamente dentro de Docker. Su servidor Admin HTTP
  está deshabilitado. Los puertos publicados se enlazan exclusivamente a loopback.

| Cliente | Bootstrap servers |
|---|---|
| Contenedores conectados a `barriodigital-kafka-net` | `kafka-1:9092,kafka-2:9092,kafka-3:9092` |
| Windows | `localhost:19092,localhost:29092,localhost:39092` |

Cada broker escucha `INTERNAL:9092` y `EXTERNAL:9093`. Los puertos externos de
Windows se traducen a 9093 y se anuncian individualmente como `localhost:19092`,
`localhost:29092` y `localhost:39092`. La comunicación entre brokers usa INTERNAL.
No usar `localhost` desde otro contenedor. Esta configuración PLAINTEXT es local;
no es una configuración de despliegue remoto.

## Archivos

| Ruta | Función |
|---|---|
| `compose.kafka.yml` | Siete servicios, red, seis volúmenes, límites y healthchecks |
| `kafka/config/broker.properties` | Configuración común en modo ZooKeeper |
| `kafka/config/zookeeper.properties` | Ensemble de tres nodos |
| `kafka/config/topics.tsv` | Contrato de los dos tópicos de negocio |
| `kafka/scripts/start-*.sh` | Arranque y validación de identificadores |
| `kafka/scripts/health-*.sh` | Salud de ZooKeeper y API Kafka |
| `kafka/scripts/common.sh` | Espera de brokers y validación estricta de tópicos |
| `kafka/scripts/init-topics.sh` | Creación idempotente; no altera tópicos existentes |
| `kafka/scripts/verify-topics.sh` | Particiones, RF, líderes, ISR y configuración |
| `kafka/scripts/smoke-test.sh` | Publicación y consumo en tópico de prueba controlado |
| `kafka/kafka-local.ps1` | Comandos Windows y comprobación de recursos |
| `kafka/verify-listeners.py` | Lectura real de Metadata Kafka desde Windows |
| `kafka/compose.empty.env` | Archivo sin credenciales para evitar lectura de `.env` |
| `kafka/.gitattributes` | Conserva finales de línea LF en los scripts Linux |
| `kafka/VALIDACION.md` | Evidencia y límites de las pruebas ejecutadas |

## Requisitos y presupuesto de recursos

Docker Desktop iniciado con motor Linux/WSL2 y Docker Compose disponible.
PowerShell para el controlador; Python 3, sin paquetes adicionales, únicamente
para la prueba opcional de listeners externos. Java y Maven del host no se usan.

| Proceso | Cantidad | Heap por proceso | Límite de memoria por contenedor |
|---|---:|---|---:|
| ZooKeeper | 3 | 64–128 MiB | 256 MiB |
| Kafka | 3 | 256–384 MiB | 1.024 MiB |
| Kafka UI | 1 | 128–256 MiB | 512 MiB |

Límites agregados: **4.25 GiB**, sin incluir el coste de Docker/WSL2 y Windows.
No representan memoria reservada ni garantizan que el sistema disponga de ella.
Los CLI usan heap máximo de 128 MiB dentro del límite de su broker.
Se limitan threads, CPU y logs de Docker (2 archivos de 5 MiB por contenedor).

`Start` comprueba motor Linux, al menos 5 GiB visibles para Docker, RAM libre de
Windows, espacio en la unidad del repositorio y del sistema, y puertos en un
arranque en frío. Rechaza un arranque en frío con menos de 3 GiB de RAM libre o
menos de 3 GiB de disco libre en las unidades comprobadas. Es un umbral mínimo:
conviene disponer de 4–5 GiB libres y no iniciar la arquitectura completa a la vez.
Si Docker tiene su disco virtual en otra unidad, comprobar también esa unidad en
Docker Desktop antes de iniciar. Los volúmenes viven en el disco de Docker, no
en la carpeta `G:` del repositorio. El tamaño disponible dentro del disco virtual
no sustituye la comprobación de espacio físico del host.

## Ejecutar desde PowerShell

Situarse en `infra-barriodigital`. No hace falta crear ni cargar un `.env`.

```powershell
.\kafka\kafka-local.ps1 -Action Config
.\kafka\kafka-local.ps1 -Action Start
.\kafka\kafka-local.ps1 -Action Status
.\kafka\kafka-local.ps1 -Action Verify
.\kafka\kafka-local.ps1 -Action Smoke
python .\kafka\verify-listeners.py
```

Si Docker no está en PATH, el script busca las instalaciones habituales. También
acepta `-DockerPath 'C:\ruta\resources\bin\docker.exe'`. Añade esa carpeta al PATH
solo del proceso para resolver el helper de Docker, sin leer credenciales ni
cambiar la configuración permanente del sistema.

`Start` valida Compose, comprueba recursos y ejecuta `up --wait`. ZooKeeper debe
tener quorum antes de marcarse healthy; los brokers dependen de los tres nodos
saludables y Kafka UI depende de los tres brokers saludables. Después, dentro de
`kafka-1`, se espera una respuesta real de los tres brokers, se crean los tópicos
y se verifican. No se mantiene un octavo contenedor de inicialización.

Repetir `Start` con la misma configuración no borra datos. La creación utiliza
`--if-not-exists`; los verificadores comprueban el contrato existente, con reintentos
acotados para convergencia de metadatos/ISR. Una configuración incompatible produce
error, no una modificación silenciosa. Los healthchecks no reinician por sí mismos
contenedores unhealthy; `restart: unless-stopped` actúa si termina el proceso.

El comando `up` directo no inicializa tópicos. Si se utiliza manualmente:

```powershell
$dc = @('compose', '--env-file', 'kafka/compose.empty.env', '-f', 'compose.kafka.yml')
docker @dc config --quiet
docker @dc up -d --wait --wait-timeout 300
docker @dc exec -T kafka-1 bash /workspace/scripts/init-topics.sh
docker @dc exec -T kafka-1 bash /workspace/scripts/verify-topics.sh
```

Conservar siempre `--env-file kafka/compose.empty.env` y `-f compose.kafka.yml`.
No combinar este proyecto con los Compose de RabbitMQ o AWS.

## Tópicos, durabilidad y almacenamiento

| Tópico | Particiones | RF | min ISR | Retención temporal | Retención por partición/réplica |
|---|---:|---:|---:|---|---:|
| `bd.requests.events.v1` | 3 | 3 | 2 | 7 días | 64 MiB |
| `bd.requests.analytics.v1` | 3 | 3 | 2 | 1 día | 64 MiB |

Ambos usan `cleanup.policy=delete`. Son secuencias de eventos, por lo que compactar
por clave eliminaría estados intermedios necesarios para replay y demostraciones.
Siete días favorecen el replay de eventos; un día limita el almacenamiento del
flujo analítico local. Los límites de tiempo y bytes se aplican conjuntamente:
la presión de tamaño puede eliminar segmentos antes de completar esos días.

Los segmentos son de 16 MiB, rotan como máximo cada hora y se revisa la retención
cada minuto. El presupuesto nominal de datos retenidos de ambos tópicos, contando
las tres réplicas, es 1.125 GiB. **No es una cuota estricta**: segmentos activos,
índices, eliminación diferida, tópicos internos y ZooKeeper agregan espacio.
ZooKeeper conserva como mínimo tres snapshots mediante autopurge horario.

No se permite autocreación de tópicos ni elección de líderes fuera del ISR.
El script de prueba usa `acks=all` e idempotencia. Los futuros productores deben
usar esas mismas garantías: `min.insync.replicas=2` por sí solo no sustituye
`acks=all`. Se requiere al menos dos réplicas sincronizadas para esas escrituras.
Los offsets y el log transaccional se configuran con RF=3; este último con ISR mínimo 2.
La replicación protege ante fallos de procesos, pero los siete contenedores comparten
un computador: no hay tolerancia al fallo físico de ese host.

La eliminación administrativa de tópicos está deshabilitada. Los scripts no
ejecutan borrado de tópicos, volúmenes ni contenedores.

## Verificación y presentación

`Verify` exige siete contenedores healthy, un líder ZooKeeper y dos seguidores,
exactamente tres particiones por tópico, RF=3, líder válido y conjunto ISR `{1,2,3}`
en cada partición. También valida las seis propiedades explícitas del contrato,
HTTP 200 en la página de Kafka UI y estado de salud `UP`.

`verify-listeners.py` envía solicitudes reales Metadata v0 a los tres puertos de
Windows y exige que todos anuncien los mismos tres endpoints externos correctos.
No basta con comprobar que un puerto acepta conexiones TCP.

`Smoke` crea/reutiliza **`bd.local.smoke.v1`**, con tres particiones, RF=3, ISR mínimo
2, retención de una hora/8 MiB por partición, segmentos de 1 MiB/1 minuto. Captura
offsets finales, publica un JSON con UUID y exige consumir exactamente ese registro.
Es una prueba secuencial de infraestructura: no ejecutar dos instancias de Smoke
al mismo tiempo. El tópico queda como evidencia; sus registros expiran según su
retención, sin borrar manualmente el tópico. No escribe en los tópicos de negocio.

En Kafka UI, seleccionar `barriodigital-local` y revisar Brokers, Topics, Partitions
y Messages del tópico de prueba. Los tópicos de negocio permanecerán vacíos en
esta fase. Los consumer groups y el lag de aplicaciones se demostrarán cuando
existan consumidores persistentes; esta prueba asigna particiones directamente
y no demuestra commits de offsets de un grupo Java.

## Diagnóstico y recuperación sin perder datos

```powershell
.\kafka\kafka-local.ps1 -Action Status
.\kafka\kafka-local.ps1 -Action Logs
docker stats --no-stream
docker system df
```

- **Docker/credential helper no encontrado:** proporcionar `-DockerPath`; no se
  requiere cambiar ni inspeccionar credenciales.
- **Puerto ocupado:** identificar el proceso y acordar cómo liberar o cambiar el
  puerto. No detener servicios ajenos automáticamente. Cambiar un puerto requiere
  cambiar también su advertised listener y el verificador externo.
- **ZooKeeper sin quorum:** revisar los tres contenedores y sus logs, DNS de la red
  y `myid`. No sustituir un volumen por el de otro nodo. El arranque rechaza IDs
  persistidos que no coincidan. Recuperar los nodos existentes y repetir Start.
- **Broker unhealthy/ISR incompleto:** revisar memoria, OOM, logs y conectividad
  ZooKeeper. Recuperar el proceso original conservando su volumen; esperar que
  vuelva al ISR antes de considerar la recuperación terminada.
- **Tópico existente distinto del contrato:** init falla. Investigar y acordar una
  migración explícita; no borrar/recrear para ocultar la diferencia.
- **RAM o disco insuficientes:** no continuar cargando servicios. Informar recursos
  disponibles y liberar capacidad manualmente sin eliminar datos del proyecto.
- **Kafka UI sin tópicos inmediatamente después de init:** refrescar tras su
  actualización de metadatos y contrastar con `Verify`, que consulta al broker.

Detención y recuperación ordinaria:

```powershell
.\kafka\kafka-local.ps1 -Action Stop
.\kafka\kafka-local.ps1 -Action Start
.\kafka\kafka-local.ps1 -Action Verify
```

`Stop` usa `docker compose stop --timeout 45`: conserva contenedores, red y los seis
volúmenes. `Start` vuelve a usar esos datos. No usar `down -v`, `volume rm`, `prune`
ni borrar directorios para recuperar el clúster. Las pruebas de caída y recuperación
no forman parte de los resultados ejecutados salvo que se indiquen en VALIDACION.

## Referencias técnicas

- [Kafka 3.9: arranque con ZooKeeper](https://kafka.apache.org/39/getting-started/quickstart/).
- [Imagen JVM oficial 3.9.1](https://github.com/apache/kafka/blob/3.9.1/docker/jvm/Dockerfile).
- [Arranque ZooKeeper incluido en Kafka 3.9.1](https://github.com/apache/kafka/blob/3.9.1/bin/zookeeper-server-start.sh).
- [Kafka UI v1.5.0](https://github.com/kafbat/kafka-ui/releases/tag/v1.5.0).

Las comprobaciones y métricas de esta ejecución están en [kafka/VALIDACION.md](kafka/VALIDACION.md).
