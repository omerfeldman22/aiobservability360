locals {
  black_agent_image_name     = "${local.chess_docker_images_name_prefix}-black:latest"
  black_agent_directory_name = "black"
  black_agent_directory_path = "${local.chess_directory_path}/${local.black_agent_directory_name}"
}

resource "docker_image" "chess_black_agent" {
  name         = "${data.azurerm_container_registry.demo.login_server}/${local.black_agent_image_name}"
  keep_locally = false

  build {
    context    = "${path.cwd}/${local.chess_directory_path}"
    dockerfile = "${local.black_agent_directory_name}/Dockerfile"
    platform   = "linux/amd64"
  }

  triggers = {
    dir_sha1 = sha1(join("", [for f in fileset(path.cwd, "${local.chess_directory_path}/**") : filesha1(f)]))
  }
}

resource "docker_registry_image" "chess_black_agent" {
  name          = docker_image.chess_black_agent.name
  keep_remotely = true

  triggers = {
    dir_sha1 = sha1(join("", [for f in fileset(path.cwd, "${local.chess_directory_path}/**") : filesha1(f)]))
  }
}

resource "kubernetes_deployment" "chess_black_agent" {
  metadata {
    name      = "chess-black-agent"
    namespace = kubernetes_namespace.chess.metadata[0].name
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "chess-black-agent"
      }
    }

    template {
      metadata {
        labels = {
          app = "chess-black-agent"
        }
      }

      spec {
        container {
          name  = "chess-black-agent"
          image = docker_registry_image.chess_black_agent.name
          resources {
            limits = {
              cpu    = "1"
              memory = "2Gi"
            }
            requests = {
              cpu    = "1"
              memory = "2Gi"
            }
          }

          port {
            container_port = 8000
            protocol       = "TCP"
          }

          env {
            name  = "OTEL_EXPORTER_OTLP_ENDPOINT"
            value = "http://${kubernetes_service.otel_collector.metadata[0].name}.${kubernetes_namespace.opentelemtry.metadata[0].name}.svc.cluster.local:4317"
          }

          env {
            name  = "TRACELOOP_BASE_URL"
            value = "http://${kubernetes_service.otel_collector.metadata[0].name}.${kubernetes_namespace.opentelemtry.metadata[0].name}.svc.cluster.local:4318"
          }
          
          env {
            name  = "OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"
            value = "true"
          }

          env {
            name  = "AZURE_OPENAI_ENDPOINT"
            value = data.azurerm_cognitive_account.demo.endpoint
          }

          env {
            name  = "AZURE_OPENAI_API_KEY"
            value = data.azurerm_cognitive_account.demo.primary_access_key
          }

          env {
            name  = "AZURE_OPENAI_DEPLOYMENT"
            value = "${var.base_name}-gpt-4o"
          }
        }
      }
    }
  }

  depends_on = [docker_registry_image.chess_black_agent]
}

resource "kubernetes_service" "chess_black_agent" {
  metadata {
    name      = "chess-black-agent"
    namespace = kubernetes_namespace.chess.metadata[0].name
  }

  spec {
    selector = {
      app = "chess-black-agent"
    }

    port {
      name        = "port-80"
      port        = 80
      target_port = 8000
      protocol    = "TCP"
    }

    type = "LoadBalancer"
  }
}