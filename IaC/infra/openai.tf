resource "azurerm_cognitive_account" "demo" {
  name                = "${var.base_name}-openai"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  kind                = "OpenAI"
  sku_name            = "S0"
}

data "azurerm_monitor_diagnostic_categories" "openai" {
  resource_id = azurerm_cognitive_account.demo.id
}

resource "azurerm_monitor_diagnostic_setting" "openai" {
  name                       = "openai-diagnostics"
  target_resource_id         = azurerm_cognitive_account.demo.id
  
  eventhub_name                  = azurerm_eventhub.diagnostic.name
  eventhub_authorization_rule_id = azurerm_eventhub_namespace_authorization_rule.monitor.id

  dynamic "enabled_log" {
    for_each = data.azurerm_monitor_diagnostic_categories.openai.log_category_types
    content {
      category = enabled_log.value
    }
  }

  dynamic "metric" {
    for_each = data.azurerm_monitor_diagnostic_categories.openai.metrics
    content {
      category = metric.value
      enabled  = true
    }
  }
}

locals {
  models = {
    "gpt-4o" = {
      name     = "gpt-4o"
      version  = "2024-11-20"
      capacity = 450
    },
    "gpt-4o-mini" = {
      name     = "gpt-4o-mini"
      version  = "2024-07-18"
      capacity = 200
    },
    "o4-mini" = {
      name     = "o4-mini"
      version  = "2025-04-16"
      capacity = 1000
    },
    "gpt-4.1-mini" = {
      name     = "gpt-4.1-mini"
      version  = "2025-04-14"
      capacity = 1000
    },
    "o3-mini" = {
      name     = "o3-mini"
      version  = "2025-01-31"
      capacity = 500
    },
  }
}

resource "azurerm_cognitive_deployment" "demo" {
  for_each = local.models

  name                 = "${var.base_name}-${each.key}"
  cognitive_account_id = azurerm_cognitive_account.demo.id

  model {
    format  = "OpenAI"
    name    = each.value.name
    version = each.value.version
  }

  sku {
    name     = "GlobalStandard"
    capacity = each.value.capacity
  }
}