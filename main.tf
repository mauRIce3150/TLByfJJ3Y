provider "azurerm" {
  features {}
}

# Resource group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
}

# Call the custom compute module
module "compute" {
  source = "./modules/compute"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  vm_name             = var.vm_name
  vm_size             = var.vm_size
  admin_username      = var.admin_username
  admin_password      = var.admin_password
  workload_script     = file("${path.module}/scripts/workload.sh")
}

# Call the custom policy module
module "policy" {
  source = "./modules/policy"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  definitions = [
    {
      name        = "audit-vm-sizes"
      policy_rule = file("${path.module}/policies/audit-vm-sizes.json")
    }
  ]

  assignments = [
    {
      name         = "restrict-vm-sizes"
      policy_name  = "audit-vm-sizes"
      display_name = "Restrict VM Sizes"
    }
  ]
}
