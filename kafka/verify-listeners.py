"""Read Kafka Metadata v0 without installing a Kafka client.

No records, groups or configurations are modified. Kafka 3.9.1 supports v0.
"""
import argparse
import json
import socket
import struct


def receive(sock, size):
    result = bytearray()
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise RuntimeError("Kafka closed an incomplete response")
        result.extend(chunk)
    return bytes(result)


PORTS = (19092, 29092, 39092)


def metadata(port, host):
    client = b"bd-infra-check"
    correlation = port
    request = struct.pack(">hhi", 3, 0, correlation)
    request += struct.pack(">h", len(client)) + client + struct.pack(">i", 0)
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(struct.pack(">i", len(request)) + request)
        size = struct.unpack(">i", receive(sock, 4))[0]
        if not 8 <= size <= 10_000_000:
            raise RuntimeError(f"Unexpected metadata length: {size}")
        response = receive(sock, size)
    returned_id, count = struct.unpack_from(">ii", response)
    if returned_id != correlation or count != 3:
        raise RuntimeError(f"Unexpected correlation/broker count: {returned_id}/{count}")
    offset = 8
    brokers = {}
    for _ in range(count):
        broker_id, length = struct.unpack_from(">ih", response, offset)
        offset += 6
        if length < 1:
            raise RuntimeError("Invalid advertised hostname")
        host = response[offset:offset + length].decode("utf-8")
        offset += length
        advertised_port = struct.unpack_from(">i", response, offset)[0]
        offset += 4
        if broker_id in brokers:
            raise RuntimeError("Duplicate broker ID")
        brokers[broker_id] = (host, advertised_port)
    expected = {broker_id: (host, external_port) for broker_id, external_port in enumerate(PORTS, 1)}
    if brokers != expected:
        raise RuntimeError(f"Incorrect EXTERNAL advertised listeners: {brokers}")
    return {"bootstrap": f"{host}:{port}", "brokers": brokers, "result": "PASS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    args = parser.parse_args()
    for broker_port in PORTS:
        print(json.dumps(metadata(broker_port, args.host)))
