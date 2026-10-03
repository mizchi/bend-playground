//! Version 1 of the C ABI; no Bend heap pointer crosses this boundary.
use std::ffi::c_void;

pub const ABI_VERSION: u32 = 1;
pub const INVALID_CONFIG: i32 = 1;
pub const PANIC: i32 = 2;

#[repr(C)]
#[derive(Clone, Copy)]
pub struct Config {
    pub abi_version: u32,
    pub width: u32,
    pub height: u32,
    pub max_frames: u32,
}

impl Config {
    pub fn validate(self) -> bool {
        self.abi_version == ABI_VERSION
            && (2..=2048).contains(&self.width)
            && (2..=2048).contains(&self.height)
            && self.width.is_multiple_of(2)
            && self.height.is_multiple_of(2)
    }
}

pub type Draw = unsafe extern "C" fn(*mut c_void, u32, u32, u32, *mut *mut c_void) -> i32;
