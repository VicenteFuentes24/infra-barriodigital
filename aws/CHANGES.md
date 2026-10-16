# Informe de cambios AWS EP3/EP4

Fecha: 2026-10-16. Workspace: `G:\Desarrollo EP3-EP4`.
Todos los repositorios estaban limpios al comenzar. No se hizo commit, staging,
push, reset, clean de Git, despliegue ni llamada a AWS. No se leyeron/copiaron
cookies reales ni se generaron credenciales de despliegue.

## Resultado

Implementado: preparacion AWS separada del entorno local, conexion AMQP multinodo,
health de Notify y documentacion por repositorio. Se conservan versiones,
endpoints, seguridad, contratos, ownership, reglas de negocio y persistencia.
El BFF/Admin no reciben una nueva integracion: no existe contrato obligatorio
para exponer administracion al frontend. El acceso de demostracion sera privado.

Validado localmente: compilaciones Java y pruebas siguientes, build Vite,
configuraciones Compose y salvaguardas de scripts. AWS NO ha sido validado.
Docker Desktop no tenia motor disponible (npipe dockerDesktopLinuxEngine ausente).
No se iniciaron contenedores ni se toco una instalacion previa.

## Pruebas ejecutadas

| Comando / proyecto | Resultado real |
| --- | --- |
| Requests: mvnw.cmd -B -ntp test | 43 pruebas, 0 fallos, 0 errores, 0 omitidas |
| Requests: mvnw.cmd -B -ntp clean package | BUILD SUCCESS; 43 pruebas, JAR generado |
| Notify: mvnw.cmd -B -ntp test | 40 pruebas, 0 fallos, 0 errores, 0 omitidas |
| Notify: mvnw.cmd -B -ntp clean package | BUILD SUCCESS; 40 pruebas, JAR generado |
| BFF: mvnw.cmd -B -ntp clean package | BUILD SUCCESS; 14 pruebas, 0 fallos/errores, JAR |
| Catalog: mvnw.cmd -B -ntp clean package | BUILD SUCCESS; 11 pruebas, 0 fallos/errores, JAR |
| RabbitMQ Admin: mvnw.cmd -B -ntp clean package | BUILD SUCCESS; 55 pruebas, 0 fallos/errores, JAR |
| python -m unittest discover -s aws/tests -v | 24 pruebas, todas OK, ninguna omitida en este entorno |
| Notify Docker HealthCheck: javac + java con servidor HTTP temporal | Compila Java 21; HTTP 200 -> exit 0; HTTP 503 -> exit 1 |
| Frontend: npm.cmd run build | TypeScript + Vite OK |
| git diff --check, siete repositorios | exit 0 en cada uno |
| bash -n aws/deploy.sh (Git Bash local) | Sintaxis OK; no se ejecuto el despliegue |
| Revision de nombres privados versionados | 0 .env reales/llaves/certificados/cookies entre los archivos trackeados revisados |

Total de la suite Java: **163 pruebas unicas**, todas aprobadas. Las ejecuciones
repetidas test/package NO se suman como pruebas diferentes. Infra aporta otras
24 pruebas y se hicieron dos comprobaciones del nuevo probe Java.
Las pruebas opt-in *IT de RabbitMQ NO fueron ejecutadas en esta adaptacion.
Las pruebas JPA usaron H2 de tests y las de seguridad JWT de tests, no Supabase
ni Entra reales. No hay nuevos mocks en produccion.

Compose valida Node1, Node2 y apps, asi como ambos Compose locales originales
con --no-env-resolution, sin leer sus .env privados. Es una validacion de modelo,
no una prueba de arranque de imagenes, DNS EC2 o conectividad AWS.

Avisos existentes: Mockito/ByteBuddy carga dinamica en tests Java 21,
H2Dialect explicito en tests, advertencia de annotation processing futura y
bundle Vite de unos 553 kB (>500 kB). No bloquean estas compilaciones y no se
refactorizan al no estar relacionados con AWS.

## Inventario exacto

41 archivos: 25 nuevos y 16 modificados.
Rutas relativas a la raiz del repositorio indicado. A = nuevo; M = modificado.
Archivos de build/temporales ignorados no son cambios para publicar.

### frontend-barriodigital

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| M | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |

