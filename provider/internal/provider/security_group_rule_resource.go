package provider

import (
	"context"
	"strings"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/int64planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*securityGroupRuleResource)(nil)
	_ resource.ResourceWithConfigure   = (*securityGroupRuleResource)(nil)
	_ resource.ResourceWithImportState = (*securityGroupRuleResource)(nil)
)

func NewSecurityGroupRuleResource() resource.Resource { return &securityGroupRuleResource{} }

type securityGroupRuleResource struct {
	client *client.Client
}

type securityGroupRuleResourceModel struct {
	ID          types.String `tfsdk:"id"`
	GroupID     types.String `tfsdk:"group_id"`
	Direction   types.String `tfsdk:"direction"`
	Protocol    types.String `tfsdk:"protocol"`
	FromPort    types.Int64  `tfsdk:"from_port"`
	ToPort      types.Int64  `tfsdk:"to_port"`
	CIDR        types.String `tfsdk:"cidr"`
	Description types.String `tfsdk:"description"`
}

func (r *securityGroupRuleResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_security_group_rule"
}

func (r *securityGroupRuleResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "One ingress or egress rule. Rules are changed by replacing them, matching how the " +
			"API adds and revokes them one at a time.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The rule ID (`sgr-...`).",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"group_id": schema.StringAttribute{
				Required:      true,
				Description:   "The security group this rule belongs to.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"direction": schema.StringAttribute{
				Required:      true,
				Description:   "`ingress` or `egress`.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"protocol": schema.StringAttribute{
				Required:      true,
				Description:   "`tcp`, `udp`, `icmp`, `icmpv6` or `all`.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"from_port": schema.Int64Attribute{
				Optional:      true,
				Description:   "First port, for tcp and udp.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.RequiresReplace()},
			},
			"to_port": schema.Int64Attribute{
				Optional:      true,
				Description:   "Last port, for tcp and udp.",
				PlanModifiers: []planmodifier.Int64{int64planmodifier.RequiresReplace()},
			},
			"cidr": schema.StringAttribute{
				Required:      true,
				Description:   "Source (ingress) or destination (egress) CIDR, IPv4 or IPv6.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"description": schema.StringAttribute{
				Optional:      true,
				Description:   "A description.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
		},
	}
}

func (r *securityGroupRuleResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
	if req.ProviderData == nil {
		return
	}
	c, err := clientFrom(req.ProviderData)
	if err != nil {
		resp.Diagnostics.AddError("shake-cloud: provider not configured", err.Error())
		return
	}
	r.client = c
}

func (r *securityGroupRuleResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan securityGroupRuleResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	groupID := plan.GroupID.ValueString()
	before, err := r.client.DescribeSecurityGroup(ctx, groupID)
	if err != nil {
		addError(&resp.Diagnostics, "read the security group", err)
		return
	}
	existing := map[string]bool{}
	for _, rule := range append(before.Ingress, before.Egress...) {
		existing[rule.RuleID] = true
	}

	request := client.SecurityGroupRuleRequest{
		Protocol: plan.Protocol.ValueString(), CIDR: plan.CIDR.ValueString(),
		FromPort: optionalInt(plan.FromPort), ToPort: optionalInt(plan.ToPort),
		Description: plan.Description.ValueString(),
	}
	group, err := r.authorize(ctx, groupID, plan.Direction.ValueString(), request)
	if err != nil {
		addError(&resp.Diagnostics, "add the rule", err)
		return
	}
	rule, ok := findNewRule(append(group.Ingress, group.Egress...), existing)
	if !ok {
		resp.Diagnostics.AddError("shake-cloud: could not find the new rule", "the API accepted the rule but did not return it")
		return
	}
	plan.ID = types.StringValue(rule.RuleID)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *securityGroupRuleResource) authorize(ctx context.Context, groupID, direction string, rule client.SecurityGroupRuleRequest) (client.SecurityGroup, error) {
	if direction == "egress" {
		return r.client.AuthorizeEgress(ctx, groupID, []client.SecurityGroupRuleRequest{rule})
	}
	return r.client.AuthorizeIngress(ctx, groupID, []client.SecurityGroupRuleRequest{rule})
}

func (r *securityGroupRuleResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state securityGroupRuleResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	group, err := r.client.DescribeSecurityGroup(ctx, state.GroupID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the security group", err)
		return
	}
	rules := group.Ingress
	if state.Direction.ValueString() == "egress" {
		rules = group.Egress
	}
	for _, rule := range rules {
		if rule.RuleID == state.ID.ValueString() {
			state.Protocol = types.StringValue(rule.Protocol)
			state.CIDR = types.StringValue(rule.CIDR)
			state.Description = types.StringValue(rule.Description)
			if rule.FromPort != nil {
				state.FromPort = types.Int64Value(int64(*rule.FromPort))
			}
			if rule.ToPort != nil {
				state.ToPort = types.Int64Value(int64(*rule.ToPort))
			}
			resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
			return
		}
	}
	resp.State.RemoveResource(ctx)
}

func (r *securityGroupRuleResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *securityGroupRuleResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state securityGroupRuleResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if _, err := r.client.RevokeSecurityGroupRule(ctx, state.GroupID.ValueString(), state.ID.ValueString()); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "revoke the rule", err)
	}
}

// ImportState takes "GROUP_ID/RULE_ID"; direction is read back from the group.
func (r *securityGroupRuleResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	groupID, ruleID, found := strings.Cut(req.ID, "/")
	if !found || groupID == "" || ruleID == "" {
		resp.Diagnostics.AddError("shake-cloud: bad import id", "use GROUP_ID/RULE_ID, e.g. sg-.../sgr-...")
		return
	}
	group, err := r.client.DescribeSecurityGroup(ctx, groupID)
	if err != nil {
		addError(&resp.Diagnostics, "read the security group", err)
		return
	}
	direction := "ingress"
	foundRule := false
	for _, rule := range group.Ingress {
		if rule.RuleID == ruleID {
			foundRule = true
		}
	}
	if !foundRule {
		for _, rule := range group.Egress {
			if rule.RuleID == ruleID {
				direction, foundRule = "egress", true
			}
		}
	}
	if !foundRule {
		resp.Diagnostics.AddError("shake-cloud: no such rule", groupID+" has no rule "+ruleID)
		return
	}
	resp.Diagnostics.Append(resp.State.SetAttribute(ctx, path.Root("id"), ruleID)...)
	resp.Diagnostics.Append(resp.State.SetAttribute(ctx, path.Root("group_id"), groupID)...)
	resp.Diagnostics.Append(resp.State.SetAttribute(ctx, path.Root("direction"), direction)...)
}

func findNewRule(rules []client.SecurityGroupRule, existing map[string]bool) (client.SecurityGroupRule, bool) {
	for _, rule := range rules {
		if !existing[rule.RuleID] {
			return rule, true
		}
	}
	return client.SecurityGroupRule{}, false
}
