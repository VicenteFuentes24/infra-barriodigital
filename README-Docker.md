# BarrioDigital EP1 - Docker Compose

Este Compose levanta solo los componentes backend requeridos en la EP1:

- BFF: puerto público 8080
- Requests: puerto interno 8081
- Catalog: puerto interno 8082

Requests y Catalog NO publican puertos al host. El BFF se comunica con ellos por DNS interno de Docker (`requests` y `catalog`).

## Requisitos

Cada servicio debe conservar su archivo `.env` real junto al `pom.xml`:

- `ms-barriodigital-bff/barriodigitalbff/.env`
- `ms-barriodigital-requests/barriodigitalrequests/.env`
- `ms-barriodigital-catalog/barriodigitalcatalog/.env`

Los `.env` no deben subirse a Git.

## Arranque

Desde `infra-barriodigital/apps`:

```bash
docker compose config
docker compose build
docker compose up -d
```

## Ver estado

```bash
docker compose ps
docker compose logs -f bff
docker compose logs -f requests
docker compose logs -f catalog
```

## Pruebas rápidas

```bash
curl http://localhost:8080/actuator/health
```

Requests y Catalog se validan mediante sus healthchecks internos y no quedan expuestos al host.

## Detener

```bash
docker compose down
```

## Reconstruir después de cambiar código

```bash
docker compose up -d --build
```

## Nota t3.micro

Tres aplicaciones Spring Boot pueden quedar ajustadas en una t3.micro. Mantener swap habilitado en EC2 y revisar memoria con:

```bash
free -h
docker stats
```

Si hay reinicios por memoria, subir temporalmente a t3.medium.
