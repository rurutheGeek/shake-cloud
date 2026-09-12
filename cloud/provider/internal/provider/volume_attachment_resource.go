package provider

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/hashicorp/terraform-plugin-framework/path"
	"github.com/hashicorp/terraform-plugin-framework/resource"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/planmodifier"
	"github.com/hashicorp/terraform-plugin-framework/resource/schema/stringplanmodifier"
	"github.com/hashicorp/terraform-plugin-framework/types"
	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

var (
	_ resource.Resource                = (*volumeAttachmentResource)(nil)
	_ resource.ResourceWithConfigure   = (*volumeAttachmentResource)(nil)
	_ resource.ResourceWithImportState = (*volumeAttachmentResource)(nil)
)

func NewVolumeAttachmentResource() resource.Resource { return &volumeAttachmentResource{} }

type volumeAttachmentResource struct {
	client *client.Client
}

type volumeAttachmentResourceModel struct {
	ID         types.String `tfsdk:"id"`
	VolumeID   types.String `tfsdk:"volume_id"`
	InstanceID types.String `tfsdk:"instance_id"`
	Device     types.String `tfsdk:"device"`
	DevicePath types.String `tfsdk:"device_path"`
}

func (r *volumeAttachmentResource) Metadata(_ context.Context, req resource.MetadataRequest, resp *resource.MetadataResponse) {
	resp.TypeName = req.ProviderTypeName + "_volume_attachment"
}

func (r *volumeAttachmentResource) Schema(_ context.Context, _ resource.SchemaRequest, resp *resource.SchemaResponse) {
	resp.Schema = schema.Schema{
		MarkdownDescription: "Attaches a `shakecloud_volume` to an instance. Mirrors `aws_volume_attachment`; the " +
			"attachment has no id of its own, so its id is the volume's.",
		Attributes: map[string]schema.Attribute{
			"id": schema.StringAttribute{
				Computed:      true,
				Description:   "The volume ID, which identifies the attachment.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.UseStateForUnknown()},
			},
			"volume_id": schema.StringAttribute{
				Required:      true,
				Description:   "The volume to attach.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace()},
			},
			"instance_id": schema.StringAttribute{
				Optional:      true,
				Computed:      true,
				Description:   "The instance to attach it to.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace(), stringplanmodifier.UseStateForUnknown()},
			},
			"device": schema.StringAttribute{
				Optional:      true,
				Computed:      true,
				Description:   "The virtio slot, e.g. virtio1. Omitted means the lowest free one.",
				PlanModifiers: []planmodifier.String{stringplanmodifier.RequiresReplace(), stringplanmodifier.UseStateForUnknown()},
			},
			"device_path": schema.StringAttribute{Computed: true, Description: "The path inside the guest, e.g. /dev/disk/by-id/virtio-vol...."},
		},
	}
}

func (r *volumeAttachmentResource) Configure(_ context.Context, req resource.ConfigureRequest, resp *resource.ConfigureResponse) {
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

func (r *volumeAttachmentResource) Create(ctx context.Context, req resource.CreateRequest, resp *resource.CreateResponse) {
	var plan volumeAttachmentResourceModel
	resp.Diagnostics.Append(req.Plan.Get(ctx, &plan)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if plan.InstanceID.ValueString() == "" {
		resp.Diagnostics.AddError("shake-cloud: instance_id is required", "set the instance to attach the volume to")
		return
	}
	if _, err := r.client.AttachVolume(ctx, plan.VolumeID.ValueString(), client.AttachVolumeRequest{
		InstanceID: plan.InstanceID.ValueString(), Device: plan.Device.ValueString(),
	}); err != nil {
		addError(&resp.Diagnostics, "attach the volume", err)
		return
	}
	attachment, err := r.wait(ctx, plan.VolumeID.ValueString(), func(v client.Volume) bool {
		return v.Attachment != nil && v.Attachment.State == "attached"
	})
	if err != nil {
		addError(&resp.Diagnostics, "wait for the attachment", err)
		return
	}
	fillVolumeAttachment(&plan, attachment)
	resp.Diagnostics.Append(resp.State.Set(ctx, &plan)...)
}

func (r *volumeAttachmentResource) Read(ctx context.Context, req resource.ReadRequest, resp *resource.ReadResponse) {
	var state volumeAttachmentResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	volume, err := r.client.DescribeVolume(ctx, state.VolumeID.ValueString())
	if isNotFound(err) {
		resp.State.RemoveResource(ctx)
		return
	}
	if err != nil {
		addError(&resp.Diagnostics, "read the volume", err)
		return
	}
	if volume.Attachment == nil {
		resp.State.RemoveResource(ctx)
		return
	}
	fillVolumeAttachment(&state, volume)
	resp.Diagnostics.Append(resp.State.Set(ctx, &state)...)
}

func (r *volumeAttachmentResource) Update(_ context.Context, _ resource.UpdateRequest, _ *resource.UpdateResponse) {
	// Every attribute forces replacement, so Update is never called.
}

func (r *volumeAttachmentResource) Delete(ctx context.Context, req resource.DeleteRequest, resp *resource.DeleteResponse) {
	var state volumeAttachmentResourceModel
	resp.Diagnostics.Append(req.State.Get(ctx, &state)...)
	if resp.Diagnostics.HasError() {
		return
	}
	if _, err := r.client.DetachVolume(ctx, state.VolumeID.ValueString()); err != nil {
		if isNotFound(err) {
			return
		}
		// The volume being deleted is not an attachment to remove.
		var apiError *client.APIError
		if !errors.As(err, &apiError) || apiError.Code != "IncorrectState" {
			addError(&resp.Diagnostics, "detach the volume", err)
			return
		}
	}
	if _, err := r.wait(ctx, state.VolumeID.ValueString(), func(v client.Volume) bool {
		return v.Attachment == nil || v.State == "deleted"
	}); err != nil && !isNotFound(err) {
		addError(&resp.Diagnostics, "wait for the detach", err)
	}
}

func (r *volumeAttachmentResource) ImportState(ctx context.Context, req resource.ImportStateRequest, resp *resource.ImportStateResponse) {
	resp.Diagnostics.Append(resp.State.SetAttribute(ctx, path.Root("id"), req.ID)...)
	resp.Diagnostics.Append(resp.State.SetAttribute(ctx, path.Root("volume_id"), req.ID)...)
}

func (r *volumeAttachmentResource) wait(ctx context.Context, volumeID string, done func(client.Volume) bool) (client.Volume, error) {
	deadline := time.Now().Add(10 * time.Minute)
	for {
		volume, err := r.client.DescribeVolume(ctx, volumeID)
		if err != nil {
			return volume, err
		}
		if done(volume) {
			return volume, nil
		}
		if time.Now().After(deadline) {
			return volume, fmt.Errorf("volume %s is still %s", volumeID, volume.State)
		}
		select {
		case <-ctx.Done():
			return volume, ctx.Err()
		case <-time.After(3 * time.Second):
		}
	}
}

func fillVolumeAttachment(model *volumeAttachmentResourceModel, volume client.Volume) {
	model.ID = types.StringValue(volume.VolumeID)
	model.VolumeID = types.StringValue(volume.VolumeID)
	if volume.Attachment != nil {
		model.InstanceID = types.StringValue(volume.Attachment.InstanceID)
		model.Device = types.StringValue(volume.Attachment.Device)
		model.DevicePath = stringOrNull(volume.Attachment.DevicePath)
	}
}
