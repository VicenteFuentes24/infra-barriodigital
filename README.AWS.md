# BarrioDigital EP3/EP4: despliegue AWS reproducible

## Alcance y estado de implementacion (17 de octubre de 2026)

**Despliegue ejecutado y probado en AWS Academy Learner Lab (us-east-1).**
Este documento registra la arquitectura que se utilizo para BarrioDigital EP3/EP4,
su estado observado y las instrucciones para reproducirla o recuperarla.
No es un manual de aprovisionamiento automatico de EC2/VPC/API Gateway:
esos recursos se crearon y configuraron desde AWS por separado.

| Elemento | Implementacion comprobada |
| --- | --- |
| Red | VPC `10.0.0.0/16`; comunicacion entre las EC2 mediante IP privadas |
| Apps | EC2 `barriodigital-apps`, t3.large, IP privada `10.0.1.154`, Elastic IP `35.172.253.68` |
| Apps/Compose | `aws/compose.apps.yml`: **BFF, Requests, Catalog, Notify, RabbitMQ Admin y Mailpit**; los seis servicios observados `healthy` |
| RabbitMQ | EC2 `rabbitmq-node1` (`10.0.1.62`) y `rabbitmq-node2` (`10.0.2.151`), t3.small; RabbitMQ 4.3.6 en cluster |
| Mensajeria | Vhost `barriodigital`; `cmd.direct`, `cmd.topic`, `cmd.dead.dlx`; tres colas principales, tres DLQ y nueve bindings |
| Identidad | Microsoft Entra ID; frontend React + MSAL en AWS Amplify |
| Entrada API | HTTP API Gateway `BarrioDigitalAPI`, ruta `ANY /api/{proxy+}` con JWT authorizer hacia el BFF |
| Comprobacion funcional | Tramites creados/cambiados de estado, eventos consumidos por Notify (ACK de `certificate.gen` y `email.send`) y prueba aislada de enrutamiento a DLQ |
| Recuperacion | Tras detener el laboratorio se iniciaron manualmente las tres EC2; Docker recupero los contenedores y se verificaron backend y AMQP |

El frontend esta disponible en:
`https://main.d4hq4m0hivkvs.amplifyapp.com/`.
El endpoint de API Gateway utilizado es:
`https://2b9x0ufr0e.execute-api.us-east-1.amazonaws.com/`.
Una solicitud sin token a `/api/bff/me` devolvio HTTP 401; el frontend
con sesion iniciada completo flujos funcionales contra el backend.
La comprobacion HTTP explicita de aceptacion de un token valido se debe
conservar como evidencia separada en la presentacion.

**No se debe confundir cluster con replicacion:** las seis colas son `classic`
y estan alojadas en node1. La pertenencia de node2 al cluster **no** asegura
alta disponibilidad de esas colas ante una caida de node1 ni quorum de metadata
si queda un unico miembro disponible.

### Codigo e infraestructura que se mantienen separados

La carpeta `aws/` contiene los Compose y scripts de despliegue para este entorno.
No reemplaza `compose.rabbitmq.yml`, `compose.yml` ni
`rabbitmq/definitions.json`, que se conservan para uso local.
Los siete repositorios siguen separados; las versiones reales y los historiales
de GitHub deben verificarse de forma independiente antes de entregar.
Los scripts nunca deben usarse para resetear un cluster existente por un fallo
de inicio ni para modificar datos sin respaldo. Para el detalle historico de
los archivos preparados, consultar [`aws/CHANGES.md`](aws/CHANGES.md).

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

Los ejemplos siguientes sirven para reproducir el despliegue en nuevas EC2.
En la instalacion actual los repositorios ya se encuentran clonados.
Verificar los commits publicados antes de utilizar estos comandos;
en cada nodo RabbitMQ solo se requiere infraestructura:

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

## RabbitMQ Management: acceso web protegido y alternativa SSH

