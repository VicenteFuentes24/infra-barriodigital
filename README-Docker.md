# Docker Compose de Apps

En la EC2 Apps, desplegar mediante [la guía SSM](README.AWS.md). Los ocho
Dockerfiles construyen sus artefactos con Java 21 desde los repositorios hermanos.
Guardar las variables reales en `aws/.env.apps` con modo `0600`.

```bash
python3 aws/deploy.py apps validate
sudo python3 aws/deploy.py apps start
sudo python3 aws/deploy.py apps ps
sudo docker compose --env-file aws/.env.apps -f aws/compose.apps.yml logs --tail 80
```

BFF y Mailpit UI están publicados en loopback. Los demás servicios de Apps se
alcanzan por nombres de servicio en la red Docker. Se conservan los volúmenes
de Notify y Mailpit.
