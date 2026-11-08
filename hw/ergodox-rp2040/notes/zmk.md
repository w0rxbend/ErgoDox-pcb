# ZMK split notes (RP2040 ErgoDox)

Notes only. No firmware, no GPIO assignment for this board, and no claim that a baud rate, LED order, or pin was verified unless a page opened for this note says so.

## What was opened

Development docs, which are also what the v0.3 branch page shows for this topic:

- https://zmk.dev/docs/features/split-keyboards
- https://zmk.dev/docs/config/split
- https://zmk.dev/docs/hardware-integration/new-shield (wired-split section and role Kconfig)
- https://zmk.dev/docs/hardware-integration/pinctrl (UART rp2040)
- https://zmk.dev/docs/hardware-integration/lighting/underglow
- https://zmk.dev/docs/features/lighting
- https://v0-3-branch.zmk.dev/docs/features/split-keyboards (same transport text as the development page)

`zmk` `main`, plus the Zephyr revision ZMK pins in `app/west.yml` (`zmkfirmware/zephyr` `v4.1.0+zmk-fixes`):

- `app/dts/bindings/zmk,wired-split.yaml`
- `app/src/split/Kconfig`
- `app/src/split/CMakeLists.txt`
- `app/src/split/wired/central.c` and `peripheral.c`
- `app/src/split/wired/Kconfig` and `Kconfig.defaults`
- `app/boards/sparkfun/pro_micro_rp2040/board.yml`
- `app/boards/sparkfun/pro_micro_rp2040/sparkfun_pro_micro_rp2040.zmk.yml`
- `app/boards/sparkfun/pro_micro_rp2040/sparkfun_pro_micro_rp2040_zmk.dts`
- Zephyr `dts/arm/raspberrypi/rpi_pico/rp2040.dtsi` (`uart0`, `uart1`)
- Zephyr `drivers/serial/Kconfig.pl011` and `drivers/serial/uart_rpi_pico_pio.c`
- Zephyr `include/zephyr/dt-bindings/pinctrl/rpi-pico-pinctrl-common.h`
- Zephyr `dts/bindings/led_strip/ws2812.yaml` and `include/zephyr/dt-bindings/led/led.h`

Locked product text used for the recommendation is in `.grok/workflows/ergodox-rp2040-pcb.rhai`: each half is an RP2040, the half that sees HOST VBUS is the central, and LINK is a second USB-C carrying full-duplex UART over a straight-through USB 2.0 C-to-C cable unless current ZMK docs show a stable, non-experimental USB split.

## Transports

https://zmk.dev/docs/features/split-keyboards says ZMK has two split transports, Bluetooth and full-duplex wired UART. Only one can be active. The split source tree matches that: `app/src/split/` contains `bluetooth/` and `wired/` only, and `app/src/split/Kconfig` defines `ZMK_SPLIT_BLE` and `ZMK_SPLIT_WIRED` and nothing else.

| Transport | Status in the docs that were opened |
| --- | --- |
| Bluetooth | "the most well tested and flexible". Enabled by `CONFIG_ZMK_SPLIT=y` plus `CONFIG_ZMK_BLE=y` on an MCU that has BLE. The same page says officially supported split keyboards use BLE. |
| Full-duplex UART | In tree, but "a recent addition, and is intended for testing by early adopters". The new-shield guide calls it "experimental wired split support". One central and one peripheral only. |
| Half-duplex UART | Not stable. See below. |
| USB-protocol split | Does not exist in these docs or in `app/src/split/`. |

Bluetooth is the only transport described as well tested. It is not usable on this board: RP2040 has no BLE radio, and the upstream SparkFun Pro Micro RP2040 ZMK metadata lists `outputs: [usb]` only (`sparkfun_pro_micro_rp2040.zmk.yml`).

## Full-duplex UART on RP2040

Yes. The wired transport is full-duplex UART, and the split configuration page lists RP2040 as an interrupt-mode UART, not as an async/DMA UART.

On Zephyr `v4.1.0+zmk-fixes`:

- `uart0` and `uart1` in `rp2040.dtsi` are `compatible = "raspberrypi,pico-uart", "arm,pl011"`, status disabled until the board enables them.
- `UART_PL011` selects `SERIAL_SUPPORT_INTERRUPT`. It does not select `SERIAL_SUPPORT_ASYNC`.
- ZMK's UART-mode choice tries async first, then interrupt, then polling (`app/src/split/wired/Kconfig`). On this UART, interrupt mode is the one whose dependency is met.
- `peripheral.c` logs "UART device does not support interrupt-driven API" if the chosen device cannot do IRQ mode. Do not point `zmk,wired-split` at a PIO UART.
- `raspberrypi,pico-uart-pio` in that Zephyr tree implements `poll_in` / `poll_out` only. ZMK documents a PIO UART node, but that node is the wrong device for this link.

