# BarrioDigital EP3/EP4: despliegue AWS reproducible

## Alcance y estado

Preparacion de repositorios, NO despliegue ejecutado. Region us-east-1 y VPC
10.0.0.0/16 existentes. No se ejecutan llamadas AWS, cambios de SG, commits ni push.
Mantener los siete repositorios separados y sus versiones Java/Spring actuales.
Los Compose locales y `rabbitmq/definitions.json` NO se reemplazan.

Arquitectura: Amplify/React -> API Gateway -> BFF -> Requests/Catalog -> Supabase.
Requests -> RabbitMQ privado -> Notify -> Mailpit/PDF/tickets. RabbitMQ Admin es
una API interna con Basic, no un endpoint del navegador. Report/Audit no se crean.

| Repositorio | Ya preparado | Ajuste AWS |
| --- | --- | --- |
| infra | Compose local, RabbitMQ y topologia central | Compose separados, scripts y plantillas AWS |
| requests | Supabase, eventos AFTER_COMMIT, confirms/returns | Lista AMQP multinodo; HTTP/entidades intactos |
| notify | ACK/NACK, retry, DLQ, ledger, PDF, tickets, Mailpit | Lista AMQP, health de imagen y volumen AWS |
| rabbitmq-admin | addresses, Basic, validaciones, health interno | Solo documentacion/exclusiones; Java intacto |
| bff | JWT Entra completo, scopes/roles, proxy configurable | URLs Docker en Compose; Java intacto |
| catalog | Supabase, variables, Docker y health | Compose con schema validate; Java intacto |
| frontend | MSAL y VITE_* | Documentar variables/build de Amplify; UI intacta |

Lista exacta de archivos, resultados y motivos: [informe](aws/CHANGES.md).
Cada repositorio contiene tambien `README.AWS.md`.

## Requisitos y capacidad

En cada EC2 Amazon Linux 2023: Docker Engine, Compose V2 (2.20+), Git, Python 3.9+
y permisos para Docker. Python usa solo biblioteca estandar, no agrega servicios.
Ejecutar Docker como usuario autorizado; no exponer el socket por TCP.
Los scripts se invocan con python3: no dependen de permisos ejecutables ni CRLF.

```bash
docker version
docker compose version
git --version
python3 --version
```

Para las cinco JVM + Mailpit se recomienda **t3.large (8 GiB)** y al menos
30-40 GiB EBS, ajustando segun imagenes, PDFs y retencion. Los limites configurados
suman unos 3.3 GiB, ademas de SO, memoria nativa, cache y compilacion. Los builds se
hacen en serie. El script exige host de clase 8 GiB (>=6 GiB detectables) y 15 GiB
libres antes de compilar; no redimensiona nada. t3.micro tiene 1 GiB y el EBS
historico de 10 GiB es insuficiente para esta configuracion. t3.medium (4 GiB)
seria ajustado incluso con imagenes precompiladas y no es el objetivo del script.
Los t3.small RabbitMQ existentes tienen 2 GiB; revisar alarmas/disco y CPU creditos.
No se promete rendimiento de produccion con estos tamanos.
Referencia: [tipos EC2](https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html).

## Clonar desde GitHub

Antes de estos pasos, revisar y publicar MANUALMENTE cada repositorio desde el
equipo de desarrollo. En cada nodo RabbitMQ solo hace falta infra:

```bash
mkdir -p ~/barriodigital-src
cd ~/barriodigital-src
git clone https://github.com/VicenteFuentes24/infra-barriodigital.git
cd infra-barriodigital
```

En la EC2 apps, clonar todos como hermanos, sin crear un monorepositorio:

```bash
mkdir -p ~/barriodigital-src
cd ~/barriodigital-src
git clone https://github.com/VicenteFuentes24/infra-barriodigital.git
git clone https://github.com/VicenteFuentes24/ms-barriodigital-bff.git
git clone https://github.com/VicenteFuentes24/ms-barriodigital-requests.git
git clone https://github.com/VicenteFuentes24/ms-barriodigital-catalog.git
git clone https://github.com/VicenteFuentes24/ms-barriodigital-notify.git
git clone https://github.com/VicenteFuentes24/ms-barriodigital-rabbitmq-admin.git
# Solo necesario si se quiere una copia local; Amplify utiliza su repo conectado.
git clone https://github.com/VicenteFuentes24/frontend-barriodigial.git frontend-barriodigital
cd infra-barriodigital
```

