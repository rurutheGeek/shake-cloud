package main

import (
	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

// version is reported to the client and used in the User-Agent, so the audit
// log can tell MCP calls from CLI and Terraform ones.
const version = "0.1.0"

// newServer builds the MCP server with the read-only tool set. Write tools are
// deliberately absent: even with a ReadWrite key, a model cannot change the
// lab through this server. Pair it with a ReadOnly key so a bug in a tool
// cannot become a change either.
func newServer(c *client.Client) *mcp.Server {
	s := mcp.NewServer(&mcp.Implementation{Name: "shakecloud", Version: version}, &mcp.ServerOptions{
		Instructions: "Read-only tools for the shake-cloud self-hosted cloud " +
			"(Proxmox VMs, volumes, security groups, S3 buckets, databases and functions). " +
			"Nothing here changes state; for that, ask the human to use the portal or the CLI.",
	})
	addTools(s, c)
	return s
}

// readTool registers a tool that never changes state, and marks it as such so
// the client can tell the model and the user that it is safe.
func readTool[In, Out any](s *mcp.Server, name, description string, h mcp.ToolHandlerFor[In, Out]) {
	mcp.AddTool(s, &mcp.Tool{
		Name:        name,
		Description: description,
		Annotations: &mcp.ToolAnnotations{ReadOnlyHint: true},
	}, h)
}
