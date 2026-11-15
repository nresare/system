# Website backend TLS

Website namespaces receive the label `trust: cluster-local`. The
`cluster-local-ca` trust-manager Bundle copies the CA certificate into a
same-named ConfigMap with a `ca.crt` key in every namespace with that label.
The website block preserves existing namespace metadata and the Argo CD
`PruneLast=true` annotation, and writes one Namespace manifest per namespace.

For a container that serves HTTPS on port 8443, opt in with:

```toml
[[website]]
name = "demo.example.com"
namespace = "demo"
image = "example/demo:latest"
tls = true
```

This generates a Certificate from the `cluster-local` ClusterIssuer with the
service DNS name as its SAN, mounts the resulting Secret read-only at `/tls`,
and configures the Service on port 443, targeting the named `https` container
port 8443. The HTTPRoute and `/healthz` liveness check use HTTPS.
Configure the application to read `/tls/tls.crt` and `/tls/tls.key`. It must
reload these files or be restarted after certificate renewal.

The generated BackendTLSPolicy validates the service hostname against the
namespace's `cluster-local-ca` ConfigMap. Envoy Gateway negotiates the upstream
HTTP version through ALPN; an HTTP/2-capable TLS server can negotiate `h2`.
Hugo websites keep their existing TLS setup on port 8443. Other websites use
plain HTTP unless `tls = true` is set.

## Request timeout

Set `request-timeout = "600s"` in a `[[website]]` block to allow requests up to
ten minutes. This sets the HTTPRoute rule's `timeouts.request`, including the
time to finish a streaming response. Values use Gateway API duration syntax
(for example, `30s` or `10m`); `0s` disables the overall request timeout.
Omitting the setting preserves the gateway's default. Stream idle timeouts
are configured separately.

# Simple gRPC deployments

Set `grpc = true` in a `[[simple]]` block to generate a cleartext gRPC Service
and container port named `grpc`, both on port 50051. The Service advertises
`appProtocol: kubernetes.io/h2c`. This port is a project convention, not a
protocol requirement.

```toml
[[simple]]
namespace = "example-grpc"
image = "example/grpc-server:latest"
grpc = true
```

The application must listen on port 50051 and implement `grpc.health.v1.Health`.
Generated Kubernetes gRPC liveness and readiness probes use health service names
`liveness` and `readiness`, respectively. The application should report liveness
while it can respond, and readiness only when it can serve traffic. The probes
use the numeric container port, as required by Kubernetes.

Omitting `grpc`, or setting it to false, keeps the HTTP defaults: Service port 80
targeting the `http` container port 8080, without gRPC probes.
