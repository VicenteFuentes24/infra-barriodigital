# infra-barriodigital

Infraestructura Docker de los servicios backend incluidos en la EP1 de BarrioDigital.

## Servicios

```text
barriodigital-bff      :8080 público en el host
barriodigital-requests :8081 solo red Docker
barriodigital-catalog  :8082 solo red Docker
```

Requests y Catalog no publican sus puertos al host. El único servicio expuesto por Compose es el BFF.

## Arquitectura de ejecución

```text
Frontend
   |
   v
AWS API Gateway
   |
   v
EC2 :8080
   |
   v
BFF
  / \
 v   v
Requests   Catalog
 :8081      :8082
   \        /
    PostgreSQL cloud
```

Dentro de Docker, el BFF resuelve los servicios por nombre:

```text
http://requests:8081
http://catalog:8082
```

## Requisitos

La estructura esperada en el servidor es:

```text
/opt/barriodigital/
├── ms-barriodigital-bff/
├── ms-barriodigital-requests/
├── ms-barriodigital-catalog/
└── infra-barriodigital/
    └── compose.yml
```

Cada servicio debe tener su `.env` real junto al `pom.xml`. Esos archivos no deben subirse a Git.

## Levantar los servicios

Desde `infra-barriodigital/`:

```bash
docker compose config -q
docker compose build
docker compose up -d
```

## Verificar estado

```bash
docker compose ps
```

Los tres servicios deben terminar en estado `healthy`.

Healthcheck del BFF:

```bash
curl http://localhost:8080/actuator/health
```

## Logs

```bash
docker compose logs --tail=100 bff
docker compose logs --tail=100 requests
docker compose logs --tail=100 catalog
```

## Actualizar un solo servicio

Ejemplo para el BFF:

```bash
cd /opt/barriodigital/ms-barriodigital-bff
git pull

cd /opt/barriodigital/infra-barriodigital
docker compose build bff
docker compose up -d bff
docker compose ps
```

## Detener

```bash
docker compose down
```

## Notas de despliegue AWS

En la implementación utilizada para la evaluación:

- los contenedores se ejecutan en una instancia EC2;
- API Gateway es el punto de entrada usado por el frontend;
- Requests y Catalog permanecen internos en la red Docker;
- el Security Group no necesita publicar 8081 ni 8082;
- el puerto 8080 corresponde al BFF y es el destino de la integración HTTP del Gateway;
- la base de datos PostgreSQL está fuera de los contenedores.

La configuración de VPC, subred, Internet Gateway, Security Group y API Gateway se administra en AWS y no está declarada dentro de este `compose.yml`.