El servicio de Management en **node1** escucha en `127.0.0.1:15672`.
Su puerto `15672` **no esta expuesto directamente** mediante el Security Group.
Para facilitar la demostracion de EP4 se configuro, de forma separada de los
Compose del repositorio, el contenedor `barriodigital-ngrok` en node1:

- URL estable: `https://juror-rumor-revision.ngrok-free.dev/`.
- Acceso HTTPS autenticado con Google OAuth y lista de correos autorizados;
  despues es necesario el usuario y contrasena propios de RabbitMQ.
- Contenedor de ngrok con `restart: unless-stopped`; su token y politica de
  acceso son privados y **no se versionan en Git**.
- La autenticacion por OAuth se observo en funcionamiento. **Queda pendiente**
  probar expresamente el rechazo de una cuenta Google no autorizada y la
  recuperacion de ngrok luego de un reinicio completo de node1.
- No publicar `5672`, `15672`, cookies, credenciales de Management ni el
  authtoken de ngrok en repositorios, capturas o diapositivas.

Para diagnostico de ngrok **en node1**:

```bash
sudo docker ps --filter name=barriodigital-ngrok
sudo docker inspect -f 'Estado={{.State.Status}} Reinicios={{.RestartCount}}' barriodigital-ngrok
sudo docker logs --since 5m --tail 30 barriodigital-ngrok
```

**Respaldo por SSH (si no funciona el acceso web):** desde un equipo con
acceso autorizado y llave privada, el operador puede crear un tunel hacia
node1 con su IP SSH publica actual (esa IP puede cambiar tras Stop/Start):

```bash
ssh -N -L 15672:127.0.0.1:15672 -i /ruta/privada/llave.pem ec2-user@IP_PUBLICA_ACTUAL_NODE1
```

Abrir `http://localhost:15672/`. No se debe agregar `15672` como puerto
publico del SG para solucionar una falla del tunel.

## Desplegar las cinco aplicaciones

En la EC2 apps, con los repos hermanos clonados. En el despliegue
real la infraestructura quedo en `/opt/barriodigital/infra-barriodigital`
y los `.env` reales se mantienen fuera de Git:

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

**Integracion utilizada durante EP4, ya comprobada:**

- API: `BarrioDigitalAPI`, ID `2b9x0ufr0e`, HTTP API en `us-east-1`.
- Ruta de aplicacion: `ANY /api/{proxy+}` con autorizador JWT (issuer/audience
  correspondientes a Microsoft Entra ID). El preflight OPTIONS se atiende sin JWT.
- Integracion HTTP publica configurada con el destino
  `http://35.172.253.68:8080/api/{proxy}`; la Elastic IP de apps permanece
  asociada tras Stop/Start.
- El BFF escucha en el puerto 8080 de la EC2. El valor de
  `BFF_BIND_ADDRESS` debe ser la IP **privada** de la interfaz EC2 (`10.0.1.154`
  en esta instalacion) y no la Elastic IP publica (AWS aplica NAT).
- `https://2b9x0ufr0e.execute-api.us-east-1.amazonaws.com/api/bff/me`
  sin token respondio HTTP 401. La interfaz de Amplify completo flujos
  autenticados; documentar aparte una respuesta HTTP 200 con JWT valido para
  cubrir la demostracion formal del autorizador.

**Consideracion de seguridad:** el BFF tambien puede ser alcanzable directamente
mediante su puerto publico segun las reglas actuales del SG. El BFF vuelve a
validar JWT, pero el hecho de usar API Gateway no prueba que toda solicitud
publica llegue exclusivamente a traves del Gateway. No afirmar que los
microservicios internos esten disponibles publicamente. Si se desea cerrar
ese acceso directo, planificar otra arquitectura (p. ej., VPC Link/ALB) y
probarla antes de una evaluacion; no cambiarla a ultima hora.

El frontend React + Vite esta desplegado en AWS Amplify:
`https://main.d4hq4m0hivkvs.amplifyapp.com/`.
Utiliza MSAL y variables `VITE_*` para tenant, registro de frontend, scope,
redirect y URL de API Gateway. No incluir client secrets ni contrasenas en
`VITE_*`, en README o en el navegador.

