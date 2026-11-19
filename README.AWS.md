# BarrioDigital en AWS

## Despliegue actual mediante SSM

| EC2 en `us-east-1` | IP privada | Uso |
| --- | --- | --- |
| RabbitMQ Node 1 | `10.0.1.77` | AMQP `5672` y Management protegido existente |
| RabbitMQ Node 2 | `10.0.2.173` | AMQP `5672` |
| Kafka | `10.0.2.174` | Tres brokers y tres ZooKeeper en t3.medium, con Kafka UI en `127.0.0.1:8090` |
| Apps | `10.0.1.68` | Ocho aplicaciones y Mailpit en t3.large, con BFF en `127.0.0.1:8080` |

Abrir una sesión para el host indicado en cada paso. Usar su ID de instancia SSM y la ruta real del checkout. Los ejemplos usan `/opt/barriodigital`. Preparar el checkout revisado en Apps mediante un canal autorizado. En Apps, los ocho repositorios Java deben estar como hermanos de `infra-barriodigital`; cada uno conserva su propio checkout. [AWS Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-sessions-start.html)

```bash
aws ssm start-session --region us-east-1 --target i-REEMPLAZAR
```

Permitir desde Apps los puertos privados AMQP `5672` de ambos nodos y Kafka `19092`, `29092`, `39092` de la EC2 Kafka. Mantener las reglas existentes de clúster RabbitMQ entre sus nodos y salida de Apps hacia Supabase y Entra. Los puertos de BFF, Kafka UI y Management se atienden localmente desde sus agentes ngrok. Los demás servicios se alcanzan en la red Docker. Mailpit recibe SMTP en `mailpit:1025` y su UI escucha en loopback del host.

### RabbitMQ

Usar ambos nodos existentes, incluidos sus volúmenes y el túnel OAuth de Management. La comprobación en Node 1 es de solo lectura. `topology_state` admite el atributo `internal=false` omitido por RabbitMQ. Usar el archivo de entorno privado existente del nodo.

```bash
cd /opt/barriodigital/infra-barriodigital
sudo python3 aws/deploy.py node1 verify
sudo python3 aws/deploy.py node1 topology
```

### Kafka

Usar el clúster Kafka existente. Los límites definidos suman 3.094 GiB para los siete contenedores. Se conservan los volúmenes y los tópicos con tres particiones, factor de replicación 3, ISR mínimo 2 y las políticas vigentes. Los clientes del clúster usan `kafka-1:9092,kafka-2:9092,kafka-3:9092`. La EC2 Apps usa los tres puertos externos privados.

```bash
cd /opt/barriodigital/infra-barriodigital
sudo python3 aws/deploy.py kafka validate
sudo python3 aws/deploy.py kafka verify
```

`verify` comprueba el quórum de ZooKeeper, los tópicos, ISR, metadatos y Kafka UI sin recrear el clúster. Desde Apps, ejecutar `python3 kafka/verify-listeners.py 10.0.2.174` para comprobar la conectividad privada.

### Comprobar Supabase antes de iniciar Apps

