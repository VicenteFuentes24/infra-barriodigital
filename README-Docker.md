# Docker Compose - BarrioDigital

El archivo `compose.yml` se encuentra en la raíz de este repositorio y levanta los tres servicios backend incluidos en la entrega actual:

- `bff`: publica `8080:8080`.
- `requests`: expone 8081 solo dentro de Docker.
- `catalog`: expone 8082 solo dentro de Docker.

Los servicios comparten la red bridge `barriodigital-net`.

## Inicio

```bash
cd /opt/barriodigital/infra-barriodigital
docker compose config -q
docker compose build
docker compose up -d
```

## Estado y logs

```bash
docker compose ps
docker compose logs --tail=100 bff
docker compose logs --tail=100 requests
docker compose logs --tail=100 catalog
```

## Healthcheck

```bash
curl http://localhost:8080/actuator/health
```

Requests y Catalog se verifican mediante los healthchecks definidos en Compose.

## Reconstrucción

Todos los servicios:

```bash
docker compose up -d --build
```

Solo un servicio, por ejemplo BFF:

```bash
docker compose build bff
docker compose up -d bff
```

## Detener

```bash
docker compose down
```
