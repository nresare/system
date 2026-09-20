```
$ helm repo add argo https://argoproj.github.io/argo-helm
"argo" has been added to your repositories

$ kubectl create ns argo

$ helm install argocd -n argo argo/argo-cd --values argo-values.yaml
```
