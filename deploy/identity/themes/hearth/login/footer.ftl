<#macro content>
  <div class="hearth-signin-context">
    <#if client?? && client.clientId == "hearth-admin">
      <strong>Hearth Administration</strong>
      <p>Sign in with your Hearth account to manage your farm. Administration is available to the Owner and accounts with a farm role.</p>
      <a href="https://localhost:8443/">Back to Administration</a>
    <#else>
      <strong>Your Hearth workspace</strong>
      <p>Sign in with your Hearth account. Your drafts and ideas stay in your own private workspace.</p>
      <a href="https://localhost:8444/">Back to your workspace</a>
    </#if>
    <span class="hearth-signin-privacy">Your account lives on this Hearth.</span>
  </div>
</#macro>
