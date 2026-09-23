// Command shakecloud-mcp serves the shake-cloud API to an MCP client over
// stdin and stdout.
//
// It registers read-only tools only: a model cannot start, stop, create or
// delete anything, and a ReadOnly access key refuses a write at the API even
// if a tool ever asked for one. The key comes from SHAKECLOUD_ACCESS_KEY, as
// with the CLI and Terraform.
package main

import (
	"context"
	"flag"
	"log"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func main() {
	endpoint := flag.String("endpoint", "", "API base URL (default: $SHAKECLOUD_ENDPOINT, then the deployment default)")
	flag.Parse()

	// stdout carries the MCP protocol; every log line must go to stderr.
	log.SetOutput(os.Stderr)
	log.SetPrefix("shakecloud-mcp: ")

	accessKey := os.Getenv("SHAKECLOUD_ACCESS_KEY")
	if accessKey == "" {
		log.Fatal("SHAKECLOUD_ACCESS_KEY is not set; issue an access key in the portal (ReadOnly is enough for these tools)")
	}
	if *endpoint == "" {
		*endpoint = os.Getenv("SHAKECLOUD_ENDPOINT")
	}
	c := client.NewWithUserAgent(*endpoint, accessKey, "shakecloud-mcp/"+version)

	// Best effort: say who the key is in the client's server log, but start
	// anyway, so a temporary API outage does not stop the client from
	// launching the server. The tools report the error when they are called.
	ctx := context.Background()
	if identity, err := c.CallerIdentity(ctx); err != nil {
		log.Printf("the API is not answering yet: %v", err)
	} else {
		log.Printf("connected as %s (account %s, key scope %s)", identity.Username, identity.AccountID, identity.AccessKeyScope)
	}

	if err := newServer(c).Run(ctx, &mcp.StdioTransport{}); err != nil {
		log.Fatal(err)
	}
}
