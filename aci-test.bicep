// =============================================================================
// aci-test.bicep
// Deploys a Python-based ACI container with managed identity in the VNet.
// Pre-installs SDK packages so customers can immediately run the test script.
//
// After deployment, customer connects and runs:
//   az container exec -g <rg> --name <name> --exec-command "python3 /opt/test_agent.py"
//
// Scope: resourceGroup.
// =============================================================================

targetScope = 'resourceGroup'

@description('Azure region.')
param location string

@description('Name of the ACI container group.')
param containerGroupName string = 'private-acr-test'

@description('Subnet resource ID (must have Microsoft.ContainerInstance/containerGroups delegation).')
param subnetId string

@description('AI Services account name.')
param aiServicesName string

@description('Project name.')
param projectName string

@description('ACR hostname to test (e.g. myacr.azurecr.io).')
param acrHost string

@description('Azure region of the ACR.')
param acrRegion string

@description('Cosmos DB account name.')
param cosmosDBName string

@description('Storage account name.')
param storageName string

@description('AI Search service name.')
param aiSearchName string

@description('Resource ID of the AI Services account (for role assignment).')
param aiServicesResourceId string

@description('URL to the test script (raw GitHub URL). Defaults to the repo branch.')
param testScriptUrl string = 'https://raw.githubusercontent.com/Kishore712/foundry-bicep-template19/kishorebr/updated-private-acr/tests/test_private_acr_agents.py'

var setupScript = 'pip install azure-ai-projects azure-identity openai requests -q 2>/dev/null && curl -sL ${testScriptUrl} -o /opt/test_agent.py && chmod +x /opt/test_agent.py && echo "Ready. Run: python3 /opt/test_agent.py" && sleep 86400'

resource containerGroup 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: containerGroupName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    osType: 'Linux'
    restartPolicy: 'Never'
    subnetIds: [
      {
        id: subnetId
      }
    ]
    containers: [
      {
        name: 'test-runner'
        properties: {
          image: 'python:3.12-slim'
          command: [
            'bash'
            '-c'
            setupScript
          ]
          environmentVariables: [
            { name: 'PROJECT_ENDPOINT', value: 'https://${aiServicesName}.services.ai.azure.com/api/projects/${projectName}' }
            { name: 'ACR_HOST', value: acrHost }
            { name: 'ACR_REGION', value: acrRegion }
            { name: 'AI_SERVICES_NAME', value: aiServicesName }
            { name: 'COSMOS_DB_NAME', value: cosmosDBName }
            { name: 'STORAGE_NAME', value: storageName }
            { name: 'AI_SEARCH_NAME', value: aiSearchName }
          ]
          resources: {
            requests: {
              cpu: 1
              memoryInGB: 2
            }
          }
        }
      }
    ]
  }
}

// Grant Cognitive Services Contributor to the ACI managed identity
resource cogServicesContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerGroup.id, aiServicesResourceId, 'CognitiveServicesContributor')
  properties: {
    principalId: containerGroup.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68')
  }
}

// Grant Reader on RG (for ARM endpoint resolution)
resource readerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerGroup.id, resourceGroup().id, 'Reader')
  properties: {
    principalId: containerGroup.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}

@description('ACI container group name.')
output containerGroupName string = containerGroup.name

@description('ACI managed identity principal ID.')
output principalId string = containerGroup.identity.principalId