The driver does not set a baud. Both halves must use the same speed on the UART node. The ZMK pages opened here do not state that speed. Do not copy `115200` from the SparkFun console node and treat it as a split requirement.

## Half-duplex

Experimental, and the user-facing feature page still says it is not finished.

- `app/dts/bindings/zmk,wired-split.yaml`: `half-duplex` is "Experimental: Enable half-duplex protocol mode". `dir-gpios` is "Experimental" and is for RS-422 direction.
- `central.c` / `peripheral.c` compile that flag in (`DT_INST_PROP_OR(0, half_duplex, false)`).
- https://zmk.dev/docs/features/split-keyboards still says half-duplex is future work, and that single-wire boards will not work with wired split until it is completed.

Do not set `half-duplex`. The locked LINK uses two wires.

## USB-protocol split

No. The feature page names only Bluetooth and full-duplex UART. There is no USB split compatible, Kconfig, or `app/src/split/usb` directory. USB on a peripheral is not a second keyboard: peripherals "will not present as keyboard devices when connected over USB". `CONFIG_ZMK_USB` is for the central's link to the host.

The locked rule says to use a USB split only if the current docs show a stable, non-experimental one. They do not. Do not design LINK as USB device-to-device.

## Central versus peripheral

Role is compile-time only. It cannot follow a VBUS GPIO at runtime.

Selection:

- `CONFIG_ZMK_SPLIT_ROLE_CENTRAL` is a bool: `y` central, `n` peripheral (`app/src/split/Kconfig`, default `n`). https://zmk.dev/docs/config/split says the same.
- `app/src/split/CMakeLists.txt` compiles `central.c` or `peripheral.c`, not both.
- The new-shield guide sets `CONFIG_ZMK_SPLIT_ROLE_CENTRAL` default `y` only inside `if SHIELD_MY_KEYBOARD_LEFT`, and `CONFIG_ZMK_SPLIT` default `y` for both halves. Convention is left central, right peripheral.
- Two firmware files are required. The feature page says a split build produces separate images, typically `<keyboard>_left` and `<keyboard>_right`.

`zmk,wired-split` has no role or VBUS property. Its properties are `device` (required UART phandle), optional `detect-gpios` (cable present, not role), and the experimental `half-duplex` / `dir-gpios`.

The "Runtime Switching" section is about switching between Bluetooth and wired UART. It is "highly experimental", has no reference design, and is not a central/peripheral handover. It does not read VBUS.

Locked requirement 1 (the half that sees HOST VBUS becomes central, so either half can be central without a reflash) is not implemented by ZMK. The workaround already written in the workflow is the one that matches the code: build a central image and a peripheral image, and flash the central image onto whichever half is plugged into the computer. A board-id strap can tell left from right. It cannot change role when VBUS appears.

## `zmk,wired-split` devicetree

Binding `app/dts/bindings/zmk,wired-split.yaml`. Shape from https://zmk.dev/docs/config/split and the new-shield guide:

```dts
/ {
    wired_split {
        compatible = "zmk,wired-split";
        device = <&uart0>;
    };
};
```

The docs use `&pro_micro_serial` when a Pro Micro interconnect already labels the UART. This keyboard is its own board, so the phandle is the enabled RP2040 UART node (`&uart0` or `&uart1`), not a shield alias that this repo does not have. Do not set `half-duplex`. `detect-gpios` is optional and is not the role pin.

Enable that UART with pinctrl and `status = "okay"`. Both halves need `CONFIG_ZMK_SPLIT=y`. Only the central image sets `CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y`.

## RP2040 UART pinctrl

From https://zmk.dev/docs/hardware-integration/pinctrl, section "UART rp2040". The GP0/GP1 numbers are the documentation example, not pins chosen for this PCB. RX needs `input-enable`. Hardware UART has no sleep pinctrl in that example.

```dts
#include <dt-bindings/pinctrl/rpi-pico-rp2040-pinctrl.h>

&pinctrl {
    uart0_default: uart0_default {
        group1 {
            pinmux = <UART0_TX_P0>;
        };
        group2 {
            pinmux = <UART0_RX_P1>;
            input-enable;
        };
    };
};

&uart0 {
    status = "okay";
    pinctrl-0 = <&uart0_default>;
    pinctrl-names = "default";
};
```

Legal hardware-UART pinmux symbols in Zephyr `rpi-pico-pinctrl-common.h` (function UART). TX and RX for one controller must be a pair from the same UART. This note does not pick one for the ErgoDox.

- UART0: TX/RX on P0/P1, P12/P13, P16/P17, P28/P29
- UART1: TX/RX on P4/P5, P8/P9, P20/P21, P24/P25

CTS/RTS macros exist in that header. Wired split does not use them.

