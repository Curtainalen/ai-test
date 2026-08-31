param([string]$BaseUrl="http://localhost:8000",[string]$Username="admin",[string]$Password="replace-with-strong-password")
$ErrorActionPreference="Stop"; $root=Split-Path -Parent $PSScriptRoot
function Api([string]$Method,[string]$Path,$Body=$null,[hashtable]$Headers=@{}){ $p=@{Method=$Method;Uri="$BaseUrl$Path";Headers=$Headers};if($null-ne$Body){$p.ContentType="application/json";$p.Body=$Body|ConvertTo-Json -Depth 30};Invoke-RestMethod @p }
function UploadFile([string]$Path,[string]$File,[hashtable]$Headers){$output=& curl.exe --silent --show-error --fail -X POST -H "Authorization: $($Headers.Authorization)" -F "file=@$File" "$BaseUrl$Path";if($LASTEXITCODE-ne 0){throw "File upload failed with curl exit code $LASTEXITCODE"};$output|ConvertFrom-Json}
function ExpectError([scriptblock]$Action,[int]$Status){try{&$Action|Out-Null;throw "Expected HTTP $Status"}catch{if($_.Exception.Response.StatusCode.value__ -ne $Status){throw}}}
function WaitUntil([scriptblock]$Action,[scriptblock]$Done,[int]$Seconds=60){$end=(Get-Date).AddSeconds($Seconds);do{$value=&$Action;if(&$Done $value){return $value};Start-Sleep -Seconds 1}while((Get-Date)-lt$end);throw "Timeout after $Seconds seconds"}

try{$auth=Api POST "/api/auth/register" @{username=$Username;password=$Password;name="Acceptance Admin"}}catch{$auth=Api POST "/api/auth/login" @{username=$Username;password=$Password}}
$h=@{Authorization="Bearer $($auth.data.access_token)"}
$project=(Api POST "/api/projects" @{name="phase-1-acceptance-$([DateTimeOffset]::Now.ToUnixTimeSeconds())";description="Automated acceptance project"} $h).data
$env=(Api POST "/api/projects/$($project.id)/environments" @{name="mock";base_url="http://mock-api:9000";variables=@{};global_headers=@{};secret_refs=@{};is_enabled=$true} $h).data

$upload=UploadFile "/api/projects/$($project.id)/requirements/upload" "$root/examples/requirements/user-login.md" $h
$docId=$upload.data.document_id
$doc=WaitUntil { (Api GET "/api/projects/$($project.id)/requirements/$docId" $null $h).data } { param($v) $v.versions[0].parse_status -in @("completed","failed") }
if($doc.versions[0].parse_status-ne"completed"){throw "Document parse failed"}
$module=$doc.modules|Select-Object -First 1
Api POST "/api/projects/$($project.id)/requirement-modules/$($module.id)/confirm" $null $h|Out-Null

$openapi=UploadFile "/api/projects/$($project.id)/api-imports" "$root/examples/openapi/login-api.yaml" $h
Api POST "/api/projects/$($project.id)/api-imports/$($openapi.data.id)/confirm?revision=$($openapi.data.revision)" $null $h|Out-Null
$interfaces=(Api GET "/api/projects/$($project.id)/interfaces" $null $h).data;$login=$interfaces|Where-Object path -eq "/login";$me=$interfaces|Where-Object path -eq "/me"

$preview=(Api POST "/api/projects/$($project.id)/requests/preview" @{environment_id=$env.id;request=@{method="POST";url="/login";headers=@{};params=@{};cookies=@{};body_type="json";body=@{username="tester";password="test-password"};auth=@{type="none"};variables=@{};extracts=@();assertions=@(@{type="status_code";expected=200})}} $h).data
if($preview.request_preview.body.password-ne"******"){throw "Preview is not masked"}
$debug=(Api POST "/api/projects/$($project.id)/requests/run" @{environment_id=$env.id;request=@{method="POST";url="/login";headers=@{};params=@{};cookies=@{};body_type="json";body=@{username="tester";password="test-password"};auth=@{type="none"};variables=@{};extracts=@(@{name="access_token";type="jmespath";expression="data.access_token";sensitive=$true});assertions=@(@{type="status_code";expected=200})}} $h).data
if("$debug"-match"acceptance-secret-token"){throw "Debug result leaked token"}

