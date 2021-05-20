// USB.c connects with a USB device and sends commands
// created 17/11/2020 by Andi
// to compile with libusb:
// see https://forums.xilinx.com/t5/Embedded-Linux/PetaLinux-2019-need-to-support-on-adding-libusb/td-p/1010540
// - enable libusb1 in petalinux-config -c rootfs /filesystem packages/misc/libusb1
// - add following entries to your project.bb:
//   inherit pkgconfig
//   TARGET_CC_ARCH += "${LDFLAGS}"
//   DEPENDS += "libusb"
// - add/modify following entries in makefile:
//   LIBUSB_CFLAGS = $(shell pkg-config --cflags libusb-1.0)
//   LIBUSB_LIBS = $(shell pkg-config --libs libusb-1.0)
//   CFLAGS = $(LIBUSB_CFLAGS) $(WARNINGS)
//   LDFLAGS = $(LIBUSB_LIBS)
//   $(APP): $(APP_OBJS)
//	   $(CXX) $(LDFLAGS) $(LDFLAGS) -o $@ $(APP_OBJS) $(LDLIBS) $(LDFLAGS) 
// last change 17/11/2020 by Andi

#include <libusb-1.0/libusb.h>
#include <stdio.h>                  // printf, fopen

// print device info
int print_info(libusb_device *dev) {
    int err, j;
    uint8_t i, k;
    struct libusb_device_descriptor dsc;
    struct libusb_config_descriptor *conf;
    const struct libusb_interface *intf;
    const struct libusb_interface_descriptor *intf_dsc;
    const struct libusb_endpoint_descriptor *ep_dsc;

    err = libusb_get_device_descriptor(dev, &dsc);
    if (!err) {
        printf("VID 0x%04x, PID 0x%04x, class 0x%02x.0x%02x, configs %d\n", (unsigned)dsc.idVendor, (unsigned)dsc.idProduct, (unsigned)dsc.bDeviceClass, (unsigned)dsc.bDeviceSubClass, (int)dsc.bNumConfigurations);
        libusb_get_config_descriptor(dev, 0, &conf);
        for(i = 0; i < conf->bNumInterfaces; ++i) {
            intf = &conf->interface[i];
            for(j = 0; j < intf->num_altsetting; ++j) {
                intf_dsc = &intf->altsetting[j];
                for(k = 0; k < intf_dsc->bNumEndpoints; k++) {
                    ep_dsc = &intf_dsc->endpoint[k];
                    printf("%i/%i: interface %03u type 0x%02x EP address 0x%02x\n", (unsigned)i, j, (unsigned)intf_dsc->bInterfaceNumber, (unsigned)ep_dsc->bDescriptorType, (unsigned)ep_dsc->bEndpointAddress);
                }
            }
        }
        libusb_free_config_descriptor(conf);
    }
    return err;
}


// enum all devices
int enum_devices(void) {
    int err, num, i;
    struct libusb_device **device;
    struct libusb_context *ctx = NULL;
    err = libusb_init(&ctx);
    if(!err) {
        //libusb_set_debug(ctx, 3); // set verbosity level to 3
        err = libusb_get_device_list(ctx, &device);
        if (err < 0) printf("error %d enumerating USB devices!\n", num);
        else {
            num = err;
            err = 0;
            printf("%d USB devices found\n", num);
            for(i = 0; (i < num) && (!err); ++i) {
                err = print_info(device[i]);
            }
            libusb_free_device_list(device, 1);
        }
        libusb_exit(ctx);
    }
    return err;
}

// open device with given VID and PID
// for testing we also write data to device and close it immediately
int open_device(int VID, int PID) {
{
    static unsigned char data[7] = "*IDN?\n"; // data to be written to device
    const int num = 6; // number of chars to write
    const int interface = 0; // device interface
    const int EP_out = 2; // device output endpoint
    int err = 0, written;
    struct libusb_device **device;
    struct libusb_device_handle *dev_handle;
    struct libusb_context *ctx = NULL;
    err = libusb_init(&ctx);
    if(!err) {
        // libusb_set_debug(ctx, 3); //set verbosity level to 3
        err = libusb_get_device_list(ctx, &device); //get the list of devices
        if(err < 0) printf("error %d enumerating USB devices!\n", err);
            dev_handle = libusb_open_device_with_vid_pid(ctx, VID, PID);
            libusb_free_device_list(device, 1);
            if(dev_handle == NULL) printf("error opening USB device VID %d PID %d!\n", VID, PID);
            else {
                // ensure no kernel driver is attached
                if(libusb_kernel_driver_active(dev_handle, 0) == 1) {
                    err = libusb_detach_kernel_driver(dev_handle, 0); 
                    if (err) printf("could not detach kernel driver from device (device in use?)\n");
                    else printf("note: kernel driver detached.\n");
                }
                if(!err) {
                    err = libusb_claim_interface(dev_handle, interface);
                    if(err) printf("error %d claiming interface %d\n", err, interface);
                    else {
                        err = libusb_bulk_transfer(dev_handle, EP_out | LIBUSB_ENDPOINT_OUT, data, num, &written, 0);
                        if(err) printf("error %d writing %d bytes\n", err, num);
                        else if(written != num) { printf("error %d bytes written instead of %d\n", written, num); err = -200; }
                        else {
                            printf("%d bytes written ok\n", num);
                            // TODO: read back responds LIBUSB_ENDPOINT_IN
                        }
                        if (libusb_release_interface(dev_handle, 0)) printf("error releasing interface\n");
                    }
                }
                libusb_close(dev_handle); //close the device we opened
            }
        }
        libusb_exit(ctx); //needs to be called to end the
    }
    return 0;
}



