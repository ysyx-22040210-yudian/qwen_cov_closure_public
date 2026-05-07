# Config-file driven image IP verification

This project verifies a configurable image-processing RTL IP using VCS.

The DUT wraps the upstream Apache-2.0 `Modules.v` image-processing block and
adds top-level configuration signals:

- `cfg_function`
- `cfg_brightness_value`
- `cfg_channel_enable`
- `cfg_threshold_enable`
- `cfg_threshold_value`

Each test case is a text file under `sim/cases/`. Each non-comment line uses
three whitespace-separated fields:

```text
item_name    random_flag    value_or_range
```

`random_flag = 0` means use the fixed value in column 3.
`random_flag = 1` means randomize within the range in column 3, written as
`(min,max)`.

Example:

```text
case_name          0  tc_bright_add
random_seed        0  101
function           0  BRIGHTNESS_ADD
brightness_value   1  (20,80)
red_enable         0  1
green_enable       0  1
blue_enable        0  1
threshold_enable   0  0
threshold_value    0  128
pixel_count        0  64
pixel_red          1  (0,255)
pixel_green        1  (0,255)
pixel_blue         1  (0,255)
```

The testbench generates random pixels from `pixel_red`, `pixel_green`, and
`pixel_blue`; there are no per-pixel entries in the case file.

Run in the Linux EDA VM:

```sh
cd /mnt/hgfs/VMshare-2/ic_lab/image_processing_cfg_ip/sim
bash run_vcs_local.sh all_cases
bash run_vcs_local.sh wave TC=tc_bright_add
make -f Makefile.vcs verdi_cov
```

Use `run_vcs_local.sh` when running from `/mnt/hgfs`; it copies the workspace
to `/tmp` first so VCS can create generated symlinks on a native Linux
filesystem.

Results:

- logs: `sim/logs/vcs/`
- coverage report: `sim/cov/urgReport/dashboard.html`
- FSDB waves: `sim/waves/`
