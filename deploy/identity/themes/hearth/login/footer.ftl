<#macro content>
  <div class="hearth-signin-context">
    <#if client?? && client.clientId == "hearth-admin">
      <strong>hearth Administration</strong>
      <p>Sign in with your hearth account to manage your farm. Administration is available to the Owner and accounts with a farm role.</p>
      <#if client.baseUrl?has_content><a href="${client.baseUrl}">Back to Administration</a></#if>
    <#else>
      <strong>Your hearth workspace</strong>
      <p>Sign in with your hearth account. Your drafts and ideas stay in your own private workspace.</p>
      <#if client?? && client.baseUrl?has_content><a href="${client.baseUrl}">Back to your workspace</a></#if>
    </#if>
    <span class="hearth-signin-privacy">Your account lives on this hearth.</span>
  </div>
</#macro>
