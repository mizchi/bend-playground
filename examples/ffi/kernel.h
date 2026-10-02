#ifndef FFI_KERNEL_H
#define FFI_KERNEL_H
#include <stdint.h>
// Built in a separate translation unit, without LTO, for every C caller.
uint32_t ffi_kernel(uint32_t x, uint32_t rounds);
#endif