Si una carpeta ya existe, NO volver a clonar encima, borrar ni resetear. Revisar
`git status` en cada repo y actualizar solo con los cambios propios resguardados.
Registrar `git rev-parse HEAD` de cada uno para repetir una version concreta;
los tags de imagen base existentes no convierten un build en bit-a-bit inmutable.

## Variables y archivos privados

Plantillas: `aws/.env.node1.example`, `aws/.env.node2.example`, `aws/.env.apps.example`.
Solo editar los archivos .env copiados; NO es necesario editar YAML en EC2.
Los secretos se ingresan localmente, nunca en Git ni en VITE_*. Usar comillas
simples en valores .env con `$`, `#` o espacios para evitar interpolacion Compose.
No ejecutar `set -x`, ni compartir `docker compose config` sin --quiet: imprime
credenciales. El script captura esa configuracion internamente sin mostrarla.

| Destino | Variables requeridas |
| --- | --- |
| RabbitMQ (ambos) | RABBITMQ_NODE1_PRIVATE_IP, RABBITMQ_NODE2_PRIVATE_IP, RABBITMQ_DATA_DIR, RABBITMQ_COOKIE_FILE, RABBITMQ_DEFAULT_USER, RABBITMQ_DEFAULT_PASS |
| BFF | AZURE_TENANT_ID, AZURE_API_AUDIENCE, FRONTEND_ORIGIN |
| Requests DB | REQUESTS_DB_URL, REQUESTS_DB_USERNAME, REQUESTS_DB_PASSWORD |
| Catalog DB | CATALOG_DB_URL, CATALOG_DB_USERNAME, CATALOG_DB_PASSWORD |
| AMQP apps | RABBITMQ_ADDRESSES, REQUESTS_RABBITMQ_USERNAME/PASSWORD, NOTIFY_RABBITMQ_USERNAME/PASSWORD, ADMIN_RABBITMQ_USERNAME/PASSWORD |
| Admin HTTP | ADMIN_HTTP_USERNAME, ADMIN_HTTP_PASSWORD (distintos del broker, minimo 16 caracteres, maximo 72 bytes UTF-8) |
| Frontend Amplify | VITE_AZURE_TENANT_ID, VITE_AZURE_CLIENT_ID, VITE_AZURE_API_SCOPE, VITE_AZURE_REDIRECT_URI, VITE_API_BASE_URL |

Opcionales con defaults en las plantillas: RABBITMQ_IMAGE, BFF_BIND_ADDRESS,
BFF_PORT, DB_POOL_SIZE, SMTP_FROM, NOTIFY_MAX_ATTEMPTS, NOTIFY_RETRY_DELAY_MS,
NOTIFY_VOLUME_NAME, MAILPIT_VOLUME_NAME, MAILPIT_UI_PORT, MAILPIT_MAX_MESSAGES,
AWS_APPS_NETWORK_NAME, REPORT_SERVICE_URL, AUDIT_SERVICE_URL. Los tags de imagen
de aplicaciones se pueden cambiar con BFF_IMAGE, REQUESTS_IMAGE, CATALOG_IMAGE,
NOTIFY_IMAGE, RABBITMQ_ADMIN_IMAGE; MAILPIT_IMAGE selecciona su version.
Vhost fijado a barriodigital en AWS; no se cambia la topologia.

Las cuentas AMQP pueden ser cuentas existentes; se recomienda separarlas por
responsabilidad y permisos minimos. Este despliegue no crea usuarios adicionales
ni altera permisos existentes. DEFAULT_USER/PASS solo inicializan un nodo nuevo;
NO cambian la cuenta de un volumen ya inicializado. Los scripts de topologia
necesitan la cuenta administradora existente de Management y nunca muestran su valor.

## Preparar los nodos RabbitMQ

Cada archivo de nodo configura su identidad y utiliza host networking de Linux:
no NAT Docker entre EC2, nodenames estables y extra_hosts para ambas IP privadas.
AMQP, distribucion Erlang y EPMD se limitan a IP privada. Management solo loopback.
No ejecutar esta configuracion EC2 host-mode como reemplazo del entorno Windows local.
En EC2, una IP publica se traduce por NAT hacia la interfaz privada: el bind
privado NO reemplaza las restricciones del SG. Verificar AMQP/Erlang sin acceso
publico antes de arrancar. Este cambio no modifica Security Groups.

