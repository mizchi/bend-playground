#include "kernel.h"

Term native_work_run(Env e, Term* f, IoWork* w) {
  (void)e; (void)w;
  return (Term)ffi_kernel((uint32_t)f[0], (uint32_t)f[1]);
}

static void __attribute__((constructor)) native_work_use(void) {
  io_eff(CID(native_work), native_work_run, 0);
}
