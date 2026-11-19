# Infraestructura de BarrioDigital en AWS

La [guía de despliegue](README.AWS.md) cubre Apps, Supabase, las comprobaciones
de los clústeres existentes y el acceso por SSM, API Gateway, ngrok y Amplify.

- [Docker Compose de Apps](README-Docker.md)
- [RabbitMQ](README-RabbitMQ.md)
- [Kafka y Kafka UI](README-Kafka.md)

Ejecutar `python -B -m unittest discover -s aws/tests -v` desde este
repositorio. Las pruebas de Compose usan datos ficticios y solo necesitan la CLI.
