# S5 R1 USB multi-camera field notes

Field tests: November 2026. This is a sanitized record of one printer, not a universal camera compatibility list.

## Tested platform and result

UltiMaker S5 R1, firmware 9.0.3.0, Linux 4.14.32-ultimaker, Allwinner A20/LIME2. Stock USB camera: VID:PID 28c7:3841. Added cameras: InnoMaker U20CAM-1080PD&N-S1 (0bda:5856) and Macally mZoomCam (fefe:3106).

**Reliable simultaneous capture from two USB cameras was not established.** The stock camera was recovered and worked in its original MJPEG mode. Logitech C310 was proposed for a later test; compatibility remains untested.

## What happened

| Configuration | Observed result |
| --- | --- |
| Stock camera, original MJPEG | Valid 800x600 snapshot; negotiated 30 fps. A successful still does not measure sustained delivered frame rate. |
| Added cameras behind an internal hub, MJPEG | Repeated URB submission error -28; no reliable two-feed result. |
| Both cameras requested YUYV 800x600, 10 fps, global quirks=128 | After correcting persistence, flags survived reboot. Snapshots timed out even without fresh -28. InnoMaker negotiated 20 fps instead of requested 10. |
| Stock alone, YUYV 800x600, 10 fps, quirks=128 | Snapshot timed out. |
| Stock returned to MJPEG; service restart | Snapshot recovered while quirks=128 was still active. This implicates the changed capture path, without isolating its exact failure. |
| InnoMaker on front USB/MUSB | YUYV and MJPEG failed with allocation/URB -28; stock MJPEG could still work. |
| Macally on front USB, MJPEG 640x480 at 30 fps | Fresh `iso hwep alloc failed for 3x1024`, then -28; no snapshot. |
| Macally requested 320x240 YUYV | Unsupported: advertised YUYV modes included 1280x720, 640x480 and 640x360; negotiation substituted 640x360. |
| Macally 640x360 YUYV, requested 10 fps | Negotiated 30 fps; fresh -28 and no snapshot. |
| Macally on shared internal EHCI path, YUYV | Fresh -28; both snapshot requests failed in that check. |
| Same shared path, Macally restored to MJPEG 640x480 | Added camera still failed; stock MJPEG recovered. |
| Final rollback and reboot/reassembly | Vendor files unchanged, experimental overrides removed, stock snapshot recovered. |

The added InnoMaker enumerated on a Windows PC and yielded one frame in an OpenCV test. Subsequent capture attempts failed; another application's exclusive access was a possibility, not proven. This did not establish printer compatibility.

## Enumeration, controller topology and streaming are separate checks

A UVC device can enumerate, acquire a video node and start an HTTP service yet still fail to capture. On the tested printer the front port was on a separate MUSB controller; stock/internal cameras used an EHCI path. Different sockets or a USB 3 hub on a USB 2 host do not establish independent controllers. Inspect `lsusb -t` and sysfs.

The installed hotplug rule `90-camera_hotplug.rules` started `mjpg-streamer@<video-index>.service`. The launcher derived a port using `808<index>` for the observed indices. Check the actual launcher; do not assume a portable numbering formula. Video node numbering follows discovery order and may differ across kernels. Identify capture nodes by capabilities and USB VID/PID or stable device paths.

A bare request to port 8080 returned `501: Not Implemented! no www-folder configured`. That is a missing homepage, not a failed camera. Use `/?action=snapshot` or `/?action=stream`. Test each feed independently before testing both.

A separate console issue was also observed: the camera worked at the current printer address, but the management page constructed snapshot URLs from an old address in the cluster inventory. A reset reportedly resolved it. Inspect the requested URL and inventory before modifying the camera driver.

## Interpreting -28 and the bandwidth quirk

- -28 is ENOSPC. It can describe periodic USB resource exhaustion. The specific MUSB `iso hwep alloc failed` message indicates hardware-endpoint allocation failure; it does not by itself prove the 480 Mbps link is saturated.
- Upstream Linux 4.14 sunxi MUSB code configures 512-byte FIFOs; the host scheduler considers packet size and high-bandwidth multiplier. This supports an endpoint-capacity explanation for 3x1024 in these tests. The exact vendor-kernel configuration was not reconstructed: an immutable silicon limit, or a mandatory 6144-byte double buffer, was **not** proven.
- `UVC_QUIRK_FIX_BANDWIDTH` (128 / 0x80) estimates bandwidth for uncompressed video. It is not an MJPEG bandwidth limiter. Global overrides may replace device-specific quirks.
- `input_uvc.so -y` requests YUYV; the host then JPEG-encodes frames. This increases raw USB traffic and host CPU work. Reducing reservations and reducing actual traffic are different effects.
- Requested resolution/FPS must be verified after negotiation. Lower requested FPS did not force these cameras to use it.
- No test proved a fixed maximum MJPEG reservation at every resolution, a power-budget cause, or a universal cure from changing ports.

## Practical next-test procedure

1. Work during printer maintenance time. Back up service launchers, overrides and module parameters; record the original value rather than assuming zero.
2. Confirm stock capture alone, then identify the second camera's actual formats, frame intervals and controller.
3. Test the added camera alone at a supported mode. Record negotiated format, fresh kernel errors and a valid image; an HTTP listener is insufficient.
4. Test both together and verify that views differ. Native camera index 1 can be unexposed even when Linux sees another camera. Separate HTTP ports do not create USB bandwidth or endpoint resources.
5. Prefer verified hardware MJPEG when it works. Treat low-rate YUYV plus a quirk as an experiment, not a default fix.
6. Restore exact original settings on failure. The baseline here was `4294967295` (automatic per-device quirks), not zero. Live module reload produced registration warnings/no video nodes in one rollback; reboot/reassembly restored capture. Do not unload camera drivers during a print.
7. Check stock capture again after rollback. No successful multi-camera recipe is claimed by this log.

No camera firmware, printer firmware or bootloader was modified. Raw logs, images, hostnames, LAN addresses, Wi-Fi identities, credentials, individual device serials and job identifiers are deliberately excluded.

## References

- [Linux UVC FAQ](https://www.ideasonboard.org/uvc/faq/)
- [Linux 4.14 sunxi MUSB configuration](https://github.com/torvalds/linux/blob/v4.14/drivers/usb/musb/sunxi.c)
- [Linux 4.14 MUSB host scheduling](https://github.com/torvalds/linux/blob/v4.14/drivers/usb/musb/musb_host.c)
- [MCP print and camera monitoring](../PRINTER_MONITORING.md)