En node1, desde el checkout infra:

```bash
test -f aws/.env.node1 || (umask 077; cp aws/.env.node1.example aws/.env.node1)
chmod 600 aws/.env.node1
# Completar aws/.env.node1 con los valores existentes (editor local).
```

En node2, usar respectivamente `.env.node2.example` y `.env.node2`.
IPs privadas iniciales configurables: node1 10.0.1.62, node2 10.0.2.151.
No utilizar las IP publicas como direcciones Erlang/AMQP.

El directorio por defecto de cada host es `/home/ec2-user/barriodigital-rabbitmq/data`.
Prepararlo SOLO si todavia no existe; si se eligio otro path, usarlo tambien aqui:

```bash
DATA_DIR=/home/ec2-user/barriodigital-rabbitmq/data
if [ ! -d "$DATA_DIR" ]; then
  sudo install -d -m 0700 -o 999 -g 999 "$DATA_DIR"
fi
sudo stat -c '%u:%g %a %n' "$DATA_DIR"
```

`RABBITMQ_COOKIE_FILE` debe apuntar a la cookie COMPARTIDA YA EXISTENTE, fuera
del checkout Git. Puede estar en el mismo data/.erlang.cookie si ya existe alli.
Debe tener propietario/grupo 999:999 y modo 0400 o 0600. No copiar el contenido
a .env, no pasarlo por linea de comandos, no generarlo de nuevo y no imprimirlo.
Si permisos/propietario no coinciden, revisar y corregir SOLO el archivo correcto
manualmente, tras verificar el path; no ejecutar chown recursivo sobre datos existentes.

Antes del primer arranque: respaldar datos existentes, revisar nodename anterior,
detener productores/consumidores y asegurar que no hay otro broker usando esos
puertos o datos. Los scripts rechazan reutilizar directorios de otro nodename
o compartidos con otro contenedor en ejecucion. NO paran contenedores desconocidos.
Si existe una instalacion manual previa, la migracion del proceso debe revisarse
manualmente antes de iniciar Compose; nunca arrancar dos brokers sobre el mismo data.
Usar sudo para que el preflight pueda inspeccionar directorios privados de UID 999;
el CONTENEDOR sigue ejecutandose como 999:999, sin capacidades adicionales.

## Iniciar Node 1 y Node 2

Comandos en **Node 1**, desde infra-barriodigital:

```bash
sudo python3 aws/deploy.py node1 validate
sudo python3 aws/deploy.py node1 start
sudo python3 aws/deploy.py node1 ps
```

Comandos en **Node 2**:

```bash
sudo python3 aws/deploy.py node2 validate
sudo python3 aws/deploy.py node2 start
sudo python3 aws/deploy.py node2 ps
```

Alternativa equivalente: `sudo bash aws/deploy.sh node1 start`.
La operacion start espera healthy y no importa definiciones automaticamente.
No arrancar aplicaciones hasta completar la union y comprobar topologia.
En un cluster ya formado, si ambos nodos estaban apagados, iniciar ambos desde
dos sesiones SSH en paralelo: el primer nodo puede esperar al segundo para
recuperar mayoria Khepri. Un timeout healthy no justifica reset ni force_boot.

## Union segura del cluster

Node1 es la fuente autoritativa. Node2 debe ser nuevo, sin colas, exchanges
personalizados, bindings, politicas ni usuarios ajenos al bootstrap. Si contiene
datos o configuraciones, la union se RECHAZA: requiere plan manual de migracion.
Mantener trafico detenido durante estas comprobaciones para evitar una carrera.

En **Node 2**, confirmar expresamente que es el nodo vacio:

```bash
sudo python3 aws/deploy.py node2 join --confirm-empty-node2
sudo python3 aws/deploy.py node2 verify
```

