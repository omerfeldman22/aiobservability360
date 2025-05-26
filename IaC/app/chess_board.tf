resource "local_file" "chess_board_config" {
  filename = "${path.cwd}/${local.chess_directory_path}/.env"
  content = templatefile("${path.cwd}/${local.chess_directory_path}/.env.tftpl", {
    white_url = kubernetes_service.chess_white_agent.status[0].load_balancer[0].ingress[0].ip,
    black_url = kubernetes_service.chess_black_agent.status[0].load_balancer[0].ingress[0].ip,
    otel_exporter_otlp_endpoint = kubernetes_service.otel_collector_lb.status[0].load_balancer[0].ingress[0].ip,
    base_name = var.base_name,
    openai_model=var.openai_model,
    openai_deployment="${var.base_name}-${var.openai_model}",
    openai_api_version=var.openai_api_version,
    openai_endpoint=data.azurerm_cognitive_account.demo.endpoint,
    openai_api_key=data.azurerm_cognitive_account.demo.primary_access_key
  })
}