Full duplex means the two signal wires cross: one side's TX goes to the other side's RX. ZMK does not mention USB D+ or D-. A straight-through USB 2.0 C-to-C cable ties D+ to D+ and D- to D-, so the boards have to swap which UART signal lands on D+. The locked mapping does that: left TX on D+ and RX on D-, right TX on D- and RX on D+. That is a connector wiring choice, not a ZMK property. LINK D+/D- are GPIO UART pins plus the series resistors and ESD required by the locked text. They are not the RP2040 USB PHY. HOST keeps the native USB peripheral.

## Per-key WS2812 or SK6812

Per-key addressable LEDs use RGB underglow, not the single-color backlight system. https://zmk.dev/docs/features/lighting says underglow "can also be used for per-key lighting" and that the WS2812 family "includes WS2812B, WS2813, SK6812, and others".

Kconfig: `CONFIG_ZMK_RGB_UNDERGLOW=y`.

On a split, `chain-length` is the number of LEDs on that half, not both halves. https://zmk.dev/docs/features/lighting.

RP2040 shape from the underglow page, which uses the SparkFun Pro Micro RP2040 and PIO SPI because that is how ZMK documents a WS2812 strip on this SoC. The pin numbers below are that page's example (`GP0` data, a dummy clock on `gpio0` 10). They are not this PCB's LED pin.

```dts
#include <dt-bindings/led/led.h>

&pinctrl {
    pio0_spi0_default: pio0_spi0_default {
        group1 {
            pinmux = <PIO0_P0>;
        };
    };
};

&pio0 {
    status = "okay";

    pio0_spi0: pio0_spi0 {
        pinctrl-0 = <&pio0_spi0_default>;
        pinctrl-names = "default";
        compatible = "raspberrypi,pico-spi-pio";
        #address-cells = <1>;
        #size-cells = <0>;
        clocks = <&system_clk>;
        clock-frequency = <4000000>;

        clk-gpios = <&gpio0 10 GPIO_ACTIVE_HIGH>;
        mosi-gpios = <&gpio0 0 GPIO_ACTIVE_HIGH>;
        miso-gpios = <&gpio0 0 GPIO_ACTIVE_HIGH>;

        led_strip: ws2812@0 {
            compatible = "worldsemi,ws2812-spi";
            reg = <0>;
            spi-max-frequency = <4000000>;
            chain-length = <10>;
            spi-one-frame = <0x70>;
            spi-zero-frame = <0x40>;
            color-mapping = <LED_COLOR_ID_GREEN
                             LED_COLOR_ID_RED
                             LED_COLOR_ID_BLUE>;
        };
    };
};

/ {
    chosen {
        zmk,underglow = &led_strip;
    };
};
```

Zephyr `ws2812.yaml` says the usual pixel order is GRB and names SK6812 as compatible. `color-mapping` is required. Zephyr `led.h` also defines `LED_COLOR_ID_WHITE`, but the ZMK underglow example is three colors. An SK6812 RGBW channel order was not taken from a datasheet in this note, so it is not specified here. `spi-one-frame` / `spi-zero-frame` are copied from the ZMK example, not retuned.

The LED data pin must not be a UART pin or a matrix pin. Chain order has to match the PCB. Brightness is a power-budget problem for the HOST port, not something these ZMK pages set.

## Upstream RP2040 board

`zmkfirmware/zmk` `app/boards/sparkfun/pro_micro_rp2040/`

- https://github.com/zmkfirmware/zmk/blob/main/app/boards/sparkfun/pro_micro_rp2040/board.yml extends `sparkfun_pro_micro_rp2040` with variant `zmk` / qualifier `rp2040`
- `sparkfun_pro_micro_rp2040.zmk.yml` id is `sparkfun_pro_micro_rp2040//zmk`, type board, arch arm, output USB, exposes `pro_micro`
- `sparkfun_pro_micro_rp2040_zmk.dts` includes the upstream board dts, disables `&pro_micro_serial` unless wired split needs it, and shrinks the code partition for a ZMK storage partition

The same tree also has `app/boards/raspberrypi/rpi_pico/`, `app/boards/adafruit/kb2040/`, `app/boards/seeed/xiao_rp2040/`, and `app/boards/waveshare/rp2040_zero/`. The SparkFun board is the one the underglow page uses for RP2040.

## Recommendation

Use full-duplex wired UART (`compatible = "zmk,wired-split"` on the hardware PL011 `uart0` or `uart1`, interrupt mode, TX crossed to RX). Do not use half-duplex, PIO UART, Bluetooth, or a USB-protocol split.

That is the transport the locked LINK requirement asks for, and the current docs do not offer a stable USB split to replace it. ZMK still labels full-duplex wired split as early-adopter / experimental. Role stays compile-time: flash the central image to the half plugged into the computer. A VBUS GPIO cannot select the role.
