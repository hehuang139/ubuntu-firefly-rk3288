/* Minimal Firefly-RK3288 direct Linux boot machine.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/error-report.h"
#include "qemu/units.h"
#include "hw/arm/boot.h"
#include "hw/arm/machines-qom.h"
#include "hw/boards.h"
#include "hw/char/serial-mm.h"
#include "hw/intc/arm_gic.h"
#include "hw/qdev-properties.h"
#include "hw/rtc/pl031.h"
#include "hw/sysbus.h"
#include "system/address-spaces.h"
#include "system/system.h"
#include "target/arm/cpu.h"
#include "target/arm/gtimer.h"

/* RK3288 GIC and UART2 map from the Linux rk3288.dtsi. */
#define CPUS 4
#define SPIS 160
#define GICD 0xffc01000
#define GICC 0xffc02000
#define UART2 0xff690000
#define UART2_SPI 57
/* Virtual-only region. Linux must use the matching emulation DTB. */
#define VIRTIO_BASE 0x90000000
#define VIRTIO_STRIDE 0x200
#define VIRTIO_FIRST_SPI 144
#define VIRTIO_COUNT 6
#define RTC_BASE 0x90001000
#define RTC_SPI 150

static void firefly_init(MachineState *ms)
{
    static struct arm_boot_info boot = { .psci_conduit = QEMU_PSCI_CONDUIT_HVC };
    static const int timer_ppi[] = {
        [GTIMER_PHYS] = 14, [GTIMER_VIRT] = 11,
        [GTIMER_HYP] = 10, [GTIMER_SEC] = 13,
    };
    MemoryRegion *sysmem = get_system_memory();
    DeviceState *gic;
    SysBusDevice *bus;

    if (!ms->kernel_filename || !ms->dtb || ms->firmware) {
        error_report("firefly-rk3288 requires -kernel and -dtb (direct Linux boot)");
        exit(1);
    }
    if (ms->ram_size != 2 * GiB ||
        strcmp(ms->cpu_type, ARM_CPU_TYPE_NAME("cortex-a15"))) {
        error_report("firefly-rk3288 uses 2 GiB RAM and four Cortex-A15 proxy cores");
        exit(1);
    }

    memory_region_add_subregion(sysmem, 0, ms->ram);
    for (int i = 0; i < CPUS; i++) {
        /* QEMU has no Cortex-A17 model. A15 supplies ARMv7-A, VFP and NEON. */
        Object *cpu = object_new(ms->cpu_type);

        object_property_set_int(cpu, "mp-affinity", i, &error_fatal);
        object_property_set_int(cpu, "cntfrq", 24000000, &error_fatal);
        object_property_set_bool(cpu, "has_el3", false, &error_fatal);
        object_property_set_bool(cpu, "has_el2", false, &error_fatal);
        object_property_set_link(cpu, "memory", OBJECT(sysmem), &error_fatal);
        qdev_realize_and_unref(DEVICE(cpu), NULL, &error_fatal);
    }
    gic = qdev_new(TYPE_ARM_GIC);
    qdev_prop_set_uint32(gic, "revision", 2);
    qdev_prop_set_uint32(gic, "num-cpu", CPUS);
    qdev_prop_set_uint32(gic, "num-irq", SPIS + GIC_INTERNAL);
    bus = SYS_BUS_DEVICE(gic);
    sysbus_realize_and_unref(bus, &error_fatal);
    sysbus_mmio_map(bus, 0, GICD);
    sysbus_mmio_map(bus, 1, GICC);
    for (int i = 0; i < CPUS; i++) {
        DeviceState *cpu = DEVICE(qemu_get_cpu(i));
        for (int j = 0; j < ARRAY_SIZE(timer_ppi); j++) {
            qdev_connect_gpio_out(cpu, j, qdev_get_gpio_in(gic,
                                 SPIS + i * GIC_INTERNAL + 16 + timer_ppi[j]));
        }
        sysbus_connect_irq(bus, i, qdev_get_gpio_in(cpu, ARM_CPU_IRQ));
        sysbus_connect_irq(bus, i + CPUS, qdev_get_gpio_in(cpu, ARM_CPU_FIQ));
    }
    serial_mm_init(sysmem, UART2, 2, qdev_get_gpio_in(gic, UART2_SPI),
                   1500000, serial_hd(0), DEVICE_LITTLE_ENDIAN);
    for (int i = 0; i < VIRTIO_COUNT; i++) {
        DeviceState *transport = qdev_new("virtio-mmio");

        qdev_prop_set_bit(transport, "force-legacy", false);
        bus = SYS_BUS_DEVICE(transport);
        sysbus_realize_and_unref(bus, &error_fatal);
        sysbus_mmio_map(bus, 0, VIRTIO_BASE + i * VIRTIO_STRIDE);
        sysbus_connect_irq(bus, 0, qdev_get_gpio_in(gic, VIRTIO_FIRST_SPI + i));
    }
    sysbus_create_simple(TYPE_PL031, RTC_BASE, qdev_get_gpio_in(gic, RTC_SPI));
    boot.ram_size = ms->ram_size;
    arm_load_kernel(ARM_CPU(first_cpu), ms, &boot);
}

static void firefly_class_init(MachineClass *mc)
{
    mc->desc = "Firefly-RK3288 (experimental direct Linux boot model)";
    mc->init = firefly_init;
    mc->default_cpu_type = ARM_CPU_TYPE_NAME("cortex-a15");
    mc->min_cpus = CPUS;
    mc->max_cpus = CPUS;
    mc->default_cpus = CPUS;
    mc->default_ram_size = 2 * GiB;
    mc->default_ram_id = "firefly-rk3288.ram";
    mc->no_floppy = true;
    mc->no_cdrom = true;
    mc->no_parallel = true;
}

DEFINE_MACHINE_ARM("firefly-rk3288", firefly_class_init)
