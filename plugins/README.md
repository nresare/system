# Website backend TLS

Website namespaces receive the label `trust: cluster-local`. The
`cluster-local-ca` trust-manager Bundle copies the CA certificate into a
same-named ConfigMap with a `ca.crt` key in every namespace with that label.
The website block preserves existing namespace metadata and the Argo CD
`PruneLast=true` annotation, and writes one Namespace manifest per namespace.

For a container that serves HTTPS on port 8080, opt in with:

```toml
[[website]]
name = "demo.example.com"
namespace = "demo"
image = "example/demo:latest"
tls = true
```

This generates a Certificate from the `cluster-local` ClusterIssuer with the
service DNS name as its SAN, mounts the resulting Secret read-only at `/tls`,
and configures the Service, HTTPRoute, and `/healthz` liveness check for HTTPS.
Configure the application to read `/tls/tls.crt` and `/tls/tls.key`. It must
reload these files or be restarted after certificate renewal.

The generated BackendTLSPolicy validates the service hostname against the
namespace's `cluster-local-ca` ConfigMap. Envoy Gateway negotiates the upstream
HTTP version through ALPN; an HTTP/2-capable TLS server can negotiate `h2`.
Hugo websites keep their existing TLS setup on port 8443. Other websites use
plain HTTP unless `tls = true` is set.
