package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"
)

func (g globals) keyPairs(args []string) error {
	if len(args) == 0 {
		return errors.New("key needs a subcommand: ls, import, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		keys, err := c.DescribeKeyPairs(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(keys)
		}
		w := table()
		fmt.Fprintln(w, "NAME\tFINGERPRINT\tCREATED")
		for _, key := range keys {
			fmt.Fprintf(w, "%s\t%s\t%s\n", key.KeyName, key.Fingerprint, key.CreatedAt.Format("2006-01-02 15:04"))
		}
		w.Flush()
		return nil
	case "import", "add":
		return g.keyPairImport(rest)
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud key rm NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteKeyPair(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	default:
		return fmt.Errorf("unknown key subcommand %q", sub)
	}
}

func (g globals) keyPairImport(args []string) error {
	flags := flag.NewFlagSet("shakecloud key import", flag.ContinueOnError)
	name := flags.String("name", "", "key name (required)")
	publicKey := flags.String("public-key", "", "the public key text; otherwise give a file")
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if *name == "" {
		flags.Usage()
		return errors.New("--name is required")
	}
	text := *publicKey
	if text == "" {
		if len(rest) != 1 {
			flags.Usage()
			return errors.New("give --public-key or a path to a .pub file")
		}
		data, err := os.ReadFile(rest[0])
		if err != nil {
			return err
		}
		text = strings.TrimSpace(string(data))
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	key, err := c.ImportKeyPair(context.Background(), *name, text)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(key)
	}
	fmt.Printf("%s  %s\n", key.KeyName, key.Fingerprint)
	return nil
}

func (g globals) accessKeys(args []string) error {
	if len(args) == 0 {
		return errors.New("access-key needs a subcommand: ls, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		keys, err := c.ListAccessKeys(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(keys)
		}
		w := table()
		fmt.Fprintln(w, "ACCESS_KEY_ID\tSTATUS\tSCOPE\tDESCRIPTION\tCREATED\tLAST_USED")
		for _, key := range keys {
			lastUsed := "-"
			if key.LastUsedDate != nil {
				lastUsed = key.LastUsedDate.Format("2006-01-02 15:04")
			}
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\n",
				key.AccessKeyID, key.Status, key.Scope, dash(key.Description), key.CreateDate.Format("2006-01-02 15:04"), lastUsed)
		}
		w.Flush()
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud access-key rm ACCESS_KEY_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteAccessKey(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s revoked\n", rest[0])
		return nil
	default:
		return fmt.Errorf("unknown access-key subcommand %q", sub)
	}
}
