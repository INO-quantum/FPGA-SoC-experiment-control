
#include <configs/platform-auto.h>

#define CONFIG_SYS_BOOTM_LEN 0xF000000

/*Required for uartless designs */
#ifndef CONFIG_BAUDRATE
#define CONFIG_BAUDRATE 115200
#ifdef CONFIG_DEBUG_UART
#undef CONFIG_DEBUG_UART
#endif
#endif

/* Add ability to read uEnv.txt when not using SPI Flash for env */

#ifndef CONFIG_ENV_IS_IN_SPI_FLASH
#define CONFIG_ENV_IS_NOWHERE
#define CONFIG_ENV_SIZE	0x20000
#undef CONFIG_PREBOOT
#define CONFIG_PREBOOT	"echo U-BOOT for Cora Z7; setenv preboot; setenv bootenv uEnv.txt;  setenv loadbootenv_addr 0x1EE00000; if test $modeboot = sdboot && env run sd_uEnvtxt_existence_test; then if env run loadbootenv; then env run importbootenv; fi; fi; dhcp"
#endif

/* added by Andi to stop BOOTP broadcasts
#ifdef CONFIG_BOOTP_SERVERIP
#undef CONFIG_BOOTP_SERVERIP
#endif
#ifdef CONFIG_BOOTP_BOOTFILESIZE
#undef CONFIG_BOOTP_BOOTFILESIZE
#endif
#ifdef CONFIG_BOOTP_BOOTPATH
#undef CONFIG_BOOTP_BOOTPATH
#endif
#ifdef CONFIG_BOOTP_GATEWAY
#undef CONFIG_BOOTP_GATEWAY
#endif
#ifdef CONFIG_BOOTP_HOSTNAME
#undef CONFIG_BOOTP_HOSTNAME
#endif
#ifdef CONFIG_BOOTP_MAY_FAIL
#undef CONFIG_BOOTP_MAY_FAIL
#endif
*/

