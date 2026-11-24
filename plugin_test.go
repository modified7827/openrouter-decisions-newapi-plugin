package openrouter

import (
	"os"
	"testing"

	"github.com/QuantumNous/new-api/common"
	"github.com/QuantumNous/new-api/pkg/jsplugin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func loadPlugin(t *testing.T) (*jsplugin.LoadedPlugin, *jsplugin.Registry) {
	t.Helper()
	source, err := os.ReadFile("plugin.js")
	require.NoError(t, err)
	registry := jsplugin.NewRegistry()
	plugin, err := registry.RegisterFactory(string(source), jsplugin.Options{Key: "openrouter"})
	require.NoError(t, err)
	return plugin, registry
}

func call(t *testing.T, plugin *jsplugin.LoadedPlugin, hook string, args ...any) map[string]any {
	t.Helper()
	value, err := plugin.Engine.Call(t.Context(), hook, args...)
	require.NoError(t, err, hook)
	encoded, err := common.Marshal(value)
	require.NoError(t, err)
	var out map[string]any
	require.NoError(t, common.Unmarshal(encoded, &out))
	return out
}

func callPath(t *testing.T, plugin *jsplugin.LoadedPlugin, base string, path []string, args ...any) map[string]any {
	t.Helper()
	value, err := plugin.Engine.CallPath(t.Context(), base, path, args...)
	require.NoError(t, err)
	encoded, err := common.Marshal(value)
	require.NoError(t, err)
	var out map[string]any
	require.NoError(t, common.Unmarshal(encoded, &out))
	return out
}

func TestOpenRouterDecisionsRoute(t *testing.T) {
	plugin, registry := loadPlugin(t)

	binding, found := registry.Generation().LookupDeclaredRoute("POST", "/v1/alpha/decisions")
	require.True(t, found)
	assert.Equal(t, "openrouter", binding.Plugin.Meta.Key)
	assert.Same(t, plugin, binding.Plugin)
	assert.Equal(t, jsplugin.RouteTypeSubmit, binding.Route.Type)
	require.NotNil(t, binding.Route.RetainResult)
	assert.False(t, *binding.Route.RetainResult)

	// {key} 前缀副本自动附送
	pinned, found := registry.Generation().LookupDeclaredRoute("POST", "/openrouter/v1/alpha/decisions")
	require.True(t, found)
	assert.True(t, pinned.Pinned)
}

func TestOpenRouterDecisionsTaskLifecycle(t *testing.T) {
	plugin, _ := loadPlugin(t)

	body := map[string]any{"model": "Decisions", "questions": map[string]any{"q": "pick"}, "state": "ctx"}
	decoded := callPath(t, plugin, "native", []string{"decodeDecisions"}, map[string]any{
		"body": map[string]any{"kind": "json", "value": body},
	})
	assert.Equal(t, "submit", decoded["kind"])
	assert.Equal(t, "Decisions", decoded["model"])
	assert.Equal(t, "decisions", decoded["action"])

	// ctx.model 保持下游别名，ctx.upstreamModel 是渠道 model_mapping 结果
	desc := call(t, plugin, "buildSubmitRequest", map[string]any{
		"baseUrl":       "https://openrouter.ai/api",
		"apiKey":        "sk-or-test",
		"action":        "decisions",
		"model":         "Decisions",
		"upstreamModel": "parallel/decisions-fast:free",
		"requestBody":   body,
	})
	assert.Equal(t, "https://openrouter.ai/api/alpha/decisions", desc["url"])
	upstreamBody := desc["body"].(map[string]any)
	assert.Equal(t, "parallel/decisions-fast:free", upstreamBody["model"])

	parsed := call(t, plugin, "parseSubmitResponse", map[string]any{"action": "decisions"}, map[string]any{
		"body": map[string]any{"id": "d-1", "answer": "yes"},
	})
	assert.Equal(t, "d-1", parsed["taskId"])
	assert.Equal(t, "SUCCESS", parsed["immediate"].(map[string]any)["status"])

	rendered := callPath(t, plugin, "native", []string{"renderDecisions"}, map[string]any{},
		map[string]any{"data": map[string]any{"id": "d-1", "answer": "yes"}})
	assert.Equal(t, "yes", rendered["answer"])
}
