package main

import (
	"context"
	"errors"
	"flag"
	"fmt"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) databases(args []string) error {
	if len(args) == 0 {
		return errors.New("database needs a subcommand: ls, create, show, rm, credentials")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		databases, err := c.DescribeDatabases(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(databases)
		}
		printDatabases(databases)
		return nil
	case "create":
		flags := flag.NewFlagSet("shakecloud database create", flag.ContinueOnError)
		storage := flags.Int("storage-gib", 5, "disk size in GiB (1-50)")
		if err := flags.Parse(rest); err != nil {
			return err
		}
		names := flags.Args()
		if len(names) != 1 {
			return errors.New("usage: shakecloud database create [--storage-gib N] NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		database, err := c.CreateDatabase(context.Background(), names[0], *storage)
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(database)
		}
		printDatabaseDetail(database)
		return nil
	case "show":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud database show DATABASE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		database, err := c.DescribeDatabase(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(database)
		}
		printDatabaseDetail(database)
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud database rm DATABASE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteDatabase(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	case "credentials", "creds":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud database credentials DATABASE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		credentials, err := c.DatabaseCredentials(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(credentials)
		}
		fmt.Printf("host      %s\n", credentials.Host)
		fmt.Printf("port      %s\n", credentials.Port)
		fmt.Printf("database  %s\n", credentials.Database)
		fmt.Printf("username  %s\n", credentials.Username)
		fmt.Printf("password  %s\n", credentials.Password)
		return nil
	default:
		return fmt.Errorf("unknown database subcommand %q", sub)
	}
}

func printDatabases(databases []client.Database) {
	w := table()
	fmt.Fprintln(w, "DATABASE_ID\tNAME\tSTATUS\tREADY\tSTORAGE_GIB\tHOST")
	for _, database := range databases {
		fmt.Fprintf(w, "%s\t%s\t%s\t%d/%d\t%d\t%s\n",
			database.DatabaseID, database.Name, database.Status,
			database.ReadyInstances, database.Instances, database.StorageGiB, database.Host)
	}
	w.Flush()
}

func printDatabaseDetail(database client.Database) {
	fmt.Printf("%s  %s  (%s %s, %dGiB)\n",
		database.DatabaseID, database.Name, database.Engine, database.EngineVersion, database.StorageGiB)
	fmt.Printf("  status %s  ready %d/%d\n", database.Status, database.ReadyInstances, database.Instances)
	fmt.Printf("  host %s:%d\n", database.Host, database.Port)
	fmt.Printf("  owner %s\n", dash(database.OwnerUsername))
}
