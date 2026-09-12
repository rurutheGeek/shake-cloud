package main

import (
	"context"
	"errors"
	"flag"
	"fmt"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) functions(args []string) error {
	if len(args) == 0 {
		return errors.New("function needs a subcommand: ls, create, show, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		functions, err := c.DescribeFunctions(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(functions)
		}
		printFunctions(functions)
		return nil
	case "create":
		flags := flag.NewFlagSet("shakecloud function create", flag.ContinueOnError)
		image := flags.String("image", "", "container image (required)")
		if err := flags.Parse(rest); err != nil {
			return err
		}
		names := flags.Args()
		if len(names) != 1 || *image == "" {
			return errors.New("usage: shakecloud function create --image IMAGE NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		function, err := c.CreateFunction(context.Background(), names[0], *image)
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(function)
		}
		printFunctionDetail(function)
		return nil
	case "show":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud function show FUNCTION_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		function, err := c.DescribeFunction(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(function)
		}
		printFunctionDetail(function)
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud function rm FUNCTION_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteFunction(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	default:
		return fmt.Errorf("unknown function subcommand %q", sub)
	}
}

func printFunctions(functions []client.Function) {
	w := table()
	fmt.Fprintln(w, "FUNCTION_ID\tNAME\tSTATUS\tIMAGE")
	for _, function := range functions {
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\n", function.FunctionID, function.Name, function.Status, function.Image)
	}
	w.Flush()
}

func printFunctionDetail(function client.Function) {
	fmt.Printf("%s  %s  (%s)\n", function.FunctionID, function.Name, function.Status)
	fmt.Printf("  image %s\n", function.Image)
	if function.URL != "" {
		fmt.Printf("  url   %s\n", function.URL)
	}
	fmt.Printf("  owner %s\n", dash(function.OwnerUsername))
}
