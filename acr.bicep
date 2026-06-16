// =============================================================================
// acr.bicep
// Azure Container Registry — supports two modes:
//   1. Create new: provisions Premium SKU ACR with public access disabled
//   2. BYO (Bring Your Own): references an existing ACR by resource ID
//
// When `existingAcrResourceId` is provided, no ACR is created — the module
// simply outputs the name and ID of the existing registry for downstream
// private endpoint wiring.
//
// Premium SKU is required for private endpoint support.
// Scope: resourceGroup.
// =============================================================================

targetScope = 'resourceGroup'

@description('Name for a new ACR instance (must be globally unique, alphanumeric only). Ignored when existingAcrResourceId is set.')
param acrName string = ''

@description('Azure region. Ignored when existingAcrResourceId is set.')
param location string = resourceGroup().location

@description('Full ARM resource ID of an existing ACR to use (BYO mode). Leave empty to create a new one.')
param existingAcrResourceId string = ''

@description('SKU for new ACR — must be Premium for private endpoint support.')
@allowed(['Premium'])
param sku string = 'Premium'

@description('Disable public network access so the registry is only reachable via private endpoint.')
param publicNetworkAccess string = 'Disabled'

@description('Tags to apply to new ACR.')
param tags object = {}

// Determine mode
var isByo = !empty(existingAcrResourceId)
var byoAcrName = isByo ? last(split(existingAcrResourceId, '/')) : ''

// Create new ACR (only when not BYO)
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (!isByo) {
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

@description('ACR resource ID (created or BYO).')
#disable-next-line BCP318
output acrId string = isByo ? existingAcrResourceId : acr.id

@description('ACR name (created or BYO).')
#disable-next-line BCP318
output acrName string = isByo ? byoAcrName : acr.name

@description('ACR login server.')
#disable-next-line BCP318
output acrLoginServer string = isByo ? '${byoAcrName}.azurecr.io' : acr.properties.loginServer