### infra-barriodigital

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| A | `.gitattributes` | Preservar LF en scripts/configuracion AWS mantenidos desde Windows. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |
| A | `aws/.env.apps.example` | Plantilla de variables AWS sin secretos; no modifica .env reales. |
| A | `aws/.env.node1.example` | Plantilla de variables AWS sin secretos; no modifica .env reales. |
| A | `aws/.env.node2.example` | Plantilla de variables AWS sin secretos; no modifica .env reales. |
| A | `aws/compose.apps.yml` | Cinco microservicios y Mailpit; red privada, health, volumenes y limites. |
| A | `aws/compose.rabbitmq.common.yml` | Host networking EC2, UID999, cookie externa RO y datos persistentes. |
| A | `aws/compose.rabbitmq.node1.yml` | Identidad Erlang y direccion privada especificas de ese nodo. |
| A | `aws/compose.rabbitmq.node2.yml` | Identidad Erlang y direccion privada especificas de ese nodo. |
| A | `aws/deploy.py` | Validar/iniciar/verificar, unir solo nodo vacio e importar una vez sin sobrescribir drift. |
| A | `aws/deploy.sh` | Entrada Bash opcional al mismo script Python. |
| A | `aws/rabbitmq.conf` | Interfaces privadas AMQP/Erlang y Management solo loopback; sin redefinir topologia. |
| A | `aws/tests/test_deploy.py` | 24 pruebas de seguridad operativa, topologia y Compose sin motor ni AWS. |
| A | `aws/CHANGES.md` | Este inventario, resultados reales y riesgos pendientes. |

### ms-barriodigital-bff

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| M | `barriodigitalbff/.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |

### ms-barriodigital-catalog

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| M | `barriodigitalcatalog/.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |

### ms-barriodigital-notify

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `notify/.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| M | `notify/.env.example` | Documentar lista AMQP multinodo opcional, sin credenciales reales. |
| M | `notify/Dockerfile` | Compilar/incluir probe y declarar healthcheck; usuario/logica intactos. |
| M | `notify/src/main/resources/application.properties` | Agregar RABBITMQ_ADDRESSES opcional, manteniendo host/puerto locales. |
| A | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |
| A | `notify/docker/HealthCheck.java` | Probe HTTP Java para la imagen Notify, sin dependencias de curl/wget. |
| A | `notify/src/test/java/cl/barriodigital/notify/config/RabbitAddressConfigurationTest.java` | Tres pruebas de configuracion local/multinodo y contratos existentes. |

### ms-barriodigital-rabbitmq-admin

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `ms-barriodigital-rabbitmq-admin/.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| A | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |

### ms-barriodigital-requests

| Estado | Archivo | Motivo |
| --- | --- | --- |
| M | `.gitignore` | Excluir archivos privados de Git; conservar plantillas. |
| M | `barriodigitalrequests/.dockerignore` | Excluir llaves/certificados del contexto Docker sin cambiar el build. |
| M | `barriodigitalrequests/.env.example` | Documentar lista AMQP multinodo opcional, sin credenciales reales. |
| M | `barriodigitalrequests/src/main/resources/application.properties` | Agregar RABBITMQ_ADDRESSES opcional, manteniendo host/puerto locales. |
| A | `README.AWS.md` | Guia AWS del repositorio; variables, decisiones y operacion sin cambiar contratos. |
| A | `barriodigitalrequests/src/test/java/cl/barriodigital/barriodigitalrequests/config/RabbitAddressConfigurationTest.java` | Tres pruebas de configuracion local/multinodo y contratos existentes. |

## Checklist por repositorio

- [x] Infra: AWS separado de local, host-mode EC2, resolucion de ambos nodos,
  cookie existente externa, UID/GID, health/restart, importacion central guardada.
- [x] Requests: addresses opcional; confirms, returns, mandatory y AFTER_COMMIT
  intactos. No outbox, tablas, cambios en DTO ni rutas.
- [x] Notify: addresses opcional, volumen persistente y probe; consumidores,
  ACK/NACK, idempotencia, reintentos, DLQ, PDF/tickets y Mailpit intactos.
- [x] Admin: ya admite addresses/vhost; mantiene Basic, cuenta HTTP separada,
  X-Admin-Request, recursos reservados y sin puerto publico.
- [x] BFF: Entra issuer/audience/firma/vigencia/scopes/roles intactos; URLs Docker
  solo por variables de Compose; sin rutas administrativas inventadas.
- [x] Catalog: DB_* existentes, Docker/health; AWS valida esquema sin alterarlo.
- [x] Frontend: MSAL/UI intactos; variables de build Amplify documentadas sin
  reemplazar su configuracion remota. No llamadas directas a microservicios.