El script comprueba que node1 sea un seed sano de un solo nodo, que node2 este
vacio y que la cookie/DNS/red permitan el contacto. Ejecuta join_cluster vivo,
sin stop_app/reset: RabbitMQ 4.1+ ya no los necesita. Si ambos ya estan unidos,
solo verifica. No usa force_boot, forget_cluster_node ni borra almacenamiento.
Referencia: [union en RabbitMQ 4.x](https://www.rabbitmq.com/docs/clustering).

Despues, en **Node 1**:

```bash
sudo python3 aws/deploy.py node1 verify
sudo python3 aws/deploy.py node1 topology --apply
```

verify comprueba ambos nodos running, membresia exacta y ausencia de alarmas/
particiones, y muestra `rabbitmqctl cluster_status`. topology compara la definicion
real antes de importar: usa el `rabbitmq/definitions.json` ORIGINAL una sola vez
si faltan todos los recursos del proyecto. Si ya coinciden, no importa nada.
Si hay diferencias o recursos parciales, aborta sin sobrescribirlos.

Se conservan cmd.direct/direct, cmd.topic/topic, cmd.dead.dlx/direct; 3 colas
principales classic + 3 DLQ; 9 bindings y 3 politicas DLX existentes. Ningun
servicio redefine politicas ni agrega argumentos DLX contradictorios.

Repetir posteriormente sin --apply para validar sin importar:

```bash
sudo python3 aws/deploy.py node1 topology
```

IMPORTANTE: dos nodos NO proporcionan HA completa. Los mensajes de colas classic
no se replican por pertenecer al cluster. addresses permite reconectar a otro
nodo, pero una cola alojada en el nodo caido puede seguir indisponible. Con Khepri
dos miembros requieren ambos para mantener mayoria de metadata; no se promete
tolerancia a perdida de un nodo ni se cambian tipos de cola o estrategias de
particion. Las opciones antiguas de particion Mnesia no solucionan esto en Khepri.
Referencia: [metadata y clustering](https://www.rabbitmq.com/docs/metadata-store/clustering).

## Management sin exposicion publica

Desde el computador del operador, configurar RMQ_NODE1_SSH_HOST con el DNS/IP
SSH actual, no con una dependencia fija del codigo:

```bash
ssh -N -L 15672:127.0.0.1:15672 ec2-user@"$RMQ_NODE1_SSH_HOST"
```

Abrir http://localhost:15672 con la cuenta RabbitMQ existente. Para node2 usar
puerto local 15673 y destino 127.0.0.1:15672 en su propia EC2.
Si se necesita llave SSH, indicar `-i` con un archivo privado EXTERNO a Git.
No abrir 15672/5672 a Internet ni modificar SG desde estos scripts.

## Desplegar las cinco aplicaciones

En la EC2 apps con los repos hermanos clonados:

```bash
cd ~/barriodigital-src/infra-barriodigital
test -f aws/.env.apps || (umask 077; cp aws/.env.apps.example aws/.env.apps)
chmod 600 aws/.env.apps
# Completar el .env local. No modificar YAML ni copiar secretos al repositorio.
python3 aws/deploy.py apps validate
python3 aws/deploy.py apps start
python3 aws/deploy.py apps ps
```

start compila en serie, crea/actualiza contenedores y espera healthy. Conserva
volumenes existentes. No borra datos, no hace down -v, no cambia Supabase ni AWS.
Cambiar valores requiere repetir start; no es necesario editar Compose.
La actualizacion puede causar interrupciones breves: no es rolling deployment.
Antes del primer start, comprobar conflictos con los contenedores de la evaluacion
anterior; no se detienen automaticamente. Mantener un respaldo y un plan manual
de cambio del BFF anterior al nuevo, sin ejecutar ambos en el mismo puerto.

La red Docker es privada por ausencia de puertos de host, con salida para
Supabase, Entra y RabbitMQ. Requests/Catalog solo exponen puertos entre servicios;
Notify/Admin no son publicos. No se usa internal:true porque bloquearia esas salidas.
La persistencia de Notify y Mailpit usa volumenes nombrados configurables.
Respaldar volumenes y revisar almacenamiento/retencion; no cambiar sus nombres
para una actualizacion ni arrancar multiples Notify sobre el mismo ledger.
Mailpit es solo de demostracion, no un proveedor de entrega de correo externa.
Docker restart unless-stopped reinicia procesos terminados, no contenedores
que permanecen ejecutandose con health unhealthy. Revisarlos con ps/inspeccion.

## API Gateway, Amplify y entrada BFF

El operador informa una Elastic IP historica de apps, pero la integracion HTTP
publica de API Gateway todavia NO esta verificada. No se consulta ni cambia AWS.
Antes del despliegue confirmar URI, puerto, metodo, stage, path /api, headers
Authorization y OPTIONS/CORS. No crear VPC Link ni ALB en esta fase.

`BFF_BIND_ADDRESS` inicia en 127.0.0.1. Con la integracion HTTP publica existente,
configurarlo con la IP PRIVADA de la interfaz EC2 o 0.0.0.0, y verificar el SG
restringido manualmente. La Elastic IP pertenece a NAT de AWS, no a la interfaz
del SO: no usarla como direccion de bind. Nunca publicar otros microservicios.
El acceso directo al BFF sigue requiriendo JWT; una integracion publica por IP
no garantiza por si sola que todo acceso provenga exclusivamente de API Gateway.
Revisar esta limitacion y el tramo Gateway->EC2 antes de usar datos sensibles.

Amplify conserva su aplicacion/configuracion existente. Variables y pasos en
README.AWS.md del frontend. VITE_API_BASE_URL debe ser Gateway HTTPS con su stage
si aplica, sin /api final; VITE_AZURE_REDIRECT_URI debe coincidir con el redirect
SPA registrado. FRONTEND_ORIGIN del BFF debe coincidir con el origen Amplify.
No se modifica Entra, no hay client secret y no se agregan credenciales Basic al navegador.

## Comprobaciones operativas

Desde apps, estos comandos solo consultan estado/salud:

```bash
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml ps
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T requests wget -qO- http://localhost:8081/actuator/health
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T catalog wget -qO- http://localhost:8082/actuator/health
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T bff wget -qO- http://localhost:8080/api/bff/health
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T notify java -cp /app/health HealthCheck
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T rabbitmq-admin java -cp /app/healthcheck HealthCheck
```

Mailpit UI via SSH: `ssh -N -L 8025:127.0.0.1:8025 ec2-user@"$APPS_SSH_HOST"`.
Abrir http://localhost:8025. Para una inspeccion del volumen Notify, desde apps:

```bash
docker compose --env-file aws/.env.apps -f aws/compose.apps.yml exec -T notify find /app/data -type f
```

No publicar contenidos de PDF/tickets/ledger, pueden incluir datos personales.
Para acceder privadamente a Admin desde Thunder Client, obtener su IP actual
en apps (solo es diagnostico; no guardar esta IP en configuraciones):

```bash
ADMIN_CONTAINER=$(docker compose --env-file aws/.env.apps -f aws/compose.apps.yml ps -q rabbitmq-admin)
docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$ADMIN_CONTAINER"
```

Con esa IP como ADMIN_CONTAINER_IP, desde el PC:
`ssh -N -L 18088:"$ADMIN_CONTAINER_IP":8088 ec2-user@"$APPS_SSH_HOST"`.
Thunder usa http://localhost:18088 y su cuenta Basic interna; mutaciones requieren
X-Admin-Request: true. El tunel no publica el puerto 8088 en EC2. Ver README
original de Admin para contratos y nombres permitidos. No manipular recursos cmd.*.

## Pruebas y limites de validacion

Pruebas de infra, sin motor Docker y sin AWS:

```bash
python3 -m unittest discover -s aws/tests -v
```

Comprueban configuraciones reales con Compose CLI, nombres, bindings/politicas,
rechazo de drift/union con datos, secretos separados, SSL DB, puertos y volumenes.
La comprobacion opcional del Compose LOCAL usa --no-env-resolution (Compose 2.30+)
para no cargar archivos privados. El despliegue normal no necesita esa opcion;
la CLI local utilizada en esta adaptacion la soporta.
Maven en cada carpeta interna: `./mvnw -B -ntp clean package`
(Windows: `.\mvnw.cmd -B -ntp clean package`). Frontend: `npm ci` y `npm run build`.
Los resultados realmente ejecutados y limitaciones estan en `aws/CHANGES.md`.

Pendiente en AWS, marcar solo al ejecutarlo:

- [ ] Confirmar API Gateway HTTP publico actual, URI/stage/path/CORS/Authorization y bind BFF.
- [ ] Verificar manualmente SG: 4369/25672 entre nodos; 5672 solo desde apps; 15672 sin Internet; SSH restringido.
- [ ] Verificar DNS extra_hosts, cookie existente y UID/GID; no hay broker duplicado ni datos sin respaldo.
- [ ] Arrancar ambos nodos, unir node2 vacio y obtener cluster_status con ambos running, sin alarmas/particiones.
- [ ] Verificar 3 exchanges, 6 colas classic, 9 bindings, 3 politicas y vhost original, sin redeclaracion.
- [ ] Validar acceso AMQP privado desde apps y permisos de las cuentas; salida SSL Supabase y Entra/JWK.
- [ ] Verificar las cinco aplicaciones healthy, Mailpit listo y puertos internos no publicados.
- [ ] Desde Amplify: login existente, me con JWT+scope, 401 sin JWT y 403 con rol/scope insuficiente.
- [ ] Mantener ownership Cliente, acceso Operador/Admin y permisos de Catalog actuales.
- [ ] Crear tramite REAL con procedimiento existente: persistencia + certificate.gen posterior al commit.
- [ ] Comprobar ADMITIDO/email, EN_TERRENO/ticket y RESUELTO/email+PDF; invalidas no publican.
- [ ] Verificar ACK, reintentos limitados, NACK y DLQ solo con pruebas aisladas, no inyectar payload invalido en produccion.
- [ ] Reiniciar Notify de forma controlada y comprobar persistencia/idempotencia, sin borrar volumen.
- [ ] Medir memoria, CPU creditos y disco. Realizar pruebas de fallo solo en entorno de ensayo con respaldo.

No ejecutar RequestRabbitBrokerIT en el broker compartido con datos o Notify:
su contrato exige cola certificate vacia y consume el mensaje de prueba. Notify/
Admin tienen pruebas opt-in aisladas que necesitan Management y servicios reales;
revisar sus READMEs. No afirmar HA por una simple reconexion a otro nodo.

## Publicacion manual por repositorio

Todavia NO se hizo commit ni push. Revisar el informe, luego en PowerShell usar
los bloques siguientes uno por uno. Antes de cada commit inspeccionar
`git diff --cached` y confirmar que solo estan los archivos esperados. Las .env
reales, cookies, llaves y certificados deben seguir ignorados. No usar git add -f.

```powershell
cd 'G:\Desarrollo EP3-EP4\infra-barriodigital'
git status --short
git add -- .gitignore .gitattributes README.AWS.md aws
git diff --cached --check
git diff --cached --stat
# Despues de revisar el diff completo:
git commit -m "Prepare separate reproducible AWS deployment"
git push origin main

cd 'G:\Desarrollo EP3-EP4\ms-barriodigital-requests'
git add -- .gitignore README.AWS.md barriodigitalrequests/.dockerignore barriodigitalrequests/.env.example barriodigitalrequests/src/main/resources/application.properties barriodigitalrequests/src/test/java/cl/barriodigital/barriodigitalrequests/config/RabbitAddressConfigurationTest.java
git diff --cached --check
git diff --cached
git commit -m "Support private RabbitMQ node addresses for AWS"
git push origin main

cd 'G:\Desarrollo EP3-EP4\ms-barriodigital-notify'
git add -- .gitignore README.AWS.md notify/.dockerignore notify/.env.example notify/Dockerfile notify/docker/HealthCheck.java notify/src/main/resources/application.properties notify/src/test/java/cl/barriodigital/notify/config/RabbitAddressConfigurationTest.java
git diff --cached --check
git diff --cached
git commit -m "Prepare Notify connection and image health for AWS"
git push origin main

cd 'G:\Desarrollo EP3-EP4\ms-barriodigital-rabbitmq-admin'
git add -- .gitignore README.AWS.md ms-barriodigital-rabbitmq-admin/.dockerignore
git diff --cached --check
git diff --cached
git commit -m "Document internal AWS RabbitMQ Admin deployment"
git push origin main

cd 'G:\Desarrollo EP3-EP4\ms-barriodigital-bff'
git add -- .gitignore README.AWS.md barriodigitalbff/.dockerignore
git diff --cached --check
git diff --cached
git commit -m "Document existing secure BFF deployment for AWS"
git push origin main

cd 'G:\Desarrollo EP3-EP4\ms-barriodigital-catalog'
git add -- .gitignore README.AWS.md barriodigitalcatalog/.dockerignore
git diff --cached --check
git diff --cached
git commit -m "Document existing Catalog deployment for AWS"
git push origin main

cd 'G:\Desarrollo EP3-EP4\frontend-barriodigital'
git add -- .gitignore .dockerignore README.AWS.md
git diff --cached --check
git diff --cached
git commit -m "Document existing Amplify and MSAL configuration"
git push origin main
```

Cada push corresponde a SU remoto, no al de infra. Si aparecen cambios de otra
persona o una rama distinta a main, detenerse y revisar antes de publicar.
Actualizar una EC2 requiere ejecutar estos pasos manuales; no hay despliegue
automatico ni credenciales AWS dentro de los repositorios.