Ni los scripts del repositorio ni los Compose aprovisionan las EC2, VPC,
Security Groups, Entra, Amplify o API Gateway automaticamente.

## Comprobaciones operativas y evidencia de EP4

### Aplicaciones (EC2 `barriodigital-apps`)

Ejecutar en la EC2 Apps:

```bash
cd /opt/barriodigital/infra-barriodigital
sudo docker compose --env-file aws/.env.apps -f aws/compose.apps.yml ps -a
curl -sS -o /dev/null -w 'BFF HTTP %{http_code}\n' http://10.0.1.154:8080/actuator/health
sudo docker compose --env-file aws/.env.apps -f aws/compose.apps.yml logs --since=20m --tail=100 notify
```

Tras el reinicio completo del laboratorio se observaron seis contenedores
`healthy` y BFF HTTP 200. Los logs de Notify registraron eventos finalizados:
`ACK command=certificate.gen ... result=completed` y
`ACK command=email.send ... result=completed`.

### Cluster RabbitMQ y topologia (en node1)

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}'
sudo docker exec barriodigital-rabbitmq-aws-node1-rabbitmq-1 rabbitmqctl cluster_status
sudo docker exec barriodigital-rabbitmq-aws-node1-rabbitmq-1 rabbitmqctl -q -p barriodigital list_queues --local name state messages
```

En la UI Management, comprobar:

1. **Overview -> Nodes**: `rabbit@rabbitmq-node1` y `rabbit@rabbitmq-node2`.
2. **Queues and Streams**: `q.cmd.email`, `q.cmd.crew`, `q.cmd.certificate`
   y sus respectivas `.dlq`, todas en estado `running`.
3. **Exchanges**: `cmd.direct` y `cmd.topic`, mas `cmd.dead.dlx` para errores.
4. **Bindings**: tres claves exactas para `cmd.direct`, tres patrones para
   `cmd.topic` y tres rutas hacia las DLQ desde `cmd.dead.dlx`.

Las capturas de pantalla de estas vistas respaldan la demostracion. Que la
cola este vacia (cero mensajes) despues de consumir correctamente es normal.
Una captura de colas existentes **no sustituye** una prueba de DLQ: se realizo
una prueba controlada con colas temporales y se comprobo la llegada del mensaje
a su DLQ, seguida de la eliminacion de recursos de prueba.

### RabbitMQ Admin

API REST interna en el contenedor `rabbitmq-admin`, Basic Auth separada de AMQP
y encabezado `X-Admin-Request: true` para mutaciones. En AWS se ejecutaron
11 comprobaciones satisfactorias de health, 401, 403, 409, creacion/consulta
de cola, exchange y binding, y eliminacion (HTTP 204). Se usaron recursos
temporales, sin alterar `cmd.*` o `q.cmd.*`.

### Limite de la demostracion sin SSH

La consola AWS, Amplify, Entra y RabbitMQ Management via ngrok se pueden
mostrar por navegador. Sin embargo, la ejecucion real de `docker compose`
**no queda demostrada solo con ver EC2 o RabbitMQ Management**. Para EP4
se debe conservar una captura o video autentico de la ejecucion y del estado
Compose de los nodos. Si el docente exige ejecutarlo en vivo, preparar un
mecanismo de acceso remoto autorizado; no simular su salida en diapositivas.

### Recuperacion luego de AWS Academy Learner Lab

Al ejecutar `End Lab`, las tres EC2 quedaron detenidas. Luego de `Start Lab`
**fue necesario encender manualmente** node1, node2 y Apps desde EC2 -> Instances.
Una vez iniciadas, Docker (`enabled`) recupero los servicios definidos con
`restart: unless-stopped`. Se comprobo BFF HTTP 200, ambas conexiones AMQP y
procesamiento posterior a la recuperacion. Las IP publicas de los nodos
RabbitMQ pueden cambiar; las direcciones **privadas** internas usadas por
las aplicaciones se conservaron en esas pruebas. Las EC2 conservan sus datos
al detenerse, pero no al terminarlas/eliminar sus volumenes.

La recuperacion automatica de ngrok **despues de apagar node1** debe volver
a verificarse explicitamente; hasta entonces no presentarla como probada.

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

### Checklist de validacion real

- [x] Confirmar integracion Gateway -> BFF, frontend Amplify y rechazo de una solicitud sin JWT (HTTP 401).
- [x] Verificar dos nodos RabbitMQ unidos, ambos running, y acceso AMQP desde Apps.
- [x] Verificar tres exchanges, seis colas `classic`, nueve bindings y politicas/rutas DLQ.
- [x] Verificar cinco microservicios + Mailpit `healthy` en EC2 Apps.
- [x] Crear y actualizar solicitudes reales; procesar eventos de Notify y revisar ACK.
- [x] Comprobar el recorrido a una DLQ mediante recursos temporales aislados.
- [x] Probar RabbitMQ Admin REST en AWS: 11 de 11 operaciones esperadas.
- [x] Detener/reiniciar las instancias y comprobar recuperacion funcional del backend.
- [x] Acceder a RabbitMQ Management mediante ngrok y autenticacion Google.
- [ ] Documentar respuesta HTTP exitosa con JWT valido y prueba de rechazo por token invalido.
- [ ] Guardar captura o grabacion de `docker compose` ejecutado en cada nodo RabbitMQ.
- [ ] Confirmar rechazo de una cuenta Google no autorizada en ngrok y recuperacion tras reinicio de node1.
- [ ] Revisar Security Groups reales y documentar permisos/alcance con capturas.
- [ ] Comprobar los commits de GitHub, el `.gitignore` y la ausencia de secretos publicados o en historial.
- [ ] Confirmar backups de volumenes y procedimiento de recuperacion de datos antes de pruebas destructivas.

No ejecutar pruebas de integracion destructivas sobre el broker con colas de
produccion. Usar colas temporales, aislamiento y credenciales de minimo
privilegio. Los resultados de `aws/CHANGES.md` describen la preparacion
historica del codigo: las pruebas posteriores en AWS se documentan aqui.

## Publicacion de esta documentacion en GitHub

El checkout local NO equivale a verificar el contenido ya publicado en GitHub.
Antes de entregar, comprobar rama, diff, archivos ignorados y estado remoto;
no publicar contrasenas, `.env`, `.pem`, cookies de Erlang ni tokens de ngrok.

Desde PowerShell en el repositorio `infra-barriodigital`:

```powershell
cd 'G:\Desarrollo EP3-EP4\infra-barriodigital'
git status --short
git diff -- README.AWS.md
git check-ignore aws/.env.apps aws/.env.node1 aws/.env.node2
git ls-files -- '*.env' 'aws/.env.*' '*.pem' '.erlang.cookie'
git add README.AWS.md
git diff --cached --check
git diff --cached --stat
git commit -m "Document AWS EP4 deployment and validation"
git push origin main
```

La salida de `git ls-files` debe inspeccionarse: las plantillas `.example`
si pueden estar versionadas; archivos `.env` reales y secretos **no**.
Si `git push` es rechazado, revisar cambios remotos antes de integrar. No usar
`--force` para resolverlo ni asumir que los otros seis repositorios se actualizan
con este push.

## Documentacion relacionada

- [`README.md`](README.md): infraestructura Compose local de EP1; no usar
  `docker compose -f compose.yml up` como sustituto del despliegue AWS.
- [`README-RabbitMQ.md`](README-RabbitMQ.md): topologia RabbitMQ local.
- [`README-Docker.md`](README-Docker.md): notas Docker.
- [`aws/CHANGES.md`](aws/CHANGES.md): informe original de preparacion y pruebas previas.
- `README.AWS.md` en cada repositorio de microservicio: ajustes y variables propias.