- [x] Todos: exclusiones de secretos revisadas; independencia de repos mantenida.

## Archivos criticos conservados

No cambiaron compose.yml, compose.rabbitmq.yml, rabbitmq/definitions.json,
Test-RabbitMQ.ps1, Compose locales de Notify/Admin, pom.xml, clases de negocio,
publicadores/consumidores existentes, clases de seguridad o componentes React.
Comprobacion SHA-256 de contenido original:

| Archivo infra | SHA-256 |
| --- | --- |
| rabbitmq/definitions.json | 679F1ADB614EE6EB5239EDB4632E9F11B3ABC6C5D908B264EFA3D62776CDA896 |
| compose.yml | B93A93C3ECB512434069048D613C3ACDB741073DD8EBFF6FA44452870CA95FF1 |
| compose.rabbitmq.yml | F0B8BD3B4A793DB2AC42C351D66CF449A8F89F6394F8AFE4BF1943CEBC321289 |

## Riesgos y pendientes manuales

1. Confirmar la integracion API Gateway actual antes de configurar bind BFF,
   stage/path, CORS y Amplify. No se crea VPC Link/ALB. La Elastic IP informada
   por el operador no se usa como dependencia fija ni como bind del SO.
2. Redimensionar apps por decision manual: t3.micro/1 GiB y EBS10 GiB no sirven
   para esta configuracion de cinco JVM. Se recomienda t3.large/8 GiB y EBS30-40
   GiB o mas segun uso. El script solo comprueba, no altera recursos AWS.
3. Verificar SG/rutas, IP privadas de ambos nodos, permisos de datos/cookie y
   ausencia de instalaciones duplicadas antes de arrancar. La IP publica NAT
   hace imprescindible el SG aun cuando el proceso enlace una interfaz privada.
4. Ejecutar arranque/union real en EC2; ambos nodos deben figurar running sin
   alarmas. Para reiniciar el cluster completo iniciar ambos en paralelo y
   esperar mayoria; no resetear ni usar force_boot por un timeout de salud.
5. Dos nodos y colas classic NO son HA completa. El cluster no replica sus
   mensajes; Khepri de dos miembros necesita ambos para mayoria. Failover de
   conexion NO garantiza disponibilidad de una cola alojada en un nodo caido.
6. AFTER_COMMIT no garantiza entrega ante crash entre DB y broker; no se agrego
   outbox por instruccion. Confirm/return fallidos siguen reportandose como antes.
7. AMQP y SMTP de demo no usan TLS dentro de la red prevista; revisar aislamiento
   de VPC/SG. No hay entrega a Internet desde Mailpit. Basic solo por acceso
   interno/tunel SSH, nunca en navegador Amplify ni expuesto al publico.
8. Probar las imagenes/health Docker reales, reconexion y flujo end-to-end con
   JWT, Supabase, PDF, correo, tickets, ACK/NACK/DLQ y volumenes persistentes.
   Los tests locales no sustituyen esa validacion. No ejecutar RequestRabbitBrokerIT
   sobre el broker AWS compartido: espera cola vacia y consume el mensaje de prueba.
9. Ledger de Notify se conserva local a UNA instancia; no habilitar multiples
   replicas sobre ese volumen. Persiste ventana de duplicado SMTP ante crash.
10. Report y Audit siguen pendientes: no se crean servicios ni datos falsos;
    BFF conserva sus respuestas 503 mientras no existan.
11. Problema PREEXISTENTE ajeno a AWS: compose.yml local usa
    ../frontend-barriodigial, pero la carpeta real es frontend-barriodigital.
    Su sintaxis valida, pero ese contexto no existe en este workspace. No se
    corrige automaticamente para conservar el entorno local solicitado.
12. Revisar valores externos reales, SSL/alcance IPv4 de Supabase y limites de
    conexiones. AWS usa JPA_DDL_AUTO=validate; si el esquema no coincide, parar
    y revisar manualmente, no habilitar una migracion automatica.

La guia [README.AWS.md](../README.AWS.md) contiene todas las variables sin
secretos, clones con los remotos reales, comandos Node1/Node2/apps, union e
importacion seguras, tuneles, pruebas AWS pendientes y comandos de commit/push
MANUALES por repositorio. Revisar antes de publicar. Nada se publica automaticamente.

