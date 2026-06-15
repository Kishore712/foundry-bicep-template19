// =============================================================================
// acr.bicep
// Azure Container Registry (Premium SKU) with public network access disabled.
// Premium is required for private endpoint support.
// Scope: resourceGroup.
// =============================================================================

targetScope = 'resourceGroup'

@description('Name of the ACR instance (must be globally unique, alphanumeric only).')
param acrName string

@description('Azure region.')
param location string

@description('SKU — must be Premium for private endpoint support.')
@allowed(['Premium'])
param sku string = 'Premium'

@description('Disable public network access so the registry is only reachable via private endpoint.')
param publicNetworkAccess string = 'Disabled'

@description('Tags to apply.')
param tags object = {}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: sku
  }
  tags: tags
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: publicNetworkAccess
    networkRuleBypassOptions: 'AzureServices'
    zoneRedundancy: 'Disabled'
    dataEndpointEnabled: false
  }
}

@description('ACR resource ID.')
output acrId string = acr.id

@description('ACR name.')
output acrName string = acr.name

@description('ACR login server (e.g. myacr.azurecr.io).')
output acrLoginServer string = acr.properties.loginServer
