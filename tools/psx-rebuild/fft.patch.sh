#!/usr/bin/env bash
# The new framework dropped psx_mod_set_vertical_gradient_reveal; the rest of FFT's 16:9 view is unchanged. Kept for reference.
T=$1
sed -i '/psx_mod_set_vertical_gradient_reveal/d' "$T/src/fft_widescreen.c"
