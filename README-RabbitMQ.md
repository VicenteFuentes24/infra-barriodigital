# RabbitMQ en AWS

Los nodos existentes usan las direcciones privadas `10.0.1.77:5672` y
`10.0.2.173:5672`. El vhost es `barriodigital`. El archivo
[`rabbitmq/definitions.json`](rabbitmq/definitions.json) describe los exchanges
`cmd.direct`, `cmd.topic`, `cmd.dead.dlx`, las seis colas classic y los bindings
y políticas DLX. La membresía del clúster por sí sola no replica las colas classic.

En Node 1, con el archivo de entorno privado existente y mediante SSM, ejecutar
`sudo python3 aws/deploy.py node1 verify` y
`sudo python3 aws/deploy.py node1 topology` para verificar sin importar.
Management sigue en el túnel HTTPS protegido ya instalado. El script
`scripts/Test-RabbitMQ.ps1` se reserva para un broker de pruebas aislado.
Consultar la [guía AWS](README.AWS.md).