$scenarioBody=@{name="Login and authorization";description="Two-step explicit variable passing";scenario_type="api";priority="P0";requirement_module_ids=@($module.id);steps=@(@{seq=1;name="Login";interface_id=$login.id;request_override=@{body_type="json";body=@{username="tester";password="test-password"}};preconditions=@();extracts=@(@{name="access_token";type="jmespath";expression="data.access_token";scope="scenario";sensitive=$true});assertions=@(@{type="status_code";expected=200});expected_result="Login succeeds";timeout_ms=30000;retry_count=0;continue_on_failure=$false},@{seq=2;name="Get current user";interface_id=$me.id;request_override=@{headers=@{Authorization="Bearer `${access_token}"}};preconditions=@();extracts=@();assertions=@(@{type="status_code";expected=200},@{type="json_field";field="data.username";expected="tester"});expected_result="Authorization succeeds";timeout_ms=30000;retry_count=0;continue_on_failure=$false})}
$scenario=(Api POST "/api/projects/$($project.id)/scenarios" $scenarioBody $h).data
ExpectError { Api POST "/api/projects/$($project.id)/executions" @{scenario_id=$scenario.id;environment_id=$env.id} ($h+@{"Idempotency-Key"="unconfirmed"}) } 409
$scenario=(Api POST "/api/projects/$($project.id)/scenarios/$($scenario.id)/confirm?revision=$($scenario.revision)" $null $h).data
$key="acceptance-$([Guid]::NewGuid())";$execution=(Api POST "/api/projects/$($project.id)/executions" @{scenario_id=$scenario.id;environment_id=$env.id} ($h+@{"Idempotency-Key"=$key})).data
$duplicate=(Api POST "/api/projects/$($project.id)/executions" @{scenario_id=$scenario.id;environment_id=$env.id} ($h+@{"Idempotency-Key"=$key})).data;if($duplicate.id-ne$execution.id){throw "Idempotency failed"}
$execution=WaitUntil { (Api GET "/api/projects/$($project.id)/executions/$($execution.id)" $null $h).data } { param($v) $v.status -in @("completed","failed","canceled") } 90
if($execution.status-ne"completed"){throw "Execution failed: $($execution.error_message)"}
$reports=(Api GET "/api/projects/$($project.id)/reports?scenario_id=$($scenario.id)" $null $h).data;$report=$reports[0];$before=(Api GET "/api/projects/$($project.id)/reports/$($report.id)" $null $h).data|ConvertTo-Json -Depth 30 -Compress
$scenarioBody.description="Changed after report creation";$scenarioBody.revision=$scenario.revision;Api PATCH "/api/projects/$($project.id)/scenarios/$($scenario.id)" $scenarioBody $h|Out-Null
$after=(Api GET "/api/projects/$($project.id)/reports/$($report.id)" $null $h).data|ConvertTo-Json -Depth 30 -Compress;if($before-ne$after){throw "Immutable report changed"}

$other=(Api POST "/api/projects" @{name="Isolation project";description=""} $h).data
$memberUser="member$([DateTimeOffset]::Now.ToUnixTimeMilliseconds())";Api POST "/api/auth/users" @{username=$memberUser;password="member-password-123";name="Unauthorized User";system_role="user"} $h|Out-Null
$memberAuth=Api POST "/api/auth/login" @{username=$memberUser;password="member-password-123"};$mh=@{Authorization="Bearer $($memberAuth.data.access_token)"}
ExpectError { Api GET "/api/projects/$($project.id)/reports/$($report.id)" $null $mh } 403

$coverage=(Api GET "/api/projects/$($project.id)/requirement-coverage" $null $h).data;if(($coverage|Where-Object requirement_module_id -eq $module.id).status-ne"passed"){throw "Coverage not passed"}
Write-Host "Phase 1 acceptance passed: project=$($project.id), execution=$($execution.id), report=$($report.id)"
