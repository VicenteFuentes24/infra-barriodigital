# Kafka en AWS

En la EC2 `10.0.2.174` ya funcionan Kafka 3.9.1 con tres brokers y tres ZooKeeper.
Apps se conecta a los listeners privados `19092`, `29092` y `39092`.
Los nombres Docker `kafka-1`, `kafka-2`, `kafka-3` usan el puerto interno
`9092`. Kafka UI queda en `127.0.0.1:8090` con su ngrok protegido existente.

Los dos tópicos, `bd.requests.events.v1` y `bd.requests.analytics.v1`, conservan
tres particiones, replicación 3, ISR mínimo 2, y sus políticas de retención de
[`kafka/config/topics.tsv`](kafka/config/topics.tsv). El bróker conserva
auto-creación de tópicos desactivada. Report y Audit usan grupos independientes.

En la sesión SSM de Kafka, `sudo python3 aws/deploy.py kafka verify` consulta
quórum, tópicos, ISR, metadatos y salud de la UI. Desde Apps,
`python3 kafka/verify-listeners.py 10.0.2.174` comprueba los tres listeners.
Los scripts de arranque y los verificadores están en `kafka/scripts`. Reservar
`smoke-test.sh` para un clúster aislado, ya que usa un tópico de prueba.
Consultar la [guía AWS](README.AWS.md).
