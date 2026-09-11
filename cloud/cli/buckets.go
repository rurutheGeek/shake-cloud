package main

import (
	"context"
	"errors"
	"flag"
	"fmt"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) buckets(args []string) error {
	if len(args) == 0 {
		return errors.New("bucket needs a subcommand: ls, create, show, rm, allow, revoke")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		buckets, err := c.DescribeBuckets(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(buckets)
		}
		printBuckets(buckets)
		return nil
	case "create":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud bucket create NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		bucket, err := c.CreateBucket(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(bucket)
		}
		fmt.Printf("%s  %s  (%s)\n", bucket.BucketName, bucket.S3Endpoint, bucket.S3Region)
		return nil
	case "show":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud bucket show NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		bucket, err := c.DescribeBucket(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(bucket)
		}
		printBucketDetail(bucket)
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud bucket rm NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteBucket(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	case "allow":
		return g.bucketAllow(rest)
	case "revoke":
		if len(rest) != 2 {
			return errors.New("usage: shakecloud bucket revoke NAME KEY_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		bucket, err := c.DeleteBucketKey(context.Background(), rest[0], rest[1])
		if err != nil {
			return err
		}
		printBucketDetail(bucket)
		return nil
	default:
		return fmt.Errorf("unknown bucket subcommand %q", sub)
	}
}

func (g globals) bucketAllow(args []string) error {
	flags := flag.NewFlagSet("shakecloud bucket allow", flag.ContinueOnError)
	read := flags.Bool("read", false, "allow reading objects")
	write := flags.Bool("write", false, "allow writing objects")
	owner := flags.Bool("owner", false, "allow managing the bucket")
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if len(rest) != 2 {
		flags.Usage()
		return errors.New("usage: shakecloud bucket allow [--read] [--write] [--owner] NAME KEY_ID")
	}
	if !*read && !*write && !*owner {
		return errors.New("give at least one of --read, --write, --owner")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	bucket, err := c.PutBucketKey(context.Background(), rest[0], rest[1], *read, *write, *owner)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(bucket)
	}
	printBucketDetail(bucket)
	return nil
}

func (g globals) s3Keys(args []string) error {
	if len(args) == 0 {
		return errors.New("s3-key needs a subcommand: ls, create, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		keys, err := c.ListS3Keys(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(keys)
		}
		w := table()
		fmt.Fprintln(w, "KEY_ID\tNAME\tCREATED")
		for _, key := range keys {
			fmt.Fprintf(w, "%s\t%s\t%s\n", key.KeyID, key.Name, key.CreatedAt.Format("2006-01-02 15:04"))
		}
		w.Flush()
		return nil
	case "create":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud s3-key create NAME")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		key, err := c.CreateS3Key(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(key)
		}
		fmt.Printf("key_id     %s\n", key.KeyID)
		if key.SecretAccessKey != "" {
			fmt.Printf("secret     %s\n", key.SecretAccessKey)
			fmt.Println("この秘密値は今しか表示されません。安全な場所へ保存してください。")
		} else {
			fmt.Println("(既存のキーです。秘密値は作成時の一度だけ表示されます)")
		}
		return nil
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud s3-key rm KEY_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		if err := c.DeleteS3Key(context.Background(), rest[0]); err != nil {
			return err
		}
		fmt.Printf("%s deleted\n", rest[0])
		return nil
	default:
		return fmt.Errorf("unknown s3-key subcommand %q", sub)
	}
}

func printBuckets(buckets []client.Bucket) {
	w := table()
	fmt.Fprintln(w, "NAME\tOWNER\tOBJECTS\tBYTES\tKEYS\tS3_ENDPOINT")
	for _, bucket := range buckets {
		fmt.Fprintf(w, "%s\t%s\t%d\t%d\t%d\t%s\n",
			bucket.BucketName, dash(bucket.OwnerUsername), bucket.Objects, bucket.Bytes, len(bucket.Keys), bucket.S3Endpoint)
	}
	w.Flush()
}

func printBucketDetail(bucket client.Bucket) {
	fmt.Printf("%s  (%s  %s)\n", bucket.BucketName, bucket.S3Endpoint, bucket.S3Region)
	fmt.Printf("  owner %s  objects %d  bytes %d\n", dash(bucket.OwnerUsername), bucket.Objects, bucket.Bytes)
	if len(bucket.Keys) == 0 {
		fmt.Println("  keys: (none)")
		return
	}
	fmt.Println("  keys:")
	for _, key := range bucket.Keys {
		perms := ""
		if key.Read {
			perms += "R"
		}
		if key.Write {
			perms += "W"
		}
		if key.Owner {
			perms += "O"
		}
		fmt.Printf("    %s  %s  %s\n", key.KeyID, perms, key.KeyName)
	}
}
