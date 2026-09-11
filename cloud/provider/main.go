// Command terraform-provider-shakecloud is the Terraform provider for the
// shake-cloud API. It is installed as a plugin and talks to the same API, with
// the same access key, as the portal and the shakecloud CLI.
package main

import (
	"context"
	"flag"
	"log"

	"github.com/hashicorp/terraform-plugin-framework/providerserver"
	"github.com/rurutheGeek/shake-cloud/cloud/provider/internal/provider"
)

func main() {
	var debug bool
	flag.BoolVar(&debug, "debug", false, "start the provider with support for debuggers and set TF_REATTACH_PROVIDERS")
	flag.Parse()

	opts := providerserver.ServeOpts{
		Address: "registry.terraform.io/ruruthegeek/shakecloud",
		Debug:   debug,
	}
	if err := providerserver.Serve(context.Background(), provider.New, opts); err != nil {
		log.Fatal(err.Error())
	}
}
