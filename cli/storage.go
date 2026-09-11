package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"os"

	"github.com/rurutheGeek/shake-cloud/cloud/client"
)

func (g globals) volumes(args []string) error {
	if len(args) == 0 {
		return errors.New("volume needs a subcommand: ls, create, rm, resize, attach, detach")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		volumes, err := c.DescribeVolumes(context.Background(), "")
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(volumes)
		}
		printVolumes(volumes)
		return nil
	case "create":
		return g.volumeCreate(rest)
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud volume rm VOLUME_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		volume, err := c.DeleteVolume(context.Background(), rest[0])
		if err != nil {
			return err
		}
		return g.volumeResult(volume)
	case "resize", "grow":
		if len(rest) != 2 {
			return errors.New("usage: shakecloud volume resize VOLUME_ID GIB")
		}
		size, err := parseInt(rest[1], "size")
		if err != nil {
			return err
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		volume, err := c.ModifyVolume(context.Background(), rest[0], size)
		if err != nil {
			return err
		}
		return g.volumeResult(volume)
	case "attach":
		return g.volumeAttach(rest)
	case "detach":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud volume detach VOLUME_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		volume, err := c.DetachVolume(context.Background(), rest[0])
		if err != nil {
			return err
		}
		return g.volumeResult(volume)
	default:
		return fmt.Errorf("unknown volume subcommand %q", sub)
	}
}

func (g globals) volumeCreate(args []string) error {
	flags := flag.NewFlagSet("shakecloud volume create", flag.ContinueOnError)
	size := flags.Int("size", 0, "size in GiB (required)")
	name := flags.String("name", "", "Name tag")
	clientToken := flags.String("client-token", "", "idempotency token")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *size <= 0 {
		flags.Usage()
		return errors.New("--size is required")
	}
	request := client.CreateVolumeRequest{SizeGiB: *size, ClientToken: *clientToken}
	if *name != "" {
		request.Tags = map[string]string{"Name": *name}
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	volume, err := c.CreateVolume(context.Background(), request)
	if err != nil {
		return err
	}
	if *clientToken == "" {
		// A volume is created asynchronously; wait a little so a create that
		// immediately fails is reported here rather than silently later.
		volume, _ = waitVolume(c, volume.VolumeID, "available", "in-use")
	}
	return g.volumeResult(volume)
}

func (g globals) volumeAttach(args []string) error {
	flags := flag.NewFlagSet("shakecloud volume attach", flag.ContinueOnError)
	instance := flags.String("instance", "", "instance id (required)")
	device := flags.String("device", "", "virtio1..virtio15")
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if len(rest) != 1 || *instance == "" {
		flags.Usage()
		return errors.New("usage: shakecloud volume attach VOLUME_ID --instance INSTANCE_ID [--device virtioN]")
	}
	c, err := g.client()
	if err != nil {
		return err
	}
	volume, err := c.AttachVolume(context.Background(), rest[0], client.AttachVolumeRequest{InstanceID: *instance, Device: *device})
	if err != nil {
		return err
	}
	return g.volumeResult(volume)
}

func waitVolume(c *client.Client, id string, wanted ...string) (client.Volume, error) {
	volume, err := c.DescribeVolume(context.Background(), id)
	return volume, err
}

func (g globals) volumeResult(volume client.Volume) error {
	if g.json {
		return g.printJSON(volume)
	}
	printVolumes([]client.Volume{volume})
	return nil
}

func printVolumes(volumes []client.Volume) {
	w := table()
	fmt.Fprintln(w, "VOLUME_ID\tNAME\tOWNER\tSIZE\tSTATE\tATTACHED_TO\tDEVICE")
	for _, v := range volumes {
		attachedTo, device := "-", "-"
		if v.Attachment != nil {
			attachedTo, device = v.Attachment.InstanceID, v.Attachment.Device
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%dGiB\t%s\t%s\t%s\n",
			v.VolumeID, dash(v.Tags["Name"]), dash(v.OwnerUsername), v.SizeGiB, v.State, attachedTo, device)
	}
	w.Flush()
}

func (g globals) images(args []string) error {
	if len(args) == 0 {
		return errors.New("image needs a subcommand: ls, upload, rm")
	}
	sub, rest := args[0], args[1:]
	switch sub {
	case "ls", "list":
		c, err := g.client()
		if err != nil {
			return err
		}
		images, err := c.DescribeImages(context.Background())
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(images)
		}
		w := table()
		fmt.Fprintln(w, "IMAGE_ID\tNAME\tOWNER\tSIZE_MIB\tSHARED")
		for _, image := range images {
			owner := image.OwnerUsername
			if image.Public {
				owner = "(shared)"
			}
			fmt.Fprintf(w, "%s\t%s\t%s\t%d\t%t\n", image.ImageID, image.Name, dash(owner), image.SizeMiB, image.Public)
		}
		w.Flush()
		return nil
	case "upload":
		return g.imageUpload(rest)
	case "rm", "delete":
		if len(rest) != 1 {
			return errors.New("usage: shakecloud image rm IMAGE_ID")
		}
		c, err := g.client()
		if err != nil {
			return err
		}
		image, err := c.DeleteImage(context.Background(), rest[0])
		if err != nil {
			return err
		}
		if g.json {
			return g.printJSON(image)
		}
		fmt.Printf("%s deleted\n", image.ImageID)
		return nil
	default:
		return fmt.Errorf("unknown image subcommand %q", sub)
	}
}

func (g globals) imageUpload(args []string) error {
	flags := flag.NewFlagSet("shakecloud image upload", flag.ContinueOnError)
	name := flags.String("name", "", "image name (required)")
	if err := flags.Parse(args); err != nil {
		return err
	}
	rest := flags.Args()
	if len(rest) != 1 || *name == "" {
		flags.Usage()
		return errors.New("usage: shakecloud image upload --name NAME FILE")
	}
	file, err := os.Open(rest[0])
	if err != nil {
		return err
	}
	defer file.Close()
	c, err := g.client()
	if err != nil {
		return err
	}
	image, err := c.ImportImage(context.Background(), *name, rest[0], file)
	if err != nil {
		return err
	}
	if g.json {
		return g.printJSON(image)
	}
	fmt.Printf("%s uploaded (%d MiB)\n", image.ImageID, image.SizeMiB)
	return nil
}

func parseInt(text, what string) (int, error) {
	var value int
	if _, err := fmt.Sscan(text, &value); err != nil {
		return 0, fmt.Errorf("%s: expected a number, got %q", what, text)
	}
	return value, nil
}
