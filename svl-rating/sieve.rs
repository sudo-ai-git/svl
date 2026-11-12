#![no_std]
#![no_main]
#![allow(non_snake_case)]

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! { loop {} }

#[no_mangle]
pub extern "C" fn sieve() -> i32 {
    const N: usize = 100_000;
    let mut comp = [0u8; N + 1];
    let mut i: usize = 2;
    while i * i <= N {
        if comp[i] == 0 {
            let mut k = i * i;
            while k <= N { comp[k] = 1; k += i; }
        }
        i += 1;
    }
    let mut count: i32 = 0;
    let mut p: usize = 2;
    while p <= N { if comp[p] == 0 { count += 1; } p += 1; }
    count
}
