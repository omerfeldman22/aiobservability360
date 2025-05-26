variable "subscription_id" {
  description = "The subscription ID in which the resources will be created."
  sensitive   = true
}

variable "base_name" {
  description = "The base name for the resources (will be used for prefix)."
}

variable "email" {
  description = "The email address of the user who will be the owner of the resources."
}

variable "region" {
  description = "The region in which the resources will be created (example: swedencentral)."
  default     = "swedencentral"
}

variable "data_location" {
  description = "The data location for the communication service."
  default     = "Europe"
}

variable "openai_model" {
  description = "The OpenAI model to use."
  default     = "gpt-4.1"
}

variable "openai_api_version" {
  description = "The OpenAI API version to use."
  default     = "2025-01-01-preview"
}