Abrir cada base con `psql -v ON_ERROR_STOP=1` usando parámetros de conexión privados y TLS. `\conninfo` permite confirmar TLS y destino. En las URLs JDBC usar al menos `sslmode=require`. Para validar también identidad del servidor usar `sslmode=verify-full` con la CA de Supabase. En una EC2 solo IPv4, usar el pooler en modo sesión si el endpoint directo del proyecto requiere IPv6. [Conexión a Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres) · [TLS de pgJDBC](https://jdbc.postgresql.org/documentation/ssl/)

Ejecutar las siguientes consultas en las bases correspondientes, dentro de `BEGIN READ ONLY;` y `ROLLBACK;`. Si un objeto o una versión falta, completar el procedimiento de migración autorizado por separado antes de iniciar Apps. El Compose mantiene Hibernate en `validate` y desactiva Flyway de Report y Audit en AWS.

```sql
-- Requests. El SQL de origen es ms-barriodigital-requests/sql/kafka/V001__requests_kafka_outbox.sql.
SELECT to_regclass('public.requests'), to_regclass('bd_requests_kafka.stream'),
       to_regclass('bd_requests_kafka.outbox'), to_regclass('bd_requests_kafka.history_hold');
SELECT version FROM bd_requests_kafka.schema_version WHERE version = 1;

-- Report. El SQL de origen es ms-report/src/main/resources/db/migration/V1__report_schema.sql.
SELECT to_regclass('bd_report.processed_event'), to_regclass('bd_report.request_projection'),
       to_regclass('bd_report.analytics_outbox'), to_regclass('bd_report.failed_event');
SELECT version FROM bd_report.flyway_schema_history WHERE version = '1' AND success;

-- Audit. El SQL de origen es ms-audit/src/main/resources/db/migration/V1__audit_history.sql.
SELECT to_regclass('bd_audit.audit_event'), to_regclass('bd_audit.failed_event');
SELECT version FROM bd_audit.flyway_schema_history WHERE version = '1' AND success;
```

Esperar nombres de tabla no nulos y una fila de versión 1 en cada consulta de versión. Confirmar el esquema preexistente de Catalog y los permisos de los usuarios runtime sobre las tablas y secuencias de su servicio. Requests publica desde su outbox en `bd.requests.events.v1`. Report y Audit consumen de forma independiente con `bd-report-v1` y `bd-audit-v1`. Report publica agregados en `bd.requests.analytics.v1`.

### Compilar y arrancar Apps

Usar Docker Engine Linux x86_64 y Compose V2 en la EC2 Apps. El helper compila las ocho imágenes Java 21 en serie desde los repositorios clonados. El primer build necesita acceso a sus registros de imágenes y a Maven Central. Mantener al menos 15 GiB libres antes del build.

```bash
cd /opt/barriodigital/infra-barriodigital
test -f aws/.env.apps || (umask 077; cp aws/.env.apps.example aws/.env.apps)
# Completar aws/.env.apps localmente antes de continuar.
chmod 600 aws/.env.apps
python3 aws/deploy.py apps validate
sudo python3 aws/deploy.py apps start
sudo python3 aws/deploy.py apps ps
curl -fsS http://127.0.0.1:8080/actuator/health
```

Variables de [`aws/.env.apps.example`](aws/.env.apps.example)

| Uso | Variables |
| --- | --- |
| Entra y Amplify | `AZURE_TENANT_ID`, `AZURE_API_AUDIENCE`, `FRONTEND_ORIGIN` |
| PostgreSQL | `REQUESTS_DB_*`, `CATALOG_DB_*`, `REPORT_DB_*`, `AUDIT_DB_*`, cada grupo con `URL`, `USERNAME` y `PASSWORD` |
| AMQP | `RABBITMQ_ADDRESSES`, `REQUESTS_RABBITMQ_USERNAME/PASSWORD`, `NOTIFY_RABBITMQ_USERNAME/PASSWORD`, `ADMIN_RABBITMQ_USERNAME/PASSWORD` |
| Kafka | `KAFKA_BOOTSTRAP_SERVERS` |
| Pools JDBC | `DB_POOL_SIZE` (3 para Requests, Catalog y Report), `AUDIT_DB_POOL_SIZE` (2 para Audit) |
| Administración interna | `ADMIN_HTTP_USERNAME/PASSWORD`, `KAFKA_ADMIN_USERNAME/PASSWORD`. Cada contraseña requiere al menos 16 caracteres y admite hasta 72 bytes UTF-8. |

### ngrok, API Gateway y Amplify

Mantener el ngrok existente de RabbitMQ Management hacia `127.0.0.1:15672`, con OAuth, lista de usuarios permitidos y autenticación de RabbitMQ. Mantener el túnel protegido existente de Kafka UI hacia `127.0.0.1:8090`. Si el BFF aún requiere su túnel, configurar ngrok v3 en la red del host de Apps con un dominio HTTPS estable. Guardar la configuración del agente BFF en `/etc/ngrok/ngrok.yml`, fuera de Git y con modo `0600`. [Configuración de ngrok](https://ngrok.com/docs/gateway/traffic-policy/getting-started/agent-endpoints)

En Apps, usar esta configuración con un valor aleatorio privado que coincida con el que configura API Gateway. Mantener desactivada la captura de cabeceras sensibles. [Variables de petición y encabezados de ngrok](https://ngrok.com/docs/gateway/traffic-policy/variables/req)

```yaml
version: 3
agent:
  authtoken: REEMPLAZAR_CON_AUTHTOKEN_PRIVADO
  web_addr: false
endpoints:
  - name: bff
    url: https://bff.example.invalid
    upstream:
      url: http://127.0.0.1:8080
    traffic_policy:
      on_http_request:
        - expressions:
            - >-
              !('x-barriodigital-origin' in req.headers) ||
              req.headers['x-barriodigital-origin'] != ['REEMPLAZAR_CON_VALOR_PRIVADO']
          actions:
            - type: custom-response
              config: {status_code: 403, body: Forbidden}
        - actions:
            - type: remove-headers
              config:
                headers: [x-barriodigital-origin]
```

En Apps, validar e iniciar el agente BFF como servicio para conservarlo al cerrar SSM. Ejecutar `install` una vez si aún no está instalado. [ngrok como servicio](https://ngrok.com/docs/gateway/agent/service)

```bash
sudo ngrok config check --config /etc/ngrok/ngrok.yml
sudo ngrok service install --config /etc/ngrok/ngrok.yml
sudo ngrok service start
```

En la HTTP API existente, configurar `ANY /api/{proxy+}` con integración pública `HTTP_PROXY` de método `ANY` a `https://<dominio-ngrok-bff>`. Aplicar `overwrite:path` con `$request.path` y `overwrite:header.x-barriodigital-origin` con el mismo valor privado de la política. Conservar el encabezado `Authorization` para el BFF. El autorizador JWT toma `$request.header.Authorization`, usa `https://login.microsoftonline.com/<AZURE_TENANT_ID>/v2.0` y la audiencia `AZURE_API_AUDIENCE`. Usar el scope delegado del token de acceso en la ruta. Configurar CORS para el origen Amplify exacto, métodos `GET, POST, PUT, PATCH, DELETE, OPTIONS` y headers `Authorization, Content-Type, Accept`. Si existe una ruta `$default` autorizada, configurar `OPTIONS /{proxy+}` sin JWT para el preflight. [Mapeo HTTP API](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-parameter-mapping.html) · [Autorización JWT](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html) · [CORS](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-cors.html)

En Amplify conservar `VITE_AZURE_TENANT_ID`, `VITE_AZURE_CLIENT_ID`, `VITE_AZURE_API_SCOPE`, `VITE_AZURE_REDIRECT_URI` y `VITE_API_BASE_URL`. Usar en `VITE_API_BASE_URL` la URL base HTTPS de API Gateway con su stage si aplica y sin `/api`. Usar como retorno de Amplify una URI HTTPS que coincida exactamente con una URI SPA ya registrada en Entra. Si no se acredita esa coincidencia, detener la publicación de esa URL y reportar el bloqueo. El build existente usa `npm ci` y `npm run build`, publica `dist` y requiere reescritura SPA a `/index.html` para rutas de navegación. [Reescrituras de Amplify](https://docs.aws.amazon.com/amplify/latest/userguide/redirects.html)

Antes de dar por hecho el acceso externo, comprobar `/api/bff/me` mediante Gateway con token válido y esperar 200, repetir sin token y esperar 401, probar el preflight desde Amplify y verificar 403 al llamar directamente al ngrok del BFF sin el encabezado de origen. Comprobar el acceso autenticado y el rechazo sin credenciales en ambas consolas de mensajería.
