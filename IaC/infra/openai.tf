resource "azurerm_cognitive_account" "demo" {
  name                = "${var.base_name}-openai"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  kind                = "OpenAI"
  sku_name            = "S0"
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