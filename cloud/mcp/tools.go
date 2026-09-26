package main

import (
	"context"

	"github.com/modelcontextprotocol/go-sdk/mcp"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

// The input shapes. A field without omitempty is required; the jsonschema tag
// is what the model reads, so it says what an id looks like.
type (
	noArgs struct{}

	eventsArgs struct {
		AccountID  string `json:"account_id,omitempty" jsonschema:"only events of this account; admins only"`
		EventName  string `json:"event_name,omitempty" jsonschema:"only events with this operation id, e.g. RunInstances"`
		MaxResults int    `json:"max_results,omitempty" jsonschema:"how many events, newest first (default 20)"`
	}

	instancesArgs struct {
		AccountID string `json:"account_id,omitempty" jsonschema:"list only this account's instances; admins only"`
	}

	instanceArgs struct {
		InstanceID string `json:"instance_id" jsonschema:"the instance id, e.g. i-0123456789abcdef0"`
	}

	volumesArgs struct {
		AccountID string `json:"account_id,omitempty" jsonschema:"list only this account's volumes; admins only"`
	}

	volumeArgs struct {
		VolumeID string `json:"volume_id" jsonschema:"the volume id, e.g. vol-0123456789abcdef0"`
	}

	securityGroupArgs struct {
		GroupID string `json:"group_id" jsonschema:"the security group id, e.g. sg-0123456789abcdef0"`
	}

	bucketArgs struct {
		BucketName string `json:"bucket_name" jsonschema:"the bucket name"`
	}

	databaseArgs struct {
		DatabaseID string `json:"database_id" jsonschema:"the database id, e.g. db-0123456789abcdef0"`
	}

	functionArgs struct {
		FunctionID string `json:"function_id" jsonschema:"the function id, e.g. fn-0123456789abcdef0"`
	}
)

// addTools registers every read-only operation the API documents. The one
// omission is GetDatabaseCredentials, which returns a password: a model must
// not pull secrets into a conversation. server_test.go checks the set against
// cloud/openapi/shakecloud.yaml, so a new read operation cannot go missing
// quietly.
func addTools(s *mcp.Server, c *client.Client) {
	readTool(s, "shakecloud_get_caller_identity",
		"Who the configured access key belongs to (account, username, admin) and whether the key is ReadOnly or ReadWrite.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, client.CallerIdentity, error) {
			identity, err := c.CallerIdentity(ctx)
			return nil, identity, err
		})

	readTool(s, "shakecloud_list_access_keys",
		"List the account's access keys: id, description, scope, status and expiry. Secrets are never returned.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.AccessKey, error) {
			keys, err := c.ListAccessKeys(ctx)
			return nil, keys, err
		})

	readTool(s, "shakecloud_lookup_events",
		"Read the audit log, newest first. Filter by account or operation id.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args eventsArgs) (*mcp.CallToolResult, []client.AuditEvent, error) {
			events, err := c.LookupEvents(ctx, args.AccountID, args.EventName, args.MaxResults)
			return nil, events, err
		})

	readTool(s, "shakecloud_describe_instances",
		"List cloud instances (VMs): state, owner, IP address, size and security groups. Admins see every account's instances.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args instancesArgs) (*mcp.CallToolResult, []client.Instance, error) {
			instances, err := c.DescribeInstances(ctx, args.AccountID)
			return nil, instances, err
		})

	readTool(s, "shakecloud_describe_instance",
		"One instance by id.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args instanceArgs) (*mcp.CallToolResult, client.Instance, error) {
			instance, err := c.DescribeInstance(ctx, args.InstanceID)
			return nil, instance, err
		})

	readTool(s, "shakecloud_describe_instance_types",
		"Named instance type shorthands (vCPUs, memory, root disk). Sizes are not a fixed catalogue; these are starting points.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.InstanceType, error) {
			types, err := c.DescribeInstanceTypes(ctx)
			return nil, types, err
		})

	readTool(s, "shakecloud_describe_capacity",
		"Node memory, CPU and storage headroom, what the cloud has allotted, and per-account usage (admins see every account).",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, client.Capacity, error) {
			capacity, err := c.DescribeCapacity(ctx)
			return nil, capacity, err
		})

	readTool(s, "shakecloud_describe_limits",
		"Quotas and capacity limits now in force, including administrator overrides.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, client.LimitsResponse, error) {
			limits, err := c.DescribeLimits(ctx)
			return nil, limits, err
		})

	readTool(s, "shakecloud_describe_images",
		"Bootable disk images available to launch instances from.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.Image, error) {
			images, err := c.DescribeImages(ctx)
			return nil, images, err
		})

	readTool(s, "shakecloud_describe_isos",
		"Installation media (ISOs): the caller's uploads plus the administrator's shared ones.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.ISO, error) {
			isos, err := c.DescribeISOs(ctx)
			return nil, isos, err
		})

	readTool(s, "shakecloud_describe_key_pairs",
		"SSH key pairs registered for the account, by name and fingerprint.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.KeyPair, error) {
			keys, err := c.DescribeKeyPairs(ctx)
			return nil, keys, err
		})

	readTool(s, "shakecloud_describe_volumes",
		"Detachable block volumes: size, state and attachment. Admins see every account's volumes.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args volumesArgs) (*mcp.CallToolResult, []client.Volume, error) {
			volumes, err := c.DescribeVolumes(ctx, args.AccountID)
			return nil, volumes, err
		})

	readTool(s, "shakecloud_describe_volume",
		"One volume by id.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args volumeArgs) (*mcp.CallToolResult, client.Volume, error) {
			volume, err := c.DescribeVolume(ctx, args.VolumeID)
			return nil, volume, err
		})

	readTool(s, "shakecloud_describe_security_groups",
		"Security groups and their ingress and egress rules.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.SecurityGroup, error) {
			groups, err := c.DescribeSecurityGroups(ctx)
			return nil, groups, err
		})

	readTool(s, "shakecloud_describe_security_group",
		"One security group by id, with its rules.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args securityGroupArgs) (*mcp.CallToolResult, client.SecurityGroup, error) {
			group, err := c.DescribeSecurityGroup(ctx, args.GroupID)
			return nil, group, err
		})

	readTool(s, "shakecloud_describe_buckets",
		"S3-compatible buckets and the key ids allowed on them.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.Bucket, error) {
			buckets, err := c.DescribeBuckets(ctx)
			return nil, buckets, err
		})

	readTool(s, "shakecloud_describe_bucket",
		"One bucket by name, with its key permissions.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args bucketArgs) (*mcp.CallToolResult, client.Bucket, error) {
			bucket, err := c.DescribeBucket(ctx, args.BucketName)
			return nil, bucket, err
		})

	readTool(s, "shakecloud_list_s3_keys",
		"S3 access key ids and names. Secrets are never returned.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.S3Key, error) {
			keys, err := c.ListS3Keys(ctx)
			return nil, keys, err
		})

	readTool(s, "shakecloud_describe_databases",
		"PostgreSQL databases (CloudNativePG): name, state, size and connection host.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.Database, error) {
			databases, err := c.DescribeDatabases(ctx)
			return nil, databases, err
		})

	readTool(s, "shakecloud_describe_database",
		"One database by id. Credentials are deliberately not available here.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args databaseArgs) (*mcp.CallToolResult, client.Database, error) {
			database, err := c.DescribeDatabase(ctx, args.DatabaseID)
			return nil, database, err
		})

	readTool(s, "shakecloud_describe_functions",
		"Serverless functions (Knative): name, state and URL.",
		func(ctx context.Context, _ *mcp.CallToolRequest, _ noArgs) (*mcp.CallToolResult, []client.Function, error) {
			functions, err := c.DescribeFunctions(ctx)
			return nil, functions, err
		})

	readTool(s, "shakecloud_describe_function",
		"One function by id.",
		func(ctx context.Context, _ *mcp.CallToolRequest, args functionArgs) (*mcp.CallToolResult, client.Function, error) {
			function, err := c.DescribeFunction(ctx, args.FunctionID)
			return nil, function, err
		})
